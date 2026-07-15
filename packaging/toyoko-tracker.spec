# -*- mode: python ; coding: utf-8 -*-

import os
import platform
import sys
from glob import glob

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
windows_arm64 = sys.platform == "win32" and platform.machine().lower() in {"arm64", "aarch64"}
hiddenimports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtQml",
    "PySide6.QtQuick",
] if windows_arm64 else []
excludes = ["pytest", "ruff", "PyQt5", "PyQt6", "PySide2"]
extra_binaries = []
extra_datas = []
if windows_arm64:
    excludes.extend(["clr", "clr_loader", "pythonnet", "webview"])
    import PySide6

    pyside_root = os.path.dirname(PySide6.__file__)
    for filename in ("Qt6WebView.dll", "Qt6WebViewQuick.dll"):
        extra_binaries.append((os.path.join(pyside_root, filename), "PySide6"))
    for source in glob(os.path.join(pyside_root, "plugins", "webview", "*.dll")):
        extra_binaries.append((source, "PySide6/plugins/webview"))
    qml_webview_root = os.path.join(pyside_root, "qml", "QtWebView")
    for source in glob(os.path.join(qml_webview_root, "**", "*"), recursive=True):
        if not os.path.isfile(source):
            continue
        destination = os.path.join(
            "PySide6/qml/QtWebView",
            os.path.relpath(os.path.dirname(source), qml_webview_root),
        )
        if source.lower().endswith(".dll"):
            extra_binaries.append((source, destination))
        else:
            extra_datas.append((source, destination))
else:
    excludes.append("PySide6")

a = Analysis(
    [entrypoint],
    pathex=[src_root],
    binaries=extra_binaries,
    datas=datas + extra_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
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
