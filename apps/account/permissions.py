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

        return False


class IsListingOwner(permissions.BasePermission):
    
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
            if hasattr(obj.company, 'user') and obj.company.user:
                return obj.company.user == request.user
        
        if hasattr(obj, 'individual_owner') and obj.individual_owner:
            return False
        
        if hasattr(obj, 'hotel') and obj.hotel:
            if hasattr(obj.hotel, 'company') and obj.hotel.company:
                if hasattr(obj.hotel.company, 'user') and obj.hotel.company.user:
                    return obj.hotel.company.user == request.user
        
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

