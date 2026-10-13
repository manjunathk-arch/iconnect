from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test import override_settings
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from datetime import time, timedelta

from .admin import CustomUserAdmin
from .models import ClusterManagerProfile, Location, StaffRoster


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class CustomUserAdminActionTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.admin_user = self.user_model.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password",
            employee_id="EMP-ADMIN",
            role="admin",
        )

    def test_mark_selected_users_inactive_admin_action(self):
        active_user = self.user_model.objects.create_user(
            username="active-user",
            email="active@example.com",
            password="password",
            employee_id="EMP-001",
            role="kitchen_staff",
            is_active=True,
        )
        already_inactive_user = self.user_model.objects.create_user(
            username="inactive-user",
            email="inactive@example.com",
            password="password",
            employee_id="EMP-002",
            role="kitchen_staff",
            is_active=False,
        )

        request = RequestFactory().post("/")
        request.user = self.admin_user
        request.session = {}
        request._messages = FallbackStorage(request)

        user_admin = CustomUserAdmin(self.user_model, AdminSite())
        user_admin.mark_users_inactive(
            request,
            self.user_model.objects.filter(
                pk__in=[active_user.pk, already_inactive_user.pk]
            ),
        )

        active_user.refresh_from_db()
        already_inactive_user.refresh_from_db()
        self.assertFalse(active_user.is_active)
        self.assertFalse(already_inactive_user.is_active)

    def test_bulk_inactivate_csv_upload_marks_matching_users_inactive(self):
        employee_match = self.user_model.objects.create_user(
            username="employee-match",
            email="employee@example.com",
            password="password",
            employee_id="EMP-101",
            role="kitchen_staff",
            is_active=True,
        )
        username_match = self.user_model.objects.create_user(
            username="username-match",
            email="username@example.com",
            password="password",
            employee_id="EMP-102",
            role="kitchen_staff",
            is_active=True,
        )
        untouched_user = self.user_model.objects.create_user(
            username="untouched",
            email="untouched@example.com",
            password="password",
            employee_id="EMP-103",
            role="kitchen_staff",
            is_active=True,
        )

        upload = SimpleUploadedFile(
            "inactive_users.csv",
            b"employee_id,username\nEMP-101,\n,username-match\n",
            content_type="text/csv",
        )

        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse("admin:customuser_bulk_inactivate"),
            {"file": upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        employee_match.refresh_from_db()
        username_match.refresh_from_db()
        untouched_user.refresh_from_db()
        self.assertFalse(employee_match.is_active)
        self.assertFalse(username_match.is_active)
        self.assertTrue(untouched_user.is_active)


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class StaffRosterTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.loc1 = Location.objects.create(code="L1", name="Outlet One")
        self.loc2 = Location.objects.create(code="L2", name="Outlet Two")
        self.staff1 = self.user_model.objects.create_user(
            username="staff-one",
            password="password",
            employee_id="S001",
            role="kitchen_staff",
            location=self.loc1,
        )
        self.staff2 = self.user_model.objects.create_user(
            username="staff-two",
            password="password",
            employee_id="S002",
            role="kitchen_staff",
            location=self.loc2,
        )
        self.manager = self.user_model.objects.create_user(
            username="manager-one",
            password="password",
            employee_id="M001",
            role="kitchen_manager",
            location=self.loc1,
        )
        self.cluster = self.user_model.objects.create_user(
            username="cluster-one",
            password="password",
            employee_id="C001",
            role="cluster_manager",
        )
        self.cluster_profile = ClusterManagerProfile.objects.create(user=self.cluster)
        self.cluster_profile.locations.add(self.loc1)
        self.admin = self.user_model.objects.create_user(
            username="admin-user",
            password="password",
            employee_id="A001",
            role="admin",
            is_staff=True,
        )
        self.week_start = timezone.localdate() - timedelta(days=timezone.localdate().weekday())

    def roster_post(self, staff, location, roster_date=None):
        return {
            "location": location.id,
            "staff": staff.id,
            "roster_date": roster_date or self.week_start,
            "shift_type": StaffRoster.BREAK_SHIFT,
            "shift_template": "BS-1|09:00",
            "login_time": "09:00",
        }

    def test_kitchen_manager_can_create_roster_for_own_outlet_staff(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("create_roster_assignment"), self.roster_post(self.staff1, self.loc1))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(StaffRoster.objects.filter(staff=self.staff1, location=self.loc1).exists())

    def test_kitchen_manager_cannot_create_roster_for_other_outlet(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("create_roster_assignment"), self.roster_post(self.staff2, self.loc2))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(StaffRoster.objects.filter(staff=self.staff2).exists())

    def test_cluster_manager_can_manage_assigned_outlet_only(self):
        self.client.force_login(self.cluster)
        allowed_response = self.client.post(reverse("create_roster_assignment"), self.roster_post(self.staff1, self.loc1))
        blocked_response = self.client.post(reverse("create_roster_assignment"), self.roster_post(self.staff2, self.loc2))

        self.assertEqual(allowed_response.status_code, 302)
        self.assertEqual(blocked_response.status_code, 302)
        self.assertTrue(StaffRoster.objects.filter(staff=self.staff1).exists())
        self.assertFalse(StaffRoster.objects.filter(staff=self.staff2).exists())

    def test_staff_sees_only_published_roster(self):
        StaffRoster.objects.create(
            staff=self.staff1,
            location=self.loc1,
            roster_date=self.week_start,
            shift_type=StaffRoster.BREAK_SHIFT,
            shift_code="BS-1",
            login_time=time(9, 0),
            created_by=self.manager,
            is_published=True,
            published_at=timezone.now(),
        )
        StaffRoster.objects.create(
            staff=self.staff2,
            location=self.loc2,
            roster_date=self.week_start,
            shift_type=StaffRoster.STAIR_SHIFT,
            shift_code="ST-2",
            login_time=time(10, 0),
            created_by=self.admin,
            is_published=True,
            published_at=timezone.now(),
        )

        self.client.force_login(self.staff1)
        response = self.client.get(reverse("staff_weekly_roster"))

        self.assertContains(response, "BS-1")
        self.assertNotContains(response, "ST-2")

    def test_staff_cannot_see_unpublished_assignments(self):
        StaffRoster.objects.create(
            staff=self.staff1,
            location=self.loc1,
            roster_date=self.week_start,
            shift_type=StaffRoster.BREAK_SHIFT,
            shift_code="BS-1",
            login_time=time(9, 0),
            created_by=self.manager,
        )

        self.client.force_login(self.staff1)
        response = self.client.get(reverse("staff_weekly_roster"))

        self.assertNotContains(response, "BS-1")
        self.assertContains(response, "Not published")

    def test_staff_dashboard_shows_todays_login_time(self):
        StaffRoster.objects.create(
            staff=self.staff1,
            location=self.loc1,
            roster_date=timezone.localdate(),
            shift_type=StaffRoster.BREAK_SHIFT,
            shift_code="BS-1",
            login_time=time(9, 0),
            created_by=self.manager,
            is_published=True,
            published_at=timezone.now(),
        )

        self.client.force_login(self.staff1)
        response = self.client.get(reverse("staff_dashboard"))

        self.assertContains(response, "MY SHIFT TODAY")
        self.assertContains(response, "09:00 AM")
        self.assertContains(response, "BS-1")

    def test_weekly_off_displays_no_login_time(self):
        StaffRoster.objects.create(
            staff=self.staff1,
            location=self.loc1,
            roster_date=timezone.localdate(),
            shift_type=StaffRoster.WEEKLY_OFF,
            shift_code="WO",
            created_by=self.manager,
            is_published=True,
            published_at=timezone.now(),
        )

        self.client.force_login(self.staff1)
        response = self.client.get(reverse("staff_dashboard"))

        self.assertContains(response, "Weekly Off")
        self.assertContains(response, "No scheduled login time")

    def test_roster_validation_rejects_duplicate_staff_date(self):
        StaffRoster.objects.create(
            staff=self.staff1,
            location=self.loc1,
            roster_date=self.week_start,
            shift_type=StaffRoster.BREAK_SHIFT,
            shift_code="BS-1",
            login_time=time(9, 0),
            created_by=self.manager,
        )

        with self.assertRaises(ValidationError):
            StaffRoster.objects.create(
                staff=self.staff1,
                location=self.loc1,
                roster_date=self.week_start,
                shift_type=StaffRoster.BREAK_SHIFT,
                shift_code="BS-2",
                login_time=time(10, 0),
                created_by=self.manager,
            )

    def test_working_shift_requires_login_time(self):
        with self.assertRaises(ValidationError):
            StaffRoster.objects.create(
                staff=self.staff1,
                location=self.loc1,
                roster_date=self.week_start,
                shift_type=StaffRoster.BREAK_SHIFT,
                shift_code="BS-1",
                created_by=self.manager,
            )

    def test_weekly_off_cannot_have_login_time(self):
        with self.assertRaises(ValidationError):
            StaffRoster.objects.create(
                staff=self.staff1,
                location=self.loc1,
                roster_date=self.week_start,
                shift_type=StaffRoster.WEEKLY_OFF,
                shift_code="WO",
                login_time=time(9, 0),
                created_by=self.manager,
            )

    def test_publishing_changes_staff_visibility(self):
        roster = StaffRoster.objects.create(
            staff=self.staff1,
            location=self.loc1,
            roster_date=self.week_start,
            shift_type=StaffRoster.BREAK_SHIFT,
            shift_code="BS-1",
            login_time=time(9, 0),
            created_by=self.manager,
        )

        self.client.force_login(self.staff1)
        self.assertNotContains(self.client.get(reverse("staff_weekly_roster")), "BS-1")

        roster.publish()
        self.assertContains(self.client.get(reverse("staff_weekly_roster")), "BS-1")

    def test_admin_csv_includes_staff_without_roster(self):
        StaffRoster.objects.create(
            staff=self.staff1,
            location=self.loc1,
            roster_date=self.week_start,
            shift_type=StaffRoster.BREAK_SHIFT,
            shift_code="BS-1",
            login_time=time(9, 0),
            created_by=self.admin,
        )

        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("export_admin_roster_csv"),
            {"week": self.week_start.strftime("%Y-%m-%d")},
        )
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("S001", content)
        self.assertIn("Updated", content)
        self.assertIn("S002", content)
        self.assertIn("Not Updated", content)

    def test_cluster_manager_roster_csv_is_limited_to_assigned_locations(self):
        StaffRoster.objects.create(
            staff=self.staff1,
            location=self.loc1,
            roster_date=self.week_start,
            shift_type=StaffRoster.BREAK_SHIFT,
            shift_code="BS-1",
            login_time=time(9, 0),
            created_by=self.cluster,
        )
        StaffRoster.objects.create(
            staff=self.staff2,
            location=self.loc2,
            roster_date=self.week_start,
            shift_type=StaffRoster.BREAK_SHIFT,
            shift_code="BS-2",
            login_time=time(10, 0),
            created_by=self.admin,
        )

        self.client.force_login(self.cluster)
        response = self.client.get(
            reverse("export_admin_roster_csv"),
            {"week": self.week_start.strftime("%Y-%m-%d")},
        )
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("S001", content)
        self.assertIn("BS-1", content)
        self.assertNotIn("S002", content)
        self.assertNotIn("BS-2", content)

    def test_cluster_manager_cannot_export_unassigned_location(self):
        self.client.force_login(self.cluster)
        response = self.client.get(
            reverse("export_admin_roster_csv"),
            {
                "week": self.week_start.strftime("%Y-%m-%d"),
                "location": self.loc2.id,
            },
        )
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("S002", content)

    def test_admin_roster_page_highlights_staff_without_roster(self):
        StaffRoster.objects.create(
            staff=self.staff1,
            location=self.loc1,
            roster_date=self.week_start,
            shift_type=StaffRoster.BREAK_SHIFT,
            shift_code="BS-1",
            login_time=time(9, 0),
            created_by=self.admin,
        )

        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("admin_roster_management"),
            {"week": self.week_start.strftime("%Y-%m-%d")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "S001")
        self.assertContains(response, "S002")
        self.assertContains(response, "Not Updated")

    def test_roster_page_handles_manager_without_assigned_location(self):
        manager_without_location = self.user_model.objects.create_user(
            username="manager-no-location",
            password="password",
            employee_id="M002",
            role="kitchen_manager",
        )

        self.client.force_login(manager_without_location)
        response = self.client.get(reverse("manager_weekly_roster"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No outlet assigned")
        self.assertContains(response, "Please contact an admin")
