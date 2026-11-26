"""Prueba REAL de los tres servidores MCP contra la cuenta demo de Google (hay que haber autorizado antes).

    python eval/prueba_mcp.py            # crea hoja, informe, evento y borrador; envía el borrador al ORIENTADOR_EMAIL del .env
    python eval/prueba_mcp.py --sin-envio

Cada paso es independiente: si uno falla se anota el error (mensaje y detalle técnico) y se sigue con el resto. El resultado se
escribe en eval/salidas/prueba_mcp.md. Todo MEDIDO (segundos: reloj; reintentos: los que informa el servidor). No se guarda
contenido de correos ni de las notas: solo recuentos.
"""
from __future__ import annotations

import json
import platform
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.agentes.puente_mcp import PuenteMCP  # noqa: E402
from app.mcp_servers import comun  # noqa: E402

SALIDAS = Path(__file__).resolve().parent / 'salidas'


def main(argv: list[str]) -> int:
    con_envio = '--sin-envio' not in argv
    zona = ZoneInfo(comun.zona_horaria())
    ahora = datetime.now(zona)
    filas, ctx = [], {}
    puente = PuenteMCP()
    puente.iniciar()

    def paso(nombre, herramienta, args=None, resumen=lambda d: ''):
        r = puente.llamar(herramienta, args or {})
        ok = r.ok
        res = resumen(r.datos) if ok and r.datos is not None else (f'{r.mensaje} | {r.detalle}' if not ok else '')
        filas.append((nombre, herramienta, 'OK' if ok else 'FALLO', round(r.segundos, 2), r.reintentos, res))
        print(f'[{"OK" if ok else "FALLO"}] {nombre} ({r.segundos:.1f} s): {res}')
        return r

    try:
        paso('1. Crear hoja «Mis notas»', 'crear_plantilla_notas', resumen=lambda d: f"creada={d['creada']} url={d['url']}")
        paso('2. Leer la hoja', 'leer_notas',
             resumen=lambda d: f"{len(d.get('materias', []))} materias, media={d.get('nota_media_bachillerato')}, avisos={len(d.get('avisos', []))}")
        paso('3. Guardar informe', 'guardar_informe', {'titulo': 'Prueba MCP (borrar cuando quieras)', 'contenido': 'Informe de prueba de Nota en Claro.'},
             resumen=lambda d: f"url={d['url']}")
        desde, hasta = ahora.date().isoformat(), (ahora + timedelta(days=4)).date().isoformat()
        r = paso('4. Huecos libres (4 días)', 'huecos_libres', {'desde': desde, 'hasta': hasta}, resumen=lambda d: f"{len(d['huecos'])} huecos")
        if r.ok and r.datos['huecos']:
            h = r.datos['huecos'][0]
            ini = datetime.fromisoformat(h['inicio'] if 'inicio' in h else h[0])
            ctx['evento'] = {'titulo': 'Prueba MCP · estudio', 'inicio': ini.isoformat(), 'fin': (ini + timedelta(minutes=30)).isoformat()}
        if 'evento' in ctx:
            paso('5. Crear un evento de estudio', 'crear_eventos_estudio', {'eventos': [ctx['evento']]}, resumen=lambda d: f"{len(d['creados'])} creado(s)")
        paso('6. Listar eventos de estudio', 'listar_eventos', {'desde': desde, 'hasta': hasta}, resumen=lambda d: f"{len(d['eventos'])} evento(s)")
        paso('7. Leer correos del orientador', 'leer_correos_orientador', resumen=lambda d: f"{len(d['correos'])} correo(s) leídos")
        r = paso('8. Crear borrador', 'crear_borrador', {'asunto': 'Prueba de Nota en Claro', 'cuerpo': 'Correo de prueba generado por eval/prueba_mcp.py.', 'destinatario': comun.orientador()},
                 resumen=lambda d: f"destinatario={d['destinatario']}")
        if con_envio and r.ok:
            t0 = time.perf_counter()
            e = puente.enviar_correo_confirmado(r.datos['borrador_id'], r.datos['destinatario'])
            res = f"enviado={e.datos.get('enviado')}" if e.ok else f'{e.mensaje} | {e.detalle}'
            filas.append(('9. Enviar el borrador (vía confirmada)', 'enviar_borrador', 'OK' if e.ok else 'FALLO', round(time.perf_counter() - t0, 2), e.reintentos, res))
            print(f'[{"OK" if e.ok else "FALLO"}] 9. Enviar: {res}')
    finally:
        puente.cerrar()

    SALIDAS.mkdir(exist_ok=True)
    md = ['# Prueba real de los servidores MCP contra Google', '',
          f'Fecha: {ahora:%Y-%m-%d %H:%M} · {platform.platform()} · **medido** (segundos: reloj; reintentos: informados por el servidor).', '',
          '| Paso | Herramienta | Resultado | Segundos | Reintentos | Detalle |', '|---|---|---|---|---|---|']
    md += [f'| {a} | `{b}` | {c} | {d} | {e} | {str(f).replace("|", "/")} |' for a, b, c, d, e, f in filas]
    (SALIDAS / 'prueba_mcp.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    return 0 if all(f[2] == 'OK' for f in filas) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
