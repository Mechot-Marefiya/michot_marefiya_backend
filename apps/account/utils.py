def generate_password(email):
    email_str = email.split("@")
    return "".join([email_str[0], "@1234"])
