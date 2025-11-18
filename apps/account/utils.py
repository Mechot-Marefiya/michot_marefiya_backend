import secrets
import string


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
