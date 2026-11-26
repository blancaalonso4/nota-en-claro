"""Cliente de Ollama. Cada llamada lleva seed, temperature, num_predict y think explícitos."""
from __future__ import annotations

import time

import ollama

from .config import ConfigRAG


class GeneradorOllama:
    def __init__(self, cfg: ConfigRAG, host: str | None = None):
        self.cfg = cfg
        self.cliente = ollama.Client(host=host) if host else ollama.Client()

    def generar(self, mensajes: list[dict]) -> dict:
        """Devuelve texto y cifras medidas: tokens de entrada/salida (los reporta Ollama) y segundos (reloj)."""
        c = self.cfg
        t0 = time.perf_counter()
        r = self.cliente.chat(
            model=c.modelo,
            messages=mensajes,
            think=c.think,
            options={'seed': c.semilla, 'temperature': c.temperature,
                     'num_predict': c.num_predict, 'num_ctx': c.num_ctx},
        )
        return {'texto': (r.message.content or '').strip(),
                'tokens_entrada': int(r.prompt_eval_count or 0),
                'tokens_salida': int(r.eval_count or 0),
                'segundos': round(time.perf_counter() - t0, 2)}
