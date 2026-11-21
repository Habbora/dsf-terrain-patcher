"""Formulário para preparar uma proposta de patch."""
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from .proposta_osm import CAMPOS_MANIFESTO, DESTINATARIO


class FormularioProposta(simpledialog.Dialog):
    def __init__(self, pai, origem, patch):
        self.arquivo = patch.arquivo if patch else Path(origem).name
        self.correcao = patch is not None
        self.iniciais = {campo: getattr(patch, campo, "") or "" for campo in CAMPOS_MANIFESTO}
        super().__init__(pai, "Propor correção OSM" if patch else "Propor novo patch OSM")

    def body(self, master):
        ttk.Label(master, text=self.arquivo).grid(row=0, columnspan=2, sticky="w")
        mensagem = (
            "Metadados carregados do catálogo. Para corrigir só o OSM, preencha o resumo."
            if self.correcao else
            "Preencha nome, aeroporto, descrição, autor e resumo da proposta."
        )
        ttk.Label(master, text=mensagem, wraplength=360).grid(row=1, columnspan=2, sticky="w", pady=(2, 8))
        self.campos = {}
        for linha, (chave, rotulo) in enumerate((
            ("nome", "Nome do patch"),
            ("aeroporto", "Aeroporto"),
            ("descricao", "Descrição do patch"),
            ("autor", "Autor do patch"),
            ("cenario_autor", "Autor do cenário"),
            ("cenario_url", "Link do cenário"),
            ("justificativa", "Resumo da proposta"),
        ), start=2):
            ttk.Label(master, text=rotulo).grid(row=linha, column=0, sticky="w", padx=(0, 8))
            entrada = ttk.Entry(master, width=42)
            entrada.insert(0, self.iniciais.get(chave, ""))
            entrada.grid(row=linha, column=1, sticky="ew", pady=2)
            self.campos[chave] = entrada
        ttk.Label(master, text=f"Para: {DESTINATARIO}").grid(row=9, columnspan=2, sticky="w", pady=(6, 0))
        return self.campos["justificativa" if self.correcao else "nome"]

    def buttonbox(self):
        botoes = ttk.Frame(self, padding=8)
        ttk.Button(botoes, text="Preparar e-mail", command=self.ok).pack(side="left", padx=4)
        ttk.Button(botoes, text="Cancelar", command=self.cancel).pack(side="left", padx=4)
        botoes.pack()
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

    def validate(self):
        dados = {chave: entrada.get().strip() for chave, entrada in self.campos.items()}
        justificativa = dados.pop("justificativa")
        if not justificativa:
            messagebox.showwarning(self.title(), "Resuma o que o patch adiciona ou corrige.", parent=self)
            return False
        if any(not dados[chave] for chave in ("nome", "aeroporto", "descricao", "autor")):
            messagebox.showwarning(self.title(), "Preencha nome, aeroporto, descrição e autor.", parent=self)
            return False
        alterados = {chave: valor for chave, valor in dados.items() if valor != self.iniciais[chave]}
        self.result = alterados, justificativa
        return True
