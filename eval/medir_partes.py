"""Cuántos tokens ocupa cada parte del prompt (instrucciones, ejemplos, fragmentos, pregunta).

Uso:  python eval/medir_partes.py

MEDIDO con el tokenizador de qwen3:4b-instruct a través de Ollama: cada trozo se manda en modo `raw` (sin plantilla de chat)
con num_predict=1 y se lee `prompt_eval_count`. La suma de trozos puede diferir en 1-2 tokens por frontera entre trozos; la
diferencia con el total real del chat (medido en eval/medir_cache.py) es la plantilla de chat («<|im_start|>…»).
Resultado en eval/salidas/partes_prompt.json
"""
import json
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.stdout.reconfigure(encoding='utf-8')

from app.rag.config import ConfigRAG  # noqa: E402
from app.rag.pipeline import SistemaRAG  # noqa: E402
from app.rag.prompt import SISTEMA_V2, mensajes_para  # noqa: E402

SALIDAS = Path(__file__).parent / 'salidas'


def main() -> None:
    cfg = ConfigRAG()
    s = SistemaRAG(cfg)
    cli = s.generador.cliente

    def n_tokens(texto: str) -> int:
        r = cli.generate(model=cfg.modelo, prompt=texto, raw=True, keep_alive=cfg.keep_alive,
                         options={'seed': cfg.semilla, 'temperature': 0, 'num_predict': 1, 'num_ctx': cfg.num_ctx,
                                  'num_thread': cfg.num_thread})
        return int(r.prompt_eval_count)

    instr, resto = SISTEMA_V2.split('\n\nEjemplo 1', 1)
    ejemplos = 'Ejemplo 1' + resto
    fijo = {'instrucciones': n_tokens(instr), 'ejemplos': n_tokens(ejemplos), 'sistema_completo': n_tokens(SISTEMA_V2)}
    print('fijo', fijo, flush=True)
    filas = []
    for q in json.loads(cfg.preguntas.read_text(encoding='utf-8'))['preguntas']:
        rec = s.recuperar(q['pregunta'])
        usuario = mensajes_para(q['pregunta'], rec, s.manifiesto)[1]['content']
        # el usuario es: «PREGUNTA: q\n\nFRAGMENTOS:\n\n...\n\nPREGUNTA: q»
        inicial = f"PREGUNTA: {q['pregunta']}\n\n"
        final = f"\n\nPREGUNTA: {q['pregunta']}"
        assert usuario.startswith(inicial) and usuario.endswith(final)
        frag = usuario[len(inicial):-len(final)]
        f = {'id': q['id'], 'pregunta_inicial': n_tokens(inicial), 'fragmentos': n_tokens(frag),
             'pregunta_final': n_tokens(final)}
        filas.append(f)
        print(f, flush=True)
    medias = {k: round(float(np.mean([f[k] for f in filas])), 1) for k in ('pregunta_inicial', 'fragmentos', 'pregunta_final')}
    res = {'modelo': cfg.modelo, 'fijo': fijo, 'medias_25_preguntas': medias, 'filas': filas}
    (SALIDAS / 'partes_prompt.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
    print(res['fijo'], medias)


if __name__ == '__main__':
    main()
