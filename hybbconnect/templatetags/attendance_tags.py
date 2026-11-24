from django import template

register = template.Library()

@register.filter
def get_item(mapping, key):
    return mapping.get(key) if mapping else None

@register.filter
def get_attendance(mapping, key):
    record = mapping.get(key) if mapping else None
    return record.attendance_type if record else ""
