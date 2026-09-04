from .models import Notification


def unread_notifications(request):
    user = getattr(request, "user", None)

    if not user or not user.is_authenticated:
        return {
            "unread_notifications": [],
            "unread_notification_count": 0,
        }

    notifications = Notification.objects.filter(
        user=user,
        is_read=False,
    )[:5]

    return {
        "unread_notifications": notifications,
        "unread_notification_count": Notification.objects.filter(
            user=user,
            is_read=False,
        ).count(),
    }
