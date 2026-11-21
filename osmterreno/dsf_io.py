"""Entrada e saída dos DSF: 7z, DSFTool, propriedades, grade de altitude e lotes de triângulos."""
import os
import shutil
import struct
import sys
import tempfile

from .cancel import run_quiet
from .paths import PROJETO, raiz_projeto


def seven_zip():
    nome = "7z.exe" if os.name == "nt" else "7z"
    pasta = "win" if os.name == "nt" else "lin"
    candidatos = [
        os.path.join(PROJETO, "tools", pasta, nome),
        os.path.join(raiz_projeto(), nome),
        shutil.which(nome) or "",
        shutil.which("7zz") or "",
    ]
    if os.name == "nt":
        candidatos += [
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
        ]
    for path in candidatos:
        if path and os.path.isfile(path):
            return path
    raise FileNotFoundError("7z nao encontrado. Instale o 7-Zip.")


def dsf_tool():
    if sys.platform == "darwin":
        pasta, nome = "mac", "DSFTool"
    elif sys.platform.startswith("linux"):
        pasta, nome = "lin", "DSFTool"
    else:
        pasta, nome = "win", "DSFTool.exe"
    path = os.path.normpath(os.path.join(PROJETO, "tools", pasta, "tools", nome))
    if not os.path.isfile(path):
        raise FileNotFoundError("DSFTool nao encontrado em tools/%s/tools" % pasta)
    return path


def find_dsfs(folder):
    found = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if d not in ("_textures", "textures", "terrain")]
        if os.path.basename(dirpath).lower() != "earth nav data" and "earth nav data" not in dirpath.lower():
            continue
        for name in filenames:
            if name.endswith(".dsf") and name[0] in "+-" and not name.endswith(".bak"):
                found.append(os.path.join(dirpath, name))
    return found


def tile_of(path):
    name = os.path.splitext(os.path.basename(path))[0]
    # File name is the southwest corner, for example -24-047.
    return int(name[:3]), int(name[3:])


def read_props(data):
    props = {}
    off = 12
    end = len(data) - 16
    while off + 8 <= end:
        aid = data[off : off + 4][::-1].decode("ascii", "replace")
        length = struct.unpack_from("<I", data, off + 4)[0]
        if aid == "PROP":
            blob = data[off + 8 : off + length]
            parts = blob.split(b"\x00")
            for i in range(0, len(parts) - 1, 2):
                key = parts[i].decode("ascii", "replace")
                val = parts[i + 1].decode("ascii", "replace")
                if key:
                    props[key] = val
            return props
        if length < 8:
            break
        off += length
    return props


def load_dsf(path, work):
    with open(path, "rb") as handle:
        magic = handle.read(2)
    raw = os.path.join(work, os.path.basename(path) + ".raw")
    if os.path.isfile(raw):
        os.remove(raw)
    if magic == b"7z":
        run_quiet([seven_zip(), "e", "-y", "-o" + work, path])
        wanted = os.path.basename(path)
        if wanted.endswith(".antes_osm"):
            wanted = wanted[: -len(".antes_osm")]
        inner = os.path.join(work, wanted)
        if not os.path.isfile(inner):
            found = [name for name in os.listdir(work) if name.lower().endswith(".dsf")]
            if len(found) != 1:
                raise RuntimeError("o 7z nao continha o DSF")
            inner = os.path.join(work, found[0])
        return inner, True
    shutil.copy2(path, raw)
    return raw, False


def copy_dsf_atomic(source, dest):
    with tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.abspath(dest))) as work:
        pending = os.path.join(work, "tile.tmp")
        shutil.copy2(source, pending)
        os.replace(pending, dest)


def store_dsf(src_raw, dest, compressed):
    with open(src_raw, "rb") as handle:
        data_check = handle.read(8)
    if data_check != b"XPLNEDSF":
        raise RuntimeError("DSF invalido depois da edicao")
    if not compressed:
        copy_dsf_atomic(src_raw, dest)
        return
    folder = os.path.dirname(src_raw)
    with tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.abspath(dest))) as work:
        archive = os.path.join(work, "tile.7z")
        run_quiet(
            [seven_zip(), "a", "-t7z", "-m0=LZMA", "-mx=5", "-md=48m", archive, "--", os.path.basename(src_raw)],
            cwd=folder,
        )
        os.replace(archive, dest)


def sample_dem(grid, west, south, lon, lat):
    height, width = grid.shape
    row = (lat - south) * (height - 1)
    col = (lon - west) * (width - 1)
    row = min(max(row, 0), height - 1)
    col = min(max(col, 0), width - 1)
    r0 = int(row)
    c0 = int(col)
    r1 = min(r0 + 1, height - 1)
    c1 = min(c0 + 1, width - 1)
    fr = row - r0
    fc = col - c0
    value = (
        grid[r0, c0] * (1 - fr) * (1 - fc)
        + grid[r0, c1] * (1 - fr) * fc
        + grid[r1, c0] * fr * (1 - fc)
        + grid[r1, c1] * fr * fc
    )
    return float(value)


class Lote(list):
    def __init__(self, tipo):
        super().__init__()
        self.tipo = tipo


def triangulos_do_lote(batch):
    """O DSF gravado guarda tiras. Ler de 3 em 3 abre buraco no meio da tira."""
    tipo = getattr(batch, "tipo", 0)
    if tipo == 1:
        saida = []
        for indice in range(len(batch) - 2):
            a, b, c = batch[indice], batch[indice + 1], batch[indice + 2]
            saida.append((a, c, b) if indice % 2 else (a, b, c))
        return saida
    if tipo == 2 and batch:
        return [(batch[0], batch[indice], batch[indice + 1]) for indice in range(1, len(batch) - 1)]
    return [tuple(batch[indice : indice + 3]) for indice in range(0, len(batch) - 2, 3)]


def read_batches(src):
    """Gera (linha, lote) para cada linha do texto do DSF. O lote vem no END_PRIMITIVE."""
    primitive = False
    batch = Lote(0)
    with open(src, "r", encoding="utf-8", errors="ignore") as fin:
        for line in fin:
            if line.startswith("BEGIN_PRIMITIVE"):
                primitive = True
                partes = line.split()
                tipo = int(partes[1]) if len(partes) > 1 else 0
                batch = Lote(tipo)
                yield line, None
                continue
            if line.startswith("END_PRIMITIVE"):
                primitive = False
                yield line, batch
                continue
            if primitive and line.startswith("PATCH_VERTEX"):
                batch.append(tuple(float(item) for item in line.split()[1:]))
                continue
            yield line, None
