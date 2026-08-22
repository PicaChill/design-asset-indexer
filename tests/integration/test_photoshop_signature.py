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
        old_text = "SYNTHETIC_OLD_SIGNATURE"
        new_text = "SYNTHETIC_NEW_SIGNATURE_测试"

        def exercise_case(case_name: str, requested_layer_name: str | None) -> None:
            case_root = root / case_name
            input_dir = case_root / "input"
            source = input_dir / "synthetic-signature.psd"
            adapter.create_synthetic_psd(source, requested_layer_name, old_text)
            source_layers = adapter.inspect_text_layers(source)
            assert len(source_layers) == 1
            original_layer_name = source_layers[0].layer_name
            if requested_layer_name is None:
                assert original_layer_name == old_text
            else:
                assert original_layer_name == requested_layer_name
            source_hash = _sha256(source)

            inspect_summary = inspect_signatures(
                input_dir,
                case_root / "inspect-reports",
                adapter,
                layer_name=original_layer_name,
                contains_text="OLD_SIGNATURE",
            )
            assert inspect_summary["matched_layer_count"] == 1

            dry_output = case_root / "dry-output"
            dry_summary = replace_signatures(
                input_dir,
                dry_output,
                adapter,
                old_text=old_text,
                new_text=new_text,
                layer_name=original_layer_name,
                dry_run=True,
            )
            assert dry_summary["status_counts"] == {"WOULD_REPLACE": 1}
            assert not (dry_output / source.name).exists()

            output_dir = case_root / "output"
            replace_summary = replace_signatures(
                input_dir,
                output_dir,
                adapter,
                old_text=old_text,
                new_text=new_text,
                layer_name=original_layer_name,
            )
            output = output_dir / source.name
            assert replace_summary["status_counts"] == {"REPLACED": 1}
            assert output.is_file()

            output_layers = adapter.inspect_text_layers(output)
            assert [
                (layer.layer_name, layer.current_text)
                for layer in output_layers
            ] == [(original_layer_name, new_text)]
            assert _sha256(source) == source_hash

        exercise_case("auto-named", None)
        exercise_case("custom-named", "Signature")

    print(f"PHOTOSHOP_VERSION={adapter.version}")
    print("SOURCE_SHA_UNCHANGED=YES")
    print("OUTPUT_TEXT_VERIFIED=YES")
    print("AUTO_NAMED_LAYER_PRESERVED=YES")
    print("CUSTOM_NAMED_LAYER_PRESERVED=YES")
