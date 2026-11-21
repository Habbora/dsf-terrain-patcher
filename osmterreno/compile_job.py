"""Compilação dos tiles: log, configuração, plano por tile e recuperação do backup."""
import json
import os
import subprocess
import tempfile
import threading
import time
import traceback
import xml.etree.ElementTree as ET

from shapely.geometry import box

from .cancel import (
    NO_WINDOW,
    Cancelado,
    cancelar,
    definir_proc_compile,
    matar_arvore,
    pedir_cancelamento,
    verificar_cancelamento,
)
from .dsf_io import copy_dsf_atomic, find_dsfs, tile_of
from .mesh_cut import recortar_dsf
from .osm_patch import BLEND_M, layers_of, load_patch
from .paths import CONFIG_PATH, LOG_DIR, OSM_DIR, PASTA_PADRAO, PROJETO, comando_self

_log_trava = threading.Lock()
_log_path = None


def iniciar_log(titulo):
    """Reescreve logs/Log.txt com esta compilação. A anterior sai."""
    global _log_path
    os.makedirs(LOG_DIR, exist_ok=True)
    _log_path = os.path.join(LOG_DIR, "Log.txt")
    with open(_log_path, "w", encoding="utf-8") as handle:
        handle.write("%s\n%s\n\n" % (titulo, time.strftime("%Y-%m-%d %H:%M:%S")))
    return _log_path


def gravar_log(linha):
    if not _log_path:
        return
    with _log_trava:
        with open(_log_path, "a", encoding="utf-8") as handle:
            handle.write("%s  %s\n" % (time.strftime("%H:%M:%S"), linha))
            handle.flush()


