"""Abre o editor OSM numa janela pywebview."""
import importlib.util
import json
import os
import webbrowser
from functools import cache

from . import APP_NAME
from .paths import EDITOR_DIR, OSM_DIR


@cache
def _servidor_editor():
    spec = importlib.util.spec_from_file_location("editor_server", os.path.join(EDITOR_DIR, "server.py"))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def abrir_editor(osm_path):
    os.makedirs(OSM_DIR, exist_ok=True)
    cfg_path = os.path.join(EDITOR_DIR, "editor-config.json")
    with open(cfg_path, "w", encoding="utf-8") as handle:
        json.dump(
            {"patches_dir": OSM_DIR, "last_file": os.path.basename(osm_path)},
            handle,
            ensure_ascii=False,
            indent=2,
        )
    url = _servidor_editor().garantir_servidor()
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError("Falta o pywebview. Rode: py -3.12 -m pip install pywebview") from exc
    janela = webview.create_window(f"{APP_NAME} — editor", url, width=1280, height=860)
    try:
        webview.start()
    except RuntimeError as exc:
        if "Failed to resolve Python.Runtime.Loader.Initialize" not in str(exc):
            raise
        if janela in webview.windows:
            webview.windows.remove(janela)
        if not webbrowser.open(url):
            raise RuntimeError(f"Abra o editor no navegador em {url}") from exc
