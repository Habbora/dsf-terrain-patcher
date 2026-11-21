"""Ponto de entrada: python -m osmterreno [--compilar-todos | --compilar-um JOB | --cortar]."""
import multiprocessing
import sys


def main():
    multiprocessing.freeze_support()
    if "--compilar-todos" in sys.argv:
        from osmterreno.compile_job import compilar_todos

        return compilar_todos()
    if "--compilar-um" in sys.argv:
        from osmterreno.compile_job import compilar_um_arquivo

        return compilar_um_arquivo(sys.argv[sys.argv.index("--compilar-um") + 1])
    if "--cortar" in sys.argv:
        from osmterreno.mesh_cut import servir_cortes

        servir_cortes()
        return 0
    from osmterreno.app import App

    App().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
