import csv
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from openpyxl import Workbook

from .models import ClusterManagerProfile, CustomUser, GroomingAudit, Location


AUDITOR_ROLES = {"kitchen_manager", "cluster_manager"}


def allowed_locations(user):
    if user.role == "kitchen_manager":
        return Location.objects.filter(pk=user.location_id) if user.location_id else Location.objects.none()
    if user.role == "cluster_manager":
        profile = ClusterManagerProfile.objects.filter(user=user).first()
        return profile.locations.all() if profile else Location.objects.none()
    return Location.objects.none()


def can_view_audit(user, audit):
    return user.role == "admin" or (
        user.role in AUDITOR_ROLES and allowed_locations(user).filter(pk=audit.kitchen_location_id).exists()
    )


def audit_employees(user, location_id):
    if not str(location_id or "").isdigit():
        return CustomUser.objects.none()
    location_id = int(location_id)
    locations = allowed_locations(user)
    if not location_id or not locations.filter(pk=location_id).exists():
        return CustomUser.objects.none()
    roles = ["kitchen_staff"] + (["kitchen_manager"] if user.role == "cluster_manager" else [])
    return CustomUser.objects.filter(
        is_active=True, role__in=roles, location_id=location_id
    ).exclude(pk=user.pk).order_by("employee_id")


@login_required
def grooming_audit(request):
    if request.user.role not in AUDITOR_ROLES:
        return HttpResponseForbidden("You are not allowed to conduct grooming audits.")
    locations = allowed_locations(request.user).order_by("name")
    selected_location = request.GET.get("location") or (str(locations.first().pk) if request.user.role == "kitchen_manager" and locations.exists() else "")
    employees = audit_employees(request.user, selected_location)
    history = GroomingAudit.objects.filter(
        kitchen_location__in=locations, auditor=request.user
    ).order_by("-audit_datetime")[:30]
    return render(request, "grooming_audit.html", {
        "locations": locations, "selected_location": selected_location,
        "employees": employees, "history": history,
        "is_cluster": request.user.role == "cluster_manager",
    })


@login_required
@require_GET
def grooming_audit_employees(request):
    if request.user.role not in AUDITOR_ROLES:
        return HttpResponseForbidden()
    employees = audit_employees(request.user, request.GET.get("location"))
    data = [{"id": e.pk, "employee_id": e.employee_id,
             "name": e.get_full_name() or e.username,
             "designation": e.get_role_display(), "location": e.location.name}
            for e in employees.select_related("location")]
    return JsonResponse({"employees": data})


@login_required
@require_POST
def submit_grooming_audit(request):
    user = request.user
    if user.role not in AUDITOR_ROLES:
        return HttpResponseForbidden()
    location_id = request.POST.get("location")
    if not str(location_id or "").isdigit() or not allowed_locations(user).filter(pk=int(location_id)).exists():
        return HttpResponseForbidden("Kitchen is not allocated to your account.")
    employee_id = request.POST.get("employee", "")
    employee = audit_employees(user, location_id).filter(pk=int(employee_id)).first() if employee_id.isdigit() else None
    if not employee:
        messages.error(request, "Select an active employee assigned to this kitchen.")
        return redirect("grooming_audit")
    photo = request.FILES.get("employee_photo")
    if not photo:
        messages.error(request, "An employee photo is required.")
        return redirect("grooming_audit")
    values = {key: request.POST.get(key, "") for key in ("jewelry_accessories", "shoes", "hands_nails", "hair_net")}
    if any(v not in {GroomingAudit.PASS, GroomingAudit.FAIL} for v in values.values()):
        messages.error(request, "Complete all four grooming checks.")
        return redirect("grooming_audit")
    audit = GroomingAudit(
        kitchen_location_id=location_id, employee=employee, auditor=user,
        employee_photo=photo, remarks=request.POST.get("remarks", "").strip(), **values,
        employee_name_snapshot=employee.get_full_name() or employee.username,
        employee_id_snapshot=employee.employee_id,
        designation_snapshot=employee.get_role_display(),
        location_name_snapshot=employee.location.name,
        auditor_name_snapshot=user.get_full_name() or user.username,
        auditor_role_snapshot=user.get_role_display(),
    )
    try:
        audit.full_clean()
        audit.save()
    except ValidationError as exc:
        if audit.employee_photo and audit.employee_photo.name:
            audit.employee_photo.delete(save=False)
        messages.error(request, "Could not save audit: " + "; ".join(exc.messages))
        return redirect("grooming_audit")
    messages.success(request, f"Grooming audit saved. Result: {audit.get_overall_result_display()}.")
    return redirect("grooming_audit")


