import csv
from io import BytesIO
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from openpyxl import Workbook

from .models import (AttendanceAuditLog, ClusterManagerProfile, CustomUser, DailyAttendance,
                     EmployeeLocationHistory, Location, Notification, StaffMovement,
                     StaffMovementAuditLog)


def allowed_locations(user):
    if user.role == "admin":
        return Location.objects.all()
    if user.role == "kitchen_manager":
        return Location.objects.filter(pk=user.location_id) if user.location_id else Location.objects.none()
    if user.role == "cluster_manager" and hasattr(user, "cluster_manager_profile"):
        return user.cluster_manager_profile.locations.all()
    return Location.objects.none()


def location_managers(location):
    qs = CustomUser.objects.filter(is_active=True, role="kitchen_manager", location=location)
    qs |= CustomUser.objects.filter(is_active=True, role="cluster_manager", cluster_manager_profile__locations=location)
    return qs.distinct()


def process_due_movements():
    """Idempotent transfer worker; invoke from the scheduler via process_due_movements command."""
    due = StaffMovement.objects.filter(status="SCHEDULED", effective_date__lte=timezone.localdate()).values_list("id", flat=True)
    for movement_id in due:
        with transaction.atomic():
            m = StaffMovement.objects.select_for_update().select_related("employee", "from_location", "to_location").filter(pk=movement_id, status="SCHEDULED").first()
            if not m:
                continue
            if m.employee.location_id != m.from_location_id:
                m.status = "CANCELLED"
                StaffMovementAuditLog.objects.create(movement=m, changed_by=m.accepted_by or m.requested_by, action="conflict_cancelled", reason="Employee location changed before scheduled transfer")
                m.save(update_fields=["status", "updated_at"])
                continue
            histories = EmployeeLocationHistory.objects.select_for_update().filter(employee=m.employee, valid_to__isnull=True)
            if not histories.exists():
                EmployeeLocationHistory.objects.create(employee=m.employee, location=m.from_location, valid_from=date.min, valid_to=m.effective_date, created_by=m.accepted_by or m.requested_by)
            else:
                histories.update(valid_to=m.effective_date)
            EmployeeLocationHistory.objects.create(employee=m.employee, location=m.to_location, valid_from=m.effective_date, movement_reference=m, created_by=m.accepted_by or m.requested_by)
            m.employee.location = m.to_location
            m.employee.save(update_fields=["location"])
            if m.employee.role == "cluster_manager" and hasattr(m.employee, "cluster_manager_profile"):
                profile = m.employee.cluster_manager_profile
                profile.locations.remove(m.from_location)
                profile.locations.add(m.to_location)
            m.status = "COMPLETED"
            m.completed_at = timezone.now()
            m.save(update_fields=["status", "completed_at", "updated_at"])
            StaffMovementAuditLog.objects.create(movement=m, changed_by=m.accepted_by or m.requested_by, action="completed")
            for recipient in list(location_managers(m.from_location)) + list(location_managers(m.to_location)):
                Notification.objects.get_or_create(user=recipient, notification_type="staff_movement", link="/staff-movement/", message=f"Movement completed for {m.employee.employee_id}: {m.from_location} to {m.to_location}.")


