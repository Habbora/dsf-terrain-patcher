"""Prévia da malha: cache de triângulos, raster em PIL e a janela VisorMalha."""
import hashlib
import os
import shutil
import socket
import tempfile
import threading
import tkinter as tk
from math import cos, radians
from tkinter import ttk

import numpy

from .cancel import run_quiet
from .compile_job import dsfs_do_osm, ler_faixa
from .dsf_io import dsf_tool, load_dsf, read_batches, triangulos_do_lote
from .geo import vertex_key
from .mesh_cut import cortar_em_texto
from .osm_patch import BLEND_M, SEA_M, layers_of, load_patch
from .paths import CACHE_DIR


def porta_aberta(port):
    sock = socket.socket()
    try:
        sock.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def assinatura_arquivo(path):
    st = os.stat(path)
    marca = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
    return "%s:%d:%d" % (os.path.abspath(path), st.st_size, marca)


def chave_cache(partes):
    return hashlib.sha1("|".join(partes).encode("utf-8")).hexdigest()


def ler_cache_tris(chave):
    path = os.path.join(CACHE_DIR, chave + ".npz")
    if not os.path.isfile(path):
        return None
    try:
        with numpy.load(path) as data:
            return numpy.array(data["tris"], dtype=numpy.float64)
    except Exception:
        return None


def gravar_cache_tris(chave, tris):
    os.makedirs(CACHE_DIR, exist_ok=True)
    destino = os.path.join(CACHE_DIR, chave + ".npz")
    tmp = destino + ".part"
    numpy.savez_compressed(tmp, tris=numpy.asarray(tris, dtype=numpy.float64).reshape(-1, 3, 3))
    os.replace(tmp + ".npz", destino)


def triangulos_do_texto(txt, bbox):
    """Triângulos cuja caixa toca a área, mesmo quando os três cantos ficam de fora."""
    west, south, east, north = bbox
    seen = set()
    bruto = []
    for _line, batch in read_batches(txt):
        if batch is None:
            continue
        for verts in triangulos_do_lote(batch):
            lons = (verts[0][0], verts[1][0], verts[2][0])
            lats = (verts[0][1], verts[1][1], verts[2][1])
            if max(lons) < west or min(lons) > east or max(lats) < south or min(lats) > north:
                continue
            key = tuple(sorted(vertex_key(v) for v in verts))
            if key in seen:
                continue
            seen.add(key)
            bruto.append(
                (
                    verts[0][0], verts[0][1], verts[0][2],
                    verts[1][0], verts[1][1], verts[1][2],
                    verts[2][0], verts[2][1], verts[2][2],
                )
            )
    if not bruto:
        return numpy.zeros((0, 3, 3), dtype=numpy.float64)
    return numpy.asarray(bruto, dtype=numpy.float64).reshape(-1, 3, 3)


def malha_da_area(path, bbox):
    chave = chave_cache((assinatura_arquivo(path), "%.5f,%.5f,%.5f,%.5f" % bbox, "malha-tira"))
    pronto = ler_cache_tris(chave)
    if pronto is not None:
        return pronto, True
    work = tempfile.mkdtemp(prefix="visor_")
    try:
        raw, _compressed = load_dsf(path, work)
        txt = os.path.join(work, "tile.txt")
        run_quiet([dsf_tool(), "--dsf2text", raw, txt])
        tris = triangulos_do_texto(txt, bbox)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    gravar_cache_tris(chave, tris)
    return tris, False


def previa_da_area(path, layers, bbox, blend_m, otimizar, log, melhorar=False, marca=""):
    """Corta o original em memória, sem gravar o DSF, e devolve os triângulos da área."""
    backup = path + ".antes_osm"
    fonte = backup if os.path.isfile(backup) else path
    chave = chave_cache(
        (
            assinatura_arquivo(fonte),
            "%.5f,%.5f,%.5f,%.5f" % bbox,
            "previa",
            "%.3f" % blend_m,
            "1" if otimizar else "0",
            "1" if melhorar else "0",
            marca,
        )
    )
    pronto = ler_cache_tris(chave)
    if pronto is not None:
        return pronto, True
    work = tempfile.mkdtemp(prefix="previa_")
    try:
        out_txt = cortar_em_texto(path, work, layers, log, True, blend_m, otimizar, melhorar)
        tris = triangulos_do_texto(out_txt, bbox)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    gravar_cache_tris(chave, tris)
    return tris, False


