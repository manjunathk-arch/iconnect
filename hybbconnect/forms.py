from django import forms
from .models import (
    Location, Ticket, KitchenLog, StaffPerformance,
    CustomUser, OrderPhoto
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
            # CM sees all staff from assigned locations
            assigned_locations = user.cluster_manager_profile.locations.all()
            self.fields["staff"].queryset = CustomUser.objects.filter(
                role="kitchen_staff",
                location__in=assigned_locations
            )

        self.fields["staff"].empty_label = "Select staff member"


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
