import secrets
import string


def generate_password(email=None):
    """
    Generate a secure random password.
    If email is provided, includes a portion of it for memorability,
    but still uses secure random generation.
    """

    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password_length = 12
    

    password = ''.join(secrets.choice(alphabet) for _ in range(password_length))
    
    # If email provided, we make it slightly more memorable by including email prefix

    if email:
        email_prefix = email.split("@")[0][:4].lower()

        if len(email_prefix) > 0:
            insert_pos = secrets.randbelow(len(password) - len(email_prefix))
            password = password[:insert_pos] + email_prefix + password[insert_pos + len(email_prefix):]
    
    return password
