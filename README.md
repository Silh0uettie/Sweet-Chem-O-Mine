# Project Sweet Chem O' Mine

<p align="center">
  <img src="assets/app_icon.svg" alt="Sweet Chem O' Mine icon" width="112">
</p>

<p align="center">
  <a href="https://github.com/Silh0uettie/Sweet-Chem-O-Mine/actions/workflows/tests.yml"><img src="https://github.com/Silh0uettie/Sweet-Chem-O-Mine/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="Platforms">
</p>

Project Sweet Chem O' Mine is an interactive desktop application for exploring
chemical screening data in molecular-feature space. It generates Morgan
fingerprints from SMILES, calculates a UMAP projection, and links selected
regions to compound values and rendered chemical structures.

This repository contains the Python package and application source. It does not
contain imported experimental datasets.

## Features

- Open `.csv`, `.xls`, and `.xlsx` tables, with worksheet selection for Excel files.
- Map columns for display name, SMILES, assay value, and an optional error bar.
- Rename the value axis independently from the imported column name.
- Configure Morgan fingerprint and UMAP parameters with inline help.
- Select compounds on the UMAP and inspect linked values and structures.
- Save named Areas of Interest (AOIs) and restore them from project files.
- Review excluded rows and non-fatal data-quality warnings.
- Export AOI tables as CSV and all three result figures as one PDF.
- Save and reopen portable `.scom` project archives.
- Choose system-driven, light, or dark interface themes.

## Installation

### Windows: Clean Computer Setup

These commands assume the user has no Python, Conda, or Git installed. They
create an application-only runtime under `%LOCALAPPDATA%\SCOM`; they do not add
Conda to `PATH`, register Python as the system default, or affect a future
personal Conda installation. The commands install the released `v0.1.3`
application source.

Open PowerShell and paste these commands:

```powershell
$SCOM = Join-Path $env:LOCALAPPDATA "SCOM"
$Runtime = Join-Path $SCOM "Runtime"
$AppEnv = Join-Path $SCOM "AppEnv"
$Source = Join-Path $SCOM "Source"
$MiniInstaller = Join-Path $env:TEMP "Miniconda3-latest-Windows-x86_64.exe"
$SourceZip = Join-Path $env:TEMP "Sweet-Chem-O-Mine-v0.1.3.zip"

New-Item -ItemType Directory -Force -Path $SCOM | Out-Null

curl.exe -L "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe" --output $MiniInstaller
if ((Get-AuthenticodeSignature -LiteralPath $MiniInstaller).Status -ne "Valid") { throw "The Miniconda download does not have a valid Windows signature." }
Start-Process -Wait -FilePath $MiniInstaller -ArgumentList @("/InstallationType=JustMe", "/AddToPath=0", "/RegisterPython=0", "/S", "/D=$Runtime")

& "$Runtime\Scripts\conda.exe" create --prefix $AppEnv -y --override-channels -c conda-forge "python=3.11" pip

curl.exe -L "https://github.com/Silh0uettie/Sweet-Chem-O-Mine/archive/refs/tags/v0.1.3.zip" --output $SourceZip
Expand-Archive -LiteralPath $SourceZip -DestinationPath $Source -Force
$Package = (Get-ChildItem -LiteralPath $Source -Directory | Select-Object -First 1).FullName

& "$AppEnv\python.exe" -m pip install --upgrade pip
& "$AppEnv\python.exe" -m pip install $Package
& "$AppEnv\pythonw.exe" -m sweet_chem_o_mine
```

The folder names `SCOM`, `Runtime`, and `AppEnv` make it explicit that this
private Miniconda copy belongs only to Sweet Chem O' Mine. Do not use
`python -m scom`: `scom` is a console command, while the Python module name is
`sweet_chem_o_mine`.

#### Create Shortcuts

After installation, paste the following commands in the same PowerShell
window to add Desktop and Start Menu shortcuts:

