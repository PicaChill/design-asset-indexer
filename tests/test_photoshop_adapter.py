from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from design_asset_indexer.photoshop import (
    PhotoshopAdapter,
    PhotoshopLayerNameRestoreError,
    ReplaceResult,
    TextLayerInfo,
)


class SimulatedTextItem:
    def __init__(self, owner: "SimulatedTextLayer", contents: str) -> None:
        self._owner = owner
        self._contents = contents

    @property
    def Contents(self) -> str:
        return self._contents

    @Contents.setter
    def Contents(self, value: str) -> None:
        self._owner.events.append("contents")
        self._contents = value
        # Photoshop automatically follows changed text when the layer has its
        # generated name. The adapter must restore the original name explicitly.
        self._owner._name = value


class SimulatedTextLayer:
    def __init__(
        self,
        name: str,
        contents: str,
        events: list[str],
        restore_mode: str = "success",
    ) -> None:
        self._name = name
        self.events = events
        self.restore_mode = restore_mode
        self.TextItem = SimulatedTextItem(self, contents)

    @property
    def Name(self) -> str:
        return self._name

    @Name.setter
    def Name(self, value: str) -> None:
        self.events.append("name")
        if self.restore_mode == "raise":
            raise RuntimeError("simulated layer-name restore failure")
        if self.restore_mode != "ignore":
            self._name = value


class SimulatedPhotoshopAdapter(PhotoshopAdapter):
    def __init__(self, layer: SimulatedTextLayer, events: list[str]) -> None:
        super().__init__()
        self.layer = layer
        self.events = events
        self.document = SimpleNamespace(Layers=[layer])

    def _open_document(self, path: Path) -> object:
        return self.document

    def _walk_text_layers(self, layers, parents=()):
        yield (
            TextLayerInfo(
                self.layer.Name,
                self.layer.Name,
                "TEXT",
                self.layer.TextItem.Contents,
            ),
            self.layer,
        )

    @staticmethod
    def _set_property(target: object, name: str, value: object) -> None:
        setattr(target, name, value)

    def _invoke_method(self, target: object, name: str, *arguments: object) -> object:
        assert name == "Save"
        self.events.append("save")
        return None

    def _close_document(self, document: object) -> None:
        self.events.append("close")


@pytest.mark.parametrize("original_name", ["OLD_TEXT", "Signature"])
def test_replace_exact_text_restores_original_layer_name_before_save(
    tmp_path: Path,
    original_name: str,
) -> None:
    events: list[str] = []
    layer = SimulatedTextLayer(original_name, "OLD_TEXT", events)
    adapter = SimulatedPhotoshopAdapter(layer, events)

    result = adapter.replace_exact_text(
        tmp_path / "output.psd",
        "OLD_TEXT",
        "NEW_TEXT",
        layer_name=original_name,
    )

    assert result == ReplaceResult(1, 1)
    assert layer.TextItem.Contents == "NEW_TEXT"
    assert layer.Name == original_name
    assert events == ["contents", "name", "save", "close"]


@pytest.mark.parametrize("restore_mode", ["raise", "ignore"])
def test_replace_exact_text_fails_before_save_when_layer_name_is_not_restored(
    tmp_path: Path,
    restore_mode: str,
) -> None:
    events: list[str] = []
    layer = SimulatedTextLayer(
        "OLD_TEXT",
        "OLD_TEXT",
        events,
        restore_mode=restore_mode,
    )
    adapter = SimulatedPhotoshopAdapter(layer, events)

    with pytest.raises(PhotoshopLayerNameRestoreError):
        adapter.replace_exact_text(
            tmp_path / "output.psd",
            "OLD_TEXT",
            "NEW_TEXT",
            layer_name="OLD_TEXT",
        )

    assert "save" not in events
    assert events[-1] == "close"
