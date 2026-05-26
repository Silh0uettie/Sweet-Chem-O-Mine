# Project Sweet Chem O' Mine

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

Python 3.11 or later is required. From a cloned copy of this repository:

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install .
python -m sweet_chem_o_mine
```

On Windows, Qt installations in deeply nested cloud-synced paths can exceed
path limits. A short environment path is a useful workaround:

```powershell
python -m venv C:\sweetchem-env
C:\sweetchem-env\Scripts\python.exe -m pip install .
C:\sweetchem-env\Scripts\python.exe -m sweet_chem_o_mine
```

For development, install the package in editable mode:

```bash
python -m pip install -e .
```

The installed entry-point commands are also available:

```bash
scom
sweet-chem-o-mine
```

The short launcher is:

```bash
scom
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

The application uses cross-platform Python and Qt libraries. It is currently
tested on Windows and is designed for testing and packaging on macOS and Linux
using platform-specific builds.

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

Windows packaging configuration is stored in `packaging/windows/`. Build from a
clean packaging environment rather than the development environment:

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
