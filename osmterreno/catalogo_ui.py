"""Janela de seleção e instalação de patches."""
from functools import partial
from hashlib import file_digest
from pathlib import Path
from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import webbrowser

from .catalogo_osm import catalogo_git, catalogo_oficial, instalar_patch
from .paths import OSM_DIR


class CatalogoOSM(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Catálogo de patches OSM")
        self.geometry("650x440")
        self.minsize(490, 360)
        self.transient(app)
        self.grab_set()
        self.patches = []
        self.baixar = None
        self._resultados = Queue()
        self.status = tk.StringVar()
        self.detalhes = tk.StringVar()

        barra = ttk.Frame(self, padding=(10, 10, 10, 0))
        barra.pack(fill="x")
        self.oficial = ttk.Button(barra, text="Catálogo oficial", command=lambda: self.carregar(catalogo_oficial))
        self.oficial.pack(side="left")
        self.git = ttk.Button(barra, text="Importar via Git…", command=self.escolher_git)
        self.git.pack(side="left", padx=6)

        tabela = ttk.Frame(self, padding=10)
        tabela.pack(fill="both", expand=True)
        self.lista = ttk.Treeview(tabela, columns=("aeroporto", "nome"), show="headings", selectmode="browse")
        self.lista.heading("aeroporto", text="Aeroporto")
        self.lista.heading("nome", text="Patch")
        self.lista.column("aeroporto", width=100, stretch=False)
        self.lista.column("nome", width=360)
        rolagem = ttk.Scrollbar(tabela, orient="vertical", command=self.lista.yview)
        self.lista.configure(yscrollcommand=rolagem.set)
        self.lista.pack(side="left", fill="both", expand=True)
        rolagem.pack(side="right", fill="y")
        self.lista.bind("<<TreeviewSelect>>", self.selecionar)

        ttk.Label(self, textvariable=self.detalhes, wraplength=455).pack(anchor="w", padx=10)
        rodape = ttk.Frame(self, padding=10)
        rodape.pack(fill="x")
        self.instalar = ttk.Button(rodape, text="Baixar patch", command=self.importar)
        self.instalar.pack(side="left")
        self.link = ttk.Button(rodape, text="Abrir cenário", command=self.abrir_cenario)
        self.link.pack(side="left", padx=6)
        ttk.Label(self, textvariable=self.status, wraplength=300).pack(side="left")
        self.carregar(catalogo_oficial)

    def trabalhar(self, acao, sucesso, status):
        for botao in (self.oficial, self.git, self.instalar, self.link):
            botao.state(["disabled"])
        self.status.set(status)

        def rodar():
            try:
                self._resultados.put((True, acao()))
            except Exception as exc:
                self._resultados.put((False, exc))

        def conferir():
            try:
                ok, resultado = self._resultados.get_nowait()
            except Empty:
                self.after(100, conferir)
                return
            self.oficial.state(["!disabled"])
            self.git.state(["!disabled"])
            self.status.set("")
            if ok:
                sucesso(resultado)
            else:
                messagebox.showerror(self.title(), str(resultado), parent=self)
            self.selecionar()

        threading.Thread(target=rodar, daemon=True).start()
        self.after(100, conferir)

    def carregar(self, origem):
        self.lista.delete(*self.lista.get_children())
        self.patches = []
        self.detalhes.set("")

        def mostrar(resultado):
            self.patches, self.baixar = resultado
            for indice, patch in enumerate(self.patches):
                self.lista.insert("", "end", iid=str(indice), values=(patch.aeroporto, patch.nome))
            if self.patches:
                self.lista.selection_set("0")
            self.status.set(f"{len(self.patches)} patch(es)")

        self.trabalhar(origem, mostrar, "Consultando o repositório Git…")

    def escolher_git(self):
        url = simpledialog.askstring(self.title(), "URL HTTPS do repositório Git:", parent=self)
        if not url:
            return
        branch = simpledialog.askstring(self.title(), "Branch ou tag (em branco para usar a padrão):", parent=self)
        if branch is not None:
            self.carregar(partial(catalogo_git, url.strip(), branch.strip()))

    def patch_selecionado(self):
        selecao = self.lista.selection()
        return self.patches[int(selecao[0])] if selecao else None

    def selecionar(self, _event=None):
        patch = self.patch_selecionado()
        ocupado = self.oficial.instate(["disabled"])
        self.instalar.state(["!disabled"] if patch and not ocupado else ["disabled"])
        self.link.state(["!disabled"] if patch and patch.cenario_url and not ocupado else ["disabled"])
        self.detalhes.set(f"Autor: {patch.autor}\n{patch.descricao}" if patch else "")

    def abrir_cenario(self):
        patch = self.patch_selecionado()
        if patch and patch.cenario_url:
            webbrowser.open(patch.cenario_url)

    def importar(self):
        patch = self.patch_selecionado()
        if not patch:
            return
        destino = Path(OSM_DIR) / patch.arquivo
        atualizar = destino.exists()
        if atualizar:
            with destino.open("rb") as local:
                if file_digest(local, "sha256").hexdigest() == patch.sha256.lower():
                    self.status.set("O patch já está atualizado.")
                    return
            if not messagebox.askyesno(
                self.title(), f"Atualizar {patch.arquivo}? Uma cópia da versão local será guardada.",
                parent=self,
            ):
                return

        def baixado(path):
            self.app.recarregar(path.name)
            self.app.write("importado do catálogo: " + path.name)
            self.status.set("Patch na lista de OSM.")

        self.trabalhar(
            lambda: instalar_patch(patch, self.baixar(patch), OSM_DIR, atualizar),
            baixado, "Baixando patch…",
        )
