"""Cliente de Ollama. Cada llamada lleva seed, temperature, num_predict y think explícitos."""
from __future__ import annotations

import time

import ollama

from .config import ConfigRAG


class GeneradorOllama:
    def __init__(self, cfg: ConfigRAG, host: str | None = None):
        self.cfg = cfg
        self.cliente = ollama.Client(host=host) if host else ollama.Client()

    def _opciones(self) -> dict:
        c = self.cfg
        opciones = {'seed': c.semilla, 'temperature': c.temperature,
                    'num_predict': c.num_predict, 'num_ctx': c.num_ctx}
        if c.num_thread is not None:
            opciones['num_thread'] = c.num_thread
        return opciones

    def generar_stream(self, mensajes: list[dict]):
        """Como `generar`, pero cede el texto a medida que Ollama lo produce: {'trozo': str} por cada fragmento y, al
        final, {'final': {...}} con el mismo diccionario que devuelve `generar`. Mismas opciones (seed, temperature,
        num_predict, think), así que la salida es la misma que sin streaming."""
        c = self.cfg
        t0 = time.perf_counter()
        partes, ultimo = [], None
        for p in self.cliente.chat(model=c.modelo, messages=mensajes, think=c.think, options=self._opciones(),
                                   keep_alive=c.keep_alive, stream=True):
            trozo = p.message.content or ''
            if trozo:
                partes.append(trozo)
                yield {'trozo': trozo}
            ultimo = p
        yield {'final': {'texto': ''.join(partes).strip(),
                         'tokens_entrada': int(getattr(ultimo, 'prompt_eval_count', 0) or 0),
                         'tokens_salida': int(getattr(ultimo, 'eval_count', 0) or 0),
                         'segundos': round(time.perf_counter() - t0, 2)}}

    def generar(self, mensajes: list[dict]) -> dict:
        """Devuelve texto y cifras medidas: tokens de entrada/salida (los reporta Ollama) y segundos (reloj)."""
        c = self.cfg
        t0 = time.perf_counter()
        opciones = self._opciones()
        r = self.cliente.chat(model=c.modelo, messages=mensajes, think=c.think, options=opciones,
                              keep_alive=c.keep_alive)
        return {'texto': (r.message.content or '').strip(),
                'tokens_entrada': int(r.prompt_eval_count or 0),
                'tokens_salida': int(r.eval_count or 0),
                'segundos': round(time.perf_counter() - t0, 2)}

    def calentar(self) -> list[float]:
        """Llamadas cortas tras cargar el modelo. Medido: sin ellas, la primera pregunta tras la carga da una salida
        distinta de las siguientes (P01: 147 vs 155 tokens). Devuelve los segundos de cada llamada."""
        return [self.generar([{'role': 'user', 'content': 'Responde solo: ok'}])['segundos']
                for _ in range(self.cfg.llamadas_calentamiento)]
