"""Diagnóstico de reproducibilidad: huellas del prompt, de los fragmentos y de la salida de una ejecución.

Uso:  python eval/diagnostico_frio.py --etiqueta frio1 [--id P01]
Añade una línea JSON a eval/salidas/diagnostico_frio.jsonl.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding='utf-8')

from app.rag.config import ConfigRAG  # noqa: E402
from app.rag.pipeline import SistemaRAG  # noqa: E402
from app.rag.prompt import mensajes_para  # noqa: E402


def sha(x: str) -> str:
    return hashlib.sha256(x.encode('utf-8')).hexdigest()[:16]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--etiqueta', required=True)
    ap.add_argument('--id', default='P01')
    ap.add_argument('--num_thread', type=int, default=None)
    ap.add_argument('--calentar', type=int, default=0, help='llamadas cortas previas, para absorber el estado de arranque')
    a = ap.parse_args()
    cfg = ConfigRAG(num_thread=a.num_thread)
    q = next(q for q in json.loads(cfg.preguntas.read_text(encoding='utf-8'))['preguntas'] if q['id'] == a.id)
    s = SistemaRAG(cfg)
    rec = s.recuperar(q['pregunta'])
    msgs = mensajes_para(q['pregunta'], rec, s.manifiesto)
    tiempos_cal = [s.generador.generar([{'role': 'user', 'content': 'Responde solo: ok'}])['segundos'] for _ in range(a.calentar)]
    g = s.generador.generar(msgs)
    fila = {'etiqueta': a.etiqueta, 'num_thread': a.num_thread, 'calentar': a.calentar, 'seg_calentar': tiempos_cal, 'fragmentos': [c['chunk_id'] for c in rec],
            'sha_fragmentos': sha(json.dumps(rec, ensure_ascii=False, sort_keys=True)),
            'sha_prompt': sha(json.dumps(msgs, ensure_ascii=False)),
            'sha_salida': sha(g['texto']), 'tokens_entrada': g['tokens_entrada'],
            'tokens_salida': g['tokens_salida'], 'segundos': g['segundos'], 'texto': g['texto']}
    out = Path(__file__).parent / 'salidas'
    out.mkdir(exist_ok=True)
    with open(out / 'diagnostico_frio.jsonl', 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(fila, ensure_ascii=False) + '\n')
    print({k: v for k, v in fila.items() if k != 'texto'})


if __name__ == '__main__':
    main()
