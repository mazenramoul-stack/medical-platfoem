"""Permission gate for the Technician-only conversion tools."""

from rest_framework.permissions import BasePermission

from apps.authentication.models import User


class IsTechnician(BasePermission):
    """Allow only authenticated users whose app role is `technician`.

    This is the real server-side enforcement for the data-conversion endpoints
    (the frontend also hides the page, but that is UX only). A doctor — or any
    other authenticated user — gets a 403.
    """

    message = 'Only technicians may use the data-conversion tools.'

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        return bool(
            user
            and user.is_authenticated
            and getattr(user, 'role', None) == User.Role.TECHNICIAN
        )
