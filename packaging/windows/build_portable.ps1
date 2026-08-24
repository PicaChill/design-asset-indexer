[CmdletBinding()]
param(
    [string]$PythonPath
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$PackagingRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PackagingRoot "..\.."))
$BuildRoot = Join-Path $PackagingRoot ".build"
$DistRoot = Join-Path $PackagingRoot ".dist"
$ReleaseRoot = Join-Path $PackagingRoot ".release"
$Version = "0.3.0"
$PortableName = "design-asset-indexer-v$Version-windows-x64"

if (-not $PythonPath) {
    $PythonPath = Join-Path $ProjectRoot ".venv-package-v030\Scripts\python.exe"
}
$PythonPath = [System.IO.Path]::GetFullPath($PythonPath)

function Reset-DisposableDirectory {
    param([Parameter(Mandatory)][string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $allowedPrefix = $PackagingRoot.TrimEnd("\") + "\"
    if (-not $fullPath.StartsWith(
        $allowedPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Refusing to clean a path outside packaging/windows: $fullPath"
    }
    $isDeclared = @($BuildRoot, $DistRoot, $ReleaseRoot) |
        Where-Object { $_.Equals($fullPath, [System.StringComparison]::OrdinalIgnoreCase) }
    if (-not $isDeclared) {
        throw "Refusing to clean an undeclared directory: $fullPath"
    }
    if (Test-Path -LiteralPath $fullPath) {
        Remove-Item -LiteralPath $fullPath -Recurse -Force
    }
    New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath"
    }
}

function Copy-DistributionLicenses {
    param(
        [Parameter(Mandatory)][string]$SitePackages,
        [Parameter(Mandatory)][string[]]$Patterns,
        [Parameter(Mandatory)][string]$Destination
    )

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $copied = 0
    foreach ($pattern in $Patterns) {
        $metadataDirectories = @(Get-ChildItem -Path (Join-Path $SitePackages $pattern) -Directory)
        foreach ($metadataDirectory in $metadataDirectories) {
            $packageTarget = Join-Path $Destination $metadataDirectory.Name
            New-Item -ItemType Directory -Path $packageTarget -Force | Out-Null
            $licenseDirectory = Join-Path $metadataDirectory.FullName "licenses"
            if (Test-Path -LiteralPath $licenseDirectory -PathType Container) {
                Copy-Item -LiteralPath $licenseDirectory -Destination $packageTarget -Recurse
                $copied += 1
            }
            foreach ($name in @("LICENSE", "LICENSE.txt", "COPYING", "COPYING.txt")) {
                $candidate = Join-Path $metadataDirectory.FullName $name
                if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                    Copy-Item -LiteralPath $candidate -Destination $packageTarget
                    $copied += 1
                }
            }
        }
    }
    if ($copied -eq 0) {
        throw "Installed-package license metadata was not found for $($Patterns -join ', ')."
    }
}

if ($env:OS -ne "Windows_NT") {
    throw "Windows is required."
}
if (-not [Environment]::Is64BitOperatingSystem) {
    throw "Windows x64 is required."
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Isolated build Python was not found. See packaging/windows/README.md."
}

$gitStatus = @(& git -C $ProjectRoot status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0) {
    throw "Unable to read Git status."
}
if ($gitStatus.Count -ne 0) {
    throw "RC builds require a clean source tree."
}

$environmentJson = & $PythonPath -c @"
import json, platform, sys, sysconfig
from importlib.metadata import version
from PySide6.QtCore import qVersion
print(json.dumps({
    "is_venv": sys.prefix != sys.base_prefix,
    "python_version": platform.python_version(),
    "architecture": platform.machine(),
    "pyside6_version": version("PySide6"),
    "qt_version": qVersion(),
    "shiboken6_version": version("shiboken6"),
    "nuitka_version": version("Nuitka"),
    "pillow_version": version("Pillow"),
    "pywin32_version": version("pywin32"),
    "ordered_set_version": version("ordered-set"),
    "zstandard_version": version("zstandard"),
    "python_root": sys.base_prefix,
    "site_packages": sysconfig.get_paths()["purelib"],
}, ensure_ascii=True))
"@
if ($LASTEXITCODE -ne 0) {
    throw "Unable to read build environment versions."
}
$environment = $environmentJson | ConvertFrom-Json

if (-not $environment.is_venv) { throw "Build Python must be an isolated venv." }
if ($environment.architecture -notmatch "AMD64|x86_64") {
    throw "Build Python must be x64."
}
if ($environment.python_version -notlike "3.11.*") { throw "Python must be 3.11.x." }
if ($environment.pyside6_version -ne "6.11.2") { throw "PySide6 must be 6.11.2." }
if ($environment.qt_version -ne "6.11.2") { throw "Qt must be 6.11.2." }
if ($environment.shiboken6_version -ne "6.11.2") { throw "Shiboken6 must be 6.11.2." }
if ($environment.nuitka_version -ne "4.1.1") { throw "Nuitka must be 4.1.1." }
if ($environment.pillow_version -ne "12.3.0") { throw "Pillow must be 12.3.0." }
if ($environment.pywin32_version -ne "312") { throw "pywin32 must be 312." }

Write-Host "Python=$($environment.python_version)"
Write-Host "Architecture=$($environment.architecture)"
Write-Host "PySide6=$($environment.pyside6_version)"
Write-Host "Qt=$($environment.qt_version)"
Write-Host "Shiboken6=$($environment.shiboken6_version)"
Write-Host "Nuitka=$($environment.nuitka_version)"
Write-Host "Pillow=$($environment.pillow_version)"
Write-Host "pywin32=$($environment.pywin32_version)"
Write-Host "DeployMode=standalone"
Write-Host "Onefile=NO"

Reset-DisposableDirectory -Path $BuildRoot
Reset-DisposableDirectory -Path $DistRoot
Reset-DisposableDirectory -Path $ReleaseRoot

$DeployTool = Join-Path (Split-Path -Parent $PythonPath) "pyside6-deploy.exe"
if (-not (Test-Path -LiteralPath $DeployTool -PathType Leaf)) {
    throw "pyside6-deploy was not found in the isolated venv."
}

$DeployLog = Join-Path $BuildRoot "pyside6-deploy.log"
$RuntimeSpec = Join-Path $PackagingRoot "pysidedeploy.runtime.spec"
Copy-Item -LiteralPath (Join-Path $PackagingRoot "pysidedeploy.spec") -Destination $RuntimeSpec
Push-Location $PackagingRoot
try {
    & $DeployTool -c ".\pysidedeploy.runtime.spec" --force 2>&1 |
        Tee-Object -FilePath $DeployLog
    if ($LASTEXITCODE -ne 0) {
        throw "pyside6-deploy failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
    if (Test-Path -LiteralPath $RuntimeSpec -PathType Leaf) {
        Remove-Item -LiteralPath $RuntimeSpec -Force
    }
}

$DeployDirectory = Join-Path $BuildRoot "deploy\DesignAssetIndexer.dist"
$BuiltExe = Join-Path $DeployDirectory "DesignAssetIndexer.exe"
if (-not (Test-Path -LiteralPath $BuiltExe -PathType Leaf)) {
    throw "Expected standalone executable was not produced: DesignAssetIndexer.exe"
}

$NuitkaReport = Join-Path $BuildRoot "nuitka-compilation-report.xml"
if (-not (Test-Path -LiteralPath $NuitkaReport -PathType Leaf)) {
    throw "Nuitka compilation report was not produced."
}
$reportText = Get-Content -Raw -LiteralPath $NuitkaReport
foreach ($requiredModule in @("win32com.client", "pythoncom", "pywintypes")) {
    if ($reportText -notmatch [regex]::Escape($requiredModule)) {
        throw "Nuitka did not automatically detect required module: $requiredModule"
    }
}

$PortableRoot = Join-Path $DistRoot $PortableName
New-Item -ItemType Directory -Path $PortableRoot -Force | Out-Null
Copy-Item -Path (Join-Path $DeployDirectory "*") -Destination $PortableRoot -Recurse -Force

$ForbiddenQtPattern = "Qt6(WebEngine|WebChannel|Quick|Qml|Multimedia|3D|Positioning|Bluetooth|SerialBus|Pdf)"
$ForbiddenQtFiles = @(
    Get-ChildItem -LiteralPath $PortableRoot -Recurse -File |
        Where-Object { $_.Name -match $ForbiddenQtPattern }
)
if ($ForbiddenQtFiles.Count -gt 0) {
    $names = ($ForbiddenQtFiles | ForEach-Object { $_.Name } | Sort-Object -Unique) -join ", "
    throw "Unexplained Qt modules were bundled: $names"
}

Copy-Item -LiteralPath (Join-Path $ProjectRoot "LICENSE") -Destination (Join-Path $PortableRoot "LICENSE.txt")
Copy-Item -LiteralPath (Join-Path $PackagingRoot "README_PORTABLE.txt") -Destination (Join-Path $PortableRoot "README.txt")
foreach ($notice in @(
    "THIRD_PARTY_NOTICES.md",
    "QT_LGPL_SOURCE_OFFER.md",
    "QT_RELINK_INSTRUCTIONS.md"
)) {
    Copy-Item -LiteralPath (Join-Path $PackagingRoot $notice) -Destination (Join-Path $PortableRoot $notice)
}

$LicenseRoot = Join-Path $PortableRoot "LICENSES"
New-Item -ItemType Directory -Path $LicenseRoot -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PackagingRoot "licenses\LGPL-3.0.txt") `
    -Destination (Join-Path $LicenseRoot "LGPL-3.0.txt")
Copy-Item -LiteralPath (Join-Path $PackagingRoot "licenses\GPL-3.0.txt") `
    -Destination (Join-Path $LicenseRoot "GPL-3.0.txt")
$PythonLicenseRoot = Join-Path $LicenseRoot "Python"
New-Item -ItemType Directory -Path $PythonLicenseRoot -Force | Out-Null
Copy-Item -LiteralPath (Join-Path ([string]$environment.python_root) "LICENSE.txt") `
    -Destination (Join-Path $PythonLicenseRoot "LICENSE.txt")
$SitePackages = [string]$environment.site_packages
Copy-DistributionLicenses -SitePackages $SitePackages `
    -Patterns @("PySide6-*.dist-info", "PySide6_Essentials-*.dist-info", "shiboken6-*.dist-info") `
    -Destination (Join-Path $LicenseRoot "QtForPython")
Copy-DistributionLicenses -SitePackages $SitePackages -Patterns @("Pillow-*.dist-info") `
    -Destination (Join-Path $LicenseRoot "Pillow")
Copy-DistributionLicenses -SitePackages $SitePackages -Patterns @("pywin32-*.dist-info") `
    -Destination (Join-Path $LicenseRoot "pywin32")
Copy-DistributionLicenses -SitePackages $SitePackages -Patterns @("Nuitka-*.dist-info") `
    -Destination (Join-Path $LicenseRoot "Nuitka")
if (-not (Get-ChildItem -LiteralPath $LicenseRoot -Recurse -File |
    Where-Object { $_.Name -match "^LGPL-3\.0" } | Select-Object -First 1)) {
    throw "The Qt LGPLv3 license text was not assembled."
}

$PythonArtifacts = Join-Path $ReleaseRoot "python"
New-Item -ItemType Directory -Path $PythonArtifacts -Force | Out-Null
Invoke-Checked -FilePath $PythonPath -Arguments @(
    "-m", "build", "--outdir", $PythonArtifacts, $ProjectRoot
)
$Wheels = @(Get-ChildItem -LiteralPath $PythonArtifacts -File -Filter "*.whl")
$Sdists = @(Get-ChildItem -LiteralPath $PythonArtifacts -File -Filter "*.tar.gz")
if ($Wheels.Count -ne 1 -or $Sdists.Count -ne 1) {
    throw "Expected exactly one wheel and one source distribution."
}
$Wheel = $Wheels[0]
$Sdist = $Sdists[0]
if ($Wheel.Name -ne "design_asset_indexer-0.3.0-py3-none-any.whl") {
    throw "Unexpected wheel name: $($Wheel.Name)"
}
if ($Sdist.Name -ne "design_asset_indexer-0.3.0.tar.gz") {
    throw "Unexpected sdist name: $($Sdist.Name)"
}

$GitSha = (& git -C $ProjectRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw "Unable to read Git SHA." }
$ExePath = Join-Path $PortableRoot "DesignAssetIndexer.exe"
$ExeSha = (Get-FileHash -LiteralPath $ExePath -Algorithm SHA256).Hash.ToLowerInvariant()
$WheelSha = (Get-FileHash -LiteralPath $Wheel.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$SdistSha = (Get-FileHash -LiteralPath $Sdist.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$ReportSha = (Get-FileHash -LiteralPath $NuitkaReport -Algorithm SHA256).Hash.ToLowerInvariant()
$QtDlls = @(
    Get-ChildItem -LiteralPath $PortableRoot -Recurse -File -Filter "Qt6*.dll" |
        ForEach-Object { $_.FullName.Substring($PortableRoot.Length + 1).Replace("\", "/") } |
        Sort-Object -Unique
)
$MicrosoftRuntimeFiles = @(
    Get-ChildItem -LiteralPath $PortableRoot -Recurse -File |
        Where-Object { $_.Name -match "^(vcruntime|msvcp|ucrtbase|api-ms-win-crt).*\.dll$" } |
        ForEach-Object { $_.FullName.Substring($PortableRoot.Length + 1).Replace("\", "/") } |
        Sort-Object -Unique
)

$Provenance = [ordered]@{
    project = "design-asset-indexer"
    version = $Version
    source_commit = $GitSha
    source_tree_clean = $true
    build_timestamp_utc = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
    build_os = [Environment]::OSVersion.VersionString
    architecture = "windows-x64"
    python_version = $environment.python_version
    pyside6_version = $environment.pyside6_version
    qt_version = $environment.qt_version
    shiboken6_version = $environment.shiboken6_version
    nuitka_version = $environment.nuitka_version
    pillow_version = $environment.pillow_version
    pywin32_version = $environment.pywin32_version
    packaging_stack = "pyside6-deploy/Nuitka"
    deploy_mode = "standalone"
    onefile = $false
    installer = $false
    code_signed = $false
    upx = $false
    telemetry = $false
    photoshop_bundled = $false
    adobe_private_components_bundled = $false
    pywin32_auto_detected = $true
    pywin32_explicit_include_required = $false
    qt_shared_libraries = $QtDlls
    qt_static_linking = $false
    microsoft_runtime_files = $MicrosoftRuntimeFiles
    nuitka_compilation_report_sha256 = $ReportSha
    bundle_inventory = "BUNDLE_INVENTORY.json"
    artifacts = [ordered]@{
        portable_exe = [ordered]@{ name = "DesignAssetIndexer.exe"; sha256 = $ExeSha }
        portable_zip = [ordered]@{ name = "$PortableName.zip"; sha256 = "recorded in SHA256SUMS.txt" }
        wheel = [ordered]@{ name = $Wheel.Name; sha256 = $WheelSha }
        sdist = [ordered]@{ name = $Sdist.Name; sha256 = $SdistSha }
    }
    reproducible_build = "NOT_CLAIMED"
}
$Provenance | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $PortableRoot "BUILD_PROVENANCE.json") -Encoding utf8

$Inventory = @(
    Get-ChildItem -LiteralPath $PortableRoot -Recurse -File |
        Sort-Object FullName |
        ForEach-Object {
            [ordered]@{
                path = $_.FullName.Substring($PortableRoot.Length + 1).Replace("\", "/")
                size = $_.Length
                sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        }
)
$Inventory | ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath (Join-Path $PortableRoot "BUNDLE_INVENTORY.json") -Encoding utf8

$ZipPath = Join-Path $ReleaseRoot "$PortableName.zip"
Compress-Archive -LiteralPath $PortableRoot -DestinationPath $ZipPath -CompressionLevel Optimal
$ZipSha = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
$HashLines = @(
    "$ZipSha  $([System.IO.Path]::GetFileName($ZipPath))",
    "$WheelSha  $($Wheel.Name)",
    "$SdistSha  $($Sdist.Name)"
)
$HashLines | Set-Content -LiteralPath (Join-Path $ReleaseRoot "SHA256SUMS.txt") -Encoding ascii

Write-Host "PORTABLE_ROOT=$PortableRoot"
Write-Host "PORTABLE_EXE=$ExePath"
Write-Host "PORTABLE_EXE_SHA256=$ExeSha"
Write-Host "PORTABLE_ZIP=$ZipPath"
Write-Host "PORTABLE_ZIP_SHA256=$ZipSha"
Write-Host "WHEEL=$($Wheel.FullName)"
Write-Host "WHEEL_SHA256=$WheelSha"
Write-Host "SDIST=$($Sdist.FullName)"
Write-Host "SDIST_SHA256=$SdistSha"
Write-Host "SHA256SUMS=$(Join-Path $ReleaseRoot 'SHA256SUMS.txt')"
