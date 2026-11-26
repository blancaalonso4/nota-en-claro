"""Evalúa el coordinador con las 30 peticiones etiquetadas de data/eval/intenciones.json (5 por intención).

    python eval/evaluar_coordinador.py

Todo MEDIDO: aciertos (intención devuelta == etiqueta), tokens de entrada y salida por llamada (los reporta Ollama) y
segundos por llamada (reloj). Salida: eval/salidas/coordinador.jsonl y eval/salidas/coordinador.md.
"""
from __future__ import annotations

import json
import platform
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.agentes.coordinador import INTENCIONES, Coordinador  # noqa: E402
from app.agentes.traza import Traza  # noqa: E402
from app.rag.config import ConfigRAG, fijar_semillas  # noqa: E402
from app.rag.generador import GeneradorOllama  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]


def main() -> None:
    cfg = ConfigRAG()
    fijar_semillas(cfg.semilla)
    peticiones = json.loads((RAIZ / 'data' / 'eval' / 'intenciones.json').read_text(encoding='utf-8'))
    print(f'Calentando {cfg.modelo}...', flush=True)
    GeneradorOllama(cfg).calentar()
    traza = Traza(sesion='eval_coordinador')
    coord = Coordinador(traza, cfg)
    filas = []
    for i, p in enumerate(peticiones, 1):
        d = coord.clasificar(p['peticion'])
        paso = traza.pasos[-1]
        filas.append({'peticion': p['peticion'], 'esperada': p['intencion'], 'obtenida': d.intencion, 'dias': d.dias,
                      'acierto': d.intencion == p['intencion'], 'tokens_entrada': paso['tokens_entrada'],
                      'tokens_salida': paso['tokens_salida'], 'segundos': paso['segundos']})
        print(f"[{i:02d}/{len(peticiones)}] {'OK ' if filas[-1]['acierto'] else 'MAL'} {p['intencion']:>18} -> {d.intencion}  ({paso['segundos']} s)", flush=True)
    out = RAIZ / 'eval' / 'salidas'
    out.mkdir(exist_ok=True)
    (out / 'coordinador.jsonl').write_text('\n'.join(json.dumps(f, ensure_ascii=False) for f in filas) + '\n', encoding='utf-8')
    aciertos = sum(f['acierto'] for f in filas)
    por = {k: sum(f['acierto'] for f in filas if f['esperada'] == k) for k in INTENCIONES}
    seg = [f['segundos'] for f in filas]
    L = [f'# Evaluación del coordinador ({datetime.now():%Y-%m-%d})', '',
         f'Modelo `{cfg.modelo}`, seed {cfg.semilla}, temperature {cfg.temperature}, num_predict 40, think False, salida restringida por esquema JSON. '
         f'{platform.platform()}, CPU sin GPU. {len(filas)} peticiones (5 por intención, `data/eval/intenciones.json`).',
         'Cifras **medidas**: aciertos (intención == etiqueta), tokens (Ollama, por llamada), segundos (reloj, por llamada).', '',
         f'**Aciertos: {aciertos}/{len(filas)}.** Tokens de entrada: media {statistics.mean(f["tokens_entrada"] for f in filas):.1f} '
         f'(mín {min(f["tokens_entrada"] for f in filas)}, máx {max(f["tokens_entrada"] for f in filas)}); '
         f'tokens de salida: media {statistics.mean(f["tokens_salida"] for f in filas):.1f}; '
         f'segundos por llamada: media {statistics.mean(seg):.2f}, mediana {statistics.median(seg):.2f}, máx {max(seg):.2f}.', '',
         '| intención | aciertos |', '|---|---|'] + [f'| {k} | {v}/5 |' for k, v in por.items()]
    fallos = [f for f in filas if not f['acierto']]
    if fallos:
        L += ['', '## Fallos', '', '| petición | esperada | obtenida |', '|---|---|---|'] + \
             [f"| {f['peticion']} | {f['esperada']} | {f['obtenida']} |" for f in fallos]
        L += ['', 'Confusiones: ' + ', '.join(f'{a}→{b} ×{n}' for (a, b), n in Counter((f['esperada'], f['obtenida']) for f in fallos).items())]
    (out / 'coordinador.md').write_text('\n'.join(L) + '\n', encoding='utf-8')
    print('\n' + '\n'.join(L[4:7]))


if __name__ == '__main__':
    main()
