"""Fail-closed PSD signature inspection and copied-output replacement service."""

from __future__ import annotations

from collections import Counter
from fnmatch import fnmatchcase
import os
from pathlib import Path
from shutil import copy2
from typing import Protocol

from .detect import detect_file
from .photoshop.errors import PhotoshopAutomationError
from .photoshop.models import ReplaceResult, TextLayerInfo
from .reports import write_csv, write_json, write_jsonl


INSPECT_FIELDS = [
    "relative_path",
    "document_opened",
    "layer_path",
    "layer_name",
    "layer_kind",
    "current_text",
    "matched",
    "error",
]

REPLACE_FIELDS = [
    "relative_path",
    "status",
    "matched_layer_count",
    "changed_layer_count",
    "old_text",
    "new_text",
    "output_relative_path",
    "error_code",
    "error_message",
]

PLAN_FIELDS = [
    "relative_path",
    "decision",
    "matched_layer_count",
    "old_text",
    "new_text",
    "output_relative_path",
    "error_code",
    "error_message",
]


class SignatureAdapter(Protocol):
    """Narrow boundary implemented by the optional Photoshop adapter."""

    def inspect_text_layers(self, path: Path) -> list[TextLayerInfo]: ...

    def replace_exact_text(
        self,
        path: Path,
        old_text: str,
        new_text: str,
        layer_name: str | None = None,
    ) -> ReplaceResult: ...


def _resolved_directory(path: Path, label: str) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError(f"{label} must be a directory")
    return resolved


def _validate_separate_roots(input_dir: Path, output_dir: Path) -> tuple[Path, Path]:
    source = _resolved_directory(input_dir, "input")
    destination = output_dir.resolve(strict=False)
    if (
        source == destination
        or destination.is_relative_to(source)
        or source.is_relative_to(destination)
    ):
        raise ValueError("input and output directories must not overlap")
    return source, destination


def _candidate_paths(root: Path, recursive: bool) -> list[Path]:
    if not recursive:
        try:
            return sorted(
                (
                    path
                    for path in root.iterdir()
                    if path.is_file() and not path.is_symlink()
                ),
                key=lambda path: (path.name.casefold(), path.name),
            )
        except OSError:
            return []

    paths: list[Path] = []
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        directory_names[:] = sorted(
            (
                name
                for name in directory_names
                if not (current_path / name).is_symlink()
            ),
            key=lambda name: (name.casefold(), name),
        )
        for name in sorted(file_names, key=lambda value: (value.casefold(), value)):
            path = current_path / name
            if not path.is_symlink():
                paths.append(path)
    return paths


def _select_psd_files(
    root: Path,
    *,
    recursive: bool,
    include: str,
    max_files: int,
) -> tuple[list[Path], bool]:
    if not include:
        raise ValueError("include pattern must not be empty")
    if max_files < 1:
        raise ValueError("maximum file count must be positive")

    selected: list[Path] = []
    for path in _candidate_paths(root, recursive):
        relative = path.relative_to(root).as_posix()
        if path.suffix.casefold() != ".psd":
            continue
        if not fnmatchcase(relative.casefold(), include.casefold()):
            continue
        try:
            if detect_file(path) != "PSD":
                continue
        except OSError:
            # Retain an unreadable .psd candidate so the per-file report can
            # record a controlled open failure instead of silently losing it.
            pass
        selected.append(path)

    selected.sort(
        key=lambda path: (
            path.relative_to(root).as_posix().casefold(),
            path.relative_to(root).as_posix(),
        )
    )
    truncated = len(selected) > max_files
    return selected[:max_files], truncated


def _matches_layer(
    layer: TextLayerInfo,
    *,
    layer_name: str | None,
    contains_text: str | None,
) -> bool:
    return (
        (layer_name is None or layer.layer_name == layer_name)
        and (contains_text is None or contains_text in layer.current_text)
    )


def _error_details(error: Exception, fallback_code: str) -> tuple[str, str]:
    if isinstance(error, PhotoshopAutomationError):
        return error.code, str(error)
    if isinstance(error, OSError):
        return "FILESYSTEM_ERROR", "Filesystem operation failed"
    return fallback_code, "Photoshop operation failed"