```powershell
$Icon = Join-Path $Package "packaging\windows\app_icon.ico"
$Shell = New-Object -ComObject WScript.Shell
$DesktopLink = Join-Path ([Environment]::GetFolderPath("Desktop")) "Sweet Chem O' Mine.lnk"
$MenuFolder = Join-Path ([Environment]::GetFolderPath("Programs")) "Sweet Chem O' Mine"
$MenuLink = Join-Path $MenuFolder "Sweet Chem O' Mine.lnk"
New-Item -ItemType Directory -Force -Path $MenuFolder | Out-Null

foreach ($Link in @($DesktopLink, $MenuLink)) {
    $Shortcut = $Shell.CreateShortcut($Link)
    $Shortcut.TargetPath = Join-Path $AppEnv "pythonw.exe"
    $Shortcut.Arguments = "-m sweet_chem_o_mine"
    $Shortcut.WorkingDirectory = $SCOM
    $Shortcut.IconLocation = $Icon
    $Shortcut.Save()
}
```

#### Remove It Later

```powershell
$SCOM = Join-Path $env:LOCALAPPDATA "SCOM"
Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath("Desktop")) "Sweet Chem O' Mine.lnk") -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath("Programs")) "Sweet Chem O' Mine") -Recurse -Force -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath (Join-Path $SCOM "Runtime\Uninstall-Miniconda3.exe")) { Start-Process -Wait -FilePath (Join-Path $SCOM "Runtime\Uninstall-Miniconda3.exe") -ArgumentList "/S" }
Remove-Item -LiteralPath $SCOM -Recurse -Force -ErrorAction SilentlyContinue
```

On university-managed computers, security policy may still block the official
Miniconda installer or prevent local software installation.

### macOS or Linux

```bash
git clone https://github.com/Silh0uettie/Sweet-Chem-O-Mine.git
cd Sweet-Chem-O-Mine
python3 -m venv ~/.venvs/sweetchem
~/.venvs/sweetchem/bin/python -m pip install --upgrade pip
~/.venvs/sweetchem/bin/python -m pip install -e .
~/.venvs/sweetchem/bin/python -m sweet_chem_o_mine
```

The package also installs console entry-point commands:

```bash
scom
sweet-chem-o-mine
```

## Workflow

1. Open a tabular data file and choose the working sheet when using Excel.
2. Assign columns for names, SMILES, values, and optional error bars.
3. Adjust fingerprint/UMAP settings or use the defaults.
4. Run the analysis and lasso-select compounds in the UMAP.
5. Save AOIs, export results, or save a full `.scom` project.

The default structural representation is a 2048-bit Morgan fingerprint with
radius 2 (ECFP4-like), displayed using a Jaccard-distance UMAP.

## Shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+O` | Open data or a project |
| `Ctrl+R` | Run analysis |
| `Ctrl+S` | Save project |
| `Ctrl+Shift+S` | Save project as |

## Data Privacy

The application source code does not include imported study data. A saved
`.scom` file intentionally contains data: it stores the imported table,
optional original source-file bytes, analysis settings, derived coordinates,
data-quality reports, plot settings, selections, and AOIs for reproducible
reopening.

Dataset extensions and `.scom` project files are excluded through `.gitignore`
to reduce accidental publication of scientific data.

## Platform Status

The application uses cross-platform Python and Qt libraries. Automated backend
tests run on Windows, macOS, and Linux through GitHub Actions; the interactive
desktop interface has primarily been exercised on Windows.

## Tests

The automated tests use only small synthetic/example molecules and no imported
research datasets:

```bash
python -m unittest discover -s tests -v
```

## Version

Distribution package name: `sweet-chem-o-mine`.

Python import/module name: `sweet_chem_o_mine`.

Command-line launcher: `scom`.

Current package version: `0.1.3`.

## Windows Portable Build

An unsigned Windows portable build is available through the
**Build Windows Portable App** GitHub Actions workflow. Windows security policy
on managed computers may prevent that portable application from starting.
Use the Python-module launch command in the installation section when
executable downloads are blocked.

For local packaging on a computer that permits application builds, the
configuration and build instructions are stored in
[`packaging/windows/README.md`](packaging/windows/README.md).

Managed computers may block newly generated unsigned executables. In that
case, continue using the installed Python-package launcher, `scom`, or build
the portable application through the **Build Windows Portable App** workflow
on GitHub Actions, which supplies a downloadable Windows artifact without
building an executable on the local managed computer.
