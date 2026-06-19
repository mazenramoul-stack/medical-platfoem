"""Permission gate for the Technician-only conversion tools.

``IsTechnician`` now lives in apps.authentication.permissions (shared with the
doctor-assignment / patient-intake surface); re-exported here for backward
compatibility with existing imports.
"""

from apps.authentication.permissions import IsTechnician

__all__ = ['IsTechnician']
