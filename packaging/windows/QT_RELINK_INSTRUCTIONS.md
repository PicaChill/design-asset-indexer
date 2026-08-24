# Replacing Qt / PySide6 shared components

This v0.3.0 Windows x64 portable build keeps Qt, PySide6, and Shiboken shared
DLL, PYD, and plugin files separate. It is not onefile, statically linked, or
protected by DRM.

1. Fully extract the portable ZIP to a writable test directory.
2. Keep an untouched backup of that directory.
3. Obtain the matching source listed in `QT_LGPL_SOURCE_OFFER.md`.
4. Build ABI-compatible Qt 6.11.2 and PySide6 / Shiboken6 6.11.2 shared
   components for Windows x64.
5. Replace the corresponding separate `Qt6*.dll`, PySide6 / Shiboken `.pyd`
   and `.dll`, and plugin files while preserving relative names and paths.
6. Run `DesignAssetIndexer.exe` from the modified directory and repeat the
   environment, GUI, inspect, plan, and synthetic-output checks.

The application does not verify signatures or hashes of replacement Qt files.
Windows loader and Qt ABI compatibility requirements still apply. The
application source and portable build recipe are available in the repository
so recipients can rebuild and test a relinked combination.
