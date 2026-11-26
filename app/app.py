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
for flujo in (sys.stdout, sys.stderr):      # también stderr: los mensajes de error salían con las tildes rotas en algunas consolas
    if hasattr(flujo, 'reconfigure'):
        flujo.reconfigure(encoding='utf-8')

from app.rag.config import RAIZ, ConfigRAG  # noqa: E402


def salir(mensaje: str) -> None:
    print(f'\nNo se puede arrancar: {mensaje}', file=sys.stderr)
    sys.exit(1)


def mensaje_ollama_apagado(servidor: str, tipo_error: str) -> str:
    """Texto para cuando Ollama no responde: qué pasa, qué hacer (en orden) y cómo comprobarlo."""
    return (f'Ollama no está funcionando (no responde en {servidor}).\n'
            '  1. Ábrelo: busca «Ollama» en el menú Inicio (después aparece un icono junto al reloj) '
            'o ejecuta `ollama serve` en otra terminal.\n'
            '  2. Si no lo tienes instalado: https://ollama.com/download\n'
            '  3. Comprueba que responde con `ollama list` y vuelve a ejecutar `python -m app.app`.\n'
            f'  (Detalle técnico: {tipo_error})')


def comprobar_ollama(cfg: ConfigRAG) -> None:
    import os

    import ollama
    try:
        modelos = {m.model for m in ollama.Client().list().models}
    except Exception as e:  # noqa: BLE001  (ConnectionError, httpx, etc.)
        servidor = os.environ.get('OLLAMA_HOST', '').strip() or 'http://localhost:11434'
        salir(mensaje_ollama_apagado(servidor, type(e).__name__))
    if cfg.modelo not in modelos and f'{cfg.modelo}:latest' not in modelos:
        salir(f'el modelo {cfg.modelo} no está descargado. Ejecuta:  ollama pull {cfg.modelo}')
    print(f'[ok] Ollama responde y {cfg.modelo} está descargado.')


def preparar_indice(cfg: ConfigRAG) -> None:
    from app.rag.indice import Indice
    ind = Indice.cargar_o_construir(cfg)
    print(f'[ok] Índice {ind.origen}: {len(ind.chunks)} fragmentos en {ind.segundos:.2f} s.')


def comprobar_google() -> None:
    """Aviso (no bloquea): la normativa y la calculadora con notas a mano funcionan sin Google."""
    from app.servicios import estado_google
    g = estado_google()
    if g['lista']:
        print('[ok] Google: credenciales, tokens y ORIENTADOR_EMAIL listos.')
        return
    print('[aviso] La parte de Google no está lista (la normativa y la calculadora con notas a mano funcionan igual):')
    if not g['credenciales']:
        print('   - falta credentials.json en la raíz del proyecto.')
    faltan = [p for p, ok in g['tokens'].items() if not ok]
    if faltan:
        print(f'   - falta autorizar {", ".join(faltan)}: python -m app.mcp_servers.autorizar')
    if g['orientador'] is None:
        print('   - falta ORIENTADOR_EMAIL en .env (copia .env.example).')


def main() -> None:
    cfg = ConfigRAG()
    comprobar_ollama(cfg)
    print('Comprobando el índice (la primera vez descarga el encoder y tarda un par de minutos)...')
    preparar_indice(cfg)
    comprobar_google()
    puerto = '8501'
    print(f'Lanzando la interfaz en http://localhost:{puerto} (Ctrl+C para parar)...')
    # headless: evita el aviso de correo de Streamlit en la primera ejecución; el navegador lo abrimos nosotros
    threading.Timer(4, lambda: webbrowser.open(f'http://localhost:{puerto}')).start()
    sys.exit(subprocess.call([sys.executable, '-m', 'streamlit', 'run', str(RAIZ / 'app' / 'interfaz.py'),
                              '--server.headless', 'true', '--server.port', puerto,
                              '--browser.gatherUsageStats', 'false'], cwd=RAIZ))


if __name__ == '__main__':
    main()
