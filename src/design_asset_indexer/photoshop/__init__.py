"""Optional Adobe Photoshop automation for copied PSD outputs."""

from .adapter import PhotoshopAdapter
from .errors import (
    PhotoshopAutomationError,
    PhotoshopInspectError,
    PhotoshopOpenError,
    PhotoshopReplaceError,
    PhotoshopSaveError,
    PhotoshopUnavailableError,
)
from .models import ReplaceResult, TextLayerInfo

__all__ = [
    "PhotoshopAdapter",
    "PhotoshopAutomationError",
    "PhotoshopInspectError",
    "PhotoshopOpenError",
    "PhotoshopReplaceError",
    "PhotoshopSaveError",
    "PhotoshopUnavailableError",
    "ReplaceResult",
    "TextLayerInfo",
]
