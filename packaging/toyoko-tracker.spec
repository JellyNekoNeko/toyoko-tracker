# -*- mode: python ; coding: utf-8 -*-

import os
import sys

from PyInstaller.utils.hooks import collect_data_files


project_root = os.path.dirname(os.path.abspath(SPECPATH))
src_root = os.path.join(project_root, "src")
entrypoint = os.path.join(project_root, "packaging", "desktop_entry.py")
icons_root = os.path.join(project_root, "packaging", "icons")
desktop_version_scope = {}
with open(os.path.join(src_root, "toyoko_tracker", "desktop_version.py"), encoding="utf-8") as stream:
    exec(stream.read(), desktop_version_scope)
desktop_version = desktop_version_scope["DESKTOP_VERSION"]

if sys.platform == "darwin":
    app_icon = os.path.join(icons_root, "toyoko-tracker.icns")
elif sys.platform == "win32":
    app_icon = os.path.join(icons_root, "toyoko-tracker.ico")
else:
    app_icon = None

datas = collect_data_files("toyoko_tracker")

a = Analysis(
    [entrypoint],
    pathex=[src_root],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "ruff", "PyQt5", "PyQt6", "PySide2", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ToyokoTracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=app_icon,
)

bundle = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="ToyokoTracker",
)

if sys.platform == "darwin":
    app = BUNDLE(
        bundle,
        name="ToyokoTracker.app",
        bundle_identifier="com.jellyneko.toyoko-tracker",
        icon=os.path.join(icons_root, "toyoko-tracker.icns"),
        info_plist={
            "CFBundleDisplayName": "东横酱 Toyoko Chan",
            "CFBundleShortVersionString": desktop_version,
            "CFBundleVersion": desktop_version,
            "NSHighResolutionCapable": True,
        },
    )
