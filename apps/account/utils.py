import secrets
import string


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
