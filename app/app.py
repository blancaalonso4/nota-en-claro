"""Punto de arranque único de Nota en Claro. Desde la raíz del proyecto:

    python -m app.app

1. Comprueba que Ollama responde y que el modelo está descargado (si no, dice qué hacer).
2. Construye el índice si falta o si cambió el corpus (si ya está, lo carga de disco).
3. Lanza la interfaz de Streamlit (`app/interfaz.py`).
"""
from __future__ import annotations

import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.rag.config import RAIZ, ConfigRAG  # noqa: E402


def salir(mensaje: str) -> None:
    print(f'\nNo se puede arrancar: {mensaje}', file=sys.stderr)
    sys.exit(1)


def comprobar_ollama(cfg: ConfigRAG) -> None:
    import ollama
    try:
        modelos = {m.model for m in ollama.Client().list().models}
    except Exception as e:  # noqa: BLE001  (ConnectionError, httpx, etc.)
        salir('Ollama no responde. Instálalo desde https://ollama.com/download y ábrelo '
              f'(o ejecuta `ollama serve`); comprueba con `ollama --version`. Detalle: {type(e).__name__}')
    if cfg.modelo not in modelos and f'{cfg.modelo}:latest' not in modelos:
        salir(f'el modelo {cfg.modelo} no está descargado. Ejecuta:  ollama pull {cfg.modelo}')
    print(f'[ok] Ollama responde y {cfg.modelo} está descargado.')


def preparar_indice(cfg: ConfigRAG) -> None:
    from app.rag.indice import Indice
    ind = Indice.cargar_o_construir(cfg)
    print(f'[ok] Índice {ind.origen}: {len(ind.chunks)} fragmentos en {ind.segundos:.2f} s.')


def main() -> None:
    cfg = ConfigRAG()
    comprobar_ollama(cfg)
    print('Comprobando el índice (la primera vez descarga el encoder y tarda un par de minutos)...')
    preparar_indice(cfg)
    puerto = '8501'
    print(f'Lanzando la interfaz en http://localhost:{puerto} (Ctrl+C para parar)...')
    # headless: evita el aviso de correo de Streamlit en la primera ejecución; el navegador lo abrimos nosotros
    threading.Timer(4, lambda: webbrowser.open(f'http://localhost:{puerto}')).start()
    sys.exit(subprocess.call([sys.executable, '-m', 'streamlit', 'run', str(RAIZ / 'app' / 'interfaz.py'),
                              '--server.headless', 'true', '--server.port', puerto,
                              '--browser.gatherUsageStats', 'false'], cwd=RAIZ))


if __name__ == '__main__':
    main()
