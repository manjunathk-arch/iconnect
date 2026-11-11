from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.urls import reverse
import re

from .models import CustomUser


@override_settings(SECURE_SSL_REDIRECT=False)
class LoginCSRFFlowTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def test_render_csrf_and_proxy_settings(self):
        self.assertEqual(settings.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https"))
        self.assertIn("iconnect-k4fg.onrender.com", settings.ALLOWED_HOSTS)
        self.assertIn("https://iconnect-k4fg.onrender.com", settings.CSRF_TRUSTED_ORIGINS)

    def test_login_form_sets_secure_cookie_and_accepts_csrf_submission_for_each_role(self):
        role_redirects = {
            "kitchen_staff": "staff_dashboard",
            "kitchen_manager": "manager_dashboard",
            "cluster_manager": "cluster_dashboard",
            "owner": "owner_dashboard",
            "admin": "admin_dashboard",
        }

        for index, (role, destination) in enumerate(role_redirects.items(), start=1):
            with self.subTest(role=role):
                employee_id = f"CSRF-{index}"
                user = CustomUser.objects.create_user(
                    username=f"csrf-user-{index}",
                    employee_id=employee_id,
                    role=role,
                    password="test-password-123",
                )
                login_url = reverse("login")
                response = self.client.get(
                    login_url,
                    secure=True,
                    HTTP_X_FORWARDED_PROTO="https",
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "name=\"csrfmiddlewaretoken\"")
                cookie = self.client.cookies.get(settings.CSRF_COOKIE_NAME)
                self.assertIsNotNone(cookie)
                self.assertTrue(cookie["secure"])
                csrf_token = re.search(
                    r'name="csrfmiddlewaretoken" value="([^"]+)"',
                    response.content.decode(),
                ).group(1)

                response = self.client.post(
                    login_url,
                    {
                        "employee_id": employee_id,
                        "password": "test-password-123",
                        "csrfmiddlewaretoken": csrf_token,
                    },
                    secure=True,
                    HTTP_X_FORWARDED_PROTO="https",
                    HTTP_ORIGIN="https://iconnect-k4fg.onrender.com",
                )
                self.assertRedirects(response, reverse(destination), fetch_redirect_response=False)
                self.assertTrue(self.client.session.get("_auth_user_id"))
                self.assertTrue(CustomUser.objects.filter(pk=user.pk).exists())
