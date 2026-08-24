# Third-party notices for the Windows portable build

This notice applies to the v0.3.0 Windows x64 standalone portable build. It is
a technical redistribution record, not legal advice.

## Application source

`design-asset-indexer` is licensed under the MIT License. `LICENSE.txt` is
included in the portable directory.

## Python runtime

- Component: CPython 3.11 x64
- License family: Python Software Foundation License
- License text: under `LICENSES/Python/`
- Source: https://www.python.org/downloads/source/

## PySide6, Shiboken6, and Qt

- Components: PySide6 6.11.2, Shiboken6 6.11.2, Qt 6.11.2 shared libraries
- Selected community license family: LGPL version 3
- Alternative licenses published upstream: GPLv2/GPLv3 or commercial terms
- LGPLv3 / GPLv3 texts: `LICENSES/LGPL-3.0.txt` and
  `LICENSES/GPL-3.0.txt`; installed-distribution notices are under
  `LICENSES/QtForPython/`
- Qt DLLs and plugins remain separate files; this build does not statically
  link Qt and is not onefile.
- The executable is unsigned and has no DRM or installer restriction that
  prevents replacement of ABI-compatible shared components.

See `QT_LGPL_SOURCE_OFFER.md` and `QT_RELINK_INSTRUCTIONS.md`.

## Pillow

- Component: Pillow 12.3.0
- License expression: MIT-CMU
- Installed-distribution license text: under `LICENSES/Pillow/`
- Source: https://github.com/python-pillow/Pillow

## pywin32

- Component: pywin32 312
- License family: Python Software Foundation / component-specific notices
- Installed-distribution license texts: under `LICENSES/pywin32/`
- Source: https://github.com/mhammond/pywin32

## Nuitka build tool

- Build tool: Nuitka 4.1.1
- Nuitka compiles the launcher and Python modules; it is not installed on the
  recipient's system by this portable package.
- Installed-distribution notices are under `LICENSES/Nuitka/`.
- Source: https://github.com/Nuitka/Nuitka

## Microsoft runtime files

The portable directory may include Microsoft runtime DLLs supplied with the
official Python or PySide6 wheels. Actual files are recorded in
`BUILD_PROVENANCE.json` and `BUNDLE_INVENTORY.json`.

## No Adobe redistribution

Adobe Photoshop, Adobe DLLs, typelibs, fonts, and private components are not
bundled. PSD writes require a separately installed compatible Photoshop.
