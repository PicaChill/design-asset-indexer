"""Small, dependency-free models shared with Photoshop automation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextLayerInfo:
    """Text-layer metadata returned by a Photoshop inspection."""

    layer_path: str
    layer_name: str
    layer_kind: str
    current_text: str


@dataclass(frozen=True)
class ReplaceResult:
    """Defensive result from changing one exact text layer in a copied PSD."""

    matched_layer_count: int
    changed_layer_count: int
