"""Janela principal do X-Plane DSF Terrain Patcher."""
import os
import shutil
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import APP_NAME
from .cancel import Cancelado, cancelar, pedir_cancelamento
from .compile_job import (
    aplicar,
    compilar_varios,
    gravar_config,
    gravar_log,
    iniciar_log,
    ler_config,
    ler_faixa,
    recuperar,
    recuperar_varios,
)
from .editor_launch import abrir_editor
from .osm_patch import BLEND_M
from .paths import OSM_DIR
from .preview import VisorMalha


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("860x580")
        self.minsize(720, 480)
        cfg = ler_config()
        self.folder = tk.StringVar(value=cfg["pasta"])
        self.faixa = tk.StringVar(value=str(cfg.get("faixa", 70)))
        self.otimizar = tk.BooleanVar(value=bool(cfg.get("otimizar", False)))
        self.melhorar = tk.BooleanVar(value=bool(cfg.get("melhorar", False)))
        self.status = tk.StringVar(value="Pronto")
        self.busy = False
        self.fechando = False
        self.botoes = []
        self.protocol("WM_DELETE_WINDOW", self.ao_fechar)
        pad = {"padx": 10, "pady": 4}
        frm = ttk.Frame(self)
        frm.pack(fill="x", **pad)
        ttk.Label(frm, text="Pasta dos terrenos").grid(row=0, column=0, sticky="w")
        self.entrada_pasta = ttk.Entry(frm, textvariable=self.folder, width=78)
        self.entrada_pasta.grid(row=1, column=0, sticky="we")
        self._botao(frm, "Pasta...", self.pick_folder).grid(row=1, column=1, padx=6)
        frm.columnconfigure(0, weight=1)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, **pad)
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        ttk.Label(left, text="OSM  ·  clique para selecionar, Ctrl para vários").pack(anchor="w")
        caixa = ttk.Frame(left)
        caixa.pack(fill="both", expand=True)
        self.lista = tk.Listbox(caixa, selectmode="extended", exportselection=False, activestyle="dotbox")
        barra = ttk.Scrollbar(caixa, orient="vertical", command=self.lista.yview)
        self.lista.configure(yscrollcommand=barra.set)
        self.lista.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        botoes = ttk.Frame(left)
        botoes.pack(fill="x", pady=6)
        for texto, comando in (
            ("Novo", self.novo),
            ("Importar", self.importar),
            ("Exportar", self.exportar),
            ("Apagar", self.apagar),
            ("Editar", self.editar),
            ("Ver malha", self.ver_malha),
            ("Selecionar tudo", self.marcar_todos),
            ("Desmarcar tudo", self.desmarcar_todos),
        ):
            self._botao(botoes, texto, comando).pack(side="left", padx=(0, 4))

        acoes = ttk.LabelFrame(body, text="Ações")
        acoes.pack(side="left", fill="y", padx=(10, 0))
        ttk.Label(acoes, text="Faixa ao redor (m)").pack(anchor="w", padx=8, pady=(8, 0))
        self.entrada_faixa = ttk.Entry(acoes, textvariable=self.faixa, width=8)
        self.entrada_faixa.pack(anchor="w", padx=8, pady=(2, 6))
        self.caixa_otimizar = ttk.Checkbutton(acoes, text="Otimizar malha (teste)", variable=self.otimizar)
        self.caixa_otimizar.pack(anchor="w", padx=8, pady=(0, 6))
        self.caixa_melhorar = ttk.Checkbutton(acoes, text="Melhorar triângulos", variable=self.melhorar)
        self.caixa_melhorar.pack(anchor="w", padx=8, pady=(0, 6))
        self._botao(acoes, "Compilar", self.compilar).pack(fill="x", padx=8, pady=(8, 4))
        self._botao(acoes, "Recuperar", self.recuperar_click).pack(fill="x", padx=8, pady=4)

        self.log = tk.Text(self, height=12, wrap="word")
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 4))
        rodape = ttk.Frame(self)
        rodape.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(rodape, textvariable=self.status).pack(anchor="w")
        self.progresso = ttk.Progressbar(rodape, mode="determinate", maximum=1)
        self.progresso.pack(fill="x", pady=(4, 0))
        self.recarregar()

    def _botao(self, pai, texto, comando):
        botao = ttk.Button(pai, text=texto, command=comando)
        self.botoes.append(botao)
        return botao

    def ao_fechar(self):
        if self.busy:
            if not messagebox.askyesno(
                APP_NAME,
                "A compilação está em andamento.\nCancelar tudo e fechar?",
            ):
                return
            self.fechando = True
            pedir_cancelamento()
            self.destroy()
            return
        if messagebox.askokcancel(APP_NAME, "Fechar o programa?"):
            self.fechando = True
            self.destroy()

    def _travar(self, travado):
        estado = "disabled" if travado else "normal"
        for botao in self.botoes:
            botao.configure(state=estado)
        self.entrada_pasta.configure(state=estado)
        self.entrada_faixa.configure(state=estado)
        self.caixa_otimizar.configure(state=estado)
        self.caixa_melhorar.configure(state=estado)
        self.lista.configure(state=estado)

    def pick_folder(self):
        path = filedialog.askdirectory(initialdir=self.folder.get() or "D:\\")
        if path:
            self.folder.set(path)
            try:
                faixa = ler_faixa(self.faixa.get())
            except RuntimeError:
                faixa = 70
            gravar_config(path, faixa, self.otimizar.get(), self.melhorar.get())

    def selecionados(self):
        escolhidos = [self.lista.get(i) for i in self.lista.curselection()]
        if not escolhidos:
            messagebox.showinfo(APP_NAME, "Selecione um ou mais OSM na lista.")
            return []
        return [os.path.join(OSM_DIR, nome) for nome in escolhidos]

    def marcar_todos(self):
        self.lista.selection_set(0, "end")

    def desmarcar_todos(self):
        self.lista.selection_clear(0, "end")

    def recarregar(self, nome=None):
        self.lista.delete(0, "end")
        os.makedirs(OSM_DIR, exist_ok=True)
        nomes = sorted(n for n in os.listdir(OSM_DIR) if n.lower().endswith(".osm"))
        for nome_arquivo in nomes:
            self.lista.insert("end", nome_arquivo)
        if nome in nomes:
            indice = nomes.index(nome)
            self.lista.selection_set(indice)
            self.lista.see(indice)

    def novo(self):
        nome = simpledialog.askstring(APP_NAME, "Nome do OSM novo:", parent=self)
        if not nome:
            return
        nome = nome.strip()
        if not nome.lower().endswith(".osm"):
            nome += ".osm"
        if any(c in nome for c in '\\/:*?"<>|'):
            messagebox.showerror(APP_NAME, "O nome tem um caractere que não pode ir no arquivo.")
            return
        destino = os.path.join(OSM_DIR, nome)
        if os.path.exists(destino):
            messagebox.showerror(APP_NAME, "Já existe um OSM com esse nome.")
            return
        os.makedirs(OSM_DIR, exist_ok=True)
        with open(destino, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(f'<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6" generator="{APP_NAME}">\n</osm>\n')
        self.recarregar(nome)
        self.write("criado " + nome)

    def importar(self):
        path = filedialog.askopenfilename(
            initialdir=OSM_DIR,
            filetypes=[("OSM", "*.osm"), ("Todos", "*.*")],
        )
        if not path:
            return
        destino = os.path.join(OSM_DIR, os.path.basename(path))
        if os.path.abspath(path) != os.path.abspath(destino):
            shutil.copy2(path, destino)
        self.recarregar(os.path.basename(destino))
        self.write("importado " + os.path.basename(destino))

    def exportar(self):
        origens = self.selecionados()
        if not origens:
            return
        if len(origens) == 1:
            origem = origens[0]
            destino = filedialog.asksaveasfilename(
                initialfile=os.path.basename(origem),
                defaultextension=".osm",
                filetypes=[("OSM", "*.osm")],
            )
            if not destino:
                return
            shutil.copy2(origem, destino)
            self.write("exportado " + destino)
            return
        pasta = filedialog.askdirectory()
        if not pasta:
            return
        for origem in origens:
            destino = os.path.join(pasta, os.path.basename(origem))
            shutil.copy2(origem, destino)
            self.write("exportado " + destino)

    def apagar(self):
        origens = self.selecionados()
        if not origens:
            return
        nomes = ", ".join(os.path.basename(p) for p in origens)
        if not messagebox.askyesno(APP_NAME, "Apagar da lista: " + nomes + "?"):
            return
        for origem in origens:
            os.remove(origem)
            self.write("apagado " + os.path.basename(origem))
        self.recarregar()

    def editar(self):
        origens = self.selecionados()
        if not origens:
            return
        if len(origens) > 1:
            messagebox.showinfo(APP_NAME, "Editar abre um OSM. Deixe só um selecionado.")
            return
        try:
            abrir_editor(origens[0])
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self.write("editor aberto em " + os.path.basename(origens[0]))

    def ver_malha(self):
        origens = self.selecionados()
        if not origens:
            return
        if len(origens) > 1:
            messagebox.showinfo(APP_NAME, "Ver malha abre um OSM. Deixe só um selecionado.")
            return
        folder = self.folder.get().strip()
        if not os.path.isdir(folder):
            messagebox.showerror(APP_NAME, "A pasta dos terrenos nao existe.")
            return
        try:
            blend_m = ler_faixa(self.faixa.get())
        except RuntimeError:
            blend_m = BLEND_M
        try:
            VisorMalha(self, folder, origens[0], blend_m, self.melhorar.get())
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def write(self, line):
        self.after(0, lambda line=line: self._escrever(line))

    def _escrever(self, line):
        self.log.insert("end", line + "\n")
        self.log.see("end")

    def _rodar(self, func):
        if self.busy:
            return
        origens = self.selecionados()
        folder = self.folder.get().strip()
        if not origens:
            return
        if not os.path.isdir(folder):
            messagebox.showerror(APP_NAME, "A pasta dos terrenos nao existe.")
            return
        try:
            faixa = ler_faixa(self.faixa.get())
        except RuntimeError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        otimizar = self.otimizar.get()
        melhorar = self.melhorar.get()
        gravar_config(folder, faixa, otimizar, melhorar)
        cancelar.clear()
        self.fechando = False
        self.busy = True
        self._travar(True)
        self.log.delete("1.0", "end")
        total = len(origens)
        self._mostrar_progresso(0, total, "Preparando…")

        titulo = "Compilar" if func is aplicar else "Recuperar"
        caminho_log = iniciar_log(titulo)
        gravar_log("pasta " + folder)
        gravar_log("faixa %.0f  otimizar %s  melhorar %s" % (faixa, otimizar, melhorar))

        def registrar(linha):
            gravar_log(linha)
            self.write(linha)

        def andamento(feito, quantos):
            texto = "Tiles prontos: %d de %d" % (feito, quantos)
            self.after(0, lambda: self._mostrar_progresso(feito, quantos, texto))

        def trabalho():
            nonlocal total
            try:
                registrar("log em " + caminho_log)
                if func is aplicar:
                    opcoes = {"faixa": faixa, "otimizar": otimizar, "melhorar": melhorar}
                    total = compilar_varios(folder, origens, registrar, opcoes, andamento)
                else:
                    total = recuperar_varios(folder, origens, registrar, andamento)
                gravar_log("concluido")
            except Cancelado:
                gravar_log("cancelado")
            except Exception as exc:
                gravar_log("ERRO\n" + traceback.format_exc())
                if not self.fechando:
                    self.after(0, lambda exc=exc: self.write("erro: " + str(exc)))
                    self.after(0, lambda exc=exc: self.write("detalhe em " + caminho_log))
                    self.after(0, lambda exc=exc: self.status.set("Falhou: " + str(exc)))
                    self.after(0, lambda exc=exc: messagebox.showerror(
                        APP_NAME, str(exc) + "\n\nDetalhe em:\n" + caminho_log
                    ))
            else:
                if not self.fechando and not cancelar.is_set():
                    self.after(0, lambda: self._mostrar_progresso(total, total, "Concluído"))
                    self.after(0, lambda: messagebox.showinfo(
                        APP_NAME,
                        "Compilação concluída.\nReinicie o X-Plane para ver.",
                    ))
            finally:
                if not self.fechando:
                    self.after(0, self._liberar)

        threading.Thread(target=trabalho, daemon=True).start()

    def _mostrar_progresso(self, feito, total, texto):
        self.status.set(texto)
        self.title(f"{APP_NAME} — {texto}")
        self.progresso.stop()
        self.progresso.configure(mode="determinate", maximum=max(total, 1), value=feito)

    def _liberar(self):
        self.busy = False
        self._travar(False)
        if self.status.get() == "Concluído":
            self.title(f"{APP_NAME} — concluído")

    def compilar(self):
        self._rodar(aplicar)

    def recuperar_click(self):
        origens = self.selecionados()
        if not origens:
            return
        nomes = ", ".join(os.path.basename(p) for p in origens)
        if not messagebox.askyesno(
            APP_NAME,
            "Voltar o DSF destes OSM para o backup original?\n" + nomes,
        ):
            return
        self._rodar(recuperar)