def filtered_audits(request):
    qs = GroomingAudit.objects.select_related("kitchen_location", "employee", "auditor")
    params = request.GET
    if params.get("from_date"):
        try:
            qs = qs.filter(audit_datetime__date__gte=date.fromisoformat(params["from_date"]))
        except ValueError:
            pass
    if params.get("to_date"):
        try:
            qs = qs.filter(audit_datetime__date__lte=date.fromisoformat(params["to_date"]))
        except ValueError:
            pass
    if params.get("location"):
        if params["location"].isdigit():
            qs = qs.filter(kitchen_location_id=int(params["location"]))
        else:
            qs = qs.none()
    if params.get("cluster_manager"):
        if params["cluster_manager"].isdigit():
            qs = qs.filter(kitchen_location__cluster_managers__user_id=int(params["cluster_manager"]))
        else:
            qs = qs.none()
    if params.get("kitchen_manager"):
        if params["kitchen_manager"].isdigit():
            qs = qs.filter(kitchen_location__customuser__pk=int(params["kitchen_manager"]), kitchen_location__customuser__role="kitchen_manager")
        else:
            qs = qs.none()
    if params.get("employee_id"):
        qs = qs.filter(employee_id_snapshot__icontains=params["employee_id"])
    if params.get("employee_name"):
        qs = qs.filter(employee_name_snapshot__icontains=params["employee_name"])
    if params.get("designation"):
        qs = qs.filter(designation_snapshot=params["designation"])
    if params.get("auditor"):
        qs = qs.filter(Q(auditor_name_snapshot__icontains=params["auditor"]) | Q(auditor__employee_id__icontains=params["auditor"]))
    if params.get("result") in {GroomingAudit.PASS, GroomingAudit.FAIL}:
        qs = qs.filter(overall_result=params["result"])
    return qs.distinct().order_by("-audit_datetime", "-pk")


@login_required
def grooming_audit_report(request):
    if request.user.role != "admin":
        return HttpResponseForbidden()
    qs = filtered_audits(request)
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    aggregate = qs.aggregate(total=Count("pk"), passed=Count("pk", filter=Q(overall_result="pass")),
                             failed=Count("pk", filter=Q(overall_result="fail")))
    total = aggregate["total"]
    unique_people = qs.values("employee_id_snapshot").distinct().count()
    summary = {
        "total": total, "employees": unique_people,
        "passed": aggregate["passed"], "failed": aggregate["failed"],
        "pass_pct": round(aggregate["passed"] * 100 / total, 1) if total else 0,
        "fail_pct": round(aggregate["failed"] * 100 / total, 1) if total else 0,
    }
    return render(request, "grooming_audit_report.html", {
        "audits": page, "summary": summary, "locations": Location.objects.order_by("name"),
        "cluster_managers": CustomUser.objects.filter(role="cluster_manager", is_active=True).order_by("employee_id"),
        "kitchen_managers": CustomUser.objects.filter(role="kitchen_manager", is_active=True).order_by("employee_id"),
        "filters": request.GET,
    })


def export_rows(qs):
    yield ["Audit Date", "Audit Time", "Kitchen Location", "Employee ID", "Employee Name", "Designation",
           "Auditor Name", "Jewelry & Accessories", "Shoes", "Hands & Nails", "Hair Net", "Overall Result", "Employee Photo Path", "Remarks"]
    for a in qs:
        yield [timezone.localtime(a.audit_datetime).date().isoformat(), timezone.localtime(a.audit_datetime).strftime("%H:%M:%S"),
               a.location_name_snapshot, a.employee_id_snapshot, a.employee_name_snapshot, a.designation_snapshot,
               a.auditor_name_snapshot, a.get_jewelry_accessories_display(), a.get_shoes_display(),
               a.get_hands_nails_display(), a.get_hair_net_display(), a.get_overall_result_display(),
               a.employee_photo.name, a.remarks]


@login_required
def grooming_audit_export(request, file_format):
    if request.user.role != "admin":
        return HttpResponseForbidden()
    rows = list(export_rows(filtered_audits(request)))
    if file_format == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="grooming-audits.csv"'
        writer = csv.writer(response)
        writer.writerows(rows)
        return response
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Grooming Audits"
    for row in rows:
        sheet.append(row)
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="grooming-audits.xlsx"'
    workbook.save(response)
    return response


@login_required
def grooming_audit_photo(request, audit_id):
    audit = get_object_or_404(GroomingAudit, pk=audit_id)
    if not can_view_audit(request.user, audit):
        return HttpResponseForbidden()
    return render(request, "grooming_audit_photo.html", {"audit": audit})


@login_required
def grooming_audit_photo_file(request, audit_id):
    audit = get_object_or_404(GroomingAudit, pk=audit_id)
    if not can_view_audit(request.user, audit):
        return HttpResponseForbidden()
    import mimetypes
    if not audit.employee_photo:
        raise Http404("Photo is unavailable.")
    try:
        photo = audit.employee_photo.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("Photo is unavailable.")
    response = FileResponse(photo, content_type=mimetypes.guess_type(audit.employee_photo.name)[0] or "application/octet-stream")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
def secure_media_photo(request, photo_path):
    """Protect the development MEDIA_URL route for audit images as well."""
    stored_name = "grooming_audits/" + photo_path
    audit = GroomingAudit.objects.filter(employee_photo=stored_name).first()
    if not audit or not can_view_audit(request.user, audit):
        return HttpResponseForbidden()
    import mimetypes
    try:
        photo = audit.employee_photo.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("Photo is unavailable.")
    response = FileResponse(photo, content_type=mimetypes.guess_type(stored_name)[0] or "application/octet-stream")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response

