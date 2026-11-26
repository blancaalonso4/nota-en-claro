# Escenarios del agente de acciones (2026-11-26)

Modelo `qwen3:4b-instruct`, seed 42, temperature 0.0, num_predict 600, think False. Windows-11-10.0.26200-SP0, CPU sin GPU.
Cifras **medidas**: tokens (los reporta Ollama por llamada), segundos (reloj, `time.perf_counter`), vueltas (llamadas al modelo). Herramientas de Google simuladas.

| Escenario | vueltas | herramientas (en orden) | eventos | tokens entrada | tokens salida | s total | resultado |
|---|---|---|---|---|---|---|---|
| plan, Física floja (5,0) | 2 | leer_notas → huecos_libres → crear_eventos_estudio | 4 | [813, 1381] | [66, 123] | 65.34 | {'Física': 2, 'Matemáticas II': 0, 'Química': 1, 'Inglés': 0, 'Lengua': 0, 'Historia': 1} |
| plan, Historia floja (4,5) | 2 | leer_notas → huecos_libres → crear_eventos_estudio | 3 | [813, 1368] | [66, 97] | 37.96 | {'Física': 0, 'Matemáticas II': 0, 'Química': 1, 'Inglés': 0, 'Lengua': 0, 'Historia': 2} |
| plan, calendario lleno | 2 | leer_notas → huecos_libres | 0 | [813, 1198] | [66, 29] | 22.58 | No hay huecos libres en el rango de fechas indicado, por lo  |
