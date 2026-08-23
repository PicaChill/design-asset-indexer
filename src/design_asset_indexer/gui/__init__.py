"""Optional PySide6 desktop GUI.

The module intentionally imports no Qt package so the base CLI remains usable
without the ``gui`` optional extra.
"""

GUI_EXTRA_HINT = "pip install 'design-asset-indexer[gui,photoshop]'"

__all__ = ["GUI_EXTRA_HINT"]
