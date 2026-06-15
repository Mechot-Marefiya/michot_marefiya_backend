import enum


class RoleCode(enum.Enum):
    USER = "user"
    ADMIN = "admin"
    COMPANY = "company"
    INDIVIDUAL_OWNER = "individual_owner"
    FRONT_DESK="front_desk"
