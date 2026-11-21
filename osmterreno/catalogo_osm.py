"""Catálogos de patches publicados em repositórios Git."""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
from xml.etree.ElementTree import ParseError

from .cancel import NO_WINDOW
from .osm_patch import load_patch


REPO_OFICIAL = "https://github.com/Habbora/dsf-terrain-patcher.git"
BRANCH_OFICIAL = "patches"
RAW_OFICIAL = "https://raw.githubusercontent.com/Habbora/dsf-terrain-patcher/refs/heads/patches/"
MAX_MANIFESTO = 512 * 1024
MAX_PATCH = 4 * 1024 * 1024
MAX_PACOTE = 64 * 1024 * 1024


@dataclass(frozen=True)
class Patch:
    arquivo: str
    nome: str
    aeroporto: str
    descricao: str
    autor: str
    sha256: str
    cenario_url: str | None
    cenario_autor: str | None = None


def _https(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None:
        raise ValueError("Informe um endereço HTTPS sem credenciais.")
    return url


def _limitar(arquivo, limite):
    dados = arquivo.read(limite + 1)
    if len(dados) > limite:
        raise ValueError("O arquivo excede o tamanho permitido.")
    return dados


def _baixar(arquivo, limite):
    pedido = Request(RAW_OFICIAL + quote(arquivo, safe=""), headers={"Cache-Control": "no-cache"})
    with urlopen(pedido, timeout=15) as resposta:
        _https(resposta.geturl())
        return _limitar(resposta, limite)


def ler_manifesto(dados):
    manifesto = json.loads(dados)
    if not isinstance(manifesto, dict) or type(manifesto.get("versao")) is not int or manifesto["versao"] != 1:
        raise ValueError("O manifest.json precisa declarar a versão 1.")
    registros = manifesto.get("patches")
    if not isinstance(registros, list):
        raise ValueError("O manifest.json precisa conter uma lista de patches.")
    patches = []
    vistos = set()
    for registro in registros:
        campos = ("arquivo", "nome", "aeroporto", "descricao", "autor", "sha256")
        if not isinstance(registro, dict) or any(
            not isinstance(registro.get(campo), str) or not registro[campo].strip() for campo in campos
        ):
            raise ValueError("Cada patch precisa de arquivo, nome, aeroporto, descrição, autor e SHA-256.")
        arquivo = registro["arquivo"]
        if not re.fullmatch(r"[^\W_][\w .-]{0,120}\.patch\.osm", arquivo, re.IGNORECASE) or PureWindowsPath(arquivo).is_reserved():
            raise ValueError("Use apenas o nome do arquivo .patch.osm no manifesto.")
        if arquivo.casefold() in vistos or not re.fullmatch(r"[0-9a-fA-F]{64}", registro["sha256"]):
            raise ValueError(f"Nome duplicado ou SHA-256 inválido para {arquivo}.")
        cenario = registro.get("cenario_url")
        cenario_autor = registro.get("cenario_autor")
        if cenario_autor is not None and (not isinstance(cenario_autor, str) or not cenario_autor.strip()):
            raise ValueError(f"Autor do cenário inválido para {arquivo}.")
        if cenario is not None:
            if not isinstance(cenario, str):
                raise ValueError(f"Link de cenário inválido para {arquivo}.")
            _https(cenario)
        vistos.add(arquivo.casefold())
        patches.append(Patch(
            **{campo: registro[campo] for campo in campos},
            cenario_url=cenario, cenario_autor=cenario_autor,
        ))
    return patches


def catalogo_oficial():
    if shutil.which("git"):
        return catalogo_git(REPO_OFICIAL, BRANCH_OFICIAL)
    return manifesto_oficial(), baixar_patch


def manifesto_oficial():
    return ler_manifesto(baixar_manifesto_oficial())


def baixar_manifesto_oficial():
    return _baixar("manifest.json", MAX_MANIFESTO)


def baixar_patch(patch):
    return _baixar(patch.arquivo, MAX_PATCH)


def catalogo_git(url, branch=None):
    _https(url)
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Instale o Git para importar um catálogo via Git.")
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    with tempfile.TemporaryDirectory(prefix="dsf-catalogo-") as pasta:
        destino = Path(pasta) / "catalogo"
        comando = [git, "-c", "protocol.allow=never", "-c", "protocol.https.allow=always",
                   "clone", "--depth=1", "--no-recurse-submodules"]
        if branch:
            comando.extend(("--branch", branch))
        try:
            resultado = subprocess.run(
                [*comando, "--", url, str(destino)], env=env, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=90, creationflags=NO_WINDOW,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("O Git demorou demais para baixar o catálogo.") from exc
        if resultado.returncode:
            raise RuntimeError(resultado.stderr.strip() or "O Git não conseguiu baixar o catálogo.")
        with _arquivo_do_git(destino, "manifest.json").open("rb") as manifesto:
            patches = ler_manifesto(_limitar(manifesto, MAX_MANIFESTO))
        arquivos = {}
        tamanho = 0
        for patch in patches:
            with _arquivo_do_git(destino, patch.arquivo).open("rb") as arquivo:
                dados = _limitar(arquivo, MAX_PATCH)
            tamanho += len(dados)
            if tamanho > MAX_PACOTE:
                raise ValueError("O pacote Git excede o tamanho permitido.")
            arquivos[patch.arquivo] = dados
    return patches, lambda patch: arquivos[patch.arquivo]


def _arquivo_do_git(destino, nome):
    arquivo = destino / nome
    if arquivo.is_symlink() or not arquivo.is_file():
        raise ValueError(f"O repositório precisa conter {nome} na raiz como arquivo comum.")
    return arquivo


def validar_osm(dados):
    try:
        flats, ramps, _ = load_patch(BytesIO(dados))
        if not flats and not ramps:
            raise ValueError("Sem altitudes de patch")
    except (KeyError, TypeError, ValueError, ParseError) as exc:
        raise ValueError("O arquivo não é um patch de terreno OSM válido.") from exc


def instalar_patch(patch, dados, pasta, atualizar=False):
    if sha256(dados).hexdigest() != patch.sha256.lower():
        raise ValueError("O conteúdo do patch diverge do manifesto. Reabra o catálogo e tente novamente.")
    validar_osm(dados)

    destino = Path(pasta) / patch.arquivo
    destino.parent.mkdir(parents=True, exist_ok=True)
    if atualizar:
        with tempfile.NamedTemporaryFile(dir=pasta, prefix=f"{patch.arquivo}-", suffix=".bak", delete=False) as backup:
            with destino.open("rb") as local:
                shutil.copyfileobj(local, backup)
        temporario = None
        try:
            with tempfile.NamedTemporaryFile(dir=pasta, delete=False) as novo:
                temporario = Path(novo.name)
                novo.write(dados)
            os.replace(temporario, destino)
        finally:
            if temporario is not None:
                temporario.unlink(missing_ok=True)
    else:
        with destino.open("xb") as arquivo:
            try:
                arquivo.write(dados)
                arquivo.flush()
            except OSError:
                arquivo.close()
                destino.unlink(missing_ok=True)
                raise
    return destino
