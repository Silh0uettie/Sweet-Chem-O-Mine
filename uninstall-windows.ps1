[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "SweetChemOMine")
)

$ErrorActionPreference = "Stop"
$installRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$desktopLink = Join-Path ([Environment]::GetFolderPath("Desktop")) "Sweet Chem O' Mine.lnk"
$startMenuFolder = Join-Path ([Environment]::GetFolderPath("Programs")) "Sweet Chem O' Mine"
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\SweetChemOMine"

$confirmation = Read-Host "Remove Sweet Chem O' Mine and its private runtime? Type YES to continue"
if ($confirmation -cne "YES") {
    Write-Host "Uninstall cancelled."
    exit 0
}

Remove-Item -LiteralPath $desktopLink -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $startMenuFolder -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $uninstallKey -Recurse -Force -ErrorAction SilentlyContinue

if (Test-Path -LiteralPath $installRoot) {
    Remove-Item -LiteralPath $installRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Sweet Chem O' Mine has been removed."
