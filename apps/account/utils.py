import secrets
import string

from apps.account.enums import RoleCode


WORKSPACE_CATEGORY_LABELS = {
    "hotel": "Hotel",
    "guesthouse": "Guest House",
    "car_rental": "Car Rental",
    "event_space": "Event Space",
}


def generate_password(email=None):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password_length = 12

    password = ''.join(secrets.choice(alphabet) for _ in range(password_length))

    if email:
        email_prefix = email.split("@")[0][:4].lower()
        if len(email_prefix) > 0 and len(password) > len(email_prefix):
            insert_pos = secrets.randbelow(len(password) - len(email_prefix))
            password = password[:insert_pos] + email_prefix + password[insert_pos + len(email_prefix):]

    return password


def validate_password_strength(password):
    errors = []
    
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    
    if not any(char.isdigit() for char in password):
        errors.append("Password must contain at least one digit.")
    
    if not any(char.isalpha() for char in password):
        errors.append("Password must contain at least one letter.")
    
    return errors


def get_workspace_summary(workspace):
    if not workspace:
        return None

    model_name = workspace.__class__.__name__
    workspace_type = None

    if model_name == "HotelProfile":
        workspace_type = "hotel"
        workspace_name = getattr(workspace, "name", None) or str(workspace)
    elif model_name == "GuestHouseProfile":
        workspace_type = "guesthouse"
        workspace_name = getattr(workspace, "title", None) or str(workspace)
    elif model_name == "EventSpaceListing":
        workspace_type = "event_space"
        workspace_name = getattr(workspace, "title", None) or str(workspace)
    elif model_name == "CarListing":
        workspace_type = "car_rental"
        workspace_name = " ".join(
            part for part in [getattr(workspace, "brand", ""), getattr(workspace, "model", "")] if part
        ).strip() or getattr(workspace, "title", None) or str(workspace)
    else:
        workspace_name = getattr(workspace, "title", None) or getattr(workspace, "name", None) or str(workspace)

    return {
        "id": str(workspace.id),
        "name": workspace_name,
        "workspace_type": workspace_type,
    }


def get_workspace_catalog_entry(workspace):
    summary = get_workspace_summary(workspace)
    if not summary:
        return None

    workspace_type = summary["workspace_type"]
    return {
        "id": summary["id"],
        "type": workspace_type,
        "name": summary["name"],
        "category": WORKSPACE_CATEGORY_LABELS.get(workspace_type, "Workspace"),
    }


def get_company_scope(user):
    if not user:
        return None
    return getattr(user, "company", None) or getattr(user, "profile", None)


def get_individual_owner_scope(user):
    if not user:
        return None
    return getattr(user, "individual_owner", None) or getattr(user, "individual_owner_profile", None)


def is_individual_owner_user(user):
    if not user or not getattr(user, "is_authenticated", False):
        return False

    if not get_individual_owner_scope(user):
        return False

    role_code = getattr(getattr(user, "role", None), "code", None)
    if role_code == RoleCode.INDIVIDUAL_OWNER.value:
        return True

    if role_code == RoleCode.FRONT_DESK.value:
        return False

    if get_company_scope(user) or getattr(user, "workspace", None):
        return False

    return role_code in {None, RoleCode.USER.value}


def get_effective_role_code(user):
    if not user:
        return None

    if is_individual_owner_user(user):
        return RoleCode.INDIVIDUAL_OWNER.value

    return getattr(getattr(user, "role", None), "code", None)
