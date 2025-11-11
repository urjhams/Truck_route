# -*- mode: python ; coding: utf-8 -*-

import sys
from PyInstaller.utils.hooks import collect_submodules, collect_dynamic_libs

# App name
APP_NAME = "Truck Route"

# Entry script
ENTRYPOINT = "source/TruckRouteApp/main.py"

# Hidden imports (for OR-Tools + SQLModel)
hidden_imports = collect_submodules("ortools") + collect_submodules("sqlmodel")
binaries = collect_dynamic_libs("ortools")

# Data files to bundle (src, dest)
datas = [
    ("source/TruckRouteApp/assets/template.xlsx", "assets"),
    ("source/TruckRouteApp/assets/Template.docx", "assets"),
    ("source/TruckRouteApp/assets/header_logo.png", "assets"),
    ("source/TruckRouteApp/assets/truckroute.db", "assets")
]

block_cipher = None

a = Analysis(
    [ENTRYPOINT],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    # Switch to onedir mode for faster startup and proper macOS bundling
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

is_macos = sys.platform == "darwin"

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name=APP_NAME,
    icon=None,              # set later .ico/.icns
    console=False,          # GUI app – no terminal window
    onefile=not is_macos,
)

app = BUNDLE(
    exe,
    name=f"{APP_NAME}.app",
    icon=None,
    bundle_identifier="com.truckroute.app",
    info_plist={
        "CFBundleDisplayName": APP_NAME,
        "NSHighResolutionCapable": True,
        "LSBackgroundOnly": False
    }
)

# macOS bundle command: pyinstaller TruckRouteApp.spec --noconfirm --clean

# windows exe: pyinstaller TruckRouteApp.spec --noconfirm --clean

# test: PYTHONPATH=source python3 -m TruckRouteApp.main 

# create environment: python -m venv .venv
# go to environemt: source .venv/bin/activate
# on windows: .venv\Scripts\activate