@login_required
def daily_attendance(request):
    process_due_movements()
    if request.user.role not in {"kitchen_manager", "cluster_manager", "admin"}:
        raise PermissionDenied
    locations = allowed_locations(request.user)
    selected = request.GET.get("location") or request.POST.get("location")
    if request.user.role == "kitchen_manager":
        selected = request.user.location_id
    location = locations.filter(pk=selected).first() if selected else locations.first()
    raw_date = request.GET.get("date") or request.POST.get("date") or timezone.localdate().isoformat()
    try:
        attendance_date = date.fromisoformat(raw_date)
    except ValueError:
        attendance_date = timezone.localdate()
    if request.method == "POST":
        if request.user.role == "cluster_manager":
            raise PermissionDenied("Cluster Managers can view attendance only.")
        if not location:
            raise PermissionDenied
        attendance_date = date.fromisoformat(request.POST.get("date"))
        if request.user.role != "admin" and attendance_date > timezone.localdate():
            messages.error(request, "Future attendance cannot be marked.")
            return redirect(f"/daily-attendance/?date={attendance_date}&location={location.pk}")
        rows = [(k.split("_", 1)[1], v) for k, v in request.POST.items() if k.startswith("attendance_")]
        for employee_id, kind in rows:
            employee = CustomUser.objects.filter(pk=employee_id, is_active=True, role__in=["kitchen_staff", "kitchen_manager"], location=location).first()
            if not employee or kind not in dict(DailyAttendance.TYPES):
                continue
            existing = DailyAttendance.objects.filter(employee=employee, attendance_date=attendance_date).first()
            if request.user.role == "kitchen_manager" and attendance_date < timezone.localdate():
                messages.error(request, "Only Admin can correct historical attendance.")
                continue
            if request.user.role == "admin" and attendance_date < timezone.localdate() and not request.POST.get("correction_reason", "").strip():
                messages.error(request, "A correction reason is required for historical attendance changes.")
                continue
            if existing and request.user.role != "admin" and existing.location_id != location.pk:
                continue
            if existing:
                old = existing.attendance_type
                existing.attendance_type = kind
                existing.marked_by = request.user
                existing.save(update_fields=["attendance_type", "marked_by", "updated_at"])
                AttendanceAuditLog.objects.create(attendance=existing, old_attendance_type=old, new_attendance_type=kind, changed_by=request.user, correction_reason=request.POST.get("correction_reason", ""), action_type="correction")
            else:
                try:
                    with transaction.atomic():
                        record = DailyAttendance.objects.create(employee=employee, attendance_date=attendance_date, attendance_type=kind, location=location, marked_by=request.user)
                        AttendanceAuditLog.objects.create(attendance=record, old_attendance_type="", new_attendance_type=kind, changed_by=request.user, action_type="create")
                except IntegrityError:
                    pass
        messages.success(request, "Attendance saved.")
        return redirect(f"/daily-attendance/?date={attendance_date}&location={location.pk}")
    employees = CustomUser.objects.filter(is_active=True, role__in=["kitchen_staff", "kitchen_manager"], location=location).order_by("employee_id") if location else CustomUser.objects.none()
    if location:
        historical_assignments = EmployeeLocationHistory.objects.filter(location=location, valid_from__lte=attendance_date).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=attendance_date)).values_list("employee_id", flat=True)
        employees = (employees | CustomUser.objects.filter(pk__in=historical_assignments, is_active=True, role__in=["kitchen_staff", "kitchen_manager"])).distinct().order_by("employee_id")
    records_qs = DailyAttendance.objects.select_related("employee").filter(attendance_date=attendance_date)
    if location:
        records_qs = records_qs.filter(location=location)
        historic_ids = records_qs.values_list("employee_id", flat=True)
        employees = (employees | CustomUser.objects.filter(pk__in=historic_ids)).distinct().order_by("employee_id")
    records = {r.employee_id: r for r in records_qs}
    return render(request, "daily_attendance.html", {"locations": locations, "location": location, "date": attendance_date, "employees": employees, "records": records, "types": DailyAttendance.TYPES, "can_mark": request.user.role in {"kitchen_manager", "admin"}})


@login_required
def admin_daily_attendance(request):
    process_due_movements()
    if request.user.role not in {"admin", "cluster_manager"}:
        raise PermissionDenied
    qs = DailyAttendance.objects.select_related("employee", "location", "marked_by")
    locs = allowed_locations(request.user)
    qs = qs.filter(location__in=locs)
    for key, field in [("from", "attendance_date__gte"), ("to", "attendance_date__lte"), ("location", "location_id"), ("type", "attendance_type"), ("employee_id", "employee__employee_id"), ("name", "employee__first_name__icontains"), ("designation", "employee__role"), ("marked_by", "marked_by__username__icontains")]:
        value = request.GET.get(key)
        if value: qs = qs.filter(**{field: value})
    if request.GET.get("month"):
        try:
            year, month = map(int, request.GET["month"].split("-")); qs = qs.filter(attendance_date__year=year, attendance_date__month=month)
        except ValueError: pass
    qs = qs.order_by("-attendance_date", "location__code", "employee__employee_id")
    summary = {kind: qs.filter(attendance_type=kind).count() for kind, _ in DailyAttendance.TYPES}
    if request.GET.get("export") in {"csv", "xlsx"}:
        headers = ["EmployeeId", "EmployeeName", "Designation", "AttendanceDate", "Type", "Location"]
        rows = ([r.employee.employee_id, r.employee.get_full_name() or r.employee.username, r.employee.get_role_display(), r.attendance_date, r.attendance_type, r.location.name] for r in qs)
        return download_report(request.GET["export"], "daily-attendance", headers, rows)
    selected_day = request.GET.get("from") or timezone.localdate().isoformat()
    recorded_locations = DailyAttendance.objects.filter(location__in=locs, attendance_date=selected_day).values_list("location_id", flat=True).distinct()
    return render(request, "admin_daily_attendance.html", {"records": qs, "locations": locs, "summary": summary, "types": DailyAttendance.TYPES, "total_employees": CustomUser.objects.filter(is_active=True, role__in=["kitchen_staff", "kitchen_manager"], location__in=locs).count(), "pending_locations": locs.exclude(pk__in=recorded_locations).count()})


