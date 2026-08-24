# Third-party GUI notices

The project's own source code remains licensed under the MIT License. The GUI
optional dependency is a separate third-party work with its own licensing.

## PySide6 / Qt for Python

- Package: PySide6 (Qt for Python)
- Versions verified for this development phase: 6.11.1 and 6.11.2
- Current stable version verified by fresh install on 2026-08-23: 6.11.2
- Project dependency range: `PySide6>=6.11.1,<7`
- License family published by the PySide6 project: LGPLv3 or GPLv2/GPLv3
  community distribution, or Qt commercial licensing
- Official project and license overview:
  https://doc.qt.io/qtforpython-6/
- Official Qt licensing overview:
  https://www.qt.io/licensing/
- PyPI package:
  https://pypi.org/project/PySide6/

## Distribution approach

PySide6 is an optional `gui` extra and is not required for the base CLI wheel.
The official v0.3.0 release uses a Windows x64 standalone
directory, with Qt shared DLLs and plugins kept as separate replaceable files.
It does not use onefile packing, an installer, DRM, UPX, code signing, telemetry,
or automatic updates. The bundle-specific inventory, notices, Qt LGPL source
route, relinking instructions, and build provenance are maintained under
[`packaging/windows/`](../packaging/windows/).

The Windows x64 portable ZIP is distributed through the project's official
GitHub Release. Its executable is unsigned, so Windows may show Unknown
publisher or SmartScreen; download only from the official Release and verify
the published SHA-256.

This notice records dependency provenance and license families; it is not a
final legal opinion.
