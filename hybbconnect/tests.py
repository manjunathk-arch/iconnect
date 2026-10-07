from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import TestCase
from django.test import RequestFactory

from .admin import CustomUserAdmin


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
