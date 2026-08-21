"""Size-prefiltered, streaming SHA-256 duplicate candidates."""

from __future__ import annotations

from collections import defaultdict
import hashlib
from pathlib import Path
from typing import Iterable


CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path, chunk_size: int = CHUNK_SIZE) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def find_duplicate_candidates(files: Iterable[tuple[str, Path, int]]) -> dict:
    by_size: dict[int, list[tuple[str, Path]]] = defaultdict(list)
    for relative_path, path, size in files:
        by_size[size].append((relative_path, path))

    groups: list[dict] = []
    errors: list[dict] = []
    for size in sorted(by_size):
        candidates = by_size[size]
        if len(candidates) < 2:
            continue
        by_digest: dict[str, list[str]] = defaultdict(list)
        for relative_path, path in sorted(candidates, key=lambda item: item[0]):
            try:
                by_digest[sha256_file(path)].append(relative_path)
            except OSError as error:
                errors.append({"relative_path": relative_path, "error": type(error).__name__})
        for digest in sorted(by_digest):
            paths = sorted(by_digest[digest], key=lambda value: (value.casefold(), value))
            if len(paths) >= 2:
                groups.append({"sha256": digest, "size": size, "paths": paths})
    groups.sort(key=lambda item: (item["size"], item["sha256"]))
    errors.sort(key=lambda item: (item["relative_path"].casefold(), item["relative_path"]))
    return {"groups": groups, "errors": errors}
