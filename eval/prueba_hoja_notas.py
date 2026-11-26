"""Prueba REAL de la hoja «Mis notas» con configuración regional española contra la cuenta demo (hay que haber autorizado).

    python eval/prueba_hoja_notas.py

Crea una hoja de PRUEBA aparte (no toca la hoja guardada en el estado de la app), comprueba la configuración regional, las casillas
resaltadas, las validaciones y que una nota escrita con coma («8,5», «0,2») se guarda como número, y al final MANDA LA HOJA A LA PAPELERA
(es una hoja que ha creado esta propia prueba). Resultado en eval/salidas/prueba_hoja_notas.md. Todo MEDIDO (lo que devuelve Google).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.mcp_servers import comun, mcp_drive  # noqa: E402
from app.mcp_servers.mcp_drive import ApiDrive  # noqa: E402

SALIDAS = Path(__file__).resolve().parent / 'salidas'


def main() -> int:
    api = ApiDrive()
    filas, hoja_id = [], None

    def paso(nombre, ok, detalle=''):
        filas.append((nombre, 'OK' if ok else 'FALLO', detalle))
        print(f'[{"OK" if ok else "FALLO"}] {nombre}: {detalle}')

    try:
        r = api.sheets.spreadsheets().create(body=mcp_drive._peticion_crear_hoja(), fields='spreadsheetId').execute()
        hoja_id = r['spreadsheetId']
        paso('1. Crear la hoja de prueba', True, hoja_id)
        api.sheets.spreadsheets().batchUpdate(spreadsheetId=hoja_id, body=mcp_drive._validaciones()).execute()
        paso('2. Aplicar las validaciones', True)
        hoja = api.sheets.spreadsheets().get(spreadsheetId=hoja_id, includeGridData=True,
                                             fields='properties(locale,timeZone),sheets(properties.title,data.rowData.values(userEnteredFormat.backgroundColor,'
                                                    'formattedValue,dataValidation))').execute()
        prop = hoja['properties']
        paso('3. Configuración regional', prop.get('locale') == 'es_ES', f"locale={prop.get('locale')} zona={prop.get('timeZone')}")
        datos = next(s for s in hoja['sheets'] if s['properties']['title'] == 'Datos')['data'][0]['rowData']
        amarillas = [bool(f['values'][1].get('userEnteredFormat', {}).get('backgroundColor')) for f in datos[:2]]
        avisos = [f['values'][2].get('formattedValue') for f in datos[:2]]
        paso('4. Casillas de «Datos» resaltadas y con aviso', all(amarillas) and all(a == '← escribe aquí' for a in avisos), f'resaltadas={amarillas} avisos={avisos}')
        notas = next(s for s in hoja['sheets'] if s['properties']['title'] == 'Notas')['data'][0]['rowData']
        reglas = {i: (notas[1]['values'][i].get('dataValidation') or {}).get('condition') for i in (1, 2, 3, 4)}
        paso('5. Validaciones de «Notas» (fila 2)', all(reglas.values()), json.dumps(reglas, ensure_ascii=False)[:400])
        # escribir como lo haría el estudiante (texto con coma, USER_ENTERED) y leer los valores sin formato
        api.sheets.spreadsheets().values().update(
            spreadsheetId=hoja_id, range='Notas!A2:E2', valueInputOption='USER_ENTERED',
            body={'values': [['Matemáticas II', '8,5', 'acceso', '0,2', 'no']]}).execute()
        api.sheets.spreadsheets().values().update(
            spreadsheetId=hoja_id, range='Datos!B1', valueInputOption='USER_ENTERED', body={'values': [['8,75']]}).execute()
        leido = api.sheets.spreadsheets().values().batchGet(
            spreadsheetId=hoja_id, ranges=['Datos!A1:B2', 'Notas!A2:E2'], valueRenderOption='UNFORMATTED_VALUE').execute()['valueRanges']
        parseado = mcp_drive.parsear_hoja(leido[0].get('values', []), leido[1].get('values', []))
        bien = (parseado['nota_media_bachillerato'] == 8.75 and parseado['materias'][0]['nota'] == 8.5
                and parseado['materias'][0]['ponderacion'] == 0.2 and not parseado['avisos'])
        paso('6. Escribir «8,5», «0,2» y «8,75» (USER_ENTERED) y leerlos con leer_notas', bien,
             f"valores={leido[1]['values'][0][1:4]} media={parseado['nota_media_bachillerato']} avisos={parseado['avisos']}")
    except Exception as e:  # noqa: BLE001
        paso('Error', False, f'{type(e).__name__}: {e}')
    finally:
        if hoja_id:
            try:
                api.drive.files().update(fileId=hoja_id, body={'trashed': True}).execute()
                paso('7. Hoja de prueba enviada a la papelera', True, hoja_id)
            except Exception as e:  # noqa: BLE001
                paso('7. Enviar a la papelera', False, f'{type(e).__name__}: {e} (bórrala a mano en Drive: {hoja_id})')
    SALIDAS.mkdir(exist_ok=True)
    (SALIDAS / 'prueba_hoja_notas.md').write_text(
        f'# Prueba real de la hoja «Mis notas» en es_ES ({datetime.now():%Y-%m-%d %H:%M})\n\nContra la cuenta demo de Google. Todo **medido** (lo que devuelve la API).\n\n'
        '| Paso | Resultado | Detalle |\n|---|---|---|\n' + '\n'.join(f'| {a} | {b} | {c.replace("|", "/")} |' for a, b, c in filas) + '\n', encoding='utf-8')
    return 0 if all(f[1] == 'OK' for f in filas) else 1


if __name__ == '__main__':
    raise SystemExit(main())
