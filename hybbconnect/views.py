import csv
from datetime import datetime, timedelta
from functools import wraps
import io


from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import (
    authenticate,
    get_user_model,
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import PasswordChangeForm
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .forms import QualityFeedbackBulkUploadForm

from .forms import (
    IConnectForm,
    KitchenLogForm,
    KitchenPlayerForm,
    OrderPhotoForm,
    QualityFeedbackForm,
    StaffTimeUpdateForm,
)
from .models import (
    Attendance,
    CustomUser,
    KitchenLog,
    Location,
    OrderPhoto,
    QualityFeedback,
    SalarySlip,
    StaffPerformance,
    StaffTimeUpdate,
    Ticket,
)


# -----------------------------------------
# ✅ Correct Category → Owner Mapping
# -----------------------------------------
CATEGORY_OWNER_MAP = {
    # IConnectForm categories
    "Training Related": "E010",
    "Critical Intervention - Cletus": "E011",
    "MIS Related": "E012",
    "HR Related": "E013",
    "Leave Request": "E013",
    "PF Related Issue": "E013",
    "Bank Account Issue": "E013",
    "Request a call Back": "E013",
    "Quality Related": "E014",

    # KitchenPlayerForm categories
    "Salary Message not received": "E013",
    "Salary Not Received": "E013",
    "Shift Manager / Kitchen Manager Issue": "E013",
    "Accommodation Issue": "E013",
    "Salary is incorrect": "E013",
    "Request - Salary Advance": "E013",
    "Co-Worker Issue": "E013",
    "Request a call Back": "E013",
    "PF Related Issues": "E013",
    "Salary Hold": "E013",
}


# --------------------------
# ✅ Role Helper Functions
# --------------------------
def is_kitchen_staff(user):
    return user.role == "kitchen_staff"

def is_kitchen_manager(user):
    return user.role == "kitchen_manager"

def is_cluster_manager(user):
    return user.role == "cluster_manager"

def is_owner(user):
    return user.role == "owner"

def is_admin(user):
    return user.role == "admin"


# --------------------------
# ✅ Custom Decorator (for Staff Only)
# --------------------------
def staff_only(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.role == "kitchen_staff":
            return view_func(request, *args, **kwargs)
        messages.warning(request, "You are not authorized to raise tickets.")
        return redirect("dashboard")
    return wrapper


# --------------------------
# ✅ Authentication Views
# --------------------------
def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return redirect("login")


def login_view(request):
    next_url = request.GET.get("next")

    if request.method == "POST":
        employee_id = request.POST.get("employee_id")
        password = request.POST.get("password")

        try:
            user_obj = CustomUser.objects.get(employee_id=employee_id)
            user = authenticate(request, username=user_obj.username, password=password)
        except CustomUser.DoesNotExist:
            user = None

        if user is not None:
            login(request, user)
            if next_url:
                return redirect(next_url)

            # Redirect by role
            role_redirects = {
                "kitchen_staff": "staff_dashboard",
                "kitchen_manager": "manager_dashboard",
                "cluster_manager": "cluster_dashboard",
                "owner": "owner_dashboard",
                "admin": "admin_dashboard",
            }
            return redirect(role_redirects.get(user.role, "dashboard"))
        else:
            messages.error(request, "Invalid Employee ID or Password")

    return render(request, "login.html")


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def change_password(request):
    """Allow any authenticated user to change only their own password."""
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Your password has been changed successfully.")
            return redirect("dashboard")
    else:
        form = PasswordChangeForm(request.user)

    return render(request, "change_password.html", {"form": form})


# --------------------------
# ✅ Universal Dashboard Redirector
# --------------------------
@login_required
def dashboard(request):
    user = request.user
    redirects = {
        "kitchen_staff": "staff_dashboard",
        "kitchen_manager": "manager_dashboard",
        "cluster_manager": "cluster_dashboard",
        "owner": "owner_dashboard",
        "admin": "admin_dashboard",
    }
    return redirect(redirects.get(user.role, "logout"))

# --------------------------
# ✅ Staff Dashboard
# --------------------------
@login_required
@user_passes_test(is_kitchen_staff)
def staff_dashboard(request):
    """Staff see their own performance, logs, and tickets."""
    performance_data = StaffPerformance.objects.filter(employee=request.user)

    # ✅ Fetch logs linked by employee_id OR staff relation
    logs = KitchenLog.objects.filter(
        Q(emp_id=request.user.employee_id) | Q(staff=request.user)
    ).order_by("-created_at")

    # ✅ Fetch all tickets raised by this staff
    my_tickets = Ticket.objects.filter(employee=request.user).order_by("-created_at")

        # 🔥 ADD: Fetch today's attendance
            # 🔥 Fetch today's attendance (single record)
    today_attendance = Attendance.objects.filter(
        user=request.user,
        date=timezone.localdate()
    ).first()

    # 🔥 Fetch last 7 days attendance (list)
    last_7_days_attendance = Attendance.objects.filter(
        user=request.user,
        date__gte=timezone.localdate() - timedelta(days=6)
    ).order_by("-date")

    context = {
        "performance_data": performance_data,
        "logs": logs,
        "my_tickets": my_tickets,
        "user_location": request.user.location,
        "today_attendance": today_attendance,
        "last_7_days_attendance": last_7_days_attendance,
    }

    return render(request, "staff_dashboard.html", context)

# --------------------------
# ✅ Staff Confirms Final Closure
# --------------------------


@login_required
def acknowledge_log(request, log_id):
    log = get_object_or_404(KitchenLog, id=log_id)

    # Only the assigned staff can acknowledge the log
    if log.staff != request.user:
        messages.error(request, "You are not authorized to acknowledge this log.")
        return redirect("staff_dashboard")

    log.is_acknowledged = True
    log.acknowledged_at = timezone.now()
    log.save()

    messages.success(request, "Log acknowledged successfully.")
    return redirect("staff_dashboard")


@login_required
@user_passes_test(is_kitchen_staff)
def my_tickets_view(request):
    my_tickets = Ticket.objects.filter(employee=request.user).order_by('-id')

    return render(request, "my_tickets.html", {
        "my_tickets": my_tickets
    })




@login_required
@user_passes_test(is_kitchen_staff)
def my_logs_view(request):
    logs = KitchenLog.objects.filter(
        Q(emp_id=request.user.employee_id) | Q(staff=request.user)
    ).order_by('-created_at')

    return render(request, "my_logs.html", {
        "logs": logs
    })




# --------------------------
# ✅ Manager Dashboard
# --------------------------

@login_required
@user_passes_test(is_kitchen_manager)
def manager_dashboard(request):
    """Manager dashboard shows tickets and staff logs."""
    # Tickets assigned to manager
    tickets = Ticket.objects.filter(reassigned_to=request.user).order_by("-created_at")

    # Staff logs from manager’s location
    staff_logs = KitchenLog.objects.filter(
        location=request.user.location.code if request.user.location else "UNKNOWN"
    ).order_by("-created_at")


    # 🔥 ADD: Fetch today's attendance
    today_attendance = Attendance.objects.filter(
        user=request.user,
        date=timezone.localdate()
    ).first()

    last_7_days_attendance = Attendance.objects.filter(
        user=request.user,
        date__gte=timezone.localdate() - timedelta(days=6)
    ).order_by("-date")

    form = IConnectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "✅ Ticket submitted successfully!")
        return redirect("manager_dashboard")

    return render(
        request,
        "manager_dashboard.html",
        {
            "tickets": tickets,
            "form": form,
            "staff_logs": staff_logs,  # ✅ send logs to template
            "today_attendance": today_attendance,
            "last_7_days_attendance": last_7_days_attendance,
        },
    )


# ✅ Manager Marks Ticket as Resolved
@login_required
def resolve_ticket(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id)

    if request.user.role != "kitchen_manager":
        messages.error(request, "Only kitchen managers can resolve tickets.")
        return redirect("manager_dashboard")

    if ticket.reassigned_to != request.user:
        messages.error(request, "This ticket isn’t assigned to you.")
        return redirect("manager_dashboard")

    ticket.status = "Resolved"
    ticket.resolved_by = request.user
    ticket.resolved_at = timezone.now()
    ticket.save()

    messages.success(request, f"Ticket #{ticket.ticket_number} marked as Resolved. Awaiting Owner confirmation.")
    return redirect("manager_dashboard")



# --------------------------
# ✅ Owner Dashboard (Upgraded + Auto Close Support)
# --------------------------

@login_required
@user_passes_test(is_owner)
def owner_dashboard(request):
    tickets = Ticket.objects.filter(
        assigned_owner=request.user
    ).order_by("-created_at")

    if request.method == "POST":
        action = request.POST.get("action")
        ticket_id = request.POST.get("ticket_id")
        remarks = request.POST.get("remarks", "").strip()
        reject_reason = request.POST.get("reject_reason", "").strip()
        closer_remarks = request.POST.get("closer_remarks", "").strip()

        if not ticket_id:
            messages.error(request, "Invalid ticket ID.")
            return redirect("owner_dashboard")

        ticket = get_object_or_404(Ticket, id=ticket_id)

        # ----------------------------------
        # 🔵 1) Owner Resolves Ticket
        # ----------------------------------
        if action == "resolve":
            ticket.status = "Resolved"
            ticket.resolved_by = request.user
            ticket.owner_remarks = remarks or "Awaiting staff confirmation"
            ticket.save()

            messages.success(
                request,
                f"✅ Ticket #{ticket.ticket_number} marked as resolved — awaiting staff confirmation."
            )

        # ----------------------------------
        # 🟠 2) Owner Adds Closer Remarks + Closes Ticket
        # ----------------------------------
        elif action == "close":
            ticket.status = "Closed"
            ticket.closed_dt = timezone.now()
            ticket.owner_closer_remarks = closer_remarks or "Closed by owner"
            ticket.save()

            messages.success(
                request,
                f"🔒 Ticket #{ticket.ticket_number} closed successfully."
            )

        # ----------------------------------
        # 🔁 3) Reassign Ticket
        # ----------------------------------
        elif action == "reassign":
            new_owner_id = request.POST.get("new_owner")

            if new_owner_id:
                new_owner = get_object_or_404(CustomUser, id=new_owner_id)

                ticket.assigned_owner = new_owner
                ticket.reassigned_to = new_owner
                ticket.status = "Reassigned"
                ticket.save()

                messages.success(
                    request,
                    f"🔁 Ticket #{ticket.ticket_number} reassigned to {new_owner.username}."
                )
            else:
                messages.error(request, "Please select a valid user to reassign.")

        # ----------------------------------
        # ❌ 4) Reject Ticket
        # ----------------------------------
        elif action == "reject":
            if not reject_reason:
                messages.error(request, "Please provide a reason for rejection.")
            else:
                ticket.status = "Rejected"
                ticket.rejection_reason = reject_reason
                ticket.rejected_by = request.user
                ticket.save()

                messages.warning(
                    request,
                    f"❌ Ticket #{ticket.ticket_number} rejected."
                )

        else:
            messages.error(request, "Invalid action.")

        return redirect("owner_dashboard")

    # Dropdown for reassign
    reassign_options = CustomUser.objects.filter(role__in=["owner", "cluster_manager"])

    context = {
        "tickets": tickets,
        "reassign_options": reassign_options,
        "assigned_tickets": tickets.filter(assigned_owner__isnull=False),
        "reassigned_tickets": tickets.filter(reassigned_to__isnull=False),
        "resolved_tickets": tickets.filter(status="Resolved"),
    }

    return render(request, "owner_dashboard.html", context)


# --------------------------
# ✅ Separate Confirm Resolution View
# --------------------------

@login_required
@user_passes_test(is_owner)
def confirm_ticket_resolution(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id)

    if request.method == "POST":
        remarks = request.POST.get("remarks", "")
        ticket.owner_confirmation = True
        ticket.status = "Resolved"  # Or "Closed" if you want final
        ticket.remarks = remarks
        ticket.save()
        messages.success(request, f"✅ Owner confirmed resolution for Ticket #{ticket.id}.")
        return redirect("owner_dashboard")

    return render(request, "confirm_resolution.html", {"ticket": ticket})


# ✅ Owner: Reassign Ticket View
@login_required
def reassign_ticket(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id, assigned_owner=request.user)

    if request.method == "POST":
        new_owner_id = request.POST.get("new_owner")
        if new_owner_id:
            new_owner = get_object_or_404(CustomUser, id=new_owner_id)
            ticket.reassigned_to = new_owner
            ticket.assigned_owner = new_owner
            ticket.status = "Reassigned"
            ticket.save()
            messages.success(request, f"🔁 Ticket #{ticket.id} reassigned to {new_owner.username}.")
        else:
            messages.error(request, "Please select a valid new owner.")
        return redirect("owner_dashboard")

    owners_managers = CustomUser.objects.filter(role__in=["owner", "cluster_manager"])
    return render(request, "reassign_ticket.html", {
        "ticket": ticket,
        "owners_managers": owners_managers
    })

@login_required
def close_ticket(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id, assigned_owner=request.user)
    ticket.status = "Resolved"
    ticket.save()
    messages.success(request, f"Ticket #{ticket.id} closed successfully.")
    return redirect("owner_dashboard")


@login_required
def confirm_resolution(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id, assigned_owner=request.user)

    if ticket.status == "Resolved" and not ticket.owner_confirmation:
        ticket.owner_confirmation = True
        ticket.status = "Resolved"
        ticket.save()
        messages.success(request, f"Ticket #{ticket.id} confirmed and closed successfully.")
    else:
        messages.warning(request, "This ticket cannot be confirmed right now.")
    return redirect("owner_dashboard")




@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):

    # -----------------------------------
    # SUMMARY METRICS
    # -----------------------------------
    total_users = CustomUser.objects.count()
    active_users = CustomUser.objects.filter(is_active=True).count()
    inactive_users = CustomUser.objects.filter(is_active=False).count()

    total_tickets = Ticket.objects.count()
    pending_tickets = Ticket.objects.filter(status="Pending").count()
    resolved_tickets = Ticket.objects.filter(status="Resolved").count()

    # -----------------------------------
    # BASE QUERYSET
    # -----------------------------------
    tickets = Ticket.objects.select_related(
        "employee",
        "assigned_owner",
        "reassigned_to",     # <-- VALID field (NOT assigned_cluster_manager)
        "location"
    ).order_by("-created_at")

    users = CustomUser.objects.all().order_by("username")
    recent_tickets = tickets[:8]

    # -----------------------------------
    # GET FILTER VALUES
    # -----------------------------------
    status = request.GET.get("status", "")
    assigned_to_raw = request.GET.get("assigned_to", "")
    location = request.GET.get("location", "")
    download = request.GET.get("download", "")

    # -----------------------------------
    # STATUS FILTER
    # -----------------------------------
    if status:
        tickets = tickets.filter(status=status)

    # -----------------------------------
    # ASSIGNED FILTER
    # -----------------------------------
    try:
        assigned_to = int(assigned_to_raw)
    except:
        assigned_to = None

    if assigned_to:
        tickets = tickets.filter(
            Q(assigned_owner__id=assigned_to) |
            Q(reassigned_to__id=assigned_to)
        )

    # -----------------------------------
    # LOCATION FILTER
    # -----------------------------------
    if location:
        tickets = tickets.filter(location=location)

    # -----------------------------------
    # FILTER DROPDOWNS
    # -----------------------------------
    locations = Ticket.objects.values_list("location", flat=True).distinct()
    categories = Ticket.objects.values_list("concern", flat=True).distinct()

    # -------------------------------------------------------
    # OT / SAC OFF UPDATES (SHOW ALL FOR ADMIN)
    # -------------------------------------------------------
    updates = StaffTimeUpdate.objects.select_related(
        "staff", "staff__location"
    ).order_by("-updated_at")

    staff_time_updates = StaffTimeUpdate.objects.select_related("staff", "updated_by").order_by("-updated_at")

    # -----------------------------------
    # CONTEXT
    # -----------------------------------
    context = {
        "total_users": total_users,
        "active_users": active_users,
        "inactive_users": inactive_users,

        "total_tickets": total_tickets,
        "pending_tickets": pending_tickets,
        "resolved_tickets": resolved_tickets,

        "tickets": tickets,
        "recent_tickets": recent_tickets,
        "users": users,

        "locations": locations,
        "categories": categories,

        "selected_status": status,
        "selected_assigned_to": assigned_to_raw,
        "selected_location": location,
        "staff_time_updates": staff_time_updates,
    }

    return render(request, "admin_dashboard.html", context)