def inspect_signatures(
    input_dir: Path,
    output_dir: Path,
    adapter: SignatureAdapter,
    *,
    recursive: bool = False,
    include: str = "*.psd",
    layer_name: str | None = None,
    contains_text: str | None = None,
    max_files: int = 100,
) -> dict:
    """Inspect PSD text layers without changing or saving source documents."""

    source, destination = _validate_separate_roots(input_dir, output_dir)
    files, truncated = _select_psd_files(
        source,
        recursive=recursive,
        include=include,
        max_files=max_files,
    )
    destination.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    opened_count = 0
    layer_count = 0
    matched_count = 0
    error_count = 0
    for path in files:
        relative = path.relative_to(source).as_posix()
        try:
            layers = adapter.inspect_text_layers(path)
        except Exception as error:
            error_code, _message = _error_details(error, "PHOTOSHOP_INSPECT_FAILED")
            error_count += 1
            rows.append(
                {
                    "relative_path": relative,
                    "document_opened": False,
                    "layer_path": "",
                    "layer_name": "",
                    "layer_kind": "",
                    "current_text": "",
                    "matched": False,
                    "error": error_code,
                }
            )
            continue

        opened_count += 1
        if not layers:
            rows.append(
                {
                    "relative_path": relative,
                    "document_opened": True,
                    "layer_path": "",
                    "layer_name": "",
                    "layer_kind": "",
                    "current_text": "",
                    "matched": False,
                    "error": "",
                }
            )
            continue

        for layer in layers:
            matched = _matches_layer(
                layer,
                layer_name=layer_name,
                contains_text=contains_text,
            )
            layer_count += 1
            matched_count += int(matched)
            rows.append(
                {
                    "relative_path": relative,
                    "document_opened": True,
                    "layer_path": layer.layer_path,
                    "layer_name": layer.layer_name,
                    "layer_kind": layer.layer_kind,
                    "current_text": layer.current_text,
                    "matched": matched,
                    "error": "",
                }
            )

    summary = {
        "command": "signature-inspect",
        "file_count": len(files),
        "document_opened_count": opened_count,
        "layer_count": layer_count,
        "matched_layer_count": matched_count,
        "error_count": error_count,
        "max_files_reached": truncated,
    }
    write_csv(destination / "signature_layers.csv", rows, INSPECT_FIELDS)
    write_jsonl(destination / "signature_layers.jsonl", rows)
    write_json(destination / "summary.json", summary)
    return summary


def _validate_replacement(old_text: str, new_text: str) -> None:
    if not old_text:
        raise ValueError("source text must not be empty")
    if not new_text:
        raise ValueError("replacement text must not be empty")
    if old_text == new_text:
        raise ValueError("source and replacement text must differ")


def _replace_row(
    *,
    relative: str,
    status: str,
    matched_count: int,
    changed_count: int,
    old_text: str,
    new_text: str,
    error_code: str = "",
    error_message: str = "",
) -> dict:
    return {
        "relative_path": relative,
        "status": status,
        "matched_layer_count": matched_count,
        "changed_layer_count": changed_count,
        "old_text": old_text,
        "new_text": new_text,
        "output_relative_path": relative,
        "error_code": error_code,
        "error_message": error_message,
    }


def _output_file(destination: Path, relative: str) -> Path:
    candidate = destination / Path(relative)
    if not candidate.resolve(strict=False).is_relative_to(destination):
        raise ValueError("output file would escape the output directory")
    return candidate


