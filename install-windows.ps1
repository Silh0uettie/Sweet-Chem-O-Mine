[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "SweetChemOMine"),
    [string]$SourceArchiveUrl = "https://github.com/Silh0uettie/Sweet-Chem-O-Mine/archive/refs/heads/main.zip",
    [string]$MinicondaUrl = "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$installRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$runtimeRoot = Join-Path $installRoot "runtime"
$environmentRoot = Join-Path $installRoot "env"
$iconPath = Join-Path $installRoot "app_icon.ico"
$uninstallPath = Join-Path $installRoot "uninstall-windows.ps1"
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("scom-install-" + [Guid]::NewGuid().ToString("N"))
$runtimeConda = Join-Path $runtimeRoot "Scripts\conda.exe"
$appPython = Join-Path $environmentRoot "python.exe"
$appPythonw = Join-Path $environmentRoot "pythonw.exe"
$desktopLink = Join-Path ([Environment]::GetFolderPath("Desktop")) "Sweet Chem O' Mine.lnk"
$startMenuFolder = Join-Path ([Environment]::GetFolderPath("Programs")) "Sweet Chem O' Mine"
$startMenuLink = Join-Path $startMenuFolder "Sweet Chem O' Mine.lnk"
$uninstallLink = Join-Path $startMenuFolder "Uninstall Sweet Chem O' Mine.lnk"
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\SweetChemOMine"

function New-Shortcut {
    param(
        [string]$Path,
        [string]$TargetPath,
        [string]$Arguments,
        [string]$WorkingDirectory,
        [string]$IconLocation
    )
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = $TargetPath
    $shortcut.Arguments = $Arguments
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.IconLocation = $IconLocation
    $shortcut.Save()
}

Write-Host "Installing Sweet Chem O' Mine into $installRoot"
New-Item -ItemType Directory -Force -Path $installRoot, $tempRoot | Out-Null

try {
    if (-not (Test-Path -LiteralPath $runtimeConda)) {
        $minicondaInstaller = Join-Path $tempRoot "Miniconda3-Windows-x86_64.exe"
        Write-Host "Downloading official Miniconda runtime..."
        Invoke-WebRequest -Uri $MinicondaUrl -OutFile $minicondaInstaller
        $signature = Get-AuthenticodeSignature -LiteralPath $minicondaInstaller
        if ($signature.Status -ne "Valid") {
            throw "The downloaded Miniconda installer does not have a valid Windows signature."
        }
        Write-Host "Installing private Python runtime..."
        $arguments = @(
            "/InstallationType=JustMe",
            "/AddToPath=0",
            "/RegisterPython=0",
            "/S",
            "/D=$runtimeRoot"
        )
        $process = Start-Process -FilePath $minicondaInstaller -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden
        if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $runtimeConda)) {
            throw "Private Miniconda runtime installation failed."
        }
    }

    if (-not (Test-Path -LiteralPath $appPython)) {
        Write-Host "Creating private Python 3.11 application environment..."
        & $runtimeConda create --prefix $environmentRoot -y "python=3.11" pip
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $appPython)) {
            throw "Private Python 3.11 application environment creation failed."
        }
    }

    $sourceArchive = Join-Path $tempRoot "sweet-chem-o-mine.zip"
    $sourceExtract = Join-Path $tempRoot "source"
    Write-Host "Downloading Sweet Chem O' Mine source..."
    Invoke-WebRequest -Uri $SourceArchiveUrl -OutFile $sourceArchive
    Expand-Archive -LiteralPath $sourceArchive -DestinationPath $sourceExtract -Force
    $sourceRoot = Get-ChildItem -LiteralPath $sourceExtract -Directory | Select-Object -First 1
    if ($null -eq $sourceRoot -or -not (Test-Path -LiteralPath (Join-Path $sourceRoot.FullName "pyproject.toml"))) {
        throw "Downloaded source archive does not contain the application package."
    }

    Write-Host "Installing application dependencies and package..."
    & $appPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Unable to update pip in the private runtime." }
    & $appPython -m pip install --upgrade $sourceRoot.FullName
    if ($LASTEXITCODE -ne 0) { throw "Unable to install Sweet Chem O' Mine." }

    Copy-Item -LiteralPath (Join-Path $sourceRoot.FullName "packaging\windows\app_icon.ico") -Destination $iconPath -Force
    Copy-Item -LiteralPath (Join-Path $sourceRoot.FullName "uninstall-windows.ps1") -Destination $uninstallPath -Force
    New-Item -ItemType Directory -Force -Path $startMenuFolder | Out-Null

    New-Shortcut -Path $desktopLink -TargetPath $appPythonw `
        -Arguments "-m sweet_chem_o_mine" -WorkingDirectory $installRoot -IconLocation $iconPath
    New-Shortcut -Path $startMenuLink -TargetPath $appPythonw `
        -Arguments "-m sweet_chem_o_mine" -WorkingDirectory $installRoot -IconLocation $iconPath
    New-Shortcut -Path $uninstallLink -TargetPath "powershell.exe" `
        -Arguments "-NoProfile -ExecutionPolicy Bypass -File `"$uninstallPath`"" `
        -WorkingDirectory $installRoot -IconLocation $iconPath

    $version = (& $appPython -c "import sweet_chem_o_mine; print(sweet_chem_o_mine.__version__)").Trim()
    New-Item -Path $uninstallKey -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "DisplayName" -Value "Sweet Chem O' Mine" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "DisplayVersion" -Value $version -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "Publisher" -Value "Sweet Chem O' Mine" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "InstallLocation" -Value $installRoot -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "DisplayIcon" -Value $iconPath -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "UninstallString" `
        -Value "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$uninstallPath`"" `
        -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "NoModify" -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name "NoRepair" -Value 1 -PropertyType DWord -Force | Out-Null

    Write-Host ""
    Write-Host "Sweet Chem O' Mine $version is installed."
    Write-Host "Launch it from the desktop shortcut or Start Menu."
}
finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
