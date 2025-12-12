from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.urls import path
from django.shortcuts import render, redirect
from django import forms

import pandas as pd

from .models import (
    CustomUser,
    Ticket,
    StaffPerformance,
    KitchenLog,
    Location,
    ClusterManagerProfile,
    SalarySlip,
    OrderPhoto,
)

from django.contrib.auth import get_user_model
from django.utils.html import format_html
import csv
from django.shortcuts import render, redirect
from django.urls import path
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from .forms import UserBulkUploadForm
from .models import CustomUser
from django.contrib.auth.admin import UserAdmin

import csv
import pandas as pd
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.shortcuts import redirect, render
from django.urls import path
from django.contrib.auth.hashers import make_password

from .models import CustomUser, Location
from .forms import UserBulkUploadForm

User = get_user_model()


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):

    change_list_template = "users_change_list.html"

    list_display = ("employee_id", "username", "role", "location",
                    "is_active", "is_staff")
    list_filter = ("role", "location", "is_active", "is_staff")
    search_fields = ("employee_id", "username", "email")
    ordering = ("employee_id",)

    fieldsets = UserAdmin.fieldsets + (
        ("Role & Location Details",
         {"fields": ("employee_id", "role", "location")}),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Role & Location Details",
         {"fields": ("employee_id", "role", "location")}),
    )

    # --------------------------
    # Custom URL
    # --------------------------
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "bulk-upload/",
                self.admin_site.admin_view(self.bulk_upload_view),
                name="customuser_bulk_upload",
            ),
        ]
        return custom + urls

    # --------------------------
    # Bulk Upload View
    # --------------------------
    def bulk_upload_view(self, request):

        if request.method == "POST":
            form = UserBulkUploadForm(request.POST, request.FILES)

            if form.is_valid():
                file = request.FILES["file"]
                filename = file.name.lower()

                users = []

                # --------------------------------
                # CSV Upload
                # --------------------------------
                if filename.endswith(".csv"):
                    decoded = file.read().decode("utf-8-sig").splitlines()
                    reader = csv.DictReader(decoded)

                    # Normalize CSV headers
                    reader.fieldnames = [
                        h.strip().lower().replace(" ", "_").replace("\ufeff", "")
                        for h in reader.fieldnames
                    ]

                    for row in reader:
                        users.append(row)

                # --------------------------------
                # Excel Upload
                # --------------------------------
                elif filename.endswith(".xlsx"):
                    df = pd.read_excel(file)

                    # Normalize Excel headers
                    df.columns = (
                        df.columns.str.strip()
                        .str.lower()
                        .str.replace(" ", "_")
                        .str.replace("\ufeff", "")
                    )

                    users = df.to_dict(orient="records")

                else:
                    messages.error(request, "Upload only .csv or .xlsx files!")
                    return redirect("..")

                # --------------------------------
                # Required Columns
                # --------------------------------
                required = ["employee_id", "username",
                            "role", "location", "password"]

                created_count = 0
                skipped_count = 0

                for row in users:

                    # Missing required fields
                    for field in required:
                        if field not in row or row[field] in [None, ""]:
                            messages.error(request, f"Missing or empty field: {field}")
                            return redirect("..")

                    # --------------------------------
                    # Skip duplicates
                    # --------------------------------
                    if CustomUser.objects.filter(username=row["username"]).exists():
                        skipped_count += 1
                        messages.warning(request, f"Skipped (username exists): {row['username']}")
                        continue

                    if CustomUser.objects.filter(employee_id=row["employee_id"]).exists():
                        skipped_count += 1
                        messages.warning(
                            request, f"Skipped (employee ID exists): {row['employee_id']}"
                        )
                        continue

                    # --------------------------------
                    # Get Location object
                    # --------------------------------
                    location_value = row["location"].strip()

                    try:
                        location_obj = Location.objects.get(code=location_value)
                    except Location.DoesNotExist:
                        messages.error(
                            request, f"❌ Location not found: {location_value}"
                        )
                        return redirect("..")

                    # --------------------------------
                    # Create new user
                    # --------------------------------
                    CustomUser.objects.create(
                        employee_id=row["employee_id"],
                        username=row["username"],
                        email=row.get("email", ""),
                        role=row["role"],
                        location=location_obj,
                        password=make_password(row["password"]),
                        is_active=True,   # 👌 Active
                        is_staff=True,    # 👌 Staff status ON
                    )

                    created_count += 1

                # --------------------------------
                # Final messages
                # --------------------------------
                messages.success(
                    request,
                    f"Upload complete! Created: {created_count}, Skipped: {skipped_count}",
                )
                return redirect("..")

        else:
            form = UserBulkUploadForm()

        return render(request, "bulk_upload.html", {"form": form})