def replace_signatures(
    input_dir: Path,
    output_dir: Path,
    adapter: SignatureAdapter,
    *,
    old_text: str,
    new_text: str,
    layer_name: str | None = None,
    dry_run: bool = False,
    recursive: bool = False,
    include: str = "*.psd",
    max_files: int = 100,
) -> dict:
    """Replace one exact text match per PSD, writing only copied outputs."""

    _validate_replacement(old_text, new_text)
    source, destination = _validate_separate_roots(input_dir, output_dir)
    files, truncated = _select_psd_files(
        source,
        recursive=recursive,
        include=include,
        max_files=max_files,
    )
    destination.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for source_path in files:
        relative = source_path.relative_to(source).as_posix()
        try:
            output_path = _output_file(destination, relative)
        except ValueError as error:
            rows.append(
                _replace_row(
                    relative=relative,
                    status="FAILED_REPLACE",
                    matched_count=0,
                    changed_count=0,
                    old_text=old_text,
                    new_text=new_text,
                    error_code="OUTPUT_PATH_ESCAPE",
                    error_message=str(error),
                )
            )
            continue

        if output_path.exists():
            rows.append(
                _replace_row(
                    relative=relative,
                    status="SKIPPED_EXISTS",
                    matched_count=0,
                    changed_count=0,
                    old_text=old_text,
                    new_text=new_text,
                )
            )
            continue

        try:
            layers = adapter.inspect_text_layers(source_path)
        except Exception as error:
            code, message = _error_details(error, "PHOTOSHOP_OPEN_FAILED")
            status = "FAILED_OPEN" if code.endswith("OPEN_FAILED") else "FAILED_REPLACE"
            rows.append(
                _replace_row(
                    relative=relative,
                    status=status,
                    matched_count=0,
                    changed_count=0,
                    old_text=old_text,
                    new_text=new_text,
                    error_code=code,
                    error_message=message,
                )
            )
            continue

        matches = [
            layer
            for layer in layers
            if layer.current_text == old_text
            and (layer_name is None or layer.layer_name == layer_name)
        ]
        if not matches:
            rows.append(
                _replace_row(
                    relative=relative,
                    status="SKIPPED_NO_MATCH",
                    matched_count=0,
                    changed_count=0,
                    old_text=old_text,
                    new_text=new_text,
                )
            )
            continue
        if len(matches) > 1:
            rows.append(
                _replace_row(
                    relative=relative,
                    status="SKIPPED_AMBIGUOUS",
                    matched_count=len(matches),
                    changed_count=0,
                    old_text=old_text,
                    new_text=new_text,
                )
            )
            continue
        if dry_run:
            rows.append(
                _replace_row(
                    relative=relative,
                    status="WOULD_REPLACE",
                    matched_count=1,
                    changed_count=0,
                    old_text=old_text,
                    new_text=new_text,
                )
            )
            continue

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _output_file(destination, relative)
            copy2(source_path, output_path)
            result = adapter.replace_exact_text(
                output_path,
                old_text,
                new_text,
                layer_name=layer_name,
            )
            if result.matched_layer_count != 1 or result.changed_layer_count != 1:
                rows.append(
                    _replace_row(
                        relative=relative,
                        status="FAILED_REPLACE",
                        matched_count=result.matched_layer_count,
                        changed_count=result.changed_layer_count,
                        old_text=old_text,
                        new_text=new_text,
                        error_code="MATCH_CHANGED_BEFORE_SAVE",
                        error_message="Exact match count changed before output save",
                    )
                )
                continue
        except Exception as error:
            code, message = _error_details(error, "PHOTOSHOP_REPLACE_FAILED")
            status = "FAILED_SAVE" if code.endswith("SAVE_FAILED") else "FAILED_REPLACE"
            rows.append(
                _replace_row(
                    relative=relative,
                    status=status,
                    matched_count=1,
                    changed_count=0,
                    old_text=old_text,
                    new_text=new_text,
                    error_code=code,
                    error_message=message,
                )
            )
            continue

        rows.append(
            _replace_row(
                relative=relative,
                status="REPLACED",
                matched_count=1,
                changed_count=1,
                old_text=old_text,
                new_text=new_text,
            )
        )

    status_counts = dict(sorted(Counter(row["status"] for row in rows).items()))
    summary = {
        "command": "signature-replace",
        "dry_run": dry_run,
        "file_count": len(files),
        "status_counts": status_counts,
        "matched_layer_count": sum(row["matched_layer_count"] for row in rows),
        "changed_layer_count": sum(row["changed_layer_count"] for row in rows),
        "max_files_reached": truncated,
    }

    if dry_run:
        decisions = {
            "SKIPPED_NO_MATCH": "SKIP_NO_MATCH",
            "SKIPPED_AMBIGUOUS": "SKIP_AMBIGUOUS",
            "SKIPPED_EXISTS": "SKIP_EXISTS",
            "FAILED_OPEN": "ERROR",
            "FAILED_REPLACE": "ERROR",
            "FAILED_SAVE": "ERROR",
        }
        plan_rows = [
            {
                "relative_path": row["relative_path"],
                "decision": decisions.get(row["status"], row["status"]),
                "matched_layer_count": row["matched_layer_count"],
                "old_text": row["old_text"],
                "new_text": row["new_text"],
                "output_relative_path": row["output_relative_path"],
                "error_code": row["error_code"],
                "error_message": row["error_message"],
            }
            for row in rows
        ]
        write_csv(destination / "planned_changes.csv", plan_rows, PLAN_FIELDS)
        write_jsonl(destination / "planned_changes.jsonl", plan_rows)
        write_json(destination / "summary.json", summary)
    else:
        write_csv(destination / "signature_replace_results.csv", rows, REPLACE_FIELDS)
        write_jsonl(destination / "signature_replace_results.jsonl", rows)
        write_json(destination / "summary.json", summary)
    return summary
