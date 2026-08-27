"""
Shared attack taxonomy — imported by both Red/sandbox and Blue.

Lives outside `backend.sandbox` and `backend.blue_team` so both can depend on it
without an import cycle.
"""

from .techniques import (
    SURFACES,
    SURFACE_ENTRY_ACTION,
    TECHNIQUES,
    Technique,
    all_action_types,
    resolve_technique,
    surface_for_action,
    techniques_for_family,
    techniques_for_surface,
)

__all__ = [
    "SURFACES",
    "SURFACE_ENTRY_ACTION",
    "TECHNIQUES",
    "Technique",
    "all_action_types",
    "resolve_technique",
    "surface_for_action",
    "techniques_for_family",
    "techniques_for_surface",
]
