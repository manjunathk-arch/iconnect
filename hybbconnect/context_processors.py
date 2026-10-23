from django.core.cache import cache

from .models import Notification


def unread_notifications(request):
    user = getattr(request, "user", None)

    if not user or not user.is_authenticated:
        return {
            "unread_notifications": [],
            "unread_notification_count": 0,
        }

    cache_key = f"unread_notifications:{user.pk}"
    cached_notifications = cache.get(cache_key)

    if cached_notifications is None:
        unread_queryset = Notification.objects.filter(
            user=user,
            is_read=False,
        ).only(
            "id",
            "notification_type",
            "message",
            "link",
            "created_at",
        )
        cached_notifications = {
            "items": list(unread_queryset[:5]),
            "count": unread_queryset.count(),
        }
        cache.set(cache_key, cached_notifications, 15)

    return {
        "unread_notifications": cached_notifications["items"],
        "unread_notification_count": cached_notifications["count"],
    }



# ===== Hybb Kitchen Academy: training pending count (sidebar badge) =====
import os
import time
import base64
import hmac
import hashlib

import requests
from django.conf import settings

ACADEMY_EXEC_URL = getattr(
    settings,
    "ACADEMY_EXEC_URL",
    "https://script.google.com/macros/s/AKfycbxm4UvyPJmLn6MGSsCIrLN4XQmSEWQM42b7BNoxdJml1AfytXFRBiAE_-fhUsL4rfHvYA/exec",
)

_SSO_SECRET = getattr(settings, "SSO_SECRET", None) or os.environ.get("SSO_SECRET", "") or ""


def _academy_build_token(emp):
    exp = int(time.time()) + 300
    payload = "{0}|{1}".format(emp, exp)
    b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig = hmac.new(_SSO_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return "{0}.{1}".format(b64, sig)


def _academy_fetch_count(emp):
    try:
        resp = requests.post(
            ACADEMY_EXEC_URL,
            json={"fn": "pendingCount", "args": [_academy_build_token(emp)]},
            timeout=5,
        )
        data = resp.json()
        return int((data.get("r") or {}).get("count", 0) or 0)
    except Exception:
        return 0


def training_pending(request):
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated) or not _SSO_SECRET:
        return {}
    emp = getattr(user, "employee_id", None)
    if not emp:
        return {}
    key = "training_pending:{0}".format(emp)
    count = cache.get(key)
    if count is None:
        count = _academy_fetch_count(emp)
        cache.set(key, count, 300)
    return {"training_pending": count}
