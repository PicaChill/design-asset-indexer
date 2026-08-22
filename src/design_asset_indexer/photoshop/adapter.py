"""Optional Windows/Photoshop COM adapter.

The module deliberately imports pywin32 only when a connection is requested,
so the package and its read-only v0.1 commands remain usable on other systems.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Iterator

from .errors import (
    PhotoshopAutomationError,
    PhotoshopInspectError,
    PhotoshopOpenError,
    PhotoshopReplaceError,
    PhotoshopSaveError,
    PhotoshopUnavailableError,
)
from .models import ReplaceResult, TextLayerInfo


TEXT_LAYER_KIND = 2
DO_NOT_SAVE_CHANGES = 2


class PhotoshopAdapter:
    """Reuse one Photoshop application connection across a batch."""

    def __init__(self) -> None:
        self._application: object | None = None

    def _connect(self) -> object:
        if self._application is not None:
            return self._application
        if sys.platform != "win32":
            raise PhotoshopUnavailableError("Adobe Photoshop automation is unavailable")
        try:
            import win32com.client  # type: ignore[import-not-found]

            self._application = win32com.client.Dispatch("Photoshop.Application")
        except Exception as error:
            raise PhotoshopUnavailableError(
                "Adobe Photoshop automation is unavailable"
            ) from error
        return self._application

    def is_available(self) -> bool:
        try:
            self._connect()
        except PhotoshopUnavailableError:
            return False
        return True

    @property
    def version(self) -> str:
        application = self._connect()
        try:
            return str(application.Version)
        except Exception as error:
            raise PhotoshopUnavailableError(
                "Adobe Photoshop version could not be read"
            ) from error

    @staticmethod
    def _dispatch(value: object) -> object:
        if hasattr(value, "_oleobj_"):
            return value
        import win32com.client  # type: ignore[import-not-found]

        return win32com.client.Dispatch(value)

    @staticmethod
    def _invoke_method(target: object, name: str, *arguments: object) -> object:
        """Invoke a COM method even when Photoshop's type library is unavailable."""

        import pythoncom  # type: ignore[import-not-found]

        dispatch_id = target._oleobj_.GetIDsOfNames(name)
        return target._oleobj_.Invoke(
            dispatch_id,
            0,
            pythoncom.DISPATCH_METHOD,
            1,
            *arguments,
        )

    @staticmethod
    def _set_property(target: object, name: str, value: object) -> None:
        import pythoncom  # type: ignore[import-not-found]

        dispatch_id = target._oleobj_.GetIDsOfNames(name)
        target._oleobj_.Invoke(
            dispatch_id,
            0,
            pythoncom.DISPATCH_PROPERTYPUT,
            0,
            value,
        )

    @classmethod
    def _items(cls, collection: object) -> Iterator[object]:
        count = int(collection.Count)
        for index in range(1, count + 1):
            yield cls._dispatch(cls._invoke_method(collection, "Item", index))

    def _walk_text_layers(
        self,
        layers: object,
        parents: tuple[str, ...] = (),
    ) -> Iterator[tuple[TextLayerInfo, object]]:
        for layer in self._items(layers):
            try:
                name = str(layer.Name)
                type_name = str(layer.typename)
                if type_name.casefold() == "layerset":
                    yield from self._walk_text_layers(layer.Layers, parents + (name,))
                    continue
                if int(layer.Kind) != TEXT_LAYER_KIND:
                    continue
                current_text = str(layer.TextItem.Contents)
            except Exception as error:
                raise PhotoshopInspectError(
                    "Photoshop layer inspection failed"
                ) from error
            path = " / ".join(parents + (name,))
            yield TextLayerInfo(path, name, "TEXT", current_text), layer

    def _open_document(self, path: Path) -> object:
        application = self._connect()
        try:
            return self._dispatch(
                self._invoke_method(application, "Open", str(path.resolve()))
            )
        except Exception as error:
            raise PhotoshopOpenError("Photoshop could not open a PSD") from error

    @classmethod
    def _close_document(cls, document: object) -> None:
        try:
            cls._invoke_method(document, "Close", DO_NOT_SAVE_CHANGES)
        except Exception:
            # The operation has already completed or failed. Never attempt a
            # second save while cleaning up the project-opened document.
            pass

    def inspect_text_layers(self, path: Path) -> list[TextLayerInfo]:
        document = self._open_document(path)
        try:
            return [info for info, _layer in self._walk_text_layers(document.Layers)]
        except PhotoshopAutomationError:
            raise
        except Exception as error:
            raise PhotoshopInspectError("Photoshop layer inspection failed") from error
        finally:
            self._close_document(document)

    def replace_exact_text(
        self,
        path: Path,
        old_text: str,
        new_text: str,
        layer_name: str | None = None,
    ) -> ReplaceResult:
        """Change exactly one matching text layer in an output PSD copy."""

        document = self._open_document(path)
        try:
            matches = [
                (info, layer)
                for info, layer in self._walk_text_layers(document.Layers)
                if info.current_text == old_text
                and (layer_name is None or info.layer_name == layer_name)
            ]
            if len(matches) != 1:
                return ReplaceResult(len(matches), 0)
            try:
                self._set_property(matches[0][1].TextItem, "Contents", new_text)
            except Exception as error:
                raise PhotoshopReplaceError(
                    "Photoshop text replacement failed"
                ) from error
            try:
                self._invoke_method(document, "Save")
            except Exception as error:
                raise PhotoshopSaveError("Photoshop could not save the output copy") from error
            return ReplaceResult(1, 1)
        finally:
            self._close_document(document)

    def create_synthetic_psd(self, path: Path, layer_name: str, text: str) -> None:
        """Create a generated-only fixture for the opt-in local canary."""

        path.parent.mkdir(parents=True, exist_ok=True)
        application = self._connect()
        document: object | None = None
        try:
            document = self._dispatch(
                self._invoke_method(
                    application.Documents,
                    "Add",
                    256,
                    256,
                    72,
                    "Synthetic Signature Canary",
                )
            )
            layer = self._dispatch(self._invoke_method(document.ArtLayers, "Add"))
            self._set_property(layer, "Kind", TEXT_LAYER_KIND)
            self._set_property(layer, "Name", layer_name)
            self._set_property(layer.TextItem, "Contents", text)
            self._invoke_method(document, "SaveAs", str(path.resolve()))
        except Exception as error:
            raise PhotoshopAutomationError(
                "Photoshop could not create the synthetic canary"
            ) from error
        finally:
            if document is not None:
                self._close_document(document)
        if not path.is_file():
            raise PhotoshopAutomationError(
                "Photoshop did not create the synthetic canary"
            )