def cor_rgb(z, low, high):
    if z <= SEA_M:
        return (29, 79, 140)
    t = 0.0 if high <= low else min(max((z - low) / (high - low), 0.0), 1.0)
    stops = ((0.0, (60, 140, 70)), (0.5, (200, 190, 90)), (1.0, (190, 90, 50)))
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t <= t1:
            k = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return tuple(int(c0[i] + (c1[i] - c0[i]) * k) for i in range(3))
    return (190, 90, 50)


def vista_com_aspecto(west, south, east, north, largura, altura):
    """Abre a caixa até a proporção da janela, para o pixel continuar quadrado."""
    meio = (south + north) * 0.5
    m_lon = 111320.0 * cos(radians(meio))
    mundo_w = max(east - west, 1e-8) * m_lon
    mundo_h = max(north - south, 1e-8) * 111320.0
    tela = largura / float(altura)
    if mundo_w / mundo_h < tela:
        mundo_w = mundo_h * tela
    else:
        mundo_h = mundo_w / tela
    cx = (west + east) * 0.5
    cy = (south + north) * 0.5
    return (
        cx - mundo_w * 0.5 / m_lon,
        cy - mundo_h * 0.5 / 111320.0,
        cx + mundo_w * 0.5 / m_lon,
        cy + mundo_h * 0.5 / 111320.0,
    )


def grade_dos_tris(tris):
    quantidade = len(tris)
    if quantidade == 0:
        return None
    west = float(tris[:, :, 0].min())
    east = float(tris[:, :, 0].max())
    south = float(tris[:, :, 1].min())
    north = float(tris[:, :, 1].max())
    cols = rows = 96
    cw = max(east - west, 1e-12) / cols
    ch = max(north - south, 1e-12) / rows
    cells = [[] for _ in range(cols * rows)]
    for indice in range(quantidade):
        tri = tris[indice]
        c0 = int((float(tri[:, 0].min()) - west) / cw)
        c1 = int((float(tri[:, 0].max()) - west) / cw)
        r0 = int((float(tri[:, 1].min()) - south) / ch)
        r1 = int((float(tri[:, 1].max()) - south) / ch)
        c0 = min(max(c0, 0), cols - 1)
        c1 = min(max(c1, 0), cols - 1)
        r0 = min(max(r0, 0), rows - 1)
        r1 = min(max(r1, 0), rows - 1)
        for linha in range(r0, r1 + 1):
            base = linha * cols
            for coluna in range(c0, c1 + 1):
                cells[base + coluna].append(indice)
    return {"cells": cells, "west": west, "south": south, "cw": cw, "ch": ch, "cols": cols, "rows": rows}


def ponto_no_triangulo(lon, lat, tri):
    x0, y0 = tri[0, 0], tri[0, 1]
    x1, y1 = tri[1, 0], tri[1, 1]
    x2, y2 = tri[2, 0], tri[2, 1]
    denominador = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if denominador == 0:
        return False
    a = ((y1 - y2) * (lon - x2) + (x2 - x1) * (lat - y2)) / denominador
    b = ((y2 - y0) * (lon - x2) + (x0 - x2) * (lat - y2)) / denominador
    c = 1.0 - a - b
    return a >= -1e-8 and b >= -1e-8 and c >= -1e-8


def triangulo_na_grade(grade, tris, lon, lat):
    if not grade:
        return None
    coluna = int((lon - grade["west"]) / grade["cw"])
    linha = int((lat - grade["south"]) / grade["ch"])
    if coluna < 0 or linha < 0 or coluna >= grade["cols"] or linha >= grade["rows"]:
        return None
    for indice in grade["cells"][linha * grade["cols"] + coluna]:
        tri = tris[indice]
        if ponto_no_triangulo(lon, lat, tri):
            return tri
    return None


