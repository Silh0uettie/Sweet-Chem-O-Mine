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

## Quick Start on Windows

Python 3.11 or later is required. On Windows, especially when your files are
inside OneDrive or another synced folder, create the Python environment in a
short local path **before** installing the application:

```powershell
py -3.11 -m venv C:\sweetchem-env
C:\sweetchem-env\Scripts\python.exe -m pip install --upgrade pip
C:\sweetchem-env\Scripts\python.exe -m pip install "git+https://github.com/Silh0uettie/Sweet-Chem-O-Mine.git"
C:\sweetchem-env\Scripts\python.exe -m sweet_chem_o_mine
```

This puts the environment and large scientific dependencies in
`C:\sweetchem-env`, outside a cloud-synced project directory. Your uploaded
tables and saved `.scom` projects are not placed there automatically.

On managed computers that block newly downloaded application executables, run
the final command above through the installed Python environment. Do not use
`python -m scom`: `scom` is a console command, while the Python module name is
`sweet_chem_o_mine`.

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

## Install from a Clone

For development or working from a local clone, keep the environment outside
the repository and install in editable mode:

```powershell
git clone https://github.com/Silh0uettie/Sweet-Chem-O-Mine.git
Set-Location Sweet-Chem-O-Mine
py -3.11 -m venv C:\sweetchem-env
C:\sweetchem-env\Scripts\python.exe -m pip install --upgrade pip
C:\sweetchem-env\Scripts\python.exe -m pip install -e .
C:\sweetchem-env\Scripts\python.exe -m sweet_chem_o_mine
```

On macOS or Linux:

```bash
python3 -m venv ~/.venvs/sweetchem
~/.venvs/sweetchem/bin/python -m pip install --upgrade pip
~/.venvs/sweetchem/bin/python -m pip install .
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

Current package version: `0.1.2`.

## Windows Portable Build

An unsigned Windows portable build is available through the
**Build Windows Portable App** GitHub Actions workflow. Windows security policy
on managed computers may prevent that portable application from starting.
Use the Python-module quick start above when executable downloads are blocked.

For local packaging on a computer that permits application builds, the
configuration is stored in `packaging/windows/`. Build from a clean packaging
environment rather than the development environment:

```powershell
python -m venv C:\sweetchem-build-env
C:\sweetchem-build-env\Scripts\python.exe -m pip install . pyinstaller pillow
.\packaging\windows\build_windows.ps1
```

The generated portable application is written outside the synced project
folder:

```text
C:\sweetchem-release\windows\Sweet Chem O Mine\
```

Managed computers may block newly generated unsigned executables. In that
case, continue using the installed Python-package launcher, `scom`, or build
the portable application through the **Build Windows Portable App** workflow
on GitHub Actions, which supplies a downloadable Windows artifact without
building an executable on the local managed computer.