def ler_config():
    base = {"pasta": PASTA_PADRAO, "faixa": 70, "otimizar": False, "melhorar": False}
    if not os.path.isfile(CONFIG_PATH):
        return base
    try:
        with open(CONFIG_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return base
    if not data.get("pasta"):
        data["pasta"] = PASTA_PADRAO
    if not data.get("faixa"):
        data["faixa"] = 70
    return data


def gravar_config(pasta, faixa, otimizar=False, melhorar=False):
    with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
        json.dump(
            {"pasta": pasta, "faixa": faixa, "otimizar": bool(otimizar), "melhorar": bool(melhorar)},
            handle,
            ensure_ascii=False,
            indent=2,
        )


def ler_faixa(texto):
    try:
        valor = float(str(texto).replace(",", "."))
    except ValueError:
        raise RuntimeError("A faixa precisa ser um número em metros.")
    if valor < 0 or valor > 500:
        raise RuntimeError("A faixa fica entre 0 e 500 m.")
    return valor


def dsfs_do_osm(folder, osm):
    patch = load_patch(osm)
    return [path for path in xpme_dsfs(folder) if cobre_tile(patch, path)]


def xpme_dsfs(folder):
    dsfs = find_dsfs(folder)
    south = [path for path in dsfs if "XPME_South_America" in path]
    return south or dsfs


def osm_do_projeto():
    os.makedirs(OSM_DIR, exist_ok=True)
    return sorted(
        os.path.join(OSM_DIR, name) for name in os.listdir(OSM_DIR) if name.lower().endswith(".osm")
    )


def cobre_tile(patch, path):
    flats, ramps, _bounds = patch
    lat, lon = tile_of(path)
    tile = box(lon, lat, lon + 1, lat + 1)
    return any(poly.intersects(tile) for poly, _alt in flats) or any(
        poly.intersects(tile) for poly, *_rest in ramps
    )


def plano_por_tile(folder, origens, log):
    """Cada tile recebe todos os OSM do projeto que caem nele, porque o corte parte do backup e apagaria os outros."""
    dsfs = xpme_dsfs(folder)
    if not dsfs:
        raise RuntimeError("nenhum DSF nessa pasta")
    patches = {}
    for osm in dict.fromkeys(list(origens) + osm_do_projeto()):
        try:
            patches[osm] = load_patch(osm)
        except (ValueError, ET.ParseError) as exc:
            if osm in origens:
                raise
            log("ignorado %s: %s" % (os.path.basename(osm), exc))
    plano = []
    for path in dsfs:
        escolhidos = [osm for osm in origens if cobre_tile(patches[osm], path)]
        if not escolhidos:
            continue
        juntos = sorted(
            (osm for osm in patches if cobre_tile(patches[osm], path)),
            key=lambda osm: os.path.basename(osm).lower(),
        )
        extras = [osm for osm in juntos if osm not in origens]
        if extras:
            log("%s: incluindo tambem %s, que cai no mesmo tile" % (
                os.path.basename(path), ", ".join(os.path.basename(osm) for osm in extras)))
        plano.append((path, juntos))
    if not plano:
        raise RuntimeError("nenhum DSF cobre a area dos OSM marcados")
    return plano


def compilar_tile(path, osms, opcoes, log=None):
    """Corta um tile com todos os OSM dele. Roda num processo separado ou no próprio processo."""
    nome = os.path.basename(path)

    def escrever(texto):
        linha = "%s  %s" % (nome, texto)
        if log is not None:
            log(linha)

    try:
        layers = []
        for osm in osms:
            flats, ramps, _bounds = load_patch(osm)
            layers += layers_of(flats, ramps)
        escrever("%d OSM, %d poligonos, faixa %.0f m" % (len(osms), len(layers), opcoes["faixa"]))
        backup = path + ".antes_osm"
        if not os.path.isfile(backup):
            copy_dsf_atomic(path, backup)
            escrever("backup criado")
        inicio = time.time()
        recortar_dsf(path, layers, escrever, True, opcoes["faixa"], opcoes["otimizar"], opcoes["melhorar"])
        escrever("pronto em %.0f s" % (time.time() - inicio))
        return "ok"
    except Cancelado:
        gravar_log(nome + "  cancelado")
        return "cancelado"
    except Exception:
        gravar_log(nome + "  ERRO\n" + traceback.format_exc())
        raise


def compilar_um_arquivo(job_path):
    """Roda um tile neste processo. Se o corte cair, só este processo fecha."""
    with open(job_path, encoding="utf-8") as handle:
        job = json.load(handle)

    def escrever(texto):
        print(texto, flush=True)

    try:
        resultado = compilar_tile(job["path"], job["osms"], job["opcoes"], escrever)
    except Exception:
        print("ERRO\n" + traceback.format_exc(), flush=True)
        return 1
    return 0 if resultado == "ok" else 2


def rodar_compilacao(path, osms, opcoes, log):
    """Compila o tile num processo à parte e devolve o código de saída."""
    fd, job = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(job, "w", encoding="utf-8") as handle:
        json.dump({"path": path, "osms": osms, "opcoes": opcoes}, handle)
    try:
        proc = subprocess.Popen(
            comando_self("--compilar-um", job),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=NO_WINDOW if os.name == "nt" else 0,
            cwd=PROJETO,
        )
        definir_proc_compile(proc)
        for raw in proc.stdout:
            linha = raw.decode("utf-8", errors="replace").rstrip()
            if linha:
                log(linha)
            if cancelar.is_set():
                matar_arvore(proc.pid)
                raise Cancelado()
        return proc.wait()
    finally:
        definir_proc_compile(None)
        try:
            os.remove(job)
        except OSError:
            pass


def compilar_varios(folder, origens, log, opcoes, progresso=None, paralelo=True):
    """Compila os OSM marcados, um tile depois do outro."""
    plano = plano_por_tile(folder, origens, log)
    total = len(plano)
    gravar_log("%d tile(s)" % total)
    if progresso:
        progresso(0, total)
    for feito, (path, osms) in enumerate(plano, start=1):
        gravar_log("inicio " + os.path.basename(path))
        codigo = rodar_compilacao(path, osms, opcoes, log)
        if cancelar.is_set():
            raise Cancelado()
        if codigo != 0:
            raise RuntimeError(
                "A compilação parou no meio de %s (código %s). O cenário só é trocado no fim, então o arquivo anterior continua no lugar."
                % (os.path.basename(path), codigo)
            )
        gravar_log("ok " + os.path.basename(path))
        if progresso:
            progresso(feito, total)
    return total


def aplicar(folder, osm, log, proteger_agua=True, blend_m=70.0, otimizar=False, melhorar=False):
    opcoes = {"faixa": blend_m, "otimizar": otimizar, "melhorar": melhorar}
    return compilar_varios(folder, [osm], log, opcoes, paralelo=False)


def recuperar_varios(folder, origens, log, progresso=None):
    """Restaura cada tile uma vez, mesmo quando vários OSM caem nele."""
    visto = []
    for osm in origens:
        for path in dsfs_do_osm(folder, osm):
            if path not in visto:
                visto.append(path)
    if not visto:
        raise RuntimeError("nenhum DSF cobre a area desses OSM")
    restored = 0
    total = len(visto)
    if progresso:
        progresso(0, total)
    for path in visto:
        verificar_cancelamento()
        backup = path + ".antes_osm"
        if not os.path.isfile(backup):
            log("sem backup: " + path)
            continue
        copy_dsf_atomic(backup, path)
        log("recuperado " + os.path.basename(path))
        restored += 1
        if progresso:
            progresso(restored, total)
    if not restored:
        raise RuntimeError("os tiles desses OSM ainda nao tem backup")
    return restored


def recuperar(folder, osm, log, proteger_agua=True):
    return recuperar_varios(folder, [osm], log)


def compilar_todos():
    """Usado pelo Compilar.bat: todos os OSM da pasta osm, com as opções salvas na janela."""
    config = ler_config()
    opcoes = {
        "faixa": ler_faixa(str(config.get("faixa", BLEND_M))),
        "otimizar": bool(config.get("otimizar")),
        "melhorar": bool(config.get("melhorar")),
    }
    origens = osm_do_projeto()
    if not origens:
        print("nenhum OSM na pasta osm")
        return 1
    try:
        compilar_varios(config["pasta"], origens, print, opcoes,
                        lambda feito, total: print("tiles prontos: %d de %d" % (feito, total)))
    except KeyboardInterrupt:
        pedir_cancelamento()
        print("cancelado")
        return 1
    except Exception as exc:
        print("erro: %s" % exc)
        return 1
    return 0
