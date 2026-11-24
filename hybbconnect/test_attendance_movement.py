from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (AttendanceAuditLog, ClusterManagerProfile, DailyAttendance,
                     Location, Notification, StaffMovement)


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class AttendanceMovementTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.source = Location.objects.create(code="SRC", name="Source")
        self.target = Location.objects.create(code="DST", name="Destination")
        self.km = User.objects.create_user(username="km", password="pw", employee_id="KM1", role="kitchen_manager", location=self.source)
        self.receiver = User.objects.create_user(username="receiver", password="pw", employee_id="KM2", role="kitchen_manager", location=self.target)
        self.unrelated_location = Location.objects.create(code="OTHER", name="Unrelated")
        self.unrelated = User.objects.create_user(username="other", password="pw", employee_id="KM3", role="kitchen_manager", location=self.unrelated_location)
        self.staff = User.objects.create_user(username="staff", password="pw", employee_id="S1", role="kitchen_staff", location=self.source)

    def test_manager_saves_attendance_with_historical_location_and_audit(self):
        self.client.force_login(self.km)
        today = timezone.localdate()
        response = self.client.post(reverse("daily_attendance"), {"date": today.isoformat(), "location": self.source.pk, f"attendance_{self.staff.pk}": "Present"})
        self.assertEqual(response.status_code, 302)
        record = DailyAttendance.objects.get(employee=self.staff, attendance_date=today)
        self.assertEqual(record.location, self.source)
        self.assertEqual(record.attendance_type, "Present")
        self.assertEqual(AttendanceAuditLog.objects.filter(attendance=record).count(), 1)

    def test_daily_attendance_page_loads_for_kitchen_manager(self):
        self.client.force_login(self.km)
        response = self.client.get(reverse("daily_attendance"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Daily Attendance")

    def test_duplicate_attendance_is_updated_not_duplicated(self):
        self.client.force_login(self.km)
        today = timezone.localdate()
        url = reverse("daily_attendance")
        for kind in ("Present", "Half Day"):
            self.client.post(url, {"date": today.isoformat(), "location": self.source.pk, f"attendance_{self.staff.pk}": kind})
        self.assertEqual(DailyAttendance.objects.filter(employee=self.staff, attendance_date=today).count(), 1)
        self.assertEqual(DailyAttendance.objects.get(employee=self.staff, attendance_date=today).attendance_type, "Half Day")

    def test_request_notifies_only_destination_and_acceptance_transfers_employee(self):
        self.client.force_login(self.km)
        effective = timezone.localdate()
        response = self.client.post(reverse("staff_movement"), {"action": "request", "employee": self.staff.pk, "from_location": self.source.pk, "to_location": self.target.pk, "effective_date": effective.isoformat(), "reason": "Staff shortage"})
        self.assertEqual(response.status_code, 302)
        movement = StaffMovement.objects.get(employee=self.staff)
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.location, self.source)
        self.assertTrue(Notification.objects.filter(user=self.receiver, notification_type="staff_movement").exists())
        self.assertFalse(Notification.objects.filter(user=self.unrelated, notification_type="staff_movement").exists())

        self.client.force_login(self.receiver)
        response = self.client.post(reverse("staff_movement"), {"action": "accept", "movement": movement.pk})
        self.assertEqual(response.status_code, 302)
        self.staff.refresh_from_db()
        movement.refresh_from_db()
        self.assertEqual(self.staff.location, self.target)
        self.assertEqual(movement.status, "COMPLETED")

    def test_cluster_manager_cannot_move_outside_allocated_scope(self):
        User = get_user_model()
        cluster = User.objects.create_user(username="cluster", password="pw", employee_id="CM1", role="cluster_manager")
        profile = ClusterManagerProfile.objects.create(user=cluster)
        profile.locations.add(self.source)
        self.client.force_login(cluster)
        response = self.client.post(reverse("staff_movement"), {"action": "request", "employee": self.staff.pk, "from_location": self.source.pk, "to_location": self.target.pk, "effective_date": (timezone.localdate() + timedelta(days=1)).isoformat(), "reason": "Business requirement"})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(StaffMovement.objects.exists())
