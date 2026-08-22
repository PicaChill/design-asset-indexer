"""Sanitized exceptions for the optional Photoshop automation adapter."""

from __future__ import annotations


class PhotoshopAutomationError(RuntimeError):
    """Base class for errors that are safe to surface without private paths."""

    code = "PHOTOSHOP_AUTOMATION_FAILED"


class PhotoshopUnavailableError(PhotoshopAutomationError):
    code = "PHOTOSHOP_UNAVAILABLE"


class PhotoshopOpenError(PhotoshopAutomationError):
    code = "PHOTOSHOP_OPEN_FAILED"


class PhotoshopInspectError(PhotoshopAutomationError):
    code = "PHOTOSHOP_INSPECT_FAILED"


class PhotoshopReplaceError(PhotoshopAutomationError):
    code = "PHOTOSHOP_REPLACE_FAILED"


class PhotoshopSaveError(PhotoshopAutomationError):
    code = "PHOTOSHOP_SAVE_FAILED"
