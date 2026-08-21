# design-asset-indexer

A privacy-first, offline CLI for indexing large local design-asset archives
without uploading files anywhere.

## What it does

`design-asset-index` recursively inventories a directory, detects common asset
formats by file signature, reads basic PSD/PSB metadata, exports embedded PSD
JPEG thumbnails when present, lists ZIP members without extraction, and finds
byte-identical duplicate candidates with SHA-256. Reports are deterministic
CSV, JSONL, and JSON files.

An optional command builds a contact sheet from a preview directory. Small
helpers also provide 64-bit dHash and Hamming distance for similarity hints.

## Why it exists

Large local design archives often mix layered documents, images, archives, and
damaged files. This tool provides a reproducible inventory without requiring
Photoshop, a database, a cloud account, or an upload step.

## Privacy model

- Offline: no network client and no telemetry.
- No uploads: files stay on the local machine.
- Read-only input: scan never writes to the input tree.
- Explicit output: generated reports and previews go only to `--out`.
- ZIP-safe: archive members are listed, never extracted or executed.

Reports include relative filenames from the selected input. Review reports
before sharing them.

## 5-minute Quick Start

Python 3.11 or newer is required.

```console
python -m venv .venv
# Windows: .venv\Scripts\python -m pip install -e ".[dev]"
# Linux/macOS: .venv/bin/python -m pip install -e ".[dev]"
python tests/generate_fixtures.py
design-asset-index scan tests/fixtures/synthetic --out scan-output
```

Build a contact sheet from extracted previews:

```console
design-asset-index contact-sheet scan-output/previews --out scan-output/contact-sheet.jpg
```

## Output files

- `inventory.csv` and `inventory.jsonl`: stable, relative-path inventory.
- `archives.jsonl`: one bounded ZIP directory record per archive.
- `duplicates.json`: byte-identical SHA-256 candidate groups.
- `previews.jsonl`: safe-name mappings for embedded PSD JPEG previews.
- `summary.json`: aggregate counts and non-fatal error totals.

## Supported formats

- PSD: basic header and image-resource parsing, including embedded JPEG
  thumbnail resources when valid.
- PSB: signature and basic header/resource parsing; broader PSB features are
  intentionally out of scope.
- JPEG, PNG, GIF: signature detection and dimensions through Pillow.
- ZIP: directory indexing only, with an entry-count safety limit.
- Other files: included in inventory as `OTHER`.

RAR is not supported in v0.1.

## Safety guarantees

The implementation does not intentionally mutate inputs, follow directory
symlinks, extract ZIP entries, delete duplicates, upload data, or emit
telemetry. Output nested inside the input directory is rejected.

## Limitations

- The PSD/PSB parser is deliberately minimal and does not render composites,
  decode layers, or validate every Photoshop feature.
- Embedded preview extraction supports JPEG thumbnail resources only.
- dHash is a low-resolution similarity hint, not proof of duplication.
- Very large or malformed resource sections and ZIP entry lists are rejected
  by safety limits.

## Development and tests

```console
python tests/generate_fixtures.py
python -m pytest
python -m build
```

Fixtures are generated from synthetic geometry and text. Binary fixtures are
ignored by Git and can be regenerated at any time.

## 中文简介

这是一个本地离线、输入只读的设计素材索引 CLI。它不会上传文件或发送
遥测；公开示例与测试只使用程序生成的 synthetic fixtures。

## License

MIT. See `LICENSE`. Pillow is a separate runtime dependency under its own
`MIT-CMU` license expression.
