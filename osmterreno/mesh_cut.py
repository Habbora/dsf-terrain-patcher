"""Corte da malha do DSF nas bordas do OSM."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from math import cos, hypot, radians

import numpy
from shapely import constrained_delaunay_triangles, get_coordinates
from shapely.geometry import MultiPoint, Polygon
from shapely.ops import snap, unary_union
from shapely.prepared import prep

from .cancel import NO_WINDOW, run_quiet, verificar_cancelamento
from .dsf_io import (
    dsf_tool,
    load_dsf,
    read_batches,
    read_props,
    sample_dem,
    store_dsf,
    tile_of,
    triangulos_do_lote,
)
from .geo import (
    barycentric,
    edge_key,
    format_vertex,
    interpolate_vertex,
    signed_area,
    surface_parts,
    vertex_key,
)
from .mesh_optimize import merge_flat, snap_layers, triangulate_face
from .osm_patch import BLEND_M, SEA_M, height_on_mesh
from .paths import PROJETO, comando_self


def clip_polygons(layers, region):
    """Contorno de cada polígono e uma única borda externa da faixa."""
    clips = [polygon for polygon, _spec in layers]
    if not region.is_empty:
        clips.append(region)
    return clips


class CortadorSeguro:
    """Corta cada triângulo num processo à parte. Se a melhoria de ângulo cair, o contorno ainda é cortado."""

    def __init__(self, clips, region, quality):
        self.clips = clips
        self.region = region
        self.quality = bool(quality)
        self.proc = None
        self.pulou = False
        self.recuados = 0
        self.feitos = 0
        self._abrir(self.quality)

    def _abrir(self, quality):
        self.proc = subprocess.Popen(
            comando_self("--cortar"),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=NO_WINDOW if os.name == "nt" else 0,
            cwd=PROJETO,
        )
        cabeca = json.dumps({
            "clips": [polygon.wkt for polygon in self.clips],
            "region": self.region.wkt,
            "quality": bool(quality),
        })
        self.proc.stdin.write((cabeca + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def _uma(self, verts):
        if self.proc is None or self.proc.poll() is not None:
            return None
        try:
            self.proc.stdin.write((json.dumps(verts) + "\n").encode("utf-8"))
            self.proc.stdin.flush()
            linha = self.proc.stdout.readline()
        except OSError:
            return None
        if not linha:
            self.fechar()
            return None
        data = json.loads(linha.decode("utf-8"))
        if isinstance(data, dict):
            return None
        return [tuple(ponto) for ponto in data]

    def cortar(self, verts):
        self.pulou = False
        if self.proc is None or self.proc.poll() is not None:
            self._abrir(self.quality)
        data = self._uma(verts)
        if data is None and self.quality:
            self.fechar()
            self._abrir(False)
            data = self._uma(verts)
            self.fechar()
            self._abrir(self.quality)
            if data is not None:
                self.recuados += 1
        if data is None:
            self.pulou = True
            if self.proc is None or self.proc.poll() is not None:
                self._abrir(self.quality)
            return [tuple(tuple(p) for p in verts)]
        self.feitos += 1
        if self.quality and self.feitos % 1500 == 0:
            self.fechar()
            self._abrir(self.quality)
        return data

    def fechar(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
        self.proc = None


def cut_triangle(verts, clips, region, quality=False):
    """Divide um triângulo nas bordas do OSM. Cada vértice é (lon, lat, extras)."""
    corners = [(v[0], v[1]) for v in verts]
    if corners[0] == corners[1] or corners[1] == corners[2] or corners[0] == corners[2]:
        return [verts]
    tri = Polygon(corners)
    if tri.is_empty or not tri.is_valid:
        tri = tri.buffer(0)
    if tri.is_empty or not region.intersects(tri):
        return [verts]
    touch = []
    for polygon in clips:
        if polygon.intersects(tri):
            touch.extend(get_coordinates(tri.exterior.intersection(polygon.boundary)).tolist())
    extra = [p for p in touch if min(hypot(p[0] - c[0], p[1] - c[1]) for c in corners) > 1e-11]
    if extra:
        tri = snap(tri, MultiPoint(extra), 1e-11)
    pieces = [tri]
    for polygon in clips:
        nxt = []
        for piece in pieces:
            if piece.is_empty or not piece.intersects(polygon):
                nxt.append(piece)
                continue
            nxt.extend(surface_parts(piece.intersection(polygon)))
            nxt.extend(surface_parts(piece.difference(polygon)))
        pieces = nxt
    if not extra and len(pieces) == 1 and abs(pieces[0].area - tri.area) <= tri.area * 1e-9:
        return [verts]
    origin = signed_area(corners[0], corners[1], corners[2])
    made = []
    for piece in pieces:
        smalls = triangulate_face(piece) if quality else surface_parts(constrained_delaunay_triangles(piece))
        if smalls is None:
            raise RuntimeError("triangulacao da face falhou")
        for small in smalls:
            if small.area <= 1e-16:
                continue
            ring = list(small.exterior.coords)[:3]
            if origin * signed_area(ring[0], ring[1], ring[2]) < 0:
                ring = [ring[0], ring[2], ring[1]]
            made.append(tuple(interpolate_vertex(point, verts) for point in ring))
    return made or [verts]


def cut_mesh_text(src, dst, layers, grid, west, south, log, proteger_agua=True, blend_m=BLEND_M, otimizar=False, melhorar=False):
    if melhorar:
        layers, region = snap_layers(src, layers, blend_m, log)
    else:
        region = unary_union([polygon for polygon, _spec in layers]).buffer(blend_m / 111320.0)
    minx, miny, maxx, maxy = region.bounds
    m_lon = 111320.0 * cos(radians((miny + maxy) * 0.5))
    if melhorar:
        clips = [polygon for polygon, _spec in layers]
    else:
        clips = clip_polygons(layers, region)
    region_ready = prep(region)
    airport_ready = prep(unary_union([polygon for polygon, _spec in layers]))
    pad = 0.002

    def decide(verts):
        lons = [v[0] for v in verts]
        lats = [v[1] for v in verts]
        if (
            max(lons) < minx - pad
            or min(lons) > maxx + pad
            or max(lats) < miny - pad
            or min(lats) > maxy + pad
        ):
            return None
        tri = Polygon([(v[0], v[1]) for v in verts])
        if tri.is_empty or not region_ready.intersects(tri):
            return False
        if proteger_agua and not airport_ready.intersects(tri):
            if all(sample_dem(grid, west, south, v[0], v[1]) <= SEA_M for v in verts):
                return False
        return True

    log("procurando a borda da malha")
    decisions = []
    locked_points = set()
    locked_edges = set()
    for _line, batch in read_batches(src):
        if batch is None:
            continue
        for verts in triangulos_do_lote(batch):
            verificar_cancelamento()
            choice = decide(verts)
            if choice is None:
                continue
            decisions.append(choice)
            if not choice:
                for n in range(3):
                    locked_points.add(vertex_key(verts[n]))
                    locked_edges.add(edge_key(verts[n], verts[(n + 1) % 3]))

    def z_for(vertex, verts):
        weights = barycentric(vertex, verts[0], verts[1], verts[2])
        tiny = 1e-7
        zero = [n for n in range(3) if abs(weights[n]) <= tiny]
        if len(zero) >= 2:
            corner = next(n for n in range(3) if n not in zero)
            if vertex_key(verts[corner]) in locked_points:
                return vertex[2]
        elif len(zero) == 1:
            a, b = [n for n in range(3) if n != zero[0]]
            if edge_key(verts[a], verts[b]) in locked_edges:
                return vertex[2]
        if vertex_key(vertex) in locked_points:
            return vertex[2]
        dem_z = sample_dem(grid, west, south, vertex[0], vertex[1])
        z_value = height_on_mesh(vertex[0], vertex[1], layers, m_lon, dem_z, proteger_agua, blend_m)
        return vertex[2] if z_value is None else z_value

    log("cortando os triangulos")
    kept = 0
    cut = 0
    pulados = 0
    cortador = CortadorSeguro(clips, region, melhorar)
    turn = 0
    before = 0
    after = 0
    pending_begin = None
    patch_begin = None
    patch_cut = []

    def write_block(begin, pieces):
        for start in range(0, len(pieces), 2000):
            fout.write("BEGIN_PRIMITIVE 0\n")
            for piece in pieces[start : start + 2000]:
                for vertex in piece:
                    fout.write(format_vertex(vertex, vertex[2]))
            fout.write("END_PRIMITIVE\n")

    try:
        with open(dst, "w", encoding="utf-8", newline="\n") as fout:
            for line, batch in read_batches(src):
                if batch is None:
                    if line.startswith("BEGIN_PRIMITIVE"):
                        pending_begin = line
                        continue
                    if line.startswith("END_PATCH") and patch_cut:
                        before += len(patch_cut)
                        merged = merge_flat(patch_cut)
                        after += len(merged)
                        write_block(patch_begin, merged)
                        patch_cut = []
                    fout.write(line)
                    continue
                begin = pending_begin or "BEGIN_PRIMITIVE 0\n"
                direct = []
                made = []
                for verts in triangulos_do_lote(batch):
                    verificar_cancelamento()
                    lons = [v[0] for v in verts]
                    lats = [v[1] for v in verts]
                    near = not (
                        max(lons) < minx - pad
                        or min(lons) > maxx + pad
                        or max(lats) < miny - pad
                        or min(lats) > maxy + pad
                    )
                    do_cut = False
                    if near:
                        do_cut = decisions[turn]
                        turn += 1
                    if not do_cut:
                        direct.append(tuple(verts))
                        kept += 1
                        continue
                    for piece in cortador.cortar(verts):
                        made.append(tuple((v[0], v[1], z_for(v, verts), *v[3:]) for v in piece))
                    if cortador.pulou:
                        pulados += 1
                    cut += 1
                    if cut % 2000 == 0:
                        log("cortando... %d" % cut)
                if otimizar and begin.split()[1:2] == ["0"]:
                    patch_begin = begin
                    patch_cut.extend(made)
                    made = []
                if direct or made:
                    fout.write("BEGIN_PRIMITIVE 0\n")
                    for piece in direct + made:
                        for vertex in piece:
                            fout.write(format_vertex(vertex, vertex[2]))
                    fout.write(line)
    finally:
        cortador.fechar()
    log("triangulos cortados %d, mantidos %d" % (cut, kept))
    if cortador.recuados:
        log("triangulos cortados no contorno, sem melhoria de angulo: %d" % cortador.recuados)
    if pulados:
        log("triangulos mantidos inteiros porque o corte interno falhou: %d" % pulados)
    if otimizar:
        log("otimizacao: %d pedacos viraram %d" % (before, after))
    return cut


def cortar_em_texto(path, work, layers, log, proteger_agua=True, blend_m=BLEND_M, otimizar=False, melhorar=False):
    """Extrai o DSF original em texto e grava o corte em work/cut.txt."""
    backup = path + ".antes_osm"
    source = backup if os.path.isfile(backup) else path
    inicio = time.time()
    raw, _compressed = load_dsf(source, work)
    log("7z aberto em %.0f s" % (time.time() - inicio))
    txt = os.path.join(work, "tile.txt")
    inicio = time.time()
    run_quiet([dsf_tool(), "--dsf2text", raw, txt])
    log("malha em texto em %.0f s" % (time.time() - inicio))
    elev = txt + ".elevation.raw"
    if not os.path.isfile(elev):
        raise RuntimeError("o tile nao tem grade de altitude: " + os.path.basename(path))
    count = os.path.getsize(elev) // 2
    side = int(round(count ** 0.5))
    grid = numpy.fromfile(elev, dtype="<i2", count=side * side).reshape(side, side)
    data = open(raw, "rb").read()
    props = read_props(data)
    lat, lon = tile_of(path)
    west = float(props.get("sim/west", lon))
    south = float(props.get("sim/south", lat))
    out_txt = os.path.join(work, "cut.txt")
    inicio = time.time()
    cut_mesh_text(txt, out_txt, layers, grid, west, south, log, proteger_agua, blend_m, otimizar, melhorar)
    log("corte em %.0f s" % (time.time() - inicio))
    return out_txt


def recortar_dsf(path, layers, log, proteger_agua=True, blend_m=BLEND_M, otimizar=False, melhorar=False):
    """Corta a malha do DSF original e grava por cima, sem trocar o backup."""
    work = tempfile.mkdtemp(prefix="malha_")
    try:
        out_txt = cortar_em_texto(path, work, layers, log, proteger_agua, blend_m, otimizar, melhorar)
        out_dsf = os.path.join(work, os.path.basename(path))
        inicio = time.time()
        run_quiet([dsf_tool(), "--text2dsf", out_txt, out_dsf])
        log("texto para dsf em %.0f s" % (time.time() - inicio))
        inicio = time.time()
        store_dsf(out_dsf, path, True)
        log("7z gravado em %.0f s" % (time.time() - inicio))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def servir_cortes():
    """Processo auxiliar: corta um triângulo por linha e morre sem levar a compilação."""
    from shapely import wkt

    cabeca = json.loads(sys.stdin.buffer.readline().decode("utf-8"))
    clips = [wkt.loads(texto) for texto in cabeca["clips"]]
    region = wkt.loads(cabeca["region"])
    quality = bool(cabeca["quality"])
    for bruto in sys.stdin.buffer:
        verts = [tuple(ponto) for ponto in json.loads(bruto.decode("utf-8"))]
        try:
            feito = cut_triangle(verts, clips, region, quality)
            saida = json.dumps(feito)
        except Exception:
            saida = json.dumps({"erro": True})
        sys.stdout.buffer.write((saida + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()
