# -*- mode: python ; coding: utf-8 -*-
"""Pacote Windows do OsmTerreno (pasta dist/OsmTerreno/)."""

import os

from PyInstaller.utils.hooks import collect_all, collect_data_files

raiz = os.path.abspath(SPECPATH)

datas = [
    (os.path.join(raiz, "editor", "editor.html"), "editor"),
    (os.path.join(raiz, "editor", "editor.css"), "editor"),
    (os.path.join(raiz, "editor", "editor.js"), "editor"),
    (os.path.join(raiz, "editor", "painel.js"), "editor"),
    (os.path.join(raiz, "editor", "visualizar-relevo.html"), "editor"),
    (os.path.join(raiz, "editor", "server.py"), "editor"),
    (os.path.join(raiz, "tools", "win"), os.path.join("tools", "win")),
    (os.path.join(raiz, "config.exemplo.json"), "."),
    (os.path.join(raiz, "README.md"), "."),
]

for nome in os.listdir(os.path.join(raiz, "osm")):
    if nome.lower().endswith(".osm"):
        datas.append((os.path.join(raiz, "osm", nome), "osm"))

binaries = []
hiddenimports = [
    "webview",
    "webview.platforms.edgechromium",
    "PIL",
    "PIL.Image",
    "triangle",
    "shapely",
    "shapely.geometry",
    "shapely.ops",
    "shapely.prepared",
    "shapely.strtree",
    "numpy",
    "tkinter",
    "multiprocessing",
    "http.server",
]

for pacote in ("shapely", "triangle", "webview", "clr_loader"):
    try:
        d, b, h = collect_all(pacote)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

try:
    datas += collect_data_files("triangle")
except Exception:
    pass

a = Analysis(
    [os.path.join(raiz, "osmterreno", "__main__.py")],
    pathex=[raiz],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OsmTerreno",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Mantém editor/, tools/ e DLLs na mesma pasta do .exe
    contents_directory=".",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="OsmTerreno",
)
