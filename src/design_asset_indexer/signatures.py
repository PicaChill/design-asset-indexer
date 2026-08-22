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


def _matching_psd_files(
    root: Path,
    *,
    recursive: bool,
    include: str,
) -> list[Path]:
    if not include:
        raise ValueError("include pattern must not be empty")

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
    return selected


def _select_psd_files(
    root: Path,
    *,
    recursive: bool,
    include: str,
    max_files: int,
) -> tuple[list[Path], bool]:
    if max_files < 1:
        raise ValueError("maximum file count must be positive")
    selected = _matching_psd_files(
        root,
        recursive=recursive,
        include=include,
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


def _inspect_one_signature(
    path: Path,
    relative: str,
    adapter: SignatureAdapter,
    *,
    layer_name: str | None,
    contains_text: str | None,
) -> tuple[list[dict], int, int, int, int]:
    """Inspect one PSD and return rows plus opened/layer/match/error counts."""

    try:
        layers = adapter.inspect_text_layers(path)
    except Exception as error:
        error_code, _message = _error_details(error, "PHOTOSHOP_INSPECT_FAILED")
        return (
            [
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
            ],
            0,
            0,
            0,
            1,
        )

    if not layers:
        return (
            [
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
            ],
            1,
            0,
            0,
            0,
        )

    rows: list[dict] = []
    matched_count = 0
    for layer in layers:
        matched = _matches_layer(
            layer,
            layer_name=layer_name,
            contains_text=contains_text,
        )
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
    return rows, 1, len(layers), matched_count, 0


def _inspection_summary(
    *,
    file_count: int,
    opened_count: int,
    layer_count: int,
    matched_count: int,
    error_count: int,
    truncated: bool,
) -> dict:
    return {
        "command": "signature-inspect",
        "file_count": file_count,
        "document_opened_count": opened_count,
        "layer_count": layer_count,
        "matched_layer_count": matched_count,
        "error_count": error_count,
        "max_files_reached": truncated,
    }


def _write_inspection_reports(destination: Path, rows: list[dict], summary: dict) -> None:
    write_csv(destination / "signature_layers.csv", rows, INSPECT_FIELDS)
    write_jsonl(destination / "signature_layers.jsonl", rows)
    write_json(destination / "summary.json", summary)


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
        file_rows, opened, layers, matched, errors = _inspect_one_signature(
            path,
            relative,
            adapter,
            layer_name=layer_name,
            contains_text=contains_text,
        )
        rows.extend(file_rows)
        opened_count += opened
        layer_count += layers
        matched_count += matched
        error_count += errors

    summary = _inspection_summary(
        file_count=len(files),
        opened_count=opened_count,
        layer_count=layer_count,
        matched_count=matched_count,
        error_count=error_count,
        truncated=truncated,
    )
    _write_inspection_reports(destination, rows, summary)
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
    """Return a contained output path with safe existing ancestry.

    ``Path.resolve`` follows existing Windows junctions/reparse points as well
    as ordinary symlinks.  Checking each existing ancestor separately also
    rejects a regular file where a directory would be required.
    """

    try:
        canonical_destination = destination.resolve(strict=False)
    except OSError as error:
        raise ValueError("output directory could not be resolved") from error
    if destination.exists() and not destination.is_dir():
        raise ValueError("output directory is not a directory")
    candidate = destination / Path(relative)
    try:
        resolved_candidate = candidate.resolve(strict=False)
    except OSError as error:
        raise ValueError("output file could not be resolved") from error
    if not resolved_candidate.is_relative_to(canonical_destination):
        raise ValueError("output file would escape the output directory")

    current = destination
    for component in Path(relative).parts[:-1]:
        current = current / component
        if not (current.exists() or current.is_symlink()):
            break
        if not current.is_dir():
            raise ValueError("output path ancestor is not a directory")
        try:
            resolved_ancestor = current.resolve(strict=True)
        except OSError as error:
            raise ValueError("output path ancestor could not be resolved") from error
        if not resolved_ancestor.is_relative_to(canonical_destination):
            raise ValueError("output file would escape the output directory")
    return candidate


def _cleanup_created_output(
    output_path: Path,
    destination: Path,
    relative: str,
) -> str:
    """Remove only a failed output file that this invocation created."""

    try:
        safe_output = _output_file(destination, relative)
        if safe_output != output_path:
            raise ValueError("output cleanup path changed")
        safe_output.unlink(missing_ok=True)
    except Exception:
        return "OUTPUT_CLEANUP_FAILED"
    return ""


def _with_cleanup_marker(
    error_code: str,
    error_message: str,
    cleanup_error: str,
) -> tuple[str, str]:
    if not cleanup_error:
        return error_code, error_message
    code = f"{error_code};{cleanup_error}" if error_code else cleanup_error
    message = f"{error_message}; output cleanup failed"
    return code, message


def _matching_replacement_layers(
    layers: list[TextLayerInfo],
    *,
    old_text: str,
    layer_name: str | None,
) -> list[TextLayerInfo]:
    """The single authoritative exact-match implementation."""

    return [
        layer
        for layer in layers
        if layer.current_text == old_text
        and (layer_name is None or layer.layer_name == layer_name)
    ]


def _plan_replacement_candidate(
    source_path: Path,
    source: Path,
    destination: Path,
    adapter: SignatureAdapter,
    *,
    old_text: str,
    new_text: str,
    layer_name: str | None,
) -> dict:
    """Classify one candidate without creating or saving an output PSD."""

    relative = source_path.relative_to(source).as_posix()
    candidate_output = destination / Path(relative)
    if candidate_output.exists() or candidate_output.is_symlink():
        return _replace_row(
            relative=relative,
            status="SKIPPED_EXISTS",
            matched_count=0,
            changed_count=0,
            old_text=old_text,
            new_text=new_text,
        )
    try:
        _output_file(destination, relative)
    except ValueError as error:
        return _replace_row(
            relative=relative,
            status="FAILED_REPLACE",
            matched_count=0,
            changed_count=0,
            old_text=old_text,
            new_text=new_text,
            error_code="OUTPUT_PATH_ESCAPE",
            error_message=str(error),
        )

    try:
        layers = adapter.inspect_text_layers(source_path)
    except Exception as error:
        code, message = _error_details(error, "PHOTOSHOP_OPEN_FAILED")
        status = "FAILED_OPEN" if code.endswith("OPEN_FAILED") else "FAILED_REPLACE"
        return _replace_row(
            relative=relative,
            status=status,
            matched_count=0,
            changed_count=0,
            old_text=old_text,
            new_text=new_text,
            error_code=code,
            error_message=message,
        )

    matches = _matching_replacement_layers(
        layers,
        old_text=old_text,
        layer_name=layer_name,
    )
    if not matches:
        return _replace_row(
            relative=relative,
            status="SKIPPED_NO_MATCH",
            matched_count=0,
            changed_count=0,
            old_text=old_text,
            new_text=new_text,
        )
    if len(matches) > 1:
        return _replace_row(
            relative=relative,
            status="SKIPPED_AMBIGUOUS",
            matched_count=len(matches),
            changed_count=0,
            old_text=old_text,
            new_text=new_text,
        )
    return _replace_row(
        relative=relative,
        status="WOULD_REPLACE",
        matched_count=1,
        changed_count=0,
        old_text=old_text,
        new_text=new_text,
    )


def _execute_planned_replacement(
    source_path: Path,
    destination: Path,
    relative: str,
    adapter: SignatureAdapter,
    *,
    old_text: str,
    new_text: str,
    layer_name: str | None,
) -> dict:
    """Execute one confirmed match using the existing copy/fail-clean contract."""

    try:
        output_path = _output_file(destination, relative)
    except ValueError as error:
        return _replace_row(
            relative=relative,
            status="FAILED_REPLACE",
            matched_count=1,
            changed_count=0,
            old_text=old_text,
            new_text=new_text,
            error_code="OUTPUT_PATH_ESCAPE",
            error_message=str(error),
        )

    output_created_this_run = False
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _output_file(destination, relative)
        try:
            output_path.touch(exist_ok=False)
        except FileExistsError:
            return _replace_row(
                relative=relative,
                status="SKIPPED_EXISTS",
                matched_count=1,
                changed_count=0,
                old_text=old_text,
                new_text=new_text,
            )
        output_created_this_run = True
        copy2(source_path, output_path)
        result = adapter.replace_exact_text(
            output_path,
            old_text,
            new_text,
            layer_name=layer_name,
        )
        if result.matched_layer_count != 1 or result.changed_layer_count != 1:
            cleanup_error = _cleanup_created_output(
                output_path,
                destination,
                relative,
            )
            error_code, error_message = _with_cleanup_marker(
                "MATCH_CHANGED_BEFORE_SAVE",
                "Exact match count changed before output save",
                cleanup_error,
            )
            return _replace_row(
                relative=relative,
                status="FAILED_REPLACE",
                matched_count=result.matched_layer_count,
                changed_count=result.changed_layer_count,
                old_text=old_text,
                new_text=new_text,
                error_code=error_code,
                error_message=error_message,
            )
    except Exception as error:
        code, message = _error_details(error, "PHOTOSHOP_REPLACE_FAILED")
        cleanup_error = ""
        if output_created_this_run:
            cleanup_error = _cleanup_created_output(
                output_path,
                destination,
                relative,
            )
        code, message = _with_cleanup_marker(code, message, cleanup_error)
        status = (
            "FAILED_SAVE"
            if code.startswith("PHOTOSHOP_SAVE_FAILED")
            else "FAILED_REPLACE"
        )
        return _replace_row(
            relative=relative,
            status=status,
            matched_count=1,
            changed_count=0,
            old_text=old_text,
            new_text=new_text,
            error_code=code,
            error_message=message,
        )

    return _replace_row(
        relative=relative,
        status="REPLACED",
        matched_count=1,
        changed_count=1,
        old_text=old_text,
        new_text=new_text,
    )


def _decision_for_status(status: str) -> str:
    return {
        "SKIPPED_NO_MATCH": "SKIP_NO_MATCH",
        "SKIPPED_AMBIGUOUS": "SKIP_AMBIGUOUS",
        "SKIPPED_EXISTS": "SKIP_EXISTS",
        "FAILED_OPEN": "ERROR",
        "FAILED_REPLACE": "ERROR",
        "FAILED_SAVE": "ERROR",
    }.get(status, status)


def _plan_report_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "relative_path": row["relative_path"],
            "decision": _decision_for_status(row["status"]),
            "matched_layer_count": row["matched_layer_count"],
            "old_text": row["old_text"],
            "new_text": row["new_text"],
            "output_relative_path": row["output_relative_path"],
            "error_code": row["error_code"],
            "error_message": row["error_message"],
        }
        for row in rows
    ]


