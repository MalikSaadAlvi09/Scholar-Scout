"""Profiles package."""
from backend.profiles.manager import (
    AcademicProfileSchema,
    get_current_profile,
    update_or_create_profile,
    get_all_profiles,
    get_profile_by_id
)

__all__ = [
    "AcademicProfileSchema",
    "get_current_profile",
    "update_or_create_profile",
    "get_all_profiles",
    "get_profile_by_id"
]
