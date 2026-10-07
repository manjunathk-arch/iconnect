from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test import override_settings
from django.test import RequestFactory
from django.urls import reverse

from .admin import CustomUserAdmin


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
