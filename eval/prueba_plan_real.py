"""Prueba REAL del plan de estudio: modelo real (Ollama) + calendario y hoja de notas REALES de la cuenta demo.

    python eval/prueba_plan_real.py

Crea de verdad las sesiones en el calendario «Nota en Claro · Estudio» y BORRA las que hubiera (es el calendario propio de
la app; el principal solo se consulta como ocupado/libre). El agente solo propone; `plan_calendario.aplicar` lo escribe. Hay que haber autorizado antes (`python -m app.mcp_servers.autorizar`) y tener
rellena la hoja «Mis notas». Todo MEDIDO: segundos (reloj), tokens (los reporta Ollama), vueltas (llamadas al modelo).
No se guardan las notas: solo recuentos y las sesiones creadas.
"""
from __future__ import annotations

import json
import platform
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.agentes.acciones import AgenteAcciones  # noqa: E402
from app.agentes import plan_calendario  # noqa: E402
from app.agentes.puente_mcp import PuenteMCP  # noqa: E402
from app.agentes.traza import Traza  # noqa: E402
from app.mcp_servers import comun  # noqa: E402
from app.rag.config import ConfigRAG, fijar_semillas  # noqa: E402
from app.rag.generador import GeneradorOllama  # noqa: E402

SALIDAS = Path(__file__).resolve().parent / 'salidas'


def main() -> int:
    cfg = ConfigRAG()
    fijar_semillas(cfg.semilla)
    print(f'Calentando {cfg.modelo}...', flush=True)
    GeneradorOllama(cfg).calentar()
    puente = PuenteMCP()
    puente.iniciar()
    traza = Traza(sesion='prueba_plan_real')
    agente = AgenteAcciones(puente, traza, cfg, orientador=comun.orientador() or None,
                            zona=comun.zona_horaria())
    try:
        res = agente.ejecutar('plan_estudio', 'Hazme un plan de estudio para esta semana', dias=7)
        ap = None
        if res.ok and res.plan_propuesto:
            ap = plan_calendario.aplicar(puente, traza, res.plan_propuesto, confirmado=True, zona=comun.zona_horaria(),
                                         huecos=res.huecos, dias=res.dias, agente='orquestador')
            res.texto = ap.texto
    finally:
        puente.cerrar()
    modelo = [p for p in traza.pasos if p['tipo'] == 'modelo']
    rechazos = [(p['herramienta'], p['error'][:160]) for p in traza.pasos if p['tipo'] == 'verificador' and p['fallo']]
    out = {'ok': res.ok, 'vueltas': res.vueltas, 'eventos': len(res.plan_propuesto), 'borrados': ap.borrados if ap else None,
           'no_borrados': ap.no_borrados if ap else None, 'error': res.error or (ap.texto if ap and not ap.ok else ''), 'rechazos_verificador': rechazos,
           'tokens_entrada': [p['tokens_entrada'] for p in modelo], 'tokens_salida': [p['tokens_salida'] for p in modelo],
           'segundos_total': traza.totales()['segundos'], 'texto': res.texto}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    SALIDAS.mkdir(exist_ok=True)
    (SALIDAS / 'prueba_plan_real.md').write_text(
        f'# Prueba real del plan de estudio ({datetime.now():%Y-%m-%d %H:%M})\n\n'
        f'Modelo `{cfg.modelo}`, seed {cfg.semilla}, temperature {cfg.temperature}, num_predict 600, think False. {platform.platform()}, CPU sin GPU. '
        'Calendario y hoja de notas REALES de la cuenta demo. Cifras **medidas** (reloj, tokens de Ollama, vueltas = llamadas al modelo).\n\n'
        f"- Resultado: {'OK' if res.ok else 'FALLO'} · vueltas {res.vueltas} · eventos propuestos {len(res.plan_propuesto)} · borrados {out['borrados']} · no borrados {out['no_borrados']} · {out['segundos_total']} s\n"
        f"- Tokens de entrada por vuelta: {out['tokens_entrada']} · de salida: {out['tokens_salida']}\n"
        f'- Rechazos del verificador: {rechazos or "ninguno"}\n'
        + (f'- Error: {res.error}\n' if res.error else '') + f'\n```\n{res.texto}\n```\n', encoding='utf-8')
    return 0 if res.ok and res.plan_propuesto and ap and ap.ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
