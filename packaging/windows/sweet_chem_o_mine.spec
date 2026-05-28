from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)


ROOT = Path(SPECPATH).parents[1]
SRC = ROOT / "src"
ICON = ROOT / "packaging" / "windows" / "app_icon.ico"
APP_ICON = SRC / "sweet_chem_o_mine" / "assets" / "app_icon.png"

datas = [(str(APP_ICON), "sweet_chem_o_mine/assets")]
datas += collect_data_files("matplotlib")
binaries = []

analysis_packages = [
    "joblib",
    "llvmlite",
    "numba",
    "numpy",
    "pynndescent",
    "rdkit",
    "scipy",
    "sklearn",
    "threadpoolctl",
    "umap",
]
for package in analysis_packages:
    datas += collect_data_files(package, include_py_files=False)
    binaries += collect_dynamic_libs(package)

for distribution in [
    "joblib",
    "llvmlite",
    "numba",
    "numpy",
    "pynndescent",
    "rdkit",
    "scikit-learn",
    "scipy",
    "threadpoolctl",
    "umap-learn",
]:
    datas += copy_metadata(distribution)

hiddenimports = [
    "openpyxl",
    "sweet_chem_o_mine.analysis",
    "sweet_chem_o_mine.data_io",
    "sweet_chem_o_mine.project_file",
    "xlrd",
]
for package in analysis_packages:
    hiddenimports += collect_submodules(package)

a = Analysis(
    [str(ROOT / "packaging" / "windows" / "launch_scom.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtMultimedia",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "tkinter",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Sweet Chem O Mine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(ICON),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Sweet Chem O Mine",
)