@login_required
@user_passes_test(is_admin)
def export_users_csv(request):
    """Download the complete user directory for administrators."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="user_directory.csv"'
    response.write("\ufeff")  # Makes the CSV open correctly in Excel.

    writer = csv.writer(response)
    writer.writerow(["EMP Name", "EMP ID", "Status", "Location", "Role"])

    users = CustomUser.objects.select_related("location").order_by("employee_id")
    for user in users:
        writer.writerow([
            user.get_full_name() or user.username,
            user.employee_id,
            "Active" if user.is_active else "Inactive",
            user.location.name if user.location else "",
            user.role,
        ])

    return response





# --------------------------
# ✅ Raise Staff Log — Cluster + Kitchen Manager (KM unchanged)
# --------------------------
@login_required
@user_passes_test(lambda u: u.role in ["kitchen_manager", "cluster_manager"])
def raise_staff_log(request):
    user = request.user

    # Pass user to form for filtering
    form = KitchenLogForm(request.POST or None, user=user)

    # 🟢 Staff filtering (for dropdowns if needed)
    if user.role == "kitchen_manager" and user.location:
        # ✅ Existing behavior — unchanged
        staff_list = CustomUser.objects.filter(role="kitchen_staff", location=user.location)

    elif user.role == "cluster_manager" and hasattr(user, "cluster_manager_profile"):
        # ✅ Cluster Manager: show all staff from assigned locations
        assigned_locations = user.cluster_manager_profile.locations.all()
        staff_list = CustomUser.objects.filter(role="kitchen_staff", location__in=assigned_locations)

    else:
        # Fallback
        staff_list = CustomUser.objects.filter(role="kitchen_staff")

    # 🟢 Handle form submission
    if request.method == "POST" and form.is_valid():
        log = form.save(commit=False)

        # ✅ Location assignment
        if user.role == "kitchen_manager":
            # 🔒 Keep KM behavior exactly the same
            if user.location:
                log.location = user.location.code
            else:
                log.location = "UNKNOWN"

        elif user.role == "cluster_manager":
            # ✅ Use selected staff’s location automatically
            if log.staff and log.staff.location:
                log.location = log.staff.location.code
            else:
                log.location = "UNKNOWN"

        # ✅ Auto-fill staff info
        if log.staff:
            log.emp_id = log.staff.employee_id or "-"
            log.emp_name = log.staff.username or "Unknown"

        log.save()

        # ✅ Redirect correctly
        redirect_page = "cluster_dashboard" if user.role == "cluster_manager" else "manager_dashboard"
        messages.success(request, "✅ Staff log recorded successfully!")
        return redirect(redirect_page)

    return render(request, "raise_staff_log.html", {
        "form": form,
        "staff_list": staff_list
    })





@login_required
@user_passes_test(lambda u: u.role == "kitchen_staff")
def confirm_ticket_closure(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id, employee=request.user)

    ticket.staff_confirmed = True
    ticket.staff_confirmed_at = timezone.now()
    ticket.status = "Closed"
    ticket.save()

    messages.success(request, "✅ Ticket closure confirmed successfully.")
    return redirect("staff_dashboard")



# --------------------------
# ✅ View All Tickets (Admin)
# --------------------------


def view_all_tickets(request):

    tickets = Ticket.objects.all().order_by("-created_at")

    # ----------------------------------
    # ⭐ FILTERS
    # ----------------------------------
    status = request.GET.get("status")
    assigned_to = request.GET.get("assigned_to")
    location = request.GET.get("location")

    if status:
        tickets = tickets.filter(status=status)

    if assigned_to:
        tickets = tickets.filter(assigned_owner_id=assigned_to)

    if location:
        tickets = tickets.filter(location__name=location)

    # ----------------------------------
    # ⭐ Prepare values for HTML table
    # Add computed fields to each ticket
    # ----------------------------------
    for t in tickets:
        # Closed date
        t.closed_dt = t.closed_at.strftime("%d-%m-%Y %H:%M") if t.closed_at else ""

        # Pending days = created → closed OR today
        if t.closed_at:
            t.pending_days = (t.closed_at.date() - t.created_at.date()).days
        else:
            t.pending_days = (timezone.now().date() - t.created_at.date()).days

        # Staff confirmation date
        t.confirm_dt = t.staff_confirmed_at.strftime("%d-%m-%Y %H:%M") if t.staff_confirmed_at else ""

        # Staff confirmation pending days
        if t.staff_confirmed_at:
            t.confirm_pending = (t.staff_confirmed_at.date() - t.created_at.date()).days
        else:
            t.confirm_pending = ""

        # Employee remarks (if exists)
        t.employee_remarks = getattr(t, "employee_remarks", "")

        # Owner remarks (if exists)
        t.owner_remarks = getattr(t, "owner_remarks", "")

        # Rejection remarks (if exists)
        t.rejection_remarks = getattr(t, "rejection_reason", "")

        # Reassigned info
        if t.reassigned_to:
            t.reassigned_info = f"Reassigned to {t.reassigned_to.username}"
        else:
            t.reassigned_info = ""

        # Time to resolve (HH:MM:SS)
        if t.closed_at:
            t.time_to_resolve = str(t.closed_at - t.created_at)
        else:
            t.time_to_resolve = ""

        # SLA breach (>48 hours)
        if t.closed_at:
            t.sla_breach = (t.closed_at - t.created_at) > timedelta(hours=48)
        else:
            t.sla_breach = False

    # ----------------------------------
    # ⭐ CSV DOWNLOAD
    # ----------------------------------
    if request.GET.get("download") == "csv":

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="tickets.csv"'

        writer = csv.writer(response)

        writer.writerow([
            "Raised Date",
            "Ticket Number",
            "Employee",
            "Employee Code",
            "Location",
            "Concern",
            "Category",
            "Status",
            "Assigned Owner",
            "Description",

            "Closed Date & Time",
            "Pending Days",
            "Staff Confirmation Date",
            "Staff Confirmation Pending Days",
            "Employee Remarks",
            "Owner Remarks",
            "Rejection Remarks",
            "Reassigned Info",
            "Time Taken To Resolve",
            "SLA Breach"
        ])

        for t in tickets:
            writer.writerow([
                t.created_at.strftime("%d-%m-%Y"),
                t.ticket_number,
                t.employee.username if t.employee else "",
                t.employee.employee_id if t.employee else "",
                t.location.name if t.location else "",
                t.concern or "",
                t.concern_category or "",
                t.status or "",
                t.assigned_owner.username if t.assigned_owner else "",
                t.description or "",

                t.closed_dt,
                t.pending_days,
                t.confirm_dt,
                t.confirm_pending,
                t.employee_remarks,
                t.owner_remarks,
                t.rejection_remarks,
                t.reassigned_info,
                t.time_to_resolve,
                "YES" if t.sla_breach else "NO",
            ])

        return response

    # ----------------------------------
    # ⭐ PAGINATION
    # ----------------------------------
    paginator = Paginator(tickets, 50)
    page = request.GET.get("page")
    tickets_page = paginator.get_page(page)

    # Dropdown lists
    owners = CustomUser.objects.filter(role="ticket_owner")
    locations = Location.objects.all()

    return render(request, "view_all_tickets.html", {
        "tickets": tickets_page,
        "owners": owners,
        "locations": locations,
    })

    # -----------------------------
    # 📌 Dynamic dropdown values
    # -----------------------------
    locations = Ticket.objects.values_list("location", flat=True).distinct()
    staff_list = CustomUser.objects.filter(role="cluster_manager")

    context = {
        "tickets": tickets,
        "locations": locations,
        "staff_list": staff_list,
    }

    return render(request, "view_all_tickets.html", context)







# --------------------------
# ✅ Kitchen Manager / HR – IConnect Form View
# --------------------------
# --------------------------
# ✅ iConnect Form (All roles)
# --------------------------

@login_required
def iconnect_form_view(request):
    user = request.user
    form = IConnectForm(request.POST or None, user=user)

    # ------------------------------------------------------
    # 🟢 STAFF LIST FILTERING
    # ------------------------------------------------------
    if user.role == "kitchen_manager" and user.location:
        staff_list = CustomUser.objects.filter(
            role="kitchen_staff",
            location=user.location
        )

    elif user.role == "cluster_manager" and hasattr(user, "cluster_manager_profile"):
        assigned_locations = user.cluster_manager_profile.locations.all()
        staff_list = CustomUser.objects.filter(
            role="kitchen_staff",
            location__in=assigned_locations
        )

    else:
        staff_list = CustomUser.objects.filter(role="kitchen_staff")

    # ------------------------------------------------------
    # 🟢 POST BLOCK — SAVE TICKET
    # ------------------------------------------------------
    if request.method == "POST" and form.is_valid():
        ticket = form.save(commit=False)

        # ------------------------------------------------------
        # 👨‍🍳 FIX 1 — ASSIGN SELECTED STAFF (NOT MANAGER)
        # ------------------------------------------------------
        selected_staff_id = request.POST.get("staff")

        if selected_staff_id:
            staff = CustomUser.objects.get(id=selected_staff_id)
            ticket.employee = staff
            ticket.employee_code = staff.employee_id
            ticket.name = staff.first_name or staff.username
                       
        else:
            # fallback — assign creator
            ticket.employee = user
            ticket.employee_code = user.employee_id
            ticket.name = user.first_name or user.username
                        
        # ------------------------------------------------------
        # 📍 LOCATION FIX
        # ------------------------------------------------------
        location_id = request.POST.get("location")

        if location_id:
            ticket.location = Location.objects.get(id=location_id)
        else:
            ticket.location = user.location
            
        # ------------------------------------------------------
        # 👨‍💼 OWNER ASSIGNMENT LOGIC
        # ------------------------------------------------------
        category = (
            form.cleaned_data.get("concern_category")
            or form.cleaned_data.get("concern")
        )

        assigned_owner = get_owner_for_category(category)

        if not assigned_owner:
            assigned_owner = (
                CustomUser.objects.filter(role="owner")
                .annotate(ticket_count=Count("tickets_owned"))
                .order_by("ticket_count")
                .first()
            )

        ticket.assigned_owner = assigned_owner
        ticket.status = "Assigned" if assigned_owner else "Pending"
        ticket.save()

        # ------------------------------------------------------
        # SUCCESS MESSAGE + REDIRECT
        # ------------------------------------------------------
        messages.success(
            request,
            f"✅ Ticket submitted successfully and assigned to "
            f"{assigned_owner.username if assigned_owner else 'No Owner'}!"
        )

        redirect_target = (
            "cluster_dashboard" if user.role == "cluster_manager"
            else "manager_dashboard" if user.role == "kitchen_manager"
            else "dashboard"
        )

        return redirect(redirect_target)

    # ------------------------------------------------------
    # GET REQUEST — LOAD FORM
    # ------------------------------------------------------
    return render(request, "iconnect_form.html", {
        "form": form,
        "staff_list": staff_list,
    })



User = get_user_model()

#✅ Utility
# --------------------------
def get_owner_for_category(category):
    """Return the correct owner User object for the given category using employee_id mapping."""
    if not category:
        return None

    category = category.strip().lower()

    for key, emp_id in CATEGORY_OWNER_MAP.items():
        if key.lower() == category:
            try:
                return User.objects.get(employee_id=emp_id, role="owner")
            except User.DoesNotExist:
                return None

    return None


# --------------------------
# ✅ Raise Ticket (Kitchen Staff)
# --------------------------

@login_required
@user_passes_test(lambda u: u.role == "kitchen_staff")
def raise_ticket(request):
    if request.method == "POST":
        form = KitchenPlayerForm(request.POST, user=request.user)
        if form.is_valid():
            ticket = form.save(commit=False)

            ticket.employee = request.user
            ticket.employee_code = request.user.employee_id
            ticket.name = request.user.username
            ticket.location = request.user.location  # ✅ FIXED: assign FK object

            category = form.cleaned_data.get("concern")

            owner_emp_id = CATEGORY_OWNER_MAP.get(category)
            owner = None

            if owner_emp_id:
                owner = CustomUser.objects.filter(employee_id=owner_emp_id, role="owner").first()

            if not owner:
                owner = (
                    CustomUser.objects.filter(role="owner")
                    .annotate(ticket_count=Count("tickets_owned"))
                    .order_by("ticket_count")
                    .first()
                )

            if owner:
                ticket.assigned_owner = owner
                ticket.status = "Assigned"
                assigned_to = f"{owner.username} ({owner.employee_id})"
            else:
                ticket.status = "Pending"
                assigned_to = "No Owner"

            ticket.save()

            messages.success(
                request,
                f"✅ Your ticket has been raised successfully and assigned to {assigned_to}!"
            )
            return redirect("staff_dashboard")
    else:
        form = KitchenPlayerForm(user=request.user)

    return render(request, "raise_ticket.html", {"form": form})



# --------------------------
# ✅ Cluster Manager — View Kitchen Managers, Staff, Logs
# --------------------------
@login_required
@user_passes_test(lambda u: u.role == "cluster_manager")
def view_kitchen_managers(request):
    user = request.user
    assigned_locations = user.cluster_manager_profile.locations.all()
    kitchen_managers = CustomUser.objects.filter(role="kitchen_manager", location__in=assigned_locations)
    return render(request, "view_kitchen_managers.html", {"kitchen_managers": kitchen_managers})


@login_required
@user_passes_test(lambda u: u.role == "cluster_manager")
def view_kitchen_staff(request):
    user = request.user
    assigned_locations = user.cluster_manager_profile.locations.all()
    kitchen_staff = CustomUser.objects.filter(role="kitchen_staff", location__in=assigned_locations)
    return render(request, "view_kitchen_staff.html", {"kitchen_staff": kitchen_staff})



@login_required
def view_kitchen_logs(request):
    emp_name = request.GET.get("emp_name", "").strip()
    employee_id = request.GET.get("employee_id", "").strip()

    # Base queryset
    kitchen_logs = KitchenLog.objects.all().order_by("-created_at")

    # -----------------------------
    # 🔍 FILTER: Employee Name
    # -----------------------------
    if emp_name:
        kitchen_logs = kitchen_logs.filter(
            Q(staff__first_name__icontains=emp_name) |
            Q(staff__last_name__icontains=emp_name) |
            Q(staff__username__icontains=emp_name) |
            Q(emp_name__icontains=emp_name)  # old logs
        )

    # -----------------------------
    # 🔍 FILTER: Employee ID
    # -----------------------------
    if employee_id:
        kitchen_logs = kitchen_logs.filter(
            Q(staff__employee_id__icontains=employee_id) |
            Q(emp_id__icontains=employee_id)  # old logs
        )

    return render(
        request,
        "view_kitchen_logs.html",
        {"kitchen_logs": kitchen_logs}
    )


# --------------------------
# ✅ Cluster Manager Dashboard (Tickets)
# --------------------------

@login_required
@user_passes_test(lambda u: u.role == "cluster_manager")
def cluster_dashboard(request):
    user = request.user

    # ✅ Assigned locations for this cluster manager
    assigned_locations = []
    if hasattr(user, "cluster_manager_profile"):
        assigned_locations = user.cluster_manager_profile.locations.all()

    # ✅ Kitchen Managers in those locations
    kitchen_managers = CustomUser.objects.filter(
        role="kitchen_manager",
        location__in=assigned_locations
    )

    # ✅ Kitchen Staff in those locations
    kitchen_staff = CustomUser.objects.filter(
        role="kitchen_staff",
        location__in=assigned_locations
    )

    # ✅ iConnect Tickets in assigned locations
    tickets = Ticket.objects.filter(
        location__in=assigned_locations
    ).order_by("-created_at")

    # ✅ Recent kitchen logs
    kitchen_logs = KitchenLog.objects.filter(
        location__in=[loc.code for loc in assigned_locations]
    ).order_by("-created_at")[:10]

    context = {
        "assigned_locations": assigned_locations,
        "kitchen_managers": kitchen_managers,
        "kitchen_staff": kitchen_staff,
        "kitchen_logs": kitchen_logs,
        "tickets": tickets,  # 👈 Added
    }
    return render(request, "cluster_dashboard.html", context)

# ✅ Cluster Manager closes a reassigned ticket
@login_required
@user_passes_test(lambda u: u.role == "cluster_manager")
def close_cluster_ticket(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id)
    user = request.user

    # ----- 1️⃣ Permission: Check if ticket location belongs to this cluster manager -----
    assigned_locations = user.cluster_manager_profile.locations.all()
    if ticket.location not in assigned_locations:
        messages.error(request, "❌ You cannot modify tickets outside your assigned locations.")
        return redirect("cluster_dashboard")

    # ----- 2️⃣ Prevent closing an already closed ticket -----
    if ticket.status == "Closed":
        messages.info(request, "ℹ️ This ticket is already closed.")
        return redirect("cluster_dashboard")

    # ----- 3️⃣ GET → Show closing remarks form -----
    if request.method == "GET":
        return render(request, "close_cluster_ticket.html", {"ticket": ticket})

    # ----- 4️⃣ POST → Save closing remarks -----
    closing_remarks = request.POST.get("closing_remarks", "").strip()

    if not closing_remarks:
        messages.error(request, "⚠️ Closing remarks are required.")
        return render(request, "close_cluster_ticket.html", {"ticket": ticket})

    ticket.status = "Closed"
    ticket.closed_at = timezone.now()
    ticket.closing_remarks = closing_remarks
    ticket.save()

    messages.success(request, f"✅ Ticket {ticket.ticket_number} closed successfully.")
    return redirect("cluster_dashboard")



# ✅ Cluster Manager confirms owner resolution
@login_required
@user_passes_test(lambda u: u.role == "cluster_manager")
def confirm_cluster_ticket(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id)
    user = request.user

    # ✅ Extract assigned location names
    assigned_locations = list(user.cluster_manager_profile.locations.values_list("name", flat=True))

    # ✅ Compare using strings
    if ticket.location not in assigned_locations:
        messages.error(request, "❌ You cannot modify tickets outside your assigned locations.")
        return redirect("cluster_dashboard")

    ticket.status = "Confirmed"
    ticket.owner_confirmed_at = timezone.now()
    ticket.resolved_confirmed = True
    ticket.save()

    messages.success(request, f"✅ Ticket {ticket.ticket_number} confirmed successfully.")
    return redirect("cluster_dashboard")

@login_required
@user_passes_test(lambda u: u.role == "cluster_manager")
def view_cluster_tickets(request):
    user = request.user
    
    assigned_locations = user.cluster_manager_profile.locations.all()

    tickets = Ticket.objects.filter(
        location__in=assigned_locations
    ).order_by("-created_at")

    return render(request, "view_cluster_tickets.html", {
        "tickets": tickets,
        "assigned_locations": assigned_locations,
    })






@login_required
def staff_salary_slip(request):
    slips = SalarySlip.objects.filter(employee=request.user).order_by('-year', '-month')
    return render(request, 'staff_salary_slip.html', {'slips': slips})

# ----------------------------------------
# IMPORTS
# ----------------------------------------



# ----------------------------------------
# 🔥 UNIFIED ROLE → LOCATION LOGIC
# ----------------------------------------
def get_user_locations(user):
    """Return list/queryset of allowed locations based on user role."""

    # 1️⃣ Kitchen Staff
    if user.role == "kitchen_staff":
        if hasattr(user, "kitchenstaff_profile"):
            return [user.kitchenstaff_profile.location]
        return [user.location] if user.location else []

    # 2️⃣ Kitchen Manager
    if user.role == "kitchen_manager":
        if hasattr(user, "kitchen_manager_profile"):
            return [user.kitchen_manager_profile.location]
        return [user.location] if user.location else []

    # 3️⃣ Cluster Manager → multiple assigned
    if user.role == "cluster_manager":
        if hasattr(user, "cluster_manager_profile"):
            return user.cluster_manager_profile.locations.all()
        return []

    # 4️⃣ Admin / Owner → all locations
    if user.role in ["admin", "owner"]:
        return Location.objects.all()

    return []


# ----------------------------------------
# ✅ Upload Order Photo
# ----------------------------------------
@login_required
def upload_order_photo(request):
    if request.method == "POST":
        form = OrderPhotoForm(request.POST, request.FILES, user=request.user)

        if form.is_valid():
            photo_obj = form.save(commit=False)
            photo_obj.uploaded_by = request.user

            # SET LOCATION BASED ON ROLE
            user = request.user
            allowed_locations = get_user_locations(user)

            # Staff/Manager: auto location
            if user.role in ["kitchen_staff", "kitchen_manager", "cluster_manager"]:
                photo_obj.location = allowed_locations[0] if allowed_locations else None

            # Cluster/Admin/Owner: select from form
            else:
                photo_obj.location = form.cleaned_data.get("location")

            photo_obj.save()
            messages.success(request, "Photo uploaded successfully!")
            return redirect("upload_order_photo")

    else:
        form = OrderPhotoForm(user=request.user)

    return render(request, "upload_order_photo.html", {"form": form})


# ----------------------------------------
# 📌 FILTER ORDER PHOTOS + CSV EXPORT
# ----------------------------------------

@login_required
def filter_order_photos(request):
    user = request.user
    user_locations = get_user_locations(user)

    photos = OrderPhoto.objects.filter(location__in=user_locations).order_by("-uploaded_at")

    # FILTER INPUTS
    date_after = request.GET.get("date_after")
    date_before = request.GET.get("date_before")
    order_id = request.GET.get("order_id")
    username = request.GET.get("username")
    full_name = request.GET.get("full_name")
    location = request.GET.get("location")   # NEW

    # DATE FILTERS
    if date_after:
        photos = photos.filter(uploaded_at__date__gte=date_after)

    if date_before:
        photos = photos.filter(uploaded_at__date__lte=date_before)

    # ORDER ID
    if order_id:
        photos = photos.filter(order_id__icontains=order_id)

    # USERNAME
    if username:
        photos = photos.filter(uploaded_by__username__icontains=username)

    # FULL NAME
    if full_name:
        photos = photos.filter(
            Q(uploaded_by__first_name__icontains=full_name) |
            Q(uploaded_by__last_name__icontains=full_name)
        )

    # LOCATION (FULL TEXT SEARCH)
    if location:
        photos = photos.filter(location__name__icontains=location)

    # CSV EXPORT
    if request.GET.get("export") == "csv":
        return export_photos_csv(request, photos)

    return render(request, "partials/order_photos_table.html", {"photos": photos})




# ----------------------------------------
# 📌 UNIFIED CSV EXPORT FUNCTION (UPDATED)
# ----------------------------------------


def export_photos_csv(request, photos_queryset):
    # Generate today's date in YYYYMMDD format
    today_str = datetime.now().strftime("%Y%m%d%h")

    # Build file name like: 20251101_KOT.csv
    file_name = f"{today_str}_KOT.csv"

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{file_name}"'

    writer = csv.writer(response)
    writer.writerow(["Order ID", "Uploaded By", "Location", "Uploaded At", "Image URL"])

    for p in photos_queryset:
        writer.writerow([
            p.order_id,
            p.uploaded_by.username if p.uploaded_by else "",
            p.location.name if p.location else "",
            p.uploaded_at.strftime("%Y-%m-%d %H:%M"),
            request.build_absolute_uri(p.photo.url) if p.photo else "",
        ])

    return response



# ----------------------------------------
# 📌 VIEW ORDER PHOTOS PAGE
# ----------------------------------------
@login_required
def view_order_photos(request):
    user = request.user
    user_locations = get_user_locations(user)

    if not user_locations:
        messages.error(request, "No locations assigned to your account.")
        return redirect("dashboard")

    photos = OrderPhoto.objects.filter(
        location__in=user_locations
    ).order_by("-uploaded_at")

    return render(request, "view_order_photos.html", {"photos": photos})


# views.py
@login_required
@user_passes_test(is_cluster_manager)
def update_staff_time(request):
    if request.method == "POST":
        form = StaffTimeUpdateForm(request.POST, user=request.user)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.updated_by = request.user
            entry.save()
            messages.success(request, "Updated successfully.")
            return redirect("cluster_dashboard")
    else:
        form = StaffTimeUpdateForm(user=request.user)

    return render(request, "update_staff_time.html", {"form": form})

@login_required
def admin_ot_sac_list(request):
    if request.user.role != "admin":
        return HttpResponseForbidden()

    records = StaffTimeUpdate.objects.select_related(
        "staff",        # FIXED
        "updated_by"    # Add this for efficiency
    ).order_by("-updated_at")

    return render(request, "admin_ot_sac_list.html", {"records": records})



@login_required
def cluster_ot_sac_list(request):
    if request.user.role != "cluster_manager":
        return HttpResponseForbidden()

    # cluster manager has ONE location
    user_location = request.user.location  

    # Fetch only records belonging to staff in the CM's location
    records = StaffTimeUpdate.objects.filter(
        staff__location=user_location
    ).select_related("staff").order_by("-updated_at")

    return render(request, "cluster_ot_sac_list.html", {"records": records})



@staff_member_required
def export_staff_updates_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="staff_time_updates.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "Employee ID",
        "Employee Name",
        "Location",
        "Type",
        "OT Hours",
        "OT Date",
        "SAC OFF Date",
        "Remarks",
        "Updated At",
    ])

    for item in StaffTimeUpdate.objects.all().order_by('-updated_at'):

        writer.writerow([
            item.staff.employee_id,
            item.staff.get_full_name(),
            item.staff.location,
            item.update_type,
            item.ot_hours if item.update_type == "TO" else "",
            item.ot_date if item.update_type == "TO" else "",
            item.sac_off_date if item.update_type == "SAC_OFF" else "",
            item.remarks,
            item.updated_at,
        ])

    return response



@login_required
def punch_in(request):
    user = request.user

    # Only Kitchen Staff & Kitchen Manager
    if not (is_kitchen_staff(user) or is_kitchen_manager(user)):
        messages.error(request, "Only kitchen staff or kitchen managers can punch in.")
        return redirect("dashboard")

    today = timezone.localdate()

    attendance, _ = Attendance.objects.get_or_create(
        user=user,
        date=today
    )

    if attendance.punch_in:
        messages.warning(request, "You have already punched in today.")
    else:
        attendance.punch_in = timezone.now()
        attendance.save()
        messages.success(request, "✅ Punch in recorded successfully.")

    return redirect("dashboard")


@login_required
def punch_out(request):
    user = request.user

    if not (is_kitchen_staff(user) or is_kitchen_manager(user)):
        messages.error(request, "Only kitchen staff or kitchen managers can punch out.")
        return redirect("dashboard")

    today = timezone.localdate()

    try:
        attendance = Attendance.objects.get(user=user, date=today)
    except Attendance.DoesNotExist:
        messages.error(request, "Please punch in before punching out.")
        return redirect("dashboard")

    if attendance.punch_out:
        messages.warning(request, "You have already punched out today.")
    elif not attendance.punch_in:
        messages.error(request, "Punch in is required before punch out.")
    else:
        attendance.punch_out = timezone.now()
        attendance.save()
        messages.success(request, "✅ Punch out recorded successfully.")

    return redirect("dashboard")




@login_required
@user_passes_test(lambda u: u.role == "cluster_manager")
def cluster_attendance_report(request):
    user = request.user

    assigned_locations = []
    if hasattr(user, "cluster_manager_profile"):
        assigned_locations = user.cluster_manager_profile.locations.all()

    last_7_days = timezone.localdate() - timedelta(days=6)

    attendance_records = Attendance.objects.select_related(
        "user", "user__location"
    ).filter(
        user__role="kitchen_staff",
        user__location__in=assigned_locations,
        date__gte=last_7_days
    ).order_by("date", "user__username")

    return render(request, "cluster_attendance_report.html", {
        "attendance_records": attendance_records,
        "assigned_locations": assigned_locations,
    })

# ======================================================
# QUALITY FEEDBACK
# ======================================================


@login_required
def raise_quality_feedback(request):

    user = request.user

    # Only KM and CM can raise Quality Feedback
    if user.role not in ["kitchen_manager", "cluster_manager"]:
        messages.error(
            request,
            "You are not authorized to raise Quality Feedback."
        )
        return redirect("dashboard")

    if request.method == "POST":

        form = QualityFeedbackForm(
            request.POST,
            user=user
        )

        if form.is_valid():

            feedback = form.save(commit=False)

            # Get selected staff
            staff = feedback.staff

            if not staff:
                messages.error(
                    request,
                    "Please select a staff member."
                )
                return render(
                    request,
                    "raise_quality_feedback.html",
                    {"form": form}
                )

            # ------------------------------------------
            # Security check
            # ------------------------------------------

            if user.role == "kitchen_manager":

                if staff.location != user.location:
                    messages.error(
                        request,
                        "You cannot raise feedback for staff from another location."
                    )
                    return redirect(
                        "raise_quality_feedback"
                    )

            elif user.role == "cluster_manager":

                assigned_locations = (
                    user.cluster_manager_profile
                    .locations.all()
                )

                if staff.location not in assigned_locations:
                    messages.error(
                        request,
                        "You cannot raise feedback for this staff member."
                    )
                    return redirect(
                        "raise_quality_feedback"
                    )

            # ------------------------------------------
            # Store staff information
            # ------------------------------------------

            feedback.emp_id = staff.employee_id
            feedback.emp_name = staff.username
            feedback.raised_by = user

            if staff.location:
                feedback.location = staff.location.code
            else:
                feedback.location = "UNKNOWN"

            feedback.save()

            messages.success(
                request,
                "Quality Feedback raised successfully."
            )

            return redirect(
                "view_quality_feedback"
            )

    else:

        form = QualityFeedbackForm(
            user=user
        )

    return render(
        request,
        "raise_quality_feedback.html",
        {
            "form": form
        }
    )


@login_required
@user_passes_test(is_admin)
def quality_feedback_analytics(request):
    """Show admin-only adoption metrics for the Quality Feedback feature."""
    today = timezone.localdate()
    month_start = today.replace(day=1)
    feedbacks = QualityFeedback.objects.all()
    users_with_feedback = (
        CustomUser.objects.filter(raised_quality_feedback__isnull=False)
        .annotate(feedback_count=Count("raised_quality_feedback"))
        .order_by("-feedback_count", "username")
    )

    return render(request, "quality_feedback_analytics.html", {
        "total_feedback": feedbacks.count(),
        "feedback_this_month": feedbacks.filter(created_at__date__gte=month_start).count(),
        "unique_raisers": users_with_feedback.count(),
        "user_usage": users_with_feedback,
    })


# ======================================================
# VIEW QUALITY FEEDBACK
# ======================================================


@login_required
def view_quality_feedback(request):

    user = request.user

    # --------------------------------------------------
    # Kitchen Staff
    # Only their own feedback
    # --------------------------------------------------

    if user.role == "kitchen_staff":

        feedbacks = QualityFeedback.objects.filter(
            staff=user
        ).order_by(
            "-feedback_date",
            "-created_at"
        )

    # --------------------------------------------------
    # Kitchen Manager
    # Only their location
    # --------------------------------------------------

    elif user.role == "kitchen_manager":

        if user.location:

            feedbacks = QualityFeedback.objects.filter(
                location=user.location.code
            ).order_by(
                "-feedback_date",
                "-created_at"
            )

        else:

            feedbacks = QualityFeedback.objects.none()

    # --------------------------------------------------
    # Cluster Manager
    # Assigned locations
    # --------------------------------------------------

    elif user.role == "cluster_manager":

        if hasattr(
            user,
            "cluster_manager_profile"
        ):

            assigned_locations = (
                user.cluster_manager_profile
                .locations
                .values_list(
                    "code",
                    flat=True
                )
            )

            feedbacks = QualityFeedback.objects.filter(
                location__in=assigned_locations
            ).order_by(
                "-feedback_date",
                "-created_at"
            )

        else:

            feedbacks = QualityFeedback.objects.none()

    # --------------------------------------------------
    # Admin / Owner
    # See everything
    # --------------------------------------------------

    elif user.role in ["admin", "owner"]:

        feedbacks = QualityFeedback.objects.all().order_by(
            "-feedback_date",
            "-created_at"
        )

    # --------------------------------------------------
    # Other users
    # --------------------------------------------------

    else:

        feedbacks = QualityFeedback.objects.none()

    # ==================================================
    # FILTERS
    # ==================================================

    employee_id = request.GET.get(
        "employee_id",
        ""
    ).strip()

    location = request.GET.get(
        "location",
        ""
    ).strip()

    # Employee ID filter
    if employee_id:

        feedbacks = feedbacks.filter(
            emp_id__icontains=employee_id
        )

    # Location filter
    if location:

        feedbacks = feedbacks.filter(
            location=location
        )

    # Locations for dropdown
    if user.role in ["admin", "owner"]:

        locations = (
            QualityFeedback.objects
            .exclude(location__isnull=True)
            .exclude(location="")
            .values_list(
                "location",
                flat=True
            )
            .distinct()
            .order_by("location")
        )

    elif user.role == "kitchen_manager":

        if user.location:
            locations = [user.location.code]
        else:
            locations = []

    elif user.role == "cluster_manager":

        if hasattr(
            user,
            "cluster_manager_profile"
        ):

            locations = (
                user.cluster_manager_profile
                .locations
                .values_list(
                    "code",
                    flat=True
                )
                .order_by("code")
            )

        else:

            locations = []

    else:

        locations = []

    return render(
        request,
        "view_quality_feedback.html",
        {
            "feedbacks": feedbacks,
            "locations": locations,
            "selected_employee_id": employee_id,
            "selected_location": location,
        }
    )


# ======================================================
# ACKNOWLEDGE QUALITY FEEDBACK
# ======================================================


@login_required
def acknowledge_quality_feedback(
    request,
    feedback_id
):

    feedback = get_object_or_404(
        QualityFeedback,
        id=feedback_id
    )

    # Only assigned staff can acknowledge
    if feedback.staff != request.user:

        messages.error(
            request,
            "You are not authorized to acknowledge this feedback."
        )

        return redirect(
            "view_quality_feedback"
        )

    # Prevent duplicate acknowledgement
    if not feedback.is_acknowledged:

        feedback.is_acknowledged = True

        feedback.acknowledged_at = timezone.now()

        feedback.save(
            update_fields=[
                "is_acknowledged",
                "acknowledged_at",
            ]
        )

        messages.success(
            request,
            "Quality Feedback acknowledged successfully."
        )

    else:

        messages.info(
            request,
            "This feedback has already been acknowledged."
        )

    return redirect(
        "view_quality_feedback"
    )


# ======================================================
# EXPORT QUALITY FEEDBACK CSV
# ======================================================


@login_required
def export_quality_feedback_csv(request):

    # Only Admin can download
    if request.user.role != "admin":

        messages.error(
            request,
            "You are not authorized to download Quality Feedback."
        )

        return redirect(
            "view_quality_feedback"
        )

    feedbacks = QualityFeedback.objects.all().order_by(
        "-feedback_date",
        "-created_at"
    )

    response = HttpResponse(
        content_type="text/csv"
    )

    response[
        "Content-Disposition"
    ] = (
        'attachment; filename="quality_feedback.csv"'
    )

    writer = csv.writer(response)

    # CSV Header
    writer.writerow([
        "Feedback Date",
        "Employee ID",
        "Employee Name",
        "Location",
        "Category",
        "Remarks",
        "Acknowledged",
        "Acknowledged At",
        "Created At",
    ])

    # CSV Data
    for feedback in feedbacks:

        writer.writerow([
            feedback.feedback_date,
            feedback.emp_id or "",
            feedback.emp_name or "",
            feedback.location or "",
            feedback.category,
            feedback.remarks or "",

            "Yes"
            if feedback.is_acknowledged
            else "No",

            feedback.acknowledged_at.strftime(
                "%d-%m-%Y %H:%M"
            )
            if feedback.acknowledged_at
            else "",

            feedback.created_at.strftime(
                "%d-%m-%Y %H:%M"
            )
            if feedback.created_at
            else "",
        ])

    return response
# =========================================================
# CLUSTER MANAGER - BULK UPLOAD QUALITY FEEDBACK
# =========================================================

@login_required
def bulk_upload_quality_feedback(request):

    # -----------------------------------------------------
    # Only Cluster Manager can use bulk upload
    # -----------------------------------------------------
    if request.user.role != "cluster_manager":
        messages.error(
            request,
            "You are not authorized to use Quality Feedback bulk upload."
        )
        return redirect("view_quality_feedback")

    # -----------------------------------------------------
    # Check Cluster Manager profile
    # -----------------------------------------------------
    if not hasattr(request.user, "cluster_manager_profile"):
        messages.error(
            request,
            "Cluster Manager profile not found."
        )
        return redirect("view_quality_feedback")

    # -----------------------------------------------------
    # Get assigned locations
    # -----------------------------------------------------
    assigned_locations = request.user.cluster_manager_profile.locations.all()

    assigned_location_codes = set(
        assigned_locations.values_list("code", flat=True)
    )

    # -----------------------------------------------------
    # POST
    # -----------------------------------------------------
    if request.method == "POST":

        form = QualityFeedbackBulkUploadForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():

            uploaded_file = request.FILES.get("file")

            # -------------------------------------------------
            # Check file
            # -------------------------------------------------
            if not uploaded_file:
                messages.error(
                    request,
                    "Please select a CSV file."
                )
                return redirect("bulk_upload_quality_feedback")

            if not uploaded_file.name.lower().endswith(".csv"):
                messages.error(
                    request,
                    "Please upload a CSV file only."
                )
                return redirect("bulk_upload_quality_feedback")

            try:

                # -------------------------------------------------
                # Read CSV
                # -------------------------------------------------
                decoded_file = uploaded_file.read().decode(
                    "utf-8-sig"
                )

                reader = csv.DictReader(
                    io.StringIO(decoded_file)
                )

                # -------------------------------------------------
                # Required columns
                # -------------------------------------------------
                required_columns = {
                    "Employee ID",
                    "Category",
                    "Remarks",
                    "Feedback Date",
                }

                csv_columns = set(
                    reader.fieldnames or []
                )

                missing_columns = required_columns - csv_columns

                if missing_columns:

                    messages.error(
                        request,
                        "Missing columns: "
                        + ", ".join(sorted(missing_columns))
                    )

                    return redirect(
                        "bulk_upload_quality_feedback"
                    )

                # -------------------------------------------------
                # Allowed Categories
                # -------------------------------------------------
                allowed_categories = {
                    "KOT Marking",
                    "Follow SOP",
                    "Quality Check",
                    "Correct Portioning",
                    "Order Verification before packing",
                    "Use Dossier",
                    "Follow dispatch checklist",
                    "Photo Adherence",
                    "Productivity",
                    "Call Cust or Thank u notes",
                }

                created_count = 0
                skipped_count = 0
                errors = []

                # -------------------------------------------------
                # Process rows
                # -------------------------------------------------
                for row_number, row in enumerate(
                    reader,
                    start=2
                ):

                    emp_id = (
                        row.get("Employee ID") or ""
                    ).strip()

                    category = (
                        row.get("Category") or ""
                    ).strip()

                    remarks = (
                        row.get("Remarks") or ""
                    ).strip()

                    feedback_date_raw = (
                        row.get("Feedback Date") or ""
                    ).strip()

                    # =============================================
                    # Basic Validation
                    # =============================================

                    if not emp_id:
                        errors.append(
                            f"Row {row_number}: Employee ID is required."
                        )
                        skipped_count += 1
                        continue

                    if not category:
                        errors.append(
                            f"Row {row_number}: Category is required."
                        )
                        skipped_count += 1
                        continue

                    if not feedback_date_raw:
                        errors.append(
                            f"Row {row_number}: Feedback Date is required."
                        )
                        skipped_count += 1
                        continue

                    # =============================================
                    # DATE VALIDATION
                    # Supports:
                    #
                    # 24-08-2026
                    # 24/08/2026
                    # 2026-08-24
                    # =============================================

                    feedback_date = None

                    date_formats = [
                        "%d-%m-%Y",
                        "%d/%m/%Y",
                        "%Y-%m-%d",
                        "%d-%m-%y",
                        "%d/%m/%y",
                    ]

                    for date_format in date_formats:

                        try:

                            feedback_date = datetime.strptime(
                                feedback_date_raw,
                                date_format
                            ).date()

                            break

                        except ValueError:
                            continue

                    # If date could not be converted
                    if feedback_date is None:

                        errors.append(
                            f"Row {row_number}: Invalid Feedback Date "
                            f"'{feedback_date_raw}'. "
                            f"Use DD-MM-YYYY, for example 24-08-2026."
                        )

                        skipped_count += 1
                        continue

                    # =============================================
                    # CATEGORY VALIDATION
                    # =============================================

                    if category not in allowed_categories:

                        errors.append(
                            f"Row {row_number}: Invalid category "
                            f"'{category}'."
                        )

                        skipped_count += 1
                        continue

                    # =============================================
                    # FIND STAFF
                    # =============================================

                    try:

                        staff = CustomUser.objects.get(
                            employee_id=emp_id,
                            role="kitchen_staff"
                        )

                    except CustomUser.DoesNotExist:

                        errors.append(
                            f"Row {row_number}: Employee ID "
                            f"{emp_id} not found."
                        )

                        skipped_count += 1
                        continue

                    except CustomUser.MultipleObjectsReturned:

                        errors.append(
                            f"Row {row_number}: Multiple users found "
                            f"with Employee ID {emp_id}."
                        )

                        skipped_count += 1
                        continue

                    # =============================================
                    # CHECK STAFF LOCATION
                    # =============================================

                    if not staff.location:

                        errors.append(
                            f"Row {row_number}: Employee ID "
                            f"{emp_id} has no location assigned."
                        )

                        skipped_count += 1
                        continue

                    staff_location_code = staff.location.code

                    # =============================================
                    # CHECK CLUSTER MANAGER LOCATION
                    # =============================================

                    if staff_location_code not in assigned_location_codes:

                        errors.append(
                            f"Row {row_number}: Employee ID "
                            f"{emp_id} belongs to "
                            f"{staff_location_code}, which is not "
                            f"assigned to you."
                        )

                        skipped_count += 1
                        continue

                    # =============================================
                    # STAFF NAME
                    # =============================================

                    staff_name = (
                        staff.get_full_name().strip()
                        if staff.get_full_name()
                        else staff.username
                    )

                    # =============================================
                    # CREATE QUALITY FEEDBACK
                    # =============================================

                    QualityFeedback.objects.create(

                        staff=staff,

                        emp_id=staff.employee_id,

                        emp_name=staff_name,

                        location=staff_location_code,

                        category=category,

                        remarks=remarks,

                        feedback_date=feedback_date,
                    )

                    created_count += 1

                # =================================================
                # SUCCESS MESSAGE
                # =================================================

                if created_count:

                    messages.success(
                        request,
                        f"{created_count} Quality Feedback "
                        f"record(s) uploaded successfully."
                    )

                # =================================================
                # SKIPPED MESSAGE
                # =================================================

                if skipped_count:

                    messages.warning(
                        request,
                        f"{skipped_count} row(s) were skipped."
                    )

                # =================================================
                # ERROR DETAILS
                # =================================================

                for error in errors[:20]:

                    messages.error(
                        request,
                        error
                    )

                # -------------------------------------------------
                # Return to Quality Feedback
                # -------------------------------------------------

                return redirect(
                    "view_quality_feedback"
                )

            except UnicodeDecodeError:

                messages.error(
                    request,
                    "Unable to read the CSV file. "
                    "Please save the file as UTF-8 CSV."
                )

            except Exception as e:

                messages.error(
                    request,
                    f"Bulk upload failed: {str(e)}"
                )

    else:

        form = QualityFeedbackBulkUploadForm()

    # ---------------------------------------------------------
    # Render page
    # ---------------------------------------------------------

    return render(
        request,
        "bulk_upload_quality_feedback.html",
        {
            "form": form,
            "assigned_locations": assigned_locations,
        }
    )

@login_required
def kitchen_log_report(request):

    logs = KitchenLog.objects.all()

    # =========================================================
    # FILTERS
    # =========================================================

    start_date = request.GET.get("start_date", "").strip()
    end_date = request.GET.get("end_date", "").strip()
    location = request.GET.get("location", "").strip()
    category = request.GET.get("category", "").strip()
    status = request.GET.get("status", "").strip()

    if start_date:
        logs = logs.filter(log_date__gte=start_date)

    if end_date:
        logs = logs.filter(log_date__lte=end_date)

    if location:
        logs = logs.filter(location__icontains=location)

    if category:
        logs = logs.filter(category__icontains=category)

    if status == "pending":
        logs = logs.filter(is_acknowledged=False)

    elif status == "acknowledged":
        logs = logs.filter(is_acknowledged=True)


    # =========================================================
    # TOTAL / STATUS
    # =========================================================

    total_logs = logs.count()

    acknowledged_count = logs.filter(
        is_acknowledged=True
    ).count()

    pending_count = logs.filter(
        is_acknowledged=False
    ).count()


    if total_logs:

        acknowledged_percentage = round(
            acknowledged_count * 100 / total_logs,
            1
        )

        pending_percentage = round(
            pending_count * 100 / total_logs,
            1
        )

    else:

        acknowledged_percentage = 0
        pending_percentage = 0


    # =========================================================
    # DATE WISE
    # =========================================================

    date_wise_report = (
        logs
        .values("log_date")
        .annotate(
            total=Count("id"),
            pending=Count(
                "id",
                filter=Q(is_acknowledged=False)
            ),
            acknowledged=Count(
                "id",
                filter=Q(is_acknowledged=True)
            )
        )
        .order_by("-log_date")
    )


    # =========================================================
    # LOCATION WISE
    # =========================================================

    location_wise_report = (
        logs
        .values("location")
        .annotate(
            total=Count("id"),
            pending=Count(
                "id",
                filter=Q(is_acknowledged=False)
            ),
            acknowledged=Count(
                "id",
                filter=Q(is_acknowledged=True)
            )
        )
        .order_by("-total")
    )


    # =========================================================
    # CATEGORY WISE
    # =========================================================

    category_wise_report = (
        logs
        .values("category")
        .annotate(
            total=Count("id"),
            pending=Count(
                "id",
                filter=Q(is_acknowledged=False)
            ),
            acknowledged=Count(
                "id",
                filter=Q(is_acknowledged=True)
            )
        )
        .order_by("-total")
    )


    # =========================================================
    # CONTEXT
    # =========================================================

    context = {

        "date_wise_report": date_wise_report,

        "location_wise_report": location_wise_report,

        "category_wise_report": category_wise_report,

        "total_logs": total_logs,

        "acknowledged_count": acknowledged_count,

        "pending_count": pending_count,

        "acknowledged_percentage": acknowledged_percentage,

        "pending_percentage": pending_percentage,

        "start_date": start_date,

        "end_date": end_date,

        "location": location,

        "category": category,

        "status": status,

    }

    return render(
        request,
        "kitchen_log_report.html",
        context
    )