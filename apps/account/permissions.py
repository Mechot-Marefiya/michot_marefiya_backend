from rest_framework import permissions
from apps.account.enums import RoleCode


class IsAdmin(permissions.BasePermission):
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser:
            return True
        
        if hasattr(request.user, 'role') and request.user.role:
            return request.user.role.code == RoleCode.ADMIN.value
        
        return False
    
    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsCompany(permissions.BasePermission):
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser or (
            hasattr(request.user, 'role') and 
            request.user.role and 
            request.user.role.code == RoleCode.ADMIN.value
        ):
            return True
        
        if hasattr(request.user, 'role') and request.user.role:
            return request.user.role.code == RoleCode.COMPANY.value
        
        return False
    
    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsUser(permissions.BasePermission):
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Admin can do everything
        if request.user.is_superuser or (
            hasattr(request.user, 'role') and 
            request.user.role and 
            request.user.role.code == RoleCode.ADMIN.value
        ):
            return True
        
        if not hasattr(request.user, 'role') or not request.user.role:
            return True
        
        return request.user.role.code == RoleCode.USER.value
    
    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsOwnerOrReadOnly(permissions.BasePermission):

    def has_object_permission(self, request, view, obj):
        if request.user and request.user.is_authenticated:
            if request.user.is_superuser or (
                hasattr(request.user, 'role') and 
                request.user.role and 
                request.user.role.code == RoleCode.ADMIN.value
            ):
                return True

        if request.method in permissions.SAFE_METHODS:
            return True

        if hasattr(obj, 'user'):
            return obj.user == request.user

        return False


class IsAuthenticatedOrReadOnly(permissions.BasePermission):

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True

        return request.user and request.user.is_authenticated


class IsCompanyOwner(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        return request.user.is_superuser or (
            hasattr(request.user, 'role') and 
            request.user.role and 
            request.user.role.code in [RoleCode.ADMIN.value, RoleCode.COMPANY.value]
        )

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser or (
            hasattr(request.user, 'role') and 
            request.user.role and 
            request.user.role.code == RoleCode.ADMIN.value
        ):
            return True

        if hasattr(obj, 'user'):
            return obj.user == request.user


        if hasattr(obj, 'company') and hasattr(obj.company, 'user'):
            return obj.company.user == request.user
            
        if hasattr(obj, 'individual_owner') and hasattr(request.user, 'individual_owner'):
             if obj.individual_owner == request.user.individual_owner:
                 return True

        return False


class IsListingOwner(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        return request.user.is_superuser or (
            hasattr(request.user, 'role') and 
            request.user.role and 
            request.user.role.code in [RoleCode.ADMIN.value, RoleCode.COMPANY.value, RoleCode.FRONT_DESK.value]
        )

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser or (
            hasattr(request.user, 'role') and 
            request.user.role and 
            request.user.role.code == RoleCode.ADMIN.value
        ):
            return True
        
        if hasattr(obj, 'company') and obj.company:
            if hasattr(obj.company, 'user') and obj.company.user == request.user:
                return True
            if hasattr(request.user, 'company') and request.user.company == obj.company:
                return True
        
        if hasattr(obj, 'individual_owner') and obj.individual_owner:
            if hasattr(request.user, 'individual_owner') and request.user.individual_owner == obj.individual_owner:
                return True

        if hasattr(obj, 'guest_house') and obj.guest_house:
            gh = obj.guest_house
            if hasattr(gh, 'company') and gh.company:
                if hasattr(gh.company, 'user') and gh.company.user == request.user:
                    return True
                if hasattr(request.user, 'company') and request.user.company == gh.company:
                    return True
            if hasattr(gh, 'individual_owner') and gh.individual_owner:
                if hasattr(request.user, 'individual_owner') and request.user.individual_owner == gh.individual_owner:
                    return True
        
        if hasattr(obj, 'hotel') and obj.hotel:
            hotel = obj.hotel
            if hasattr(hotel, 'company') and hotel.company:
                if hasattr(hotel.company, 'user') and hotel.company.user == request.user:
                    return True
                if hasattr(request.user, 'company') and request.user.company == hotel.company:
                    return True
        return False


class IsBookingOwner(permissions.BasePermission):
    
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser or (
            hasattr(request.user, 'role') and 
            request.user.role and 
            request.user.role.code == RoleCode.ADMIN.value
        ):
            return True
        
        if hasattr(obj, 'user') and obj.user == request.user:
            return True
        
        if hasattr(obj, 'items') and obj.items.exists():
            for item in obj.items.all():
                if hasattr(item, 'room') and item.room:
                    room = item.room
                    if hasattr(room, 'hotel') and room.hotel:
                        if hasattr(room.hotel, 'company') and room.hotel.company:
                            if hasattr(room.hotel.company, 'user') and room.hotel.company.user:
                                if room.hotel.company.user == request.user:
                                    return True
        
        return False


class IsCarRentalOwner(permissions.BasePermission):
    
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser or (
            hasattr(request.user, 'role') and 
            request.user.role and 
            request.user.role.code == RoleCode.ADMIN.value
        ):
            return True
        
        if hasattr(obj, 'renter') and obj.renter == request.user:
            return True
        
        if hasattr(obj, 'rental_items') and obj.rental_items.exists():
            for item in obj.rental_items.all():
                if hasattr(item, 'car_listing') and item.car_listing:
                    car = item.car_listing
                    if hasattr(car, 'company') and car.company:
                        if hasattr(car.company, 'user') and car.company.user:
                            if car.company.user == request.user:
                                return True
                    if hasattr(car, 'individual_owner') and car.individual_owner:
                        return False
        
        return False


class CanModifyBooking(permissions.BasePermission):
    
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser or (
            hasattr(request.user, 'role') and 
            request.user.role and 
            request.user.role.code == RoleCode.ADMIN.value
        ):
            return True
        
        if hasattr(obj, 'status'):
            if obj.status != 'pending':
                return False
        
        if hasattr(obj, 'user') and obj.user == request.user:
            return True
        
        return False


class IsPublicReadOnly(permissions.BasePermission):
    
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        
        return request.user and request.user.is_authenticated
class IsCompanyOrFrontDesk(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            if request.user.is_superuser:
                return True
            if hasattr(request.user, 'role') and request.user.role:
                return self.has_allowed_role(request.user.role)
        return False
    
    def has_allowed_role(self, role):
        user_role_code = role.code.lower()
        allowed_codes = {RoleCode.COMPANY.value.lower(), RoleCode.FRONT_DESK.value.lower()}

        if user_role_code in allowed_codes:
            return True

        while role.parent is not None:
            role = role.parent
            if role.code.lower() in allowed_codes:
                return True
        
        return False
class ORPermission(permissions.BasePermission):
    """
    Accepts multiple permissions and allows access if ANY of them pass.
    """
    def __init__(self, *permissions):
        self.permissions = permissions

    def has_permission(self, request, view):
        return any(p().has_permission(request, view) for p in self.permissions)

    def has_object_permission(self, request, view, obj):
        return any(
            p().has_object_permission(request, view, obj)
            if hasattr(p, 'has_object_permission') else False
            for p in self.permissions
        )


class IsGuestHouseBookingOwner(permissions.BasePermission):
    """
    Permission class for GuestHouse bookings.
    Allows access if user is:
    - Admin
    - The renter (customer) who made the booking
    - Company owner of the guesthouse being booked
    """
    
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Admin always allowed
        if request.user.is_superuser or (
            hasattr(request.user, 'role') and 
            request.user.role and 
            request.user.role.code == RoleCode.ADMIN.value
        ):
            return True
        
        # Renter (customer) owns booking
        if hasattr(obj, 'renter') and obj.renter == request.user:
            return True
        
        # Company owns guesthouse
        if hasattr(obj, 'items') and obj.items.exists():
            for item in obj.items.all():
                if hasattr(item, 'room') and item.room:
                    guesthouse = item.room
                    if hasattr(guesthouse, 'company') and guesthouse.company:
                        if hasattr(guesthouse.company, 'user') and guesthouse.company.user:
                            if guesthouse.company.user == request.user:
                                return True
        
        return False