def raster_malha(tris, vista, largura, altura, low, high, aneis):
    """Uma imagem só. A janela não aguenta um polígono do Tk por triângulo."""
    from PIL import Image, ImageDraw

    west, south, east, north = vista
    imagem = Image.new("RGB", (largura, altura), (17, 17, 17))
    draw = ImageDraw.Draw(imagem)
    m_lon = 111320.0 * cos(radians((south + north) * 0.5))
    sx = largura / max((east - west) * m_lon, 1e-6)
    sy = altura / max((north - south) * 111320.0, 1e-6)
    for tri in tris:
        lons = tri[:, 0]
        lats = tri[:, 1]
        if float(lons.max()) < west or float(lons.min()) > east or float(lats.max()) < south or float(lats.min()) > north:
            continue
        pontos = [((float(lon) - west) * m_lon * sx, (north - float(lat)) * 111320.0 * sy) for lon, lat in zip(lons, lats)]
        draw.polygon(pontos, fill=cor_rgb(float(tri[:, 2].mean()), low, high), outline=(0, 0, 0))
    for anel, cor in aneis:
        pontos = [((lon - west) * m_lon * sx, (north - lat) * 111320.0 * sy) for lon, lat in anel]
        if len(pontos) >= 2:
            draw.line(pontos, fill=cor, width=2)
    return imagem


