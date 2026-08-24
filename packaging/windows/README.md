# Windows x64 portable packaging

This directory is the auditable source of truth for the official v0.3.0
Premium Simple Windows portable release.

## Architecture

- official `pyside6-deploy` wrapper with the Nuitka 4.1.1 backend
- Windows x86_64 `standalone` directory mode
- Qt shared DLLs and plugins remain separate and replaceable
- no onefile, installer, updater, UPX, icon, code signing, telemetry, or Adobe
  components
- a thin launcher that delegates directly to
  `design_asset_indexer.gui.app:main`

`pysidedeploy.spec` records the Qt Widgets modules and plugins used by the
application. The build rejects unexplained QtWebEngine, QtQuick, QML,
QtMultimedia, and Qt3D payloads.

PySide6 6.11.2 currently injects its own default icon whenever
`pyside6-deploy` runs a build, even when the spec leaves `icon` empty. Because
this repository has no approved original icon, the script records the official
`pyside6-deploy --dry-run` command and invokes its pinned Nuitka 4.1.1 backend
with the same standalone settings while intentionally omitting only that
default-icon option. No alternative packager or image asset is used.

## Isolated build environment

Use Python 3.11 x64 and do not install packaging tools globally:

```powershell
py -3.11 -m venv .venv-package-v030
& ".\.venv-package-v030\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv-package-v030\Scripts\python.exe" -m pip install -e ".[dev]" -r ".\packaging\windows\requirements-build.txt"
```

Then run:

```powershell
& ".\packaging\windows\build_portable.ps1" `
  -ExpectedSourceCommit <exact-40-character-main-SHA>
```

The script requires a clean source tree and deletes only these validated,
ignored, disposable directories:

```text
packaging/windows/.build/
packaging/windows/.dist/
packaging/windows/.release/
```

It never tags, publishes, uploads, installs globally, or reads user PSD files.

## Official release distribution

The Windows x64 portable ZIP is distributed through the project's official
GitHub Release. The executable is unsigned, so Windows may show Unknown
publisher or SmartScreen. Download only from the official Release and verify
the published SHA-256. Review `THIRD_PARTY_NOTICES.md`,
`QT_LGPL_SOURCE_OFFER.md`, and `QT_RELINK_INSTRUCTIONS.md` before
redistribution.