# =====================================================================
# ✅ Ticket Admin
# =====================================================================

from django.contrib import admin
from .models import Ticket


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):

    # -------------------------------------------------------------
    # SHOW COLUMNS IN ADMIN TABLE
    # -------------------------------------------------------------
    list_display = (
        "ticket_number",
        "employee_code",
        "employee",
        "name",
        "location",
        "concern_category",
        "concern",
        "assigned_owner",
        "reassigned_to",
        "status",
        "created_at",
    )

    # -------------------------------------------------------------
    # FILTERS ON RIGHT SIDE
    # -------------------------------------------------------------
    list_filter = (
        "status",
        "location",
        "concern_category",
        "assigned_owner",
        "reassigned_to",
        "created_at",
    )

    # -------------------------------------------------------------
    # SEARCH BAR FIELDS
    # -------------------------------------------------------------
    search_fields = (
        "ticket_number",
        "employee_code",
        "name",
        "employee__username",
        "employee__employee_id",
        "location__name",
        "concern",
    )

    # -------------------------------------------------------------
    # READ ONLY FIELDS
    # (Auto-generated fields should NOT be editable)
    # -------------------------------------------------------------
    readonly_fields = (
        "ticket_number",
        "created_at",
        "updated_at",
    )

    # -------------------------------------------------------------
    # ORDERING
    # -------------------------------------------------------------
    ordering = ("-created_at",)




# =====================================================================
# ✅ Staff Performance Admin - with Bulk Upload
# =====================================================================

class BulkUploadForm(forms.Form):
    file = forms.FileField(label="Upload CSV/Excel File")


@admin.register(StaffPerformance)
class StaffPerformanceAdmin(admin.ModelAdmin):
    list_display = ("employee", "month", "rating", "earning_total", "deduction_total")
    search_fields = ("employee__username", "month")
    list_filter = ("month", "employee__role")
    ordering = ("-month",)
    change_list_template = "staff_performance_changelist.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("bulk-upload/", self.admin_site.admin_view(self.bulk_upload_view),
                 name="staffperformance_bulk_upload"),
        ]
        return custom_urls + urls

    def bulk_upload_view(self, request):
        if request.method == "POST":
            form = BulkUploadForm(request.POST, request.FILES)
            if form.is_valid():
                file = request.FILES["file"]

                try:
                    df = (
                        pd.read_csv(file)
                        if file.name.endswith(".csv")
                        else pd.read_excel(file)
                    )
                except Exception as e:
                    self.message_user(request, f"❌ Error reading file: {e}", level=messages.ERROR)
                    return redirect("..")

                required_columns = [
                    "employee_id", "month", "bau_status", "rating", "incentive",
                    "ot_sacoff_amount", "referral_bonus", "dsat_deduction",
                    "wrong_order_deduction", "mrd_deduction_staff",
                    "other_deduction", "earning_total", "deduction_total"
                ]

                missing = [c for c in required_columns if c not in df.columns]
                if missing:
                    self.message_user(request, f"❌ Missing columns: {', '.join(missing)}",
                                      level=messages.ERROR)
                    return redirect("..")

                created_count = 0

                for _, row in df.iterrows():
                    try:
                        user = CustomUser.objects.get(employee_id=row["employee_id"])
                        StaffPerformance.objects.update_or_create(
                            employee=user,
                            month=row["month"],
                            defaults={
                                "bau_status": row["bau_status"],
                                "rating": row["rating"],
                                "incentive": row["incentive"],
                                "ot_sacoff_amount": row["ot_sacoff_amount"],
                                "referral_bonus": row["referral_bonus"],
                                "dsat_deduction": row["dsat_deduction"],
                                "wrong_order_deduction": row["wrong_order_deduction"],
                                "mrd_deduction_staff": row["mrd_deduction_staff"],
                                "other_deduction": row["other_deduction"],
                                "earning_total": row["earning_total"],
                                "deduction_total": row["deduction_total"],
                            },
                        )
                        created_count += 1
                    except CustomUser.DoesNotExist:
                        continue

                self.message_user(request, f"✅ Uploaded {created_count} records successfully.",
                                  level=messages.SUCCESS)
                return redirect("..")

        else:
            form = BulkUploadForm()

        return render(request, "bulk_upload_form.html",
                      {"form": form, "title": "Bulk Upload Staff Performance", "opts": self.model._meta})


# =====================================================================
# ✅ Kitchen Log Admin
# =====================================================================

