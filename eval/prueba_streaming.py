"""Comprueba el streaming: mismo texto que sin streaming y cuándo llega el primer trozo.

Uso:  python eval/prueba_streaming.py --id P03
Mide (MEDIDO): segundos hasta el primer trozo, segundos totales, nº de trozos y si el texto coincide con `responder`.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding='utf-8')

from app.rag.config import ConfigRAG  # noqa: E402
from app.rag.pipeline import SistemaRAG  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--id', default='P03')
    a = ap.parse_args()
    cfg = ConfigRAG()
    q = next(q for q in json.loads(cfg.preguntas.read_text(encoding='utf-8'))['preguntas'] if q['id'] == a.id)
    s = SistemaRAG(cfg)
    s.calentar()

    def con_stream():
        t0 = time.perf_counter()
        primero, trozos, res = None, 0, None
        for ev in s.responder_stream(q['pregunta']):
            if 'trozo' in ev:
                trozos += 1
                primero = primero or time.perf_counter() - t0
            else:
                res = ev['resultado']
        return res['salida_modelo'], primero, time.perf_counter() - t0, trozos

    def sin_stream():
        t0 = time.perf_counter()
        r = s.responder(q['pregunta'])
        return r['salida_modelo'], time.perf_counter() - t0

    # La salida de Ollama depende de si el prompt estaba ya en caché (ver docs/decisiones.md), así que se comparan
    # ejecuciones en el MISMO estado: 1.ª (sin caché de la pregunta) sin streaming vs con streaming tras `ollama stop`,
    # y 2.ª (prompt entero en caché) sin streaming vs con streaming.
    import subprocess
    res = {}
    for modo in ('sin', 'con'):
        subprocess.run(['ollama', 'stop', cfg.modelo], capture_output=True)
        time.sleep(3)
        s.calentar()
        a1 = sin_stream() if modo == 'sin' else con_stream()
        a2 = sin_stream() if modo == 'sin' else con_stream()
        res[modo] = (a1, a2)
        print(f"[medido] {modo} streaming · 1.ª (prompt sin caché): {a1[-1] if modo == 'sin' else a1[2]:.1f} s"
              + (f" (primer trozo a los {a1[1]:.1f} s, {a1[3]} trozos)" if modo == 'con' else '')
              + f" · 2.ª (en caché): {a2[-1] if modo == 'sin' else a2[2]:.1f} s")
    print('[medido] 1.ª ejecución idéntica con y sin streaming:', res['sin'][0][0] == res['con'][0][0])
    print('[medido] 2.ª ejecución idéntica con y sin streaming:', res['sin'][1][0] == res['con'][1][0])


if __name__ == '__main__':
    main()
