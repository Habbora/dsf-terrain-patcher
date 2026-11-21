"""Compatibilidade: o programa agora é o pacote osmterreno (python -m osmterreno)."""
import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from osmterreno.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
