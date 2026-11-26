"""Evalúa el coordinador con las 30 peticiones etiquetadas de data/eval/intenciones.json (5 por intención) y, aparte, con
el conjunto de control de 10 peticiones nuevas de data/eval/intenciones_control.json (escritas como las escribiría un estudiante).

    python eval/evaluar_coordinador.py [--etiqueta antes|despues]

Todo MEDIDO: aciertos (intención devuelta == etiqueta), tokens de entrada y salida por llamada (los reporta Ollama) y
segundos por llamada (reloj). Salida: eval/salidas/coordinador[_<etiqueta>].jsonl y .md.
"""
from __future__ import annotations

import argparse
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
    ap = argparse.ArgumentParser()
    ap.add_argument('--etiqueta', default='', help='sufijo de los archivos de salida (p. ej. antes, despues)')
    etiqueta = ap.parse_args().etiqueta
    sufijo = '_' + etiqueta if etiqueta else ''
    cfg = ConfigRAG()
    fijar_semillas(cfg.semilla)
    peticiones = [{**p, 'conjunto': 'principal'} for p in json.loads((RAIZ / 'data' / 'eval' / 'intenciones.json').read_text(encoding='utf-8'))]
    peticiones += [{**p, 'conjunto': 'control'} for p in json.loads((RAIZ / 'data' / 'eval' / 'intenciones_control.json').read_text(encoding='utf-8'))]
    print(f'Calentando {cfg.modelo}...', flush=True)
    GeneradorOllama(cfg).calentar()
    traza = Traza(sesion='eval_coordinador')
    coord = Coordinador(traza, cfg)
    filas = []
    for i, p in enumerate(peticiones, 1):
        d = coord.clasificar(p['peticion'])
        paso = traza.pasos[-1]
        filas.append({'conjunto': p['conjunto'], 'peticion': p['peticion'], 'esperada': p['intencion'], 'obtenida': d.intencion, 'dias': d.dias,
                      'acierto': d.intencion == p['intencion'], 'tokens_entrada': paso['tokens_entrada'],
                      'tokens_salida': paso['tokens_salida'], 'segundos': paso['segundos']})
        print(f"[{i:02d}/{len(peticiones)}] {'OK ' if filas[-1]['acierto'] else 'MAL'} {p['intencion']:>18} -> {d.intencion}  ({paso['segundos']} s)", flush=True)
    out = RAIZ / 'eval' / 'salidas'
    out.mkdir(exist_ok=True)
    (out / f'coordinador{sufijo}.jsonl').write_text('\n'.join(json.dumps(f, ensure_ascii=False) for f in filas) + '\n', encoding='utf-8')
    principal = [f for f in filas if f['conjunto'] == 'principal']
    control = [f for f in filas if f['conjunto'] == 'control']
    seg = [f['segundos'] for f in filas]
    L = [f'# Evaluación del coordinador ({datetime.now():%Y-%m-%d}){f" · {etiqueta}" if etiqueta else ""}', '',
         f'Modelo `{cfg.modelo}`, seed {cfg.semilla}, temperature {cfg.temperature}, num_predict 40, think False, salida restringida por esquema JSON. '
         f'{platform.platform()}, CPU sin GPU.',
         'Cifras **medidas**: aciertos (intención == etiqueta), tokens (Ollama, por llamada), segundos (reloj, por llamada).', '',
         f'- **Conjunto principal** (`data/eval/intenciones.json`, 5 por intención): **{sum(f["acierto"] for f in principal)}/{len(principal)}**.',
         f'- **Conjunto de control** (`data/eval/intenciones_control.json`, 10 peticiones nuevas escritas como un estudiante): '
         f'**{sum(f["acierto"] for f in control)}/{len(control)}**.',
         f'- Tokens de entrada: media {statistics.mean(f["tokens_entrada"] for f in filas):.1f} '
         f'(mín {min(f["tokens_entrada"] for f in filas)}, máx {max(f["tokens_entrada"] for f in filas)}); '
         f'tokens de salida: media {statistics.mean(f["tokens_salida"] for f in filas):.1f}; '
         f'segundos por llamada: media {statistics.mean(seg):.2f}, mediana {statistics.median(seg):.2f}, máx {max(seg):.2f}.', '',
         '| intención (principal) | aciertos |', '|---|---|'] +         [f'| {k} | {sum(f["acierto"] for f in principal if f["esperada"] == k)}/5 |' for k in INTENCIONES]
    L += ['', '## Conjunto de control, petición a petición', '', '| petición | esperada | obtenida |', '|---|---|---|'] +          [f"| {f['peticion']} | {f['esperada']} | {f['obtenida']}{'' if f['acierto'] else ' ✗'} |" for f in control]
    fallos = [f for f in filas if not f['acierto']]
    if fallos:
        L += ['', 'Confusiones: ' + ', '.join(f'{a}→{b} ×{n}' for (a, b), n in Counter((f['esperada'], f['obtenida']) for f in fallos).items())]
    (out / f'coordinador{sufijo}.md').write_text('\n'.join(L) + '\n', encoding='utf-8')
    print('\n' + '\n'.join(L[5:9]))


if __name__ == '__main__':
    main()
