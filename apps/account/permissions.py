from rest_framework import permissions


class IsOwnerOrReadOnly(permissions.BasePermission):

    def has_object_permission(self, request, view, obj):

        if request.method in permissions.SAFE_METHODS:
            return True


        return obj.user == request.user


class IsAuthenticatedOrReadOnly(permissions.BasePermission):

    def has_permission(self, request, view):

        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions require authentication
        return request.user and request.user.is_authenticated


class IsCompanyOwner(permissions.BasePermission):

    def has_object_permission(self, request, view, obj):

        if not request.user or not request.user.is_authenticated:
            return False


        if hasattr(obj, 'user'):
            return obj.user == request.user


        if hasattr(obj, 'company') and hasattr(obj.company, 'user'):
            return obj.company.user == request.user

        return False

