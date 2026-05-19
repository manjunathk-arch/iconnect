from django.contrib.auth import get_user_model
User = get_user_model()

CATEGORY_OWNER_MAP = {
    "Training Related": "E010",
    "Critical Intervention - Cletus": "E011",
    "MIS Related": "E012",
    "HR Related": "E013",
    "Leave Request": "E013",
    "PF Related Issue": "E013",
    "Bank Account Issue": "E013",
    "Request a call Babk": "E013",
    "Quality Related": "E014",
    "Salary Message not received": "E013",
    "Salary Not Received": "E013",
    "Shift Manager / Kitchen Manager Issue": "E013",
    "Accommodation Issue": "E013",
    "Salary is incorrect": "E013",
    "Request - Salary Advance": "E013",
    "Co-Worker Issue": "E013",
    "Request a call Back": "E013",
    "PF Related Issues": "E013",
}

def get_owner_for_category(category_name):
    """Return the owner user object for a given category."""
    print("🔍 Category received:", category_name)
    employee_id = CATEGORY_OWNER_MAP.get(category_name)
    print("🔍 Mapped employee_id:", employee_id)
    if not employee_id:
        print("⚠️ No mapping found for:", category_name)
        return None

    owner = User.objects.filter(employee_id=employee_id, role="owner").first()
    print("🔍 Owner found:", owner)
    return owner



def is_kitchen_staff_or_manager(user):
    return user.role in ("kitchen_staff", "kitchen_manager")
