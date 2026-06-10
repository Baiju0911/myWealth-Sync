from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied


def require_permission(required_codename):
    """
    Explicit dynamic decorator to audit incoming request user signatures
    against live MySQL role assignment entries.
    """

    class DynamicRBACPermission(BasePermission):
        def has_permission(self, request, view):
            # 1. Verify user authentication status
            if not request.user or not request.user.is_authenticated:
                return False

            # 2. Check if the user has an assigned role configuration
            if not request.user.role:
                raise PermissionDenied(
                    "Authentication credentials validated, but no structural role profile is bound."
                )

            # 3. Dynamic database query lookup (Hits cache or memory indexes fast)
            has_right = request.user.role.permissions.filter(
                codename=required_codename
            ).exists()
            if not has_right:
                raise PermissionDenied(
                    f"Access Denied. Your profile lacks the permission right token: [{required_codename}]"
                )

            return True

    return DynamicRBACPermission
