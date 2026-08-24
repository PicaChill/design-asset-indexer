from __future__ import annotations

import configparser
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WINDOWS_PACKAGING = ROOT / "packaging" / "windows"


def test_portable_spec_is_auditable_standalone_configuration():
    config = configparser.ConfigParser(interpolation=None)
    config.read(WINDOWS_PACKAGING / "pysidedeploy.spec", encoding="utf-8")

    assert config["nuitka"]["mode"] == "standalone"
    assert "onefile" not in config["nuitka"]["extra_args"].lower()
    assert config["app"]["title"] == "DesignAssetIndexer"
    assert config["app"]["input_file"] == "launcher.py"
    assert config["app"]["project_dir"] == "../.."
    assert config["app"]["project_file"] == ""
    assert config["app"]["exec_directory"] == ".build/deploy"
    assert config["app"]["icon"] == ""
    assert config["qt"]["modules"].split(",") == ["Core", "Gui", "Widgets"]
    assert config["qt"]["qml_files"] == ""
    assert config["qt"]["plugins"].split(",") == [
        "platforms",
        "styles",
        "imageformats",
        "iconengines",
    ]
    extra_args = config["nuitka"]["extra_args"]
    assert "--windows-console-mode=disable" in extra_args
    assert "--noinclude-dlls=*/imageformats/qpdf.dll" in extra_args
    assert "--noinclude-dlls=qt6pdf.dll" in extra_args
    assert "--output-filename=DesignAssetIndexer.exe" in extra_args
    assert '--product-name="Design Asset Indexer"' in extra_args
    assert "--product-version=0.3.0" in extra_args
    assert "--file-version=0.3.0.0" in extra_args


def test_portable_launcher_is_only_a_thin_gui_delegate():
    source = (WINDOWS_PACKAGING / "launcher.py").read_text(encoding="utf-8")
    assert source.count("design_asset_indexer.gui.app") == 1
    assert "from design_asset_indexer.gui.app import main" in source
    assert "raise SystemExit(main())" in source
    for forbidden in ("PhotoshopAdapter", "WorkflowController", "win32com", "requests"):
        assert forbidden not in source


def test_build_script_has_bounded_release_contract():
    source = (WINDOWS_PACKAGING / "build_portable.ps1").read_text(encoding="utf-8")
    required = (
        "DeployMode=standalone",
        "Onefile=NO",
        "design-asset-indexer-v$Version-windows-x64",
        "DesignAssetIndexer.exe",
        "BUILD_PROVENANCE.json",
        "BUNDLE_INVENTORY.json",
        "SHA256SUMS.txt",
        "QT_LGPL_SOURCE_OFFER.md",
        "QT_RELINK_INSTRUCTIONS.md",
        "licenses\\LGPL-3.0.txt",
        "licenses\\GPL-3.0.txt",
        "Unexplained Qt modules were bundled",
        "Release builds require a clean source tree",
        "[string]$ExpectedSourceCommit",
        "ExpectedSourceCommit does not match HEAD",
        "Release source version must be 0.3.0",
        "source_commit = $ExpectedSourceCommit",
        "--dry-run",
    )
    assert all(value in source for value in required)
    for forbidden in (
        "git clean",
        "git push",
        "gh release",
        "curl |",
        "Invoke-WebRequest",
        "--onefile",
    ):
        assert forbidden.lower() not in source.lower()
    assert "upx = $false" in source.lower()
    assert "pywin32_auto_detected = $true" in source.lower()
    assert "pywin32_explicit_include_required = $false" in source.lower()
    assert "--windows-icon-from-ico" not in source


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell syntax is Windows-only")
def test_build_script_parses_in_windows_powershell():
    powershell = shutil.which("powershell")
    assert powershell is not None
    script_path = str(WINDOWS_PACKAGING / "build_portable.ps1").replace("'", "''")
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "[scriptblock]::Create((Get-Content -Raw -LiteralPath "
            f"'{script_path}')) | Out-Null",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell gate is Windows-only")
def test_build_script_rejects_a_source_commit_mismatch_before_building():
    powershell = shutil.which("powershell")
    assert powershell is not None
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(WINDOWS_PACKAGING / "build_portable.ps1"),
            "-PythonPath",
            sys.executable,
            "-ExpectedSourceCommit",
            "0" * 40,
        ],
        capture_output=True,
        check=False,
    )
    output = (result.stdout or b"") + (result.stderr or b"")
    assert result.returncode != 0
    assert b"ExpectedSourceCommit does not match HEAD" in output


def test_packaging_source_has_no_private_paths_or_binary_fonts():
    absolute_windows_path = re.compile(r"(?<![a-z])[a-z]:[\\/]", re.IGNORECASE)
    for path in WINDOWS_PACKAGING.rglob("*"):
        if not path.is_file():
            continue
        relative_parts = path.relative_to(WINDOWS_PACKAGING).parts
        if any(part in {".build", ".dist", ".release"} for part in relative_parts):
            continue
        assert path.suffix.lower() not in {".ttf", ".otf", ".woff", ".woff2"}
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert not absolute_windows_path.search(text), path


def test_required_distribution_license_texts_are_present():
    assert (WINDOWS_PACKAGING / "licenses" / "LGPL-3.0.txt").stat().st_size > 7_000
    assert (WINDOWS_PACKAGING / "licenses" / "GPL-3.0.txt").stat().st_size > 30_000


def test_v030_metadata_and_public_docs_are_synchronized():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    init_source = (ROOT / "src" / "design_asset_indexer" / "__init__.py").read_text(
        encoding="utf-8"
    )
    window_source = (
        ROOT / "src" / "design_asset_indexer" / "gui" / "premium_simple_window.py"
    ).read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "WINDOWS_PSD_SIGNATURE_GUIDE_CN.md").read_text(
        encoding="utf-8"
    )
    assert project["version"] == "0.3.0"
    assert '__version__ = "0.3.0"' in init_source
    assert "· 开发版" not in window_source
    assert "## 0.3.0 - 2026-08-24" in (ROOT / "CHANGELOG.md").read_text(
        encoding="utf-8"
    )
    assert "DesignAssetIndexer.exe" in readme
    assert "portable 用户不需要另外安装 Python" in readme
    assert "GUI、exe 或一键安装包" not in readme
    assert "v0.2.0" not in guide
    assert "design-asset-indexer-v020" not in guide


def test_normal_wheel_dependencies_do_not_include_packaging_toolchain():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    assert all("Nuitka" not in dependency for dependency in project["dependencies"])
    assert all("PySide6" not in dependency for dependency in project["dependencies"])
