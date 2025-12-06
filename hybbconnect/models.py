# models.py — HybbConnect

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from django.contrib.auth import get_user_model


# ---------------------------------------------------------
# 1️⃣ LOCATION MODEL
# ---------------------------------------------------------
class Location(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.code} - {self.name}"


# ---------------------------------------------------------
# 2️⃣ CORRECT CUSTOM USER MODEL  (ONLY ONE)
# ---------------------------------------------------------
class CustomUser(AbstractUser):
    employee_id = models.CharField(max_length=20, unique=True)
    role = models.CharField(
        max_length=20,
        choices=[
            ('kitchen_staff', 'Kitchen Staff'),
            ('kitchen_manager', 'Kitchen Manager'),
            ('cluster_manager', 'Cluster Manager'),
            ('owner', 'Owner'),
            ('admin', 'Admin'),
        ]
    )
    location = models.ForeignKey('Location', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.username or self.email or self.employee_id


# ---------------------------------------------------------
# 3️⃣ TICKET MODEL
# ---------------------------------------------------------
class Ticket(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Assigned', 'Assigned'),
        ('Reassigned', 'Reassigned'),
        ('In Progress', 'In Progress'),
        ('Resolved', 'Resolved'),
        ('Closed', 'Closed'),
        ('Rejected', 'Rejected'),
    ]

    ticket_number = models.CharField(max_length=20, unique=True, blank=True, null=True)
    employee = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="tickets")
    employee_code = models.CharField(max_length=20, blank=True, null=True)
    name = models.CharField(max_length=100, blank=True, null=True)

    location = models.ForeignKey("Location", on_delete=models.SET_NULL, null=True, blank=True)

    concern = models.CharField(max_length=200)
    concern_category = models.CharField(max_length=200, blank=True, null=True)
    description = models.TextField()
    closing_remarks = models.TextField(null=True, blank=True)
    owner_closer_remarks = models.TextField(blank=True, null=True)
    cluster_closer_remarks = models.TextField(blank=True, null=True)

    


    assigned_owner = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="tickets_owned"
    )

    reassigned_to = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets_reassigned'
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Pending")
    mobile_number = models.CharField(max_length=15, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    staff_confirmed = models.BooleanField(default=False)
    staff_confirmed_at = models.DateTimeField(null=True, blank=True)


    def __str__(self):
        return f"Ticket #{self.ticket_number}"

    # ⭐ AUTO-GENERATE TICKET NUMBER HERE
    def save(self, *args, **kwargs):
        if not self.ticket_number:
            last = Ticket.objects.order_by('-id').first()

            if last and last.ticket_number and last.ticket_number.startswith("TIK-"):
                last_num = int(last.ticket_number.split("-")[1])
                new_num = last_num + 1
            else:
                new_num = 1

            self.ticket_number = f"TIK-{new_num:05d}"

        super().save(*args, **kwargs)




# ---------------------------------------------------------
# 4️⃣ STAFF PERFORMANCE
# ---------------------------------------------------------
class StaffPerformance(models.Model):
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    month = models.CharField(max_length=20)
    bau_status = models.CharField(max_length=50)

    rating = models.DecimalField(max_digits=4, decimal_places=2)
    incentive = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    ot_sacoff_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    referral_bonus = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    dsat_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    wrong_order_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    mrd_deduction_staff = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    other_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    earning_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deduction_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.employee.username} - {self.month}"


# ---------------------------------------------------------
# 5️⃣ KITCHEN LOG
# ---------------------------------------------------------
class KitchenLog(models.Model):
    CATEGORY_CHOICES = [
        ("Reporting Issue", "Reporting Issue"),
        ("Kot Process", "Kot Process"),
        ("Behaviour Issue", "Behaviour Issue"),
        ("Grooming", "Grooming"),
        ("Assigned Task Not Completed", "Assigned Task Not Completed"),
    ]

    staff = models.ForeignKey(
        "CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_logs",
        limit_choices_to={"role": "kitchen_staff"}
    )

    emp_id = models.CharField(max_length=50, blank=True, null=True)
    emp_name = models.CharField(max_length=100, blank=True, null=True)
    location = models.CharField(max_length=50, default="UNKNOWN")

    category = models.CharField(max_length=200, choices=CATEGORY_CHOICES)
    remarks = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    log_date = models.DateField(default=timezone.now, verbose_name="Log Date")

    is_acknowledged = models.BooleanField(default=False)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        if self.staff:
            return f"{self.staff.username} - {self.category}"
        return f"{self.emp_name or 'Unknown'} ({self.emp_id or 'N/A'}) - {self.category}"


# ---------------------------------------------------------
# 6️⃣ CLUSTER MANAGER PROFILE
# ---------------------------------------------------------
User = get_user_model()

class ClusterManagerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="cluster_manager_profile")
    locations = models.ManyToManyField(Location, related_name="cluster_managers")

    def __str__(self):
        return self.user.username


# ---------------------------------------------------------
# 7️⃣ SALARY SLIP
# ---------------------------------------------------------
class SalarySlip(models.Model):
    employee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='salary_slips')

    month = models.CharField(max_length=20)
    year = models.IntegerField()

    present_days = models.IntegerField(null=True, blank=True)
    lop_days = models.IntegerField(null=True, blank=True)

    sac_off_ot = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    rating_incentive = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    km_mrd_incentive = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    arrears = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    referral_bonus = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    mrd_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    km_mrd_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    photo_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    missing_item_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    net_pay = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.employee.username} - {self.month}-{self.year}"


# ---------------------------------------------------------
# 8️⃣ ORDER PHOTO
# ---------------------------------------------------------
class OrderPhoto(models.Model):
    order_id = models.CharField(max_length=50)
    photo = models.ImageField(upload_to="order_photos/", null=True, blank=True)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True
    )

    uploaded_at = models.DateTimeField(default=timezone.now)

    location = models.ForeignKey("Location", on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.order_id} - {self.uploaded_by.username if self.uploaded_by else 'Unknown'}"


class Notification(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    message = models.TextField()
    link = models.CharField(max_length=255, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']



# models.py
class StaffTimeUpdate(models.Model):
    TYPE_CHOICES = (
        ("TO", "Time Off (TO)"),
        ("SAC_OFF", "SAC Off"),
    )

    staff = models.ForeignKey(User, on_delete=models.CASCADE, related_name="time_updates")
    update_type = models.CharField(max_length=20, choices=TYPE_CHOICES)

    # TO fields
    ot_hours = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    ot_date = models.DateField(null=True, blank=True)

    # SAC OFF fields
    sac_off_date = models.DateField(null=True, blank=True)

    remarks = models.TextField()

    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="updated_time_entries")
    updated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.staff} - {self.update_type}"
