"""Compatibilidade: o servidor do editor agora é editor/server.py."""
import os
import runpy

runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py"), run_name="__main__")
