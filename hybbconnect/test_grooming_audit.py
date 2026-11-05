from io import BytesIO
from pathlib import Path
import shutil
from copy import deepcopy
import sys
import types

# Requests is declared by the project; this checkout's virtualenv lacks it.
# The training processor is disabled below, so provide a test-only import stub
# only when the real dependency is unavailable.
try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    sys.modules["requests"] = types.ModuleType("requests")

from django.conf import settings
from django.template import engines
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import ClusterManagerProfile, CustomUser, GroomingAudit, Location


class GroomingAuditTests(TestCase):
    def setUp(self):
        self.media_dir = Path(__file__).resolve().parent / ".test_media"
        templates = deepcopy(settings.TEMPLATES)
        templates[0]["OPTIONS"]["context_processors"] = [
            item for item in templates[0]["OPTIONS"]["context_processors"]
            if item != "hybbconnect.context_processors.training_pending"
        ]
        self.settings_override = override_settings(MEDIA_ROOT=self.media_dir, TEMPLATES=templates)
        self.settings_override.enable()
        engines._engines.clear()
        self.loc1 = Location.objects.create(code="K1", name="Kitchen One")
        self.loc2 = Location.objects.create(code="K2", name="Kitchen Two")
        self.manager = self.user("KM1", "kitchen_manager", self.loc1)
        self.other_manager = self.user("KM2", "kitchen_manager", self.loc2)
        self.cluster = self.user("CM1", "cluster_manager")
        self.profile = ClusterManagerProfile.objects.create(user=self.cluster)
        self.profile.locations.add(self.loc1)
        self.staff = self.user("S1", "kitchen_staff", self.loc1)
        self.manager_staff = self.user("KM3", "kitchen_manager", self.loc1)
        self.admin = self.user("AD1", "admin")
        self.owner = self.user("OW1", "owner")

    def tearDown(self):
        self.settings_override.disable()
        engines._engines.clear()
        shutil.rmtree(self.media_dir, ignore_errors=True)

    @staticmethod
    def user(emp_id, role, location=None, active=True):
        user = CustomUser(
            username=emp_id, employee_id=emp_id,
            role=role, location=location, is_active=active,
        )
        user.set_unusable_password()
        user.save()
        return user

    @staticmethod
    def photo(name="employee.png", valid=True, size=1):
        if valid:
            stream = BytesIO()
            Image.new("RGB", (2, 2), "white").save(stream, format="PNG")
            content = stream.getvalue()
        else:
            content = b"not an image"
        if size > 1:
            content += b"0" * (size - 1)
        return SimpleUploadedFile(name, content, content_type="image/png")

    def submit(self, user=None, location=None, employee=None, checks=None, photo=None):
        user = user or self.manager
        checks = checks or {key: "pass" for key in ("jewelry_accessories", "shoes", "hands_nails", "hair_net")}
        employee_id = employee.pk if isinstance(employee, CustomUser) else (employee or self.staff.pk)
        location_id = location.pk if isinstance(location, Location) else (location or self.loc1.pk)
        payload = {"location": str(location_id), "employee": str(employee_id),
                   "remarks": "test note", **checks, "employee_photo": photo or self.photo()}
        self.client.force_login(user)
        return self.client.post(reverse("submit_grooming_audit"), payload)

    def test_kitchen_manager_sees_own_location_and_not_another(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("grooming_audit_employees"), {"location": self.loc1.pk}).status_code, 200)
        self.assertEqual(self.client.get(reverse("grooming_audit_employees"), {"location": self.loc2.pk}).json()["employees"], [])

    def test_cluster_manager_sees_allocated_locations_only(self):
        self.client.force_login(self.cluster)
        self.assertEqual(self.client.get(reverse("grooming_audit_employees"), {"location": self.loc1.pk}).status_code, 200)
        self.assertEqual(self.client.get(reverse("grooming_audit_employees"), {"location": self.loc2.pk}).json()["employees"], [])

    def test_cluster_manager_cannot_submit_for_unallocated_location(self):
        self.assertEqual(self.submit(self.cluster, location=self.loc2).status_code, 403)

    def test_kitchen_manager_can_audit_kitchen_staff(self):
        self.assertEqual(self.submit().status_code, 302)
        self.assertEqual(GroomingAudit.objects.get().employee, self.staff)

    def test_audit_form_renders_for_manager_and_cluster_manager(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("grooming_audit")).status_code, 200)
        self.client.force_login(self.cluster)
        self.assertEqual(self.client.get(reverse("grooming_audit")).status_code, 200)

    def test_cluster_manager_can_audit_kitchen_staff_and_manager(self):
        self.assertEqual(self.submit(self.cluster).status_code, 302)
        self.assertEqual(self.submit(self.cluster, employee=self.manager_staff).status_code, 302)
        self.assertEqual(GroomingAudit.objects.count(), 2)

    def test_users_cannot_audit_themselves(self):
        self.assertEqual(self.submit(employee=self.manager).status_code, 302)
        self.assertEqual(GroomingAudit.objects.count(), 0)

    def test_inactive_employees_cannot_be_audited(self):
        inactive = self.user("S2", "kitchen_staff", self.loc1, active=False)
        self.assertEqual(self.submit(employee=inactive).status_code, 302)
        self.assertEqual(GroomingAudit.objects.count(), 0)

    def test_employee_must_belong_to_selected_kitchen(self):
        self.assertEqual(self.submit(location=self.loc2, employee=self.staff).status_code, 403)
        self.assertEqual(GroomingAudit.objects.count(), 0)

    def test_all_checklist_values_are_mandatory(self):
        checks = {"jewelry_accessories": "pass", "shoes": "", "hands_nails": "pass", "hair_net": "pass"}
        self.submit(checks=checks)
        self.assertEqual(GroomingAudit.objects.count(), 0)

    def test_employee_photo_is_mandatory(self):
        self.client.force_login(self.manager)
        data = {"location": self.loc1.pk, "employee": self.staff.pk,
                **{key: "pass" for key in ("jewelry_accessories", "shoes", "hands_nails", "hair_net")}}
        self.client.post(reverse("submit_grooming_audit"), data)
        self.assertEqual(GroomingAudit.objects.count(), 0)

    def test_invalid_image_is_rejected(self):
        self.submit(photo=self.photo(valid=False))
        self.assertEqual(GroomingAudit.objects.count(), 0)

    def test_oversized_image_is_rejected(self):
        self.submit(photo=self.photo(size=5 * 1024 * 1024 + 1))
        self.assertEqual(GroomingAudit.objects.count(), 0)

    def test_all_passes_create_overall_pass(self):
        self.submit()
        self.assertEqual(GroomingAudit.objects.get().overall_result, GroomingAudit.PASS)

    def test_any_failure_creates_overall_fail(self):
        self.submit(checks={"jewelry_accessories": "pass", "shoes": "fail", "hands_nails": "pass", "hair_net": "pass"})
        self.assertEqual(GroomingAudit.objects.get().overall_result, GroomingAudit.FAIL)

    def test_multiple_audits_same_employee_same_day_are_preserved(self):
        self.submit()
        self.submit()
        self.assertEqual(GroomingAudit.objects.count(), 2)

    def test_records_survive_employee_transfer_and_keep_snapshots(self):
        self.submit()
        audit = GroomingAudit.objects.get()
        self.staff.location = self.loc2
        self.staff.save()
        audit.refresh_from_db()
        self.assertEqual(audit.kitchen_location, self.loc1)
        self.assertEqual(audit.location_name_snapshot, self.loc1.name)
        self.assertEqual(audit.employee_id_snapshot, "S1")

    def test_admin_can_view_all_reports(self):
        self.submit()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("grooming_audit_report")).status_code, 200)

    def test_unauthorized_role_cannot_access_reports_or_audit(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("grooming_audit_report")).status_code, 403)
        self.assertEqual(self.client.get(reverse("grooming_audit")).status_code, 403)

    def test_filters_match_snapshots_and_result(self):
        self.submit()
        self.submit(checks={"jewelry_accessories": "fail", "shoes": "pass", "hands_nails": "pass", "hair_net": "pass"})
        self.client.force_login(self.admin)
        response = self.client.get(reverse("grooming_audit_report"), {"employee_id": "S1", "result": "fail"})
        self.assertEqual(response.context["summary"]["total"], 1)

    def test_admin_location_manager_and_cluster_filters_combine(self):
        self.submit()
        self.client.force_login(self.admin)
        response = self.client.get(reverse("grooming_audit_report"), {
            "location": self.loc1.pk, "cluster_manager": self.cluster.pk,
            "kitchen_manager": self.manager.pk, "employee_name": "S1",
            "designation": "Kitchen Staff", "auditor": "KM1",
        })
        self.assertEqual(response.context["summary"]["total"], 1)

    def test_csv_export_works(self):
        self.submit()
        self.client.force_login(self.admin)
        response = self.client.get(reverse("grooming_audit_export", args=["csv"]))
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(b"Employee ID", response.content)

    def test_excel_export_works(self):
        self.submit()
        self.client.force_login(self.admin)
        response = self.client.get(reverse("grooming_audit_export", args=["xlsx"]))
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertTrue(response.content.startswith(b"PK"))

    def test_photo_is_restricted_and_history_is_read_only(self):
        self.submit()
        audit = GroomingAudit.objects.get()
        self.client.force_login(self.other_manager)
        self.assertEqual(self.client.get(reverse("grooming_audit_photo_file", args=[audit.pk])).status_code, 403)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("grooming_audit_photo_file", args=[audit.pk])).status_code, 200)
        audit.remarks = "changed"
        with self.assertRaises(Exception):
            audit.save()

    def test_direct_media_url_for_photo_is_protected(self):
        self.submit()
        audit = GroomingAudit.objects.get()
        suffix = audit.employee_photo.name.split("/", 1)[1]
        self.client.force_login(self.other_manager)
        self.assertEqual(self.client.get(reverse("secure_grooming_media", args=[suffix])).status_code, 403)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("secure_grooming_media", args=[suffix])).status_code, 200)