class VisorMalha(tk.Toplevel):
    def __init__(self, master, folder, osm, blend_m=BLEND_M, melhorar=False):
        super().__init__(master)
        self.blend_m = blend_m
        self.melhorar = melhorar
        self.title("Malha — " + os.path.basename(osm))
        self.geometry("1000x760")
        self.folder = folder
        self.osm = osm
        self.fonte = tk.StringVar(value="atual")
        self.info = tk.StringVar(value="Lendo o DSF…")
        self.tris = None
        self.grade = None
        self.low = 0.0
        self.high = 1.0
        self.foto = None
        self.vista = None
        self._vista_pedida = None
        self._zoom_origem = None
        self._ox = 0.0
        self._oy = 0.0
        self._k = 1.0
        self._sx = 1.0
        self._sy = 1.0
        self._arrasto = None
        self._moveu = False
        self._raster_pedido = 0
        self._tela = (0, 0)
        topo = ttk.Frame(self)
        topo.pack(fill="x", padx=8, pady=6)
        ttk.Radiobutton(topo, text="Atual", variable=self.fonte, value="atual", command=self.carregar).pack(side="left")
        ttk.Radiobutton(topo, text="Original", variable=self.fonte, value="original", command=self.carregar).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(topo, text="Prévia", variable=self.fonte, value="previa", command=self.carregar).pack(side="left", padx=(8, 0))
        ttk.Button(topo, text="Gerar prévia", command=self.gerar_previa).pack(side="left", padx=(8, 0))
        ttk.Label(topo, textvariable=self.info).pack(side="left", padx=12)
        self.canvas = tk.Canvas(self, background="#111111", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        rodape = ttk.Frame(self)
        rodape.pack(fill="x", padx=8, pady=4)
        self.posicao = tk.StringVar(value="")
        ttk.Label(rodape, textvariable=self.posicao, font=("Consolas", 10)).pack(side="left")
        ttk.Label(
            rodape,
            text="Roda: zoom   Arrastar: mover   Botão direito: copiar coordenada",
        ).pack(side="right")
        self.canvas.bind("<MouseWheel>", self.zoom)
        self.canvas.bind("<ButtonPress-3>", self.copiar_coordenada)
        self.canvas.bind("<ButtonPress-1>", self.iniciar_arrasto)
        self.canvas.bind("<B1-Motion>", self.arrastar)
        self.canvas.bind("<ButtonRelease-1>", self.soltar)
        self.canvas.bind("<Motion>", self.mostrar_altura)
        self.canvas.bind("<Configure>", self.redimensionar)
        self.flats, self.ramps, bounds = load_patch(osm)
        pad = 250.0 / 111320.0
        self.bbox = (bounds[0] - pad, bounds[1] - pad, bounds[2] + pad, bounds[3] + pad)
        self.aneis = [(list(polygon.exterior.coords), (255, 59, 59)) for polygon, _alt in self.flats]
        self.aneis += [(list(polygon.exterior.coords), (255, 159, 26)) for polygon, *_rest in self.ramps]
        self.after(60, self.carregar)

    def _config_atual(self):
        try:
            faixa = ler_faixa(self.master.faixa.get())
        except Exception:
            faixa = self.blend_m
        return faixa, bool(self.master.otimizar.get()), bool(self.master.melhorar.get())

    def gerar_previa(self):
        self.fonte.set("previa")
        self.carregar()

    def carregar(self):
        paths = dsfs_do_osm(self.folder, self.osm)
        if not paths:
            self.info.set("Nenhum DSF cobre esse OSM.")
            return
        fonte = self.fonte.get()
        self.pedido = getattr(self, "pedido", 0) + 1
        pedido = self.pedido
        escolhidos = []
        for path in paths:
            backup = path + ".antes_osm"
            if fonte == "original":
                if os.path.isfile(backup):
                    escolhidos.append(backup)
            else:
                escolhidos.append(path)
        if not escolhidos:
            self.info.set("Esse tile ainda não tem backup .antes_osm.")
            return
        previa = fonte == "previa"
        blend_m, otimizar, melhorar = self._config_atual()
        self.blend_m = blend_m
        self.info.set(
            "Prévia com a configuração atual…" if previa else "Lendo o DSF…"
        )
        bbox = self.bbox
        layers = layers_of(self.flats, self.ramps)
        marca = assinatura_arquivo(self.osm) if previa else ""

        def aviso(texto):
            self.after(0, lambda: pedido == self.pedido and self.info.set("Prévia: " + texto))

        def trabalho():
            try:
                partes = []
                do_cache = True
                for path in escolhidos:
                    if previa:
                        tris, usou = previa_da_area(
                            path, layers, bbox, blend_m, otimizar, aviso, melhorar, marca
                        )
                    else:
                        tris, usou = malha_da_area(path, bbox)
                    do_cache = do_cache and usou
                    partes.append(tris)
                if not partes:
                    juntos = numpy.zeros((0, 3, 3), dtype=numpy.float64)
                else:
                    juntos = numpy.concatenate(partes, axis=0)
                grade = grade_dos_tris(juntos)
            except Exception as exc:
                self.after(0, lambda exc=exc: pedido == self.pedido and self.info.set("Erro: " + str(exc)))
                return
            self.after(0, lambda: pedido == self.pedido and self.receber(juntos, grade, do_cache))

        threading.Thread(target=trabalho, daemon=True).start()

    def receber(self, tris, grade, do_cache):
        if not self.winfo_exists():
            return
        self.tris = tris
        self.grade = grade
        if len(tris):
            zs = tris[:, :, 2]
            acima = zs[zs > SEA_M]
            self.low = float(acima.min()) if acima.size else 0.0
            self.high = float(acima.max()) if acima.size else 1.0
        else:
            self.low, self.high = 0.0, 1.0
        nome = {"atual": "atual", "original": "original", "previa": "prévia"}[self.fonte.get()]
        origem = "cache" if do_cache else "lido agora"
        if self.fonte.get() == "previa":
            _, otimizar, melhorar = self._config_atual()
            origem += "   otimizar %s   melhorar %s" % (
                "sim" if otimizar else "não",
                "sim" if melhorar else "não",
            )
        self.info.set(
            "%s: %d triângulos na área   altura %.1f a %.1f m   %s"
            % (nome, len(tris), self.low, self.high, origem)
        )
        self.vista = None
        self._vista_pedida = None
        self._pedir_raster(self.bbox, ajustar=True)

    def _pedir_raster(self, caixa, ajustar=False):
        if self.tris is None or not self.winfo_exists():
            return
        largura = self.canvas.winfo_width()
        altura = self.canvas.winfo_height()
        if largura < 50 or altura < 50:
            self.after(50, lambda: self._pedir_raster(caixa, ajustar))
            return
        if ajustar:
            vista = vista_com_aspecto(caixa[0], caixa[1], caixa[2], caixa[3], largura, altura)
        else:
            vista = caixa
        self._raster_pedido += 1
        pedido = self._raster_pedido
        tris = self.tris
        low, high = self.low, self.high
        aneis = self.aneis

        def trabalho():
            try:
                imagem = raster_malha(tris, vista, largura, altura, low, high, aneis)
            except Exception as exc:
                self.after(0, lambda exc=exc: pedido == self._raster_pedido and self.info.set("Erro ao desenhar: " + str(exc)))
                return
            self.after(0, lambda: pedido == self._raster_pedido and self.mostrar_imagem(imagem, vista))

        threading.Thread(target=trabalho, daemon=True).start()

    def mostrar_imagem(self, imagem, vista):
        if not self.winfo_exists():
            return
        from PIL import ImageTk

        west, south, east, north = vista
        largura, altura = imagem.size
        m_lon = 111320.0 * cos(radians((south + north) * 0.5))
        self.vista = vista
        self._ox = 0.0
        self._oy = 0.0
        self._k = 1.0
        self._zoom_origem = None
        if self._vista_pedida == vista:
            self._vista_pedida = None
        self._sx = largura / max((east - west) * m_lon, 1e-6)
        self._sy = altura / max((north - south) * 111320.0, 1e-6)
        self._tela = (largura, altura)
        self.foto = ImageTk.PhotoImage(imagem)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.foto, anchor="nw", tags="mapa")

    def redimensionar(self, event):
        if self.tris is None or self.vista is None or self._moveu:
            return
        if abs(event.width - self._tela[0]) < 12 and abs(event.height - self._tela[1]) < 12:
            return
        pendente = getattr(self, "_resize", None)
        if pendente:
            self.after_cancel(pendente)
        self._resize = self.after(200, lambda: self._pedir_raster(self.vista, ajustar=True))

    def zoom(self, event):
        if self.vista is None:
            return
        fator = 1.25 if event.delta > 0 else 0.8
        if self._zoom_origem is None:
            self._zoom_origem = self.vista
            self._zoom_xy = (event.x, event.y)
            self._zoom_fator = 1.0
        self._zoom_fator *= fator
        x, y = self._zoom_xy
        caixa = self._zoom_caixa(self._zoom_origem, x, y, self._zoom_fator)
        self._vista_pedida = caixa
        pendente = getattr(self, "_zoom", None)
        if pendente:
            self.after_cancel(pendente)
        self._zoom = self.after(80, lambda caixa=caixa: self._pedir_raster(caixa, ajustar=False))

    def _zoom_caixa(self, caixa, x, y, fator):
        west, south, east, north = caixa
        largura = max(self.canvas.winfo_width(), 1)
        altura = max(self.canvas.winfo_height(), 1)
        lon = west + (east - west) * (x / largura)
        lat = north - (north - south) * (y / altura)
        span_lon = min(max((east - west) / fator, 1e-6), 40.0)
        span_lat = min(max((north - south) / fator, 1e-6), 40.0)
        esquerda = lon - span_lon * (x / largura)
        cima = lat + span_lat * (y / altura)
        return (esquerda, cima - span_lat, esquerda + span_lon, cima)

    def iniciar_arrasto(self, event):
        self._arrasto = (event.x, event.y)
        self._moveu = False

    def arrastar(self, event):
        if not self._arrasto or self.vista is None:
            return
        dx = event.x - self._arrasto[0]
        dy = event.y - self._arrasto[1]
        if dx or dy:
            self._moveu = True
        self._arrasto = (event.x, event.y)
        self._ox += dx
        self._oy += dy
        self.canvas.move("mapa", dx, dy)

    def soltar(self, event):
        if self._arrasto is None or self.vista is None or not self._moveu:
            self._arrasto = None
            return
        self._arrasto = None
        self._zoom_origem = None
        west, south, east, north = self.vista
        m_lon = 111320.0 * cos(radians((south + north) * 0.5))
        dlon = -self._ox / self._sx / m_lon
        dlat = self._oy / self._sy / 111320.0
        self._vista_pedida = (west + dlon, south + dlat, east + dlon, north + dlat)
        self._pedir_raster(self._vista_pedida, ajustar=False)

    def _mundo(self, x, y):
        bx = x - self._ox
        by = y - self._oy
        return (self.vista[3] - by / self._sy, self.vista[0] + bx / self._sx)

    def coordenada(self, event):
        if self.vista is None:
            return None
        return self._mundo(event.x, event.y)

    def mostrar_altura(self, event):
        ponto = self.coordenada(event)
        if ponto is None:
            return
        texto = "lat %.7f   lon %.7f" % ponto
        tri = triangulo_na_grade(self.grade, self.tris, ponto[1], ponto[0])
        if tri is not None:
            texto += "   vértices: %s m" % ", ".join("%.2f" % float(v) for v in tri[:, 2])
        self.posicao.set(texto)

    def copiar_coordenada(self, event):
        ponto = self.coordenada(event)
        if ponto is None:
            return
        texto = "%.7f, %.7f" % ponto
        self.clipboard_clear()
        self.clipboard_append(texto)
        self.posicao.set("copiado: " + texto)
