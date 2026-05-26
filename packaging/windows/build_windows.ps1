param(
    [string]$Python = "C:\sweetchem-build-env\Scripts\python.exe",
    [string]$WorkPath = "C:\sweetchem-pyinstaller-build",
    [string]$DistPath = "C:\sweetchem-release\windows"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$SpecPath = Join-Path $ProjectRoot "packaging\windows\sweet_chem_o_mine.spec"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment not found: $Python"
}

Push-Location $ProjectRoot
try {
    $env:QT_QPA_PLATFORM = "offscreen"
    & $Python -B "packaging\windows\create_icon_assets.py"
    if ($LASTEXITCODE -ne 0) { throw "Icon generation failed." }
    & $Python -m PyInstaller --noconfirm --clean --workpath $WorkPath --distpath $DistPath $SpecPath
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
    Write-Host "Portable Windows application created in $DistPath\Sweet Chem O Mine"
}
finally {
    Pop-Location
}
