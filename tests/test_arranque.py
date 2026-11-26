"""Arranque `python -m app.app` con Ollama apagado o sin el modelo (sin Ollama real)."""
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from app import app as arranque
from app.rag.config import ConfigRAG

RAIZ = Path(__file__).resolve().parents[1]


def test_ollama_apagado_da_un_mensaje_claro_y_sale_sin_traza(monkeypatch, capsys):
    import ollama

    class Apagado:
        def list(self):
            raise ConnectionError('Failed to connect to Ollama')
    monkeypatch.setattr(ollama, 'Client', lambda *a, **k: Apagado())
    monkeypatch.delenv('OLLAMA_HOST', raising=False)
    with pytest.raises(SystemExit) as e:
        arranque.comprobar_ollama(ConfigRAG())
    assert e.value.code == 1
    err = capsys.readouterr().err
    assert 'No se puede arrancar' in err and 'Ollama no está funcionando' in err and 'http://localhost:11434' in err
    assert 'menú Inicio' in err and 'ollama serve' in err and 'https://ollama.com/download' in err and 'ollama list' in err
    assert 'Traceback' not in err and 'ConnectionError' in err        # el tipo de error va como detalle, no como mensaje


def test_ollama_apagado_dice_el_servidor_configurado(monkeypatch, capsys):
    import ollama
    monkeypatch.setattr(ollama, 'Client', lambda *a, **k: NS(list=lambda: (_ for _ in ()).throw(ConnectionError('x'))))
    monkeypatch.setenv('OLLAMA_HOST', 'http://127.0.0.1:11999')
    with pytest.raises(SystemExit):
        arranque.comprobar_ollama(ConfigRAG())
    assert 'http://127.0.0.1:11999' in capsys.readouterr().err


def test_modelo_sin_descargar_dice_el_comando(monkeypatch, capsys):
    import ollama
    monkeypatch.setattr(ollama, 'Client', lambda *a, **k: NS(list=lambda: NS(models=[NS(model='otro:latest')])))
    with pytest.raises(SystemExit):
        arranque.comprobar_ollama(ConfigRAG())
    assert 'ollama pull qwen3:4b-instruct' in capsys.readouterr().err


def test_arranque_real_con_ollama_apagado_termina_con_codigo_1_y_texto_legible():
    """Lanza `python -m app.app` de verdad apuntando a un puerto sin Ollama: sale al momento, con las tildes bien y sin traza."""
    r = subprocess.run([sys.executable, '-m', 'app.app'], cwd=RAIZ, capture_output=True, timeout=120,
                       env={**__import__('os').environ, 'OLLAMA_HOST': 'http://127.0.0.1:11999'})
    err = r.stderr.decode('utf-8')                     # el programa fuerza UTF-8 en stderr
    assert r.returncode == 1 and 'Ollama no está funcionando' in err and 'Traceback' not in err
