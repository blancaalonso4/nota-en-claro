# Escenarios del agente de acciones (2026-11-26)

Modelo `qwen3:4b-instruct`, seed 42, temperature 0.0, num_predict 600, think False. Windows-11-10.0.26200-SP0, CPU sin GPU.
Cifras **medidas**: tokens (los reporta Ollama por llamada), segundos (reloj, `time.perf_counter`), vueltas (llamadas al modelo). Herramientas de Google simuladas.

| Escenario | vueltas | herramientas (en orden) | eventos | tokens entrada | tokens salida | s total | resultado |
|---|---|---|---|---|---|---|---|
| plan, Física floja (5,0) | 3 | leer_notas → huecos_libres → crear_eventos_estudio | 4 | [703, 1184, 1329] | [66, 101, 247] | 78.04 | {'Física': 1, 'Matemáticas II': 1, 'Química': 1, 'Inglés': 0, 'Lengua': 0, 'Historia': 1} |
| plan, Historia floja (4,5) | 3 | leer_notas → huecos_libres → crear_eventos_estudio | 5 | [703, 1184, 1627] | [66, 337, 313] | 142.64 | {'Física': 0, 'Matemáticas II': 0, 'Química': 0, 'Inglés': 0, 'Lengua': 0, 'Historia': 5} |