@admin.register(KitchenLog)
class KitchenLogAdmin(admin.ModelAdmin):
    list_display = ("emp_id", "emp_name", "location", "category", "created_at")
    search_fields = ("emp_id", "emp_name", "category")
    list_filter = ("location", "category", "created_at")
    ordering = ("-created_at",)


# =====================================================================
# ✅ Location Admin
# =====================================================================

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")
    ordering = ("code",)


# =====================================================================
# ✅ Cluster Manager Profile Admin
# =====================================================================

class ClusterManagerProfileInline(admin.TabularInline):
    model = ClusterManagerProfile.locations.through
    extra = 1


@admin.register(ClusterManagerProfile)
class ClusterManagerProfileAdmin(admin.ModelAdmin):
    list_display = ("user",)
    inlines = [ClusterManagerProfileInline]
    filter_horizontal = ("locations",)
    search_fields = ("user__username",)


# =====================================================================
# ✅ Salary Slip Admin (Upload Excel/CSV)
# =====================================================================

class UploadFileForm(forms.Form):
    file = forms.FileField(label="Select Excel or CSV file")


@admin.register(SalarySlip)
class SalarySlipAdmin(admin.ModelAdmin):
    list_display = ('employee', 'month', 'year', 'net_pay', 'created_at')
    search_fields = ('employee__username', 'month', 'year')
    list_filter = ('year', 'month')
    change_list_template = "salaryslip_changelist.html"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('upload-salary/', self.admin_site.admin_view(self.upload_salary), name='upload_salary'),
        ]
        return custom + urls

    def upload_salary(self, request):
        if request.method == "POST":
            form = UploadFileForm(request.POST, request.FILES)
            if form.is_valid():
                file = form.cleaned_data['file']

                try:
                    df = pd.read_excel(file) if file.name.endswith(('.xls', '.xlsx')) else pd.read_csv(file)
                except Exception as e:
                    messages.error(request, f"❌ Error reading file: {e}")
                    return redirect("..")

                required_columns = [
                    'employee_id', 'month', 'year', 'present_days', 'lop_days',
                    'sac_off_ot', 'rating_incentive', 'km_mrd_incentive', 'arrears',
                    'referral_bonus', 'mrd_deduction', 'km_mrd_deduction',
                    'photo_deduction', 'missing_item_deduction', 'net_pay'
                ]

                missing_cols = [c for c in required_columns if c not in df.columns]
                if missing_cols:
                    messages.error(request, f"❌ Missing: {', '.join(missing_cols)}")
                    return redirect("..")

                created, skipped = 0, []

                for _, row in df.iterrows():
                    emp_id = str(row['employee_id']).strip()
                    user = User.objects.filter(employee_id=emp_id).first()

                    if not user:
                        skipped.append(emp_id)
                        continue

                    SalarySlip.objects.create(
                        employee=user,
                        month=row['month'],
                        year=row['year'],
                        present_days=row.get('present_days', 0) or 0,
                        lop_days=row.get('lop_days', 0) or 0,
                        sac_off_ot=row.get('sac_off_ot', 0) or 0,
                        rating_incentive=row.get('rating_incentive', 0) or 0,
                        km_mrd_incentive=row.get('km_mrd_incentive', 0) or 0,
                        arrears=row.get('arrears', 0) or 0,
                        referral_bonus=row.get('referral_bonus', 0) or 0,
                        mrd_deduction=row.get('mrd_deduction', 0) or 0,
                        km_mrd_deduction=row.get('km_mrd_deduction', 0) or 0,
                        photo_deduction=row.get('photo_deduction', 0) or 0,
                        missing_item_deduction=row.get('missing_item_deduction', 0) or 0,
                        net_pay=row.get('net_pay', 0) or 0,
                    )
                    created += 1

                msg = f"✅ {created} salary slips uploaded."
                if skipped:
                    msg += f" ⚠️ Skipped {len(skipped)} invalid employee IDs: {', '.join(skipped)}"

                messages.success(request, msg)
                return redirect("..")

        return render(request, 'upload_salary.html', {"form": UploadFileForm(), "title": "Upload Salary Slips"})


# =====================================================================
# ✅ Order Photo Admin
# =====================================================================

@admin.register(OrderPhoto)
class OrderPhotoAdmin(admin.ModelAdmin):
    list_display = ("order_id", "uploaded_by", "location", "uploaded_at")
    search_fields = ("order_id", "uploaded_by__username")
    list_filter = ("location", "uploaded_at")
    readonly_fields = ("image_preview",)

    def image_preview(self, obj):
        if obj.photo:
            return format_html(
                '<img src="{}" style="max-width:300px;border-radius:6px;">', obj.photo.url
            )
        return "No Image"

    image_preview.short_description = "Photo Preview"


