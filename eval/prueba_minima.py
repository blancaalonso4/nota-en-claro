"""Prueba mínima: una pregunta del conjunto de evaluación, de principio a fin con Ollama.

Uso:  python eval/prueba_minima.py --id P01
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding='utf-8')

from app.rag.config import ConfigRAG  # noqa: E402
from app.rag.pipeline import SistemaRAG, formatear  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--id', default='P01')
    a = ap.parse_args()
    cfg = ConfigRAG()
    q = next(q for q in json.loads(cfg.preguntas.read_text(encoding='utf-8'))['preguntas'] if q['id'] == a.id)

    t0 = time.perf_counter()
    sistema = SistemaRAG(cfg)
    t_arranque = time.perf_counter() - t0
    print(f"[medido] índice {sistema.indice.origen}: {len(sistema.indice.chunks)} fragmentos, "
          f"{sistema.indice.segundos:.2f} s (arranque total {t_arranque:.1f} s)")
    t_cal = sistema.calentar()
    print(f"[medido] calentamiento del modelo: {t_cal} s")
    print(f"Pregunta {q['id']}: {q['pregunta']}\n")

    r = sistema.responder(q['pregunta'])
    print(formatear(r))
    if r['abstiene']:
        print('motivo:', r['motivo'])
    print(f"\n[medido] modelo {cfg.modelo} · think={cfg.think} · seed={cfg.semilla} · temperature={cfg.temperature} "
          f"· num_predict={cfg.num_predict}")
    print(f"[medido] tokens de entrada: {r['tokens_entrada']} · tokens de salida: {r['tokens_salida']} "
          f"· segundos (generar): {r['segundos_generar']}")
    print('dato_clave esperado:', q.get('dato_clave'))
    print('salida cruda del modelo:\n' + r['salida_modelo'])


if __name__ == '__main__':
    main()
