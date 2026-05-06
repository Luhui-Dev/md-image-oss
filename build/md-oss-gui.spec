# PyInstaller spec for md-oss-gui (cross-platform).
#
# Usage:
#   pip install pyinstaller
#   pyinstaller --clean build/md-oss-gui.spec
#
# Output:
#   macOS:    dist/md-oss-gui.app
#   Windows:  dist/md-oss-gui/md-oss-gui.exe   (single-folder mode)
#   Linux:    dist/md-oss-gui/md-oss-gui
#
# Code signing & notarisation are intentionally left out — wire them in
# when publishing.

# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

PROJECT_ROOT = Path(SPECPATH).parent
ENTRY = str(PROJECT_ROOT / "md_image_oss" / "gui" / "app.py")

hidden = [
    # OSS SDK pulls in submodules dynamically.
    "oss2",
    "oss2.api",
    "oss2.auth",
    "oss2.exceptions",
    "oss2.models",
    # Pillow plugins are imported lazily.
    "PIL.Image",
    "PIL.JpegImagePlugin",
    "PIL.PngImagePlugin",
    "PIL.WebPImagePlugin",
    "PIL.GifImagePlugin",
    # Keyring backends — pick the right one per platform at runtime.
    "keyring.backends",
    "keyring.backends.macOS",
    "keyring.backends.Windows",
    "keyring.backends.SecretService",
    "keyring.backends.kwallet",
    "keyring.backends.fail",
    "keyring.backends.chainer",
]

a = Analysis(
    [ENTRY],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="md-oss-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="md-oss-gui",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="md-oss-gui.app",
        icon=None,
        bundle_identifier="com.md-image-oss.gui",
        info_plist={
            "NSHighResolutionCapable": "True",
            "CFBundleShortVersionString": "0.3.0",
            "CFBundleVersion": "0.3.0",
            "LSMinimumSystemVersion": "11.0",
        },
    )
