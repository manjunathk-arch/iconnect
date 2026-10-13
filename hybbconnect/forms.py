from datetime import datetime

from django import forms
from .models import (
    Location, Ticket, KitchenLog, StaffPerformance, QualityFeedback,
    CustomUser, OrderPhoto, StaffRoster
)


from django import forms
from .models import Ticket, Location

class KitchenPlayerForm(forms.ModelForm):

    CONCERN_CHOICES = [
        ('', '--- Select Concern ---'),
        ('Salary is incorrect', 'Salary is incorrect'),
        ('Salary Not Received', 'Salary Not Received'),
        ('Accommodation Issue', 'Accommodation Issue'),
        ('Request - Salary Advance', 'Request - Salary Advance'),
        ('PF Related Issues', 'PF Related Issues'),
        ('Shift Manager / Kitchen Manager Issue', 'Shift Manager / Kitchen Manager Issue'),
        ('Request a Call Back', 'Request a Call Back'),
        ('Co-Worker Issue', 'Co-Worker Issue'),
        ('Salary Message not received', 'Salary Message not received'),
        
    ]

    concern = forms.ChoiceField(
        choices=CONCERN_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Ticket
        fields = ['concern', 'description']  # ⬅️ notice: location REMOVED
        widgets = {
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        ticket = super().save(commit=False)

        # Assign staff details
        ticket.employee = self.user
        ticket.employee_code = self.user.employee_id
        ticket.name = self.user.username
        ticket.location = self.user.location  # ALWAYS a Location instance

        if commit:
            ticket.save()

        return ticket




# ======================================================
# 2️⃣ KITCHEN MANAGER → STAFF LOG
# ======================================================

class KitchenLogForm(forms.ModelForm):
    class Meta:
        model = KitchenLog
        fields = ["staff", "category", "remarks", "log_date"]
        widgets = {
            "log_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        self.fields["staff"].queryset = CustomUser.objects.none()

        if user and user.role == "kitchen_manager" and user.location:
            # KM sees only staff in their location
            self.fields["staff"].queryset = CustomUser.objects.filter(
                role="kitchen_staff",
                location=user.location
            )

        elif user and user.role == "cluster_manager" and hasattr(user, "cluster_manager_profile"):
            # CM sees kitchen staff and kitchen managers from assigned locations
            assigned_locations = user.cluster_manager_profile.locations.all()
            self.fields["staff"].queryset = CustomUser.objects.filter(
                role__in=["kitchen_staff", "kitchen_manager"],
                location__in=assigned_locations
            ).order_by("location__code", "role", "username")

        self.fields["staff"].empty_label = "Select team member"

# ======================================================
# 3️⃣ QUALITY FEEDBACK FORM
# ======================================================

class QualityFeedbackForm(forms.ModelForm):
    class Meta:
        model = QualityFeedback
        fields = ["staff", "category", "remarks", "feedback_date"]
        widgets = {
            "feedback_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-control"
                }
            ),
            "remarks": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        self.fields["staff"].queryset = CustomUser.objects.none()

        # Kitchen Manager → Only staff in own location
        if user and user.role == "kitchen_manager" and user.location:
            self.fields["staff"].queryset = CustomUser.objects.filter(
                role="kitchen_staff",
                location=user.location
            )

        # Cluster Manager → Staff in assigned locations
        elif (
            user
            and user.role == "cluster_manager"
            and hasattr(user, "cluster_manager_profile")
        ):
            assigned_locations = user.cluster_manager_profile.locations.all()

            self.fields["staff"].queryset = CustomUser.objects.filter(
                role="kitchen_staff",
                location__in=assigned_locations
            )

        self.fields["staff"].empty_label = "Select Staff Member"

# ======================================================
# 3️⃣ ICONNECT FORM – KITCHEN MANAGER / HR
# ======================================================

class IConnectForm(forms.ModelForm):
    CONCERN_CATEGORY_CHOICES = [
        ("Training Related", "Training Related"),
        ("HR Related", "HR Related"),
        ("MIS Related", "MIS Related"),
    ]

    concern_category = forms.ChoiceField(
        choices=CONCERN_CATEGORY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True
    )

    class Meta:
        model = Ticket
        fields = ["employee_code", "name", "concern_category", "concern", "description", "location"]
        widgets = {
            "employee_code": forms.TextInput(attrs={"class": "form-control"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "concern": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "location": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # default location choices
        self.fields["location"].queryset = Location.objects.all()

        # Restrict location for Kitchen Manager
        if user and user.role == "kitchen_manager":
            self.fields["location"].queryset = Location.objects.filter(id=user.location.id)

        # 🔥 If employee_code exists in POST → auto-fill location and disable field
        if "employee_code" in self.data:
            emp_code = self.data.get("employee_code")

            try:
                staff = CustomUser.objects.get(employee_id=emp_code, role="kitchen_staff")


                # show only this location
                self.fields["location"].queryset = Location.objects.filter(id=staff.location.id)

                # preset selected location
                self.fields["location"].initial = staff.location.id

                # ❌ Disable the dropdown (make read-only)
                self.fields["location"].widget.attrs["disabled"] = True
                self.fields["location"].disabled = True

            except CustomUser.DoesNotExist:
                pass



# ======================================================
# 4️⃣ STAFF PERFORMANCE FORM
# ======================================================

class StaffPerformanceForm(forms.ModelForm):
    class Meta:
        model = StaffPerformance
        fields = [
            "employee", "month", "bau_status", "rating",
            "incentive", "ot_sacoff_amount", "referral_bonus",
            "dsat_deduction", "wrong_order_deduction",
            "mrd_deduction_staff", "other_deduction",
            "earning_total", "deduction_total",
        ]
        widgets = {
            field: (
                forms.NumberInput(attrs={"class": "form-control"})
                if "amount" in field or "deduction" in field or "total" in field
                else forms.TextInput(attrs={"class": "form-control"})
            )
            for field in fields
        }


# ======================================================
# 5️⃣ ORDER PHOTO FORM
# ======================================================

class OrderPhotoForm(forms.ModelForm):

    class Meta:
        model = OrderPhoto
        fields = ["order_id", "photo", "location"]
        widgets = {
            "order_id": forms.TextInput(attrs={"class": "form-control"}),
            "photo": forms.ClearableFileInput(attrs={
                "class": "form-control",
                "accept": "image/*",
                "capture": "environment"
            }),
            "location": forms.Select(attrs={"class": "form-control"})
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user")
        super().__init__(*args, **kwargs)

        # Kitchen Staff → hide location
        if user.role == "kitchen_staff" and hasattr(user, "kitchenstaff_profile"):
            self.fields["location"].initial = user.kitchenstaff_profile.location
            self.fields["location"].widget = forms.HiddenInput()

        # Kitchen Manager → hide location
        elif user.role == "kitchen_manager" and hasattr(user, "kitchen_manager_profile"):
            self.fields["location"].initial = user.kitchen_manager_profile.location
            self.fields["location"].widget = forms.HiddenInput()

        # Cluster Manager → limit to assigned locations
        elif user.role == "cluster_manager" and hasattr(user, "cluster_manager_profile"):
            self.fields["location"].queryset = (
                user.cluster_manager_profile.locations.all()
            )

        else:
            # Safety fallback
            self.fields.pop("location")

# forms.py
from django import forms
from .models import StaffTimeUpdate, User

class StaffTimeUpdateForm(forms.ModelForm):
    class Meta:
        model = StaffTimeUpdate
        fields = ["staff", "update_type", "ot_hours", "ot_date", "sac_off_date", "remarks"]

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user")
        super().__init__(*args, **kwargs)

        # Only show Kitchen Managers + Kitchen Staff
        self.fields['staff'].queryset = User.objects.filter(role__in=["kitchen_manager", "kitchen_staff"])

        # Initially hide conditional fields
        self.fields["ot_hours"].required = False
        self.fields["ot_date"].required = False
        self.fields["sac_off_date"].required = False

    def clean(self):
        cleaned = super().clean()
        update_type = cleaned.get("update_type")

        if update_type == "TO":
            if not cleaned.get("ot_hours") or not cleaned.get("ot_date"):
                raise forms.DateInput("OT Hours and OT Date are required for TO.")
            cleaned["sac_off_date"] = None

        if update_type == "SAC_OFF":
            if not cleaned.get("sac_off_date"):
                raise forms.DateInput("SAC OFF date is required.")
            cleaned["ot_hours"] = None
            cleaned["ot_date"] = None

        return cleaned


from django import forms

class UserBulkUploadForm(forms.Form):
    file = forms.FileField(label="Upload CSV File")


class UserInactiveBulkUploadForm(forms.Form):
    file = forms.FileField(label="Upload CSV File")


class StaffRosterForm(forms.ModelForm):
    SHIFT_DEFAULTS = [
        ("BS-1|09:00", "BS-1 - 09:00 AM"),
        ("BS-2|10:00", "BS-2 - 10:00 AM"),
        ("BS-3|12:00", "BS-3 - 12:00 PM"),
        ("BS-4|11:00", "BS-4 - 11:00 AM"),
        ("BS-5|09:00", "BS-5 - 09:00 AM"),
        ("BS-6|12:00", "BS-6 - 12:00 PM"),
        ("BS-7|08:00", "BS-7 - 08:00 AM"),
        ("BS-8|08:00", "BS-8 - 08:00 AM"),
        ("BS-9|12:00", "BS-9 - 12:00 PM"),
        ("ST-1|08:00", "ST-1 - 08:00 AM"),
        ("ST-1|01:00", "ST-1 - 01:00 AM"),
        ("ST-2|09:00", "ST-2 - 09:00 AM"),
        ("ST-3|14:00", "ST-3 - 02:00 PM"),
        ("ST-4|16:00", "ST-4 - 04:00 PM"),
        ("ST-5|10:00", "ST-5 - 10:00 AM"),
        ("ST-6|13:00", "ST-6 - 01:00 PM"),
    ]

    shift_template = forms.ChoiceField(
        choices=[("", "Select shift code")] + SHIFT_DEFAULTS,
        required=False,
        label="Shift code",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    shift_code = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = StaffRoster
        fields = ["location", "staff", "roster_date", "shift_type", "shift_code", "login_time"]
        widgets = {
            "location": forms.Select(attrs={"class": "form-select"}),
            "staff": forms.Select(attrs={"class": "form-select"}),
            "roster_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "shift_type": forms.Select(attrs={"class": "form-select"}),
            "login_time": forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        self.authorized_locations = kwargs.pop("authorized_locations", Location.objects.none())
        super().__init__(*args, **kwargs)

        self.fields["location"].queryset = self.authorized_locations
        self.fields["staff"].queryset = CustomUser.objects.none()

        location_id = self.data.get("location") if self.data else None
        if location_id:
            self.fields["staff"].queryset = CustomUser.objects.filter(
                role="kitchen_staff",
                is_active=True,
                location_id=location_id,
                location__in=self.authorized_locations,
            ).order_by("employee_id", "username")
        elif self.instance.pk:
            self.fields["staff"].queryset = CustomUser.objects.filter(
                role="kitchen_staff",
                location=self.instance.location,
            ).order_by("employee_id", "username")
            if self.instance.shift_type != StaffRoster.WEEKLY_OFF:
                self.fields["shift_template"].initial = (
                    f"{self.instance.shift_code}|{self.instance.login_time.strftime('%H:%M')}"
                    if self.instance.login_time
                    else ""
                )
        else:
            self.fields["staff"].queryset = CustomUser.objects.filter(
                role="kitchen_staff",
                is_active=True,
                location__in=self.authorized_locations,
            ).order_by("location__code", "employee_id", "username")

    def clean(self):
        cleaned = super().clean()
        location = cleaned.get("location")
        staff = cleaned.get("staff")
        shift_type = cleaned.get("shift_type")
        shift_template = cleaned.get("shift_template")
        login_time = cleaned.get("login_time")

        if location and location not in self.authorized_locations:
            raise forms.ValidationError("You are not authorized to manage this outlet.")

        if staff and location and staff.location_id != location.id:
            raise forms.ValidationError("Selected staff member does not belong to this outlet.")

        if shift_type == StaffRoster.WEEKLY_OFF:
            cleaned["login_time"] = None
            cleaned["shift_code"] = "WO"
            return cleaned

        if not shift_template:
            self.add_error("shift_template", "Select a shift code.")
            return cleaned

        shift_code, default_time = shift_template.split("|", 1)
        cleaned["shift_code"] = shift_code
        if not login_time:
            cleaned["login_time"] = datetime.strptime(default_time, "%H:%M").time()

        return cleaned

    def save(self, commit=True):
        roster = super().save(commit=False)
        roster.shift_code = self.cleaned_data["shift_code"]
        roster.login_time = self.cleaned_data["login_time"]
        if self.user and not roster.created_by_id:
            roster.created_by = self.user
        if roster.pk and roster.is_published:
            roster.is_published = False
            roster.published_at = None
        if commit:
            roster.save()
        return roster



# ======================================================
# QUALITY FEEDBACK BULK UPLOAD
# ======================================================

class QualityFeedbackBulkUploadForm(forms.Form):
    file = forms.FileField(
        label="Upload Quality Feedback CSV",
        widget=forms.FileInput(
            attrs={
                "class": "form-control",
                "accept": ".csv"
            }
        )
    )
