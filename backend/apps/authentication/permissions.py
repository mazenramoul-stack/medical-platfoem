"""Shared DRF permissions keyed on the app `role` field."""

from rest_framework.permissions import BasePermission

from .models import User


class IsTechnician(BasePermission):
    """Allow only authenticated users whose app role is `technician`.

    This is the real server-side gate for technician-only capabilities (the
    data-conversion tools and the doctor-assignment / patient-intake surface).
    The frontend also hides those pages, but that is UX only — any other
    authenticated user (a doctor) gets a 403.
    """

    message = 'Only technicians may perform this action.'

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        return bool(
            user
            and user.is_authenticated
            and getattr(user, 'role', None) == User.Role.TECHNICIAN
        )
