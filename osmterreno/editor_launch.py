"""Abre o editor OSM numa janela pywebview."""
import importlib.util
import json
import os

from . import APP_NAME
from .paths import EDITOR_DIR, OSM_DIR


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
    spec = importlib.util.spec_from_file_location("editor_server", os.path.join(EDITOR_DIR, "server.py"))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    url = modulo.garantir_servidor()
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError("Falta o pywebview. Rode: py -3.12 -m pip install pywebview") from exc
    webview.create_window(f"{APP_NAME} — editor", url, width=1280, height=860)
    webview.start()
