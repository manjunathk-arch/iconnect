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
