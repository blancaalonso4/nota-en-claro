# Prueba real de la hoja «Mis notas» en es_ES (2026-11-26 21:36)

Contra la cuenta demo de Google. Todo **medido** (lo que devuelve la API).

| Paso | Resultado | Detalle |
|---|---|---|
| 1. Crear la hoja de prueba | OK | 1kVvi0Maedh2zFDrRJ9awSrCPpRFxkeUt9iJxfj10O70 |
| 2. Aplicar las validaciones | OK |  |
| 3. Configuración regional | OK | locale=es_ES zona=Europe/Madrid |
| 4. Casillas de «Datos» resaltadas y con aviso | OK | resaltadas=[True, True] avisos=['← escribe aquí', '← escribe aquí'] |
| 5. Validaciones de «Notas» (fila 2) | OK | {"1": {"type": "NUMBER_BETWEEN", "values": [{"userEnteredValue": "0"}, {"userEnteredValue": "10"}]}, "2": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": "acceso"}, {"userEnteredValue": "admisión"}]}, "3": {"type": "NUMBER_BETWEEN", "values": [{"userEnteredValue": "0"}, {"userEnteredValue": "0,2"}]}, "4": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": "sí"}, {"userEnteredValue": " |
| 6. Escribir «8,5», «0,2» y «8,75» (USER_ENTERED) y leerlos con leer_notas | OK | valores=[8.5, 'acceso', 0.2] media=8.75 avisos=[] |
| 7. Hoja de prueba enviada a la papelera | OK | 1kVvi0Maedh2zFDrRJ9awSrCPpRFxkeUt9iJxfj10O70 |