@login_required
def staff_movement(request):
    process_due_movements()
    user = request.user
    if user.role not in {"admin", "kitchen_manager", "cluster_manager"}: raise PermissionDenied
    authorized = allowed_locations(user)
    incoming = StaffMovement.objects.filter(to_location__in=authorized, status="PENDING_ACCEPTANCE")
    visible = StaffMovement.objects.select_related("employee", "from_location", "to_location", "requested_by", "accepted_by")
    if user.role != "admin": visible = visible.filter(Q(from_location__in=authorized) | Q(to_location__in=authorized))
    else:
        for key, field in [("employee_id", "employee__employee_id"), ("employee_name", "employee__first_name__icontains"), ("designation", "employee__role"), ("from_location", "from_location_id"), ("to_location", "to_location_id"), ("effective_date", "effective_date"), ("status", "status"), ("requested_by", "requested_by__username__icontains"), ("accepted_by", "accepted_by__username__icontains")]:
            value = request.GET.get(key)
            if value: visible = visible.filter(**{field: value})
    if request.method == "POST" and request.POST.get("action") == "request":
        employee = get_object_or_404(CustomUser, pk=request.POST.get("employee"), is_active=True, role__in=["kitchen_staff", "kitchen_manager"])
        source = get_object_or_404(authorized, pk=request.POST.get("from_location"))
        destination_scope = Location.objects.all() if user.role in {"admin", "kitchen_manager"} else authorized
        destination = get_object_or_404(destination_scope, pk=request.POST.get("to_location"))
        if user.role != "admin" and (employee.location_id != source.pk or source.pk not in authorized.values_list("id", flat=True)):
            raise PermissionDenied
        if destination.pk == source.pk: raise PermissionDenied
        effective = date.fromisoformat(request.POST["effective_date"])
        if user.role != "admin" and effective < timezone.localdate(): raise PermissionDenied("Backdated movements require admin.")
        if StaffMovement.objects.filter(employee=employee, status__in=["PENDING_ACCEPTANCE", "ACCEPTED", "SCHEDULED"]).exists():
            messages.error(request, "This employee already has an active movement request.")
        else:
            m = StaffMovement.objects.create(employee=employee, from_location=source, to_location=destination, effective_date=effective, movement_reason=request.POST["reason"], remarks=request.POST.get("remarks", ""), requested_by=user, status="PENDING_ACCEPTANCE")
            StaffMovementAuditLog.objects.create(movement=m, changed_by=user, action="requested")
            msg = f"New Staff/Manager Movement Request\nEmployee ID: {employee.employee_id}\nEmployee Name: {employee.get_full_name() or employee.username}\nDesignation: {employee.get_role_display()}\nCurrent Location: {source}\nProposed Location: {destination}\nEffective Date: {effective}\nRequested By: {user}\nReason: {m.movement_reason}"
            for recipient in location_managers(destination):
                Notification.objects.create(user=recipient, sent_by=user, notification_type="staff_movement", message=msg, link="/staff-movement/")
            messages.success(request, "Movement request sent to destination managers.")
        return redirect("staff_movement")
    if request.method == "POST" and request.POST.get("action") in {"accept", "reject", "cancel"}:
        m = get_object_or_404(StaffMovement.objects.select_related("employee", "from_location", "to_location"), pk=request.POST.get("movement"))
        action = request.POST["action"]
        with transaction.atomic():
            m = StaffMovement.objects.select_for_update().get(pk=m.pk)
            if action == "accept":
                if m.status != "PENDING_ACCEPTANCE" or (user.role != "admin" and (m.to_location_id not in authorized.values_list("id", flat=True) or user == m.requested_by)): raise PermissionDenied
                m.accepted_by=user; m.accepted_at=timezone.now(); m.status="SCHEDULED" if m.effective_date > timezone.localdate() else "ACCEPTED"; m.save()
                StaffMovementAuditLog.objects.create(movement=m, changed_by=user, action="accepted", reason=request.POST.get("remarks", ""))
                for rec in location_managers(m.from_location):
                    Notification.objects.create(user=rec, sent_by=user, notification_type="staff_movement", message=f"Movement accepted for {m.employee.employee_id} to {m.to_location}.", link="/staff-movement/")
                if m.status == "ACCEPTED":
                    m.status="SCHEDULED"; m.save(update_fields=["status", "updated_at"]); process_due_movements()
            elif action == "reject":
                if m.status != "PENDING_ACCEPTANCE" or (user.role != "admin" and (m.to_location_id not in authorized.values_list("id", flat=True) or user == m.requested_by)): raise PermissionDenied
                reason=request.POST.get("remarks", "").strip()
                if not reason: messages.error(request, "Rejection remarks are required."); return redirect("staff_movement")
                m.status="REJECTED"; m.rejected_by=user; m.rejected_at=timezone.now(); m.rejection_reason=reason; m.save()
                StaffMovementAuditLog.objects.create(movement=m, changed_by=user, action="rejected", reason=reason)
                Notification.objects.create(user=m.requested_by, sent_by=user, notification_type="staff_movement", message=f"Movement rejected for {m.employee.employee_id}: {reason}", link="/staff-movement/")
            elif action == "cancel":
                if user.role != "admin": raise PermissionDenied
                reason=request.POST.get("remarks", "").strip()
                if not reason: messages.error(request, "Cancellation reason is required."); return redirect("staff_movement")
                if m.status in {"COMPLETED", "REJECTED", "CANCELLED"}: raise PermissionDenied
                m.status="CANCELLED"; m.save(update_fields=["status", "updated_at"]); StaffMovementAuditLog.objects.create(movement=m, changed_by=user, action="cancelled", reason=reason)
        return redirect("staff_movement")
    employees = CustomUser.objects.filter(is_active=True, role__in=["kitchen_staff", "kitchen_manager"], location__in=authorized).select_related("location").order_by("employee_id")
    destinations = Location.objects.all() if user.role in {"admin", "kitchen_manager"} else authorized
    return render(request, "staff_movement.html", {"locations": authorized, "destinations": destinations, "employees": employees, "movements": visible.order_by("-requested_at"), "incoming": incoming.select_related("employee", "from_location", "to_location", "requested_by"), "admin": user.role == "admin"})


