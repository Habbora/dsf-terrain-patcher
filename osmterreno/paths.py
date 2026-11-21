"""Caminhos do projeto. Não importa nenhum módulo pesado."""
import os
import sys


def congelado():
    return bool(getattr(sys, "frozen", False))


def raiz_projeto():
    """Pasta do OsmTerreno (osm/, editor/, tools/). No .exe é a pasta do executável."""
    if congelado():
        return os.path.dirname(os.path.abspath(sys.executable))
    pacote = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(pacote, ".."))


def comando_self(*args):
    """Linha de comando para relançar este programa (corte auxiliar / tile)."""
    if congelado():
        return [sys.executable, *args]
    return [sys.executable, "-m", "osmterreno", *args]


PROJETO = raiz_projeto()
OSM_DIR = os.path.join(PROJETO, "osm")
LOG_DIR = os.path.join(PROJETO, "logs")
CACHE_DIR = os.path.join(PROJETO, "cache")
EDITOR_DIR = os.path.join(PROJETO, "editor")
CONFIG_PATH = os.path.join(PROJETO, "config.json")
PASTA_PADRAO = r"D:\SteamLibrary\steamapps\common\X-Plane 12\XPlane Map Enhancement Data"
