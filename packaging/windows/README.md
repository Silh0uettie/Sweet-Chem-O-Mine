# Windows Packaging

This folder contains the reproducible Windows portable-build configuration.

## Prerequisites

Use a clean Windows Python environment dedicated to packaging. Do not use an
environment created with `--system-site-packages`, because PyInstaller needs
the scientific dependencies to come from one consistent environment.

```powershell
python -m venv C:\sweetchem-build-env
C:\sweetchem-build-env\Scripts\python.exe -m pip install --upgrade pip
C:\sweetchem-build-env\Scripts\python.exe -m pip install . pyinstaller pillow
```

## Build

From the project root:

```powershell
.\packaging\windows\build_windows.ps1
```

To use another packaging environment:

```powershell
.\packaging\windows\build_windows.ps1 -Python C:\path\to\python.exe
```

Output:

```text
C:\sweetchem-release\windows\Sweet Chem O Mine\Sweet Chem O Mine.exe
```

This is a portable one-folder application build. The full folder must be
distributed together; the `.exe` cannot be copied out by itself.
The generated executable and PyInstaller working files are placed outside the
OneDrive project folder so the build does not repeatedly sync new executable
artifacts.

On managed university computers, endpoint security may block a locally built,
unsigned executable. The Python-package version remains usable through `scom`
when local security policy prevents the portable build from running.

## Managed Computer Option

The GitHub Actions workflow `.github/workflows/windows-portable.yml` builds the
portable Windows folder on a GitHub-hosted Windows runner. Run **Build Windows
Portable App** from the repository's Actions page, then download the
`Sweet-Chem-O-Mine-Windows-Portable` artifact. A tagged release also triggers
the workflow automatically.

## Manual Verification Checklist

1. Start `Sweet Chem O Mine.exe`.
2. Open a CSV file and run an analysis.
3. Open an XLSX file and select a worksheet.
4. Select compounds, save an AOI, and export CSV/PDF output.
5. Save and reopen a `.scom` project.
6. Switch light/dark/auto theme modes.
