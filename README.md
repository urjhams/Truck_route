# READ ME

### App spec (TruckRouteApp.spec - stay in root folder):

```python
# -*- mode: python ; coding: utf-8 -*-

import sys
from PyInstaller.utils.hooks import collect_submodules

# App name
APP_NAME = "Truck Route"

# Entry script
ENTRYPOINT = "source/TruckRouteApp/main.py"

# Hidden imports (for OR-Tools + SQLModel)
hidden_imports = collect_submodules("ortools") + collect_submodules("sqlmodel")

# Data files to bundle (src, dest)
datas = [
    # ("source/TruckRouteApp/assets/template.xlsx", "assets")
]

block_cipher = None

a = Analysis(
    [ENTRYPOINT],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name=APP_NAME,
    icon=None,              # set later .ico/.icns
    console=False,          # GUI app – no terminal window
)

app = BUNDLE(
    exe,
    name=f"{APP_NAME}.app",
    icon=None,
    bundle_identifier="com.truckroute.app",
    info_plist={
        "CFBundleDisplayName": APP_NAME,
        "NSHighResolutionCapable": "True",
        "LSBackgroundOnly": False,
        "LSUIElement": False,   # Required to hide helper process from Dock
    }
)

# macOS bundle command: pyinstaller TruckRouteApp.spec --noconfirm --clean

# windows exe: pyinstaller TruckRouteApp.spec --noconfirm --clean

## Additional Dependencies

The new pallet label export relies on [`python-docx`](https://python-docx.readthedocs.io/) to manipulate the Word
template stored under `source/TruckRouteApp/assets/Template.docx`. Install it in your virtual environment before
running the UI:

```bash
pip install python-docx
```
```