@login_required
def export_movements(request):
    if request.user.role != "admin": raise PermissionDenied
    qs = StaffMovement.objects.select_related("employee", "from_location", "to_location", "requested_by", "accepted_by").order_by("-requested_at")
    for key, field in [("employee_id", "employee__employee_id"), ("employee_name", "employee__first_name__icontains"), ("designation", "employee__role"), ("from_location", "from_location_id"), ("to_location", "to_location_id"), ("effective_date", "effective_date"), ("status", "status")]:
        value = request.GET.get(key)
        if value: qs = qs.filter(**{field: value})
    headers = ["EmployeeId","EmployeeName","Designation","FromLocation","ToLocation","MovementEffectiveDate","MovementReason","RequestedBy","RequestedDate","AcceptedBy","AcceptedDate","Status"]
    rows = ([m.employee.employee_id,m.employee.get_full_name() or m.employee.username,m.employee.get_role_display(),m.from_location.name,m.to_location.name,m.effective_date,m.movement_reason,m.requested_by,m.requested_at,m.accepted_by or "",m.accepted_at or "",m.get_status_display()] for m in qs)
    return download_report(request.GET.get("format", "csv"), "staff-movements", headers, rows)


def download_report(file_format, filename, headers, rows):
    if file_format == "xlsx":
        workbook = Workbook(); sheet = workbook.active; sheet.append(headers)
        for row in rows: sheet.append([str(value) if value is not None else "" for value in row])
        buffer = BytesIO(); workbook.save(buffer)
        response = HttpResponse(buffer.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
        return response
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
    writer = csv.writer(response); writer.writerow(headers); writer.writerows(rows)
    return response