def _replacement_summary(
    rows: list[dict],
    *,
    file_count: int,
    truncated: bool,
    dry_run: bool,
) -> dict:
    return {
        "command": "signature-replace",
        "dry_run": dry_run,
        "file_count": file_count,
        "status_counts": dict(
            sorted(Counter(row["status"] for row in rows).items())
        ),
        "matched_layer_count": sum(row["matched_layer_count"] for row in rows),
        "changed_layer_count": sum(row["changed_layer_count"] for row in rows),
        "max_files_reached": truncated,
    }


def _write_plan_reports(destination: Path, rows: list[dict], summary: dict) -> None:
    plan_rows = _plan_report_rows(rows)
    write_csv(destination / "planned_changes.csv", plan_rows, PLAN_FIELDS)
    write_jsonl(destination / "planned_changes.jsonl", plan_rows)
    write_json(destination / "summary.json", summary)


def _write_replacement_reports(
    destination: Path,
    rows: list[dict],
    summary: dict,
) -> None:
    write_csv(destination / "signature_replace_results.csv", rows, REPLACE_FIELDS)
    write_jsonl(destination / "signature_replace_results.jsonl", rows)
    write_json(destination / "summary.json", summary)


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
        planned = _plan_replacement_candidate(
            source_path,
            source,
            destination,
            adapter,
            old_text=old_text,
            new_text=new_text,
            layer_name=layer_name,
        )
        if dry_run or planned["status"] != "WOULD_REPLACE":
            rows.append(planned)
            continue
        rows.append(
            _execute_planned_replacement(
                source_path,
                destination,
                planned["relative_path"],
                adapter,
                old_text=old_text,
                new_text=new_text,
                layer_name=layer_name,
            )
        )

    summary = _replacement_summary(
        rows,
        file_count=len(files),
        truncated=truncated,
        dry_run=dry_run,
    )

    if dry_run:
        _write_plan_reports(destination, rows, summary)
    else:
        _write_replacement_reports(destination, rows, summary)
    return summary
