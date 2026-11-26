"""Latencia y caché de prefijo de Ollama con N preguntas seguidas en caliente.

Uso:  python eval/medir_cache.py --etiqueta antes [--pregunta-al-principio si|no] [--n 5]

Por pregunta registra (todo MEDIDO): tokens totales del prompt (`prompt_eval_count`, que en esta versión de Ollama
incluye los reutilizados), tokens reutilizados de caché (línea «cached n_tokens» de server.log del propio Ollama),
tokens realmente evaluados (total - reutilizados), segundos de evaluación del prompt (`prompt_eval_duration`),
segundos de generación y segundos totales (recuperar + generar). Protocolo: `ollama stop`, calentamiento y preguntas seguidas.
Resultado en eval/salidas/cache_<etiqueta>.json
"""
import argparse
import dataclasses
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.stdout.reconfigure(encoding='utf-8')

from app.rag.config import ConfigRAG  # noqa: E402
from app.rag.pipeline import SistemaRAG  # noqa: E402
from app.rag.prompt import mensajes_para  # noqa: E402

LOG = Path(os.environ['LOCALAPPDATA']) / 'Ollama' / 'server.log'
SALIDAS = Path(__file__).parent / 'salidas'


def tokens_cacheados(desde: int) -> list[tuple[int, int]]:
    """(tokens del prompt, tokens reutilizados) de cada petición registrada en server.log desde el byte `desde`."""
    with open(LOG, 'rb') as fh:
        fh.seek(desde)
        txt = fh.read().decode('utf-8', 'replace')
    out, total = [], None
    for linea in txt.splitlines():
        m = re.search(r'new prompt,.*task\.n_tokens = (\d+)', linea)
        if m:
            total = int(m.group(1))
        m = re.search(r'cached n_tokens = (\d+)', linea)
        if m and total is not None:
            out.append((total, int(m.group(1))))
            total = None
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--etiqueta', required=True)
    ap.add_argument('--pregunta-al-principio', choices=['si', 'no'], default='si')
    ap.add_argument('--n', type=int, default=5)
    a = ap.parse_args()
    cfg = ConfigRAG()
    s = SistemaRAG(cfg)
    preguntas = json.loads(cfg.preguntas.read_text(encoding='utf-8'))['preguntas'][:a.n]
    s.recuperar('calentamiento del reordenador')   # carga del reordenador fuera de la medida
    subprocess.run(['ollama', 'stop', cfg.modelo], capture_output=True)
    time.sleep(3)
    s.calentar()
    filas = []
    for q in preguntas:
        t0 = time.perf_counter()
        rec = s.recuperar(q['pregunta'])
        t_rec = time.perf_counter() - t0
        msgs = mensajes_para(q['pregunta'], rec, s.manifiesto, pregunta_al_principio=a.pregunta_al_principio == 'si')
        marca = LOG.stat().st_size
        t1 = time.perf_counter()
        r = s.generador.cliente.chat(model=cfg.modelo, messages=msgs, think=cfg.think, keep_alive=cfg.keep_alive,
                                     options={'seed': cfg.semilla, 'temperature': cfg.temperature,
                                              'num_predict': cfg.num_predict, 'num_ctx': cfg.num_ctx,
                                              'num_thread': cfg.num_thread})
        t_gen = time.perf_counter() - t1
        time.sleep(0.5)
        reg = tokens_cacheados(marca)
        total, cache = reg[-1] if reg else (None, None)
        f = {'id': q['id'], 'tokens_prompt': int(r.prompt_eval_count), 'tokens_reutilizados': cache,
             'tokens_evaluados': None if cache is None else int(r.prompt_eval_count) - cache,
             'seg_eval_prompt': round(r.prompt_eval_duration / 1e9, 2), 'tokens_salida': int(r.eval_count),
             'seg_generacion': round(t_gen, 2), 'seg_recuperar': round(t_rec, 2),
             'seg_total': round(t_rec + t_gen, 2), 'sha_salida': __import__('hashlib').sha256(
                 (r.message.content or '').encode()).hexdigest()[:10]}
        filas.append(f)
        print(json.dumps(f, ensure_ascii=False), flush=True)
    res = {'etiqueta': a.etiqueta, 'pregunta_al_principio': a.pregunta_al_principio, 'modelo': cfg.modelo,
           'filas': filas, 'suma_seg_total': round(sum(f['seg_total'] for f in filas), 1),
           'suma_seg_generacion': round(sum(f['seg_generacion'] for f in filas), 1),
           'suma_tokens_prompt': sum(f['tokens_prompt'] for f in filas),
           'suma_tokens_reutilizados': sum(f['tokens_reutilizados'] or 0 for f in filas),
           'suma_tokens_evaluados': sum(f['tokens_evaluados'] or 0 for f in filas)}
    (SALIDAS / f'cache_{a.etiqueta}.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
    print({k: v for k, v in res.items() if k.startswith('suma')})


if __name__ == '__main__':
    main()
