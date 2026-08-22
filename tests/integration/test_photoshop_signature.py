from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import pytest

from design_asset_indexer.photoshop import PhotoshopAdapter
from design_asset_indexer.signatures import inspect_signatures, replace_signatures


pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or os.environ.get("PHOTOSHOP_INTEGRATION_TEST") != "1",
    reason="requires opt-in Windows Photoshop integration environment",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_synthetic_photoshop_signature_canary() -> None:
    adapter = PhotoshopAdapter()
    if not adapter.is_available():
        pytest.skip("Adobe Photoshop automation is unavailable")

    with TemporaryDirectory(prefix="design-asset-indexer-photoshop-canary-") as directory:
        root = Path(directory)
        input_dir = root / "input"
        source = input_dir / "synthetic-signature.psd"
        old_text = "SYNTHETIC_OLD_SIGNATURE"
        new_text = "SYNTHETIC_NEW_SIGNATURE_测试"
        adapter.create_synthetic_psd(source, "Signature", old_text)
        source_hash = _sha256(source)

        inspect_summary = inspect_signatures(
            input_dir,
            root / "inspect-reports",
            adapter,
            layer_name="Signature",
            contains_text="OLD_SIGNATURE",
        )
        assert inspect_summary["matched_layer_count"] == 1

        dry_output = root / "dry-output"
        dry_summary = replace_signatures(
            input_dir,
            dry_output,
            adapter,
            old_text=old_text,
            new_text=new_text,
            layer_name="Signature",
            dry_run=True,
        )
        assert dry_summary["status_counts"] == {"WOULD_REPLACE": 1}
        assert not (dry_output / source.name).exists()

        output_dir = root / "output"
        replace_summary = replace_signatures(
            input_dir,
            output_dir,
            adapter,
            old_text=old_text,
            new_text=new_text,
            layer_name="Signature",
        )
        output = output_dir / source.name
        assert replace_summary["status_counts"] == {"REPLACED": 1}
        assert output.is_file()

        output_layers = adapter.inspect_text_layers(output)
        assert [
            layer.current_text
            for layer in output_layers
            if layer.layer_name == "Signature"
        ] == [new_text]
        assert _sha256(source) == source_hash

    print(f"PHOTOSHOP_VERSION={adapter.version}")
    print("SOURCE_SHA_UNCHANGED=YES")
    print("OUTPUT_TEXT_VERIFIED=YES")
