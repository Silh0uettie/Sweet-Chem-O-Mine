from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


ROOT = Path(SPECPATH).parents[1]
SRC = ROOT / "src"
ICON = ROOT / "packaging" / "windows" / "app_icon.ico"
APP_ICON = SRC / "sweet_chem_o_mine" / "assets" / "app_icon.png"

datas = [(str(APP_ICON), "sweet_chem_o_mine/assets")]
datas += collect_data_files("matplotlib")

a = Analysis(
    [str(ROOT / "packaging" / "windows" / "launch_scom.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "umap",
        "openpyxl",
        "xlrd",
        "sweet_chem_o_mine.analysis",
        "sweet_chem_o_mine.data_io",
        "sweet_chem_o_mine.project_file",
    ],
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
