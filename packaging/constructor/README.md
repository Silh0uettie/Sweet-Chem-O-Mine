# Windows Installer With Conda Constructor

This packaging path creates a standalone Windows installer containing its own
private Python/Conda runtime and Sweet Chem O' Mine dependencies.

The installed application:

- uses `%LOCALAPPDATA%\SweetChemOMine` by default;
- does not add Conda or Python to `PATH`;
- does not register Python as the system default;
- creates desktop and Start Menu shortcuts; and
- appears in Windows **Add or remove programs** with an uninstaller.

## GitHub Build

The **Build Windows Constructor Installer** workflow creates the installer on
GitHub Actions and uploads it as an artifact. It builds the local package from
`recipe/meta.yaml` and gives that package to Constructor through a temporary
local Conda channel.

## Local Build

On an unrestricted Windows development computer with Miniforge or Conda:

```powershell
conda install -c conda-forge constructor boa
$channelPath = Join-Path $env:TEMP "scom-conda-bld"
$outputPath = Join-Path $env:TEMP "scom-installer"
conda mambabuild packaging\constructor\recipe --no-test --output-folder $channelPath
$env:SCOM_LOCAL_CHANNEL = "file:///" + ($channelPath -replace '\\', '/')
constructor packaging\constructor --output-dir $outputPath
```

The installer is created as:

```text
Sweet-Chem-O-Mine-Windows-Installer-0.1.4.exe
```

## Managed Computers

This installer is an executable and is unsigned unless a future signing step
is configured. A managed computer can block the installer under the same
Microsoft Defender policy that blocks a newly built portable executable.
Constructor improves installation and uninstallation; it does not bypass
institutional application-control policy.
