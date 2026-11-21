"""Cancelamento cooperativo e controle dos processos filhos."""
import os
import subprocess
import threading

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
cancelar = threading.Event()
_proc_trava = threading.Lock()
_proc_atual = None
_proc_compile = None
_checagens = 0


class Cancelado(Exception):
    pass


def verificar_cancelamento():
    """Chamada dentro dos laços. Só consulta o aviso a cada 500 vezes, porque entre processos ele custa caro."""
    global _checagens
    _checagens += 1
    if _checagens % 500 == 0 and cancelar.is_set():
        raise Cancelado()


def matar_arvore(pid):
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=NO_WINDOW,
        )
    else:
        os.kill(pid, 15)


def definir_proc_compile(proc):
    """Guarda (ou limpa, com None) o processo do tile em compilação, para o cancelamento poder matá-lo."""
    global _proc_compile
    with _proc_trava:
        _proc_compile = proc


def pedir_cancelamento():
    cancelar.set()
    with _proc_trava:
        proc = _proc_atual
        compile_proc = _proc_compile
    if proc is not None and proc.poll() is None:
        proc.kill()
    if compile_proc is not None and compile_proc.poll() is None:
        matar_arvore(compile_proc.pid)


def run_quiet(args, cwd=None):
    if cancelar.is_set():
        raise Cancelado()
    kwargs = {"cwd": cwd, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = info
        kwargs["creationflags"] = NO_WINDOW | subprocess.DETACHED_PROCESS
    proc = subprocess.Popen(args, **kwargs)
    global _proc_atual
    with _proc_trava:
        _proc_atual = proc
    try:
        while True:
            try:
                code = proc.wait(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                if cancelar.is_set():
                    proc.kill()
                    proc.wait()
                    raise Cancelado()
    finally:
        with _proc_trava:
            if _proc_atual is proc:
                _proc_atual = None
    if cancelar.is_set():
        raise Cancelado()
    if code != 0:
        raise subprocess.CalledProcessError(code, args)
