"""Prepara propostas de patches para revisão por e-mail."""
from email.message import EmailMessage
from email.policy import SMTP
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from .catalogo_osm import (
    MAX_MANIFESTO, MAX_PATCH, baixar_manifesto_oficial,
    ler_manifesto, manifesto_oficial, validar_osm,
)
from .paths import PROJETO


DESTINATARIO = "alisson@habbora.com.br"
ARQUIVOS_RENOMEADOS = {
    "sbbr.patch.osm": "brasilia.patch.osm",
    "sbgl.patch.osm": "rio de janeiro.patch.osm",
    "sbsp4.patch.osm": "são paulo.patch.osm",
}
CAMPOS_MANIFESTO = ("nome", "aeroporto", "descricao", "autor", "cenario_autor", "cenario_url")


def _nome_patch(caminho):
    arquivo = Path(caminho)
    return arquivo.name if arquivo.name.lower().endswith(".patch.osm") else arquivo.stem + ".patch.osm"


def _localizar_patch(patches, arquivo):
    nome = arquivo.casefold()
    renomeado = ARQUIVOS_RENOMEADOS.get(nome)
    por_nome = {patch.arquivo.casefold(): indice for indice, patch in enumerate(patches)}
    return por_nome.get(nome, por_nome.get(renomeado))


def metadados_da_proposta(caminho):
    patches = manifesto_oficial()
    indice = _localizar_patch(patches, _nome_patch(caminho))
    return patches[indice] if indice is not None else None


def _atualizar_manifesto(original, arquivo, dados, campos):
    patches = ler_manifesto(original)
    bruto = json.loads(original)
    indice = _localizar_patch(patches, arquivo)
    registro = dict(bruto["patches"][indice]) if indice is not None else {"arquivo": arquivo}
    for campo in CAMPOS_MANIFESTO:
        if campo in campos:
            if campos[campo]:
                registro[campo] = campos[campo]
            else:
                registro.pop(campo, None)
    registro["sha256"] = sha256(dados).hexdigest()
    if indice is None:
        bruto["patches"].append(registro)
    else:
        bruto["patches"][indice] = registro
    faltam = [campo for campo in ("nome", "aeroporto", "descricao", "autor") if not registro.get(campo)]
    if faltam:
        raise ValueError("Preencha nome, aeroporto, descrição e autor.")
    conteudo = (json.dumps(bruto, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(conteudo) > MAX_MANIFESTO:
        raise ValueError("O manifesto atualizado excede o tamanho permitido.")
    ler_manifesto(conteudo)
    arquivo = registro["arquivo"]
    if indice is not None and registro == json.loads(original)["patches"][indice]:
        raise ValueError("O catálogo já tem esta versão do patch e dos metadados.")
    return arquivo, registro, indice is not None, conteudo


def preparar_proposta(caminho, campos, justificativa):
    with Path(caminho).open("rb") as handle:
        dados = handle.read(MAX_PATCH + 1)
    if len(dados) > MAX_PATCH:
        raise ValueError("O patch excede o tamanho permitido.")
    validar_osm(dados)
    arquivo, registro, correcao, manifesto = _atualizar_manifesto(
        baixar_manifesto_oficial(), _nome_patch(caminho), dados, campos,
    )
    acao = "Correção" if correcao else "Novo patch"
    titulo = " ".join(f"{acao} OSM — {registro['aeroporto']} — {registro['nome']}".split())
    email = EmailMessage(policy=SMTP)
    email["To"] = DESTINATARIO
    email["Subject"] = titulo
    email["X-Unsent"] = "1"
    email.set_content(
        f"Olá, Alisson.\n\nGostaria de propor uma alteração no catálogo de patches OSM.\n\n"
        f"Aeroporto: {registro['aeroporto']}\nArquivo: {arquivo}\n\n{justificativa}\n"
    )
    email.add_attachment(dados, maintype="application", subtype="xml", filename=arquivo)
    email.add_attachment(manifesto, maintype="application", subtype="json", filename="manifest.json")

    raiz = Path(PROJETO) / "propostas"
    raiz.mkdir(exist_ok=True)
    pasta = Path(tempfile.mkdtemp(prefix="osm-", dir=raiz))
    (pasta / arquivo).write_bytes(dados)
    (pasta / "manifest.json").write_bytes(manifesto)
    rascunho = pasta / "proposta.eml"
    rascunho.write_bytes(email.as_bytes())
    return rascunho


def abrir_no_sistema(caminho):
    if sys.platform == "win32":
        os.startfile(caminho)
    else:
        comando = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.run([comando, str(caminho)], check=True, timeout=10)
