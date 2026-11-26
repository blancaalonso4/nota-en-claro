# Resultados de evaluación

**Todas las cifras de este documento son MEDIDAS** en esta máquina, sobre las 25 preguntas de `data/eval/preguntas.json` (20 respondibles + 5 sin respuesta), con las definiciones del Caso III. Semilla 42, `temperature 0`. Generado por `eval/evaluar.py`; detalle por pregunta en `eval/salidas/*.csv`.

## Entorno

- Fecha: 2026-11-26 12:19
- Máquina: HPBlanca · Windows-11-10.0.26200-SP0 · Intel64 Family 6 Model 154 Stepping 4, GenuineIntel · 12 hilos · 15.7 GB RAM · sin GPU
- Python: 3.14.10
- Ollama: ollama version is 0.40.18
- Modelos Ollama (digest, tamaño): `qwen3:4b-instruct` 0edcdef34593 (2.5 GB); `qwen3:8b` 500a1f067a9f (5.2 GB)
- Librerías: torch 2.15.0, sentence-transformers 5.7.0, transformers 5.24.1, numpy 2.5.5, ollama 0.6.3

## a) Solo recuperación (sin LLM)

Índice: 256 fragmentos (ventana 250, solape 35, e5-small). Acierto@k sobre las 20 respondibles; en las de dos evidencias cuenta solo si están las dos. Segundos por pregunta (medidos; modelos ya cargados, carga del reordenador 64.9 s aparte).

| Configuración | acierto@1 | acierto@3 | acierto@5 | acierto@10 | s/pregunta (media) | s/pregunta (máx) |
|---|---|---|---|---|---|---|
| sin reordenador | 12/20 | 16/20 | 17/20 | 18/20 | 0.0277 | 0.0385 |
| con reordenador (top-20) | 15/20 | 19/20 | 19/20 | 19/20 | 2.7451 | 3.4249 |

**Ganadora (criterio: más aciertos@3, luego @1, luego @5, y a igualdad la más rápida): con reordenador (top-20).**

## b) Generación completa

Recuperación usada: con reordenador (top-20), k = 3. `think=False` salvo que el modelo no lo admita (columna «think»). Correcta = no se abstiene, cita un fragmento de oro y da el `dato_clave` en la respuesta; en las sin respuesta, correcta = se abstiene. Fidelidad = correctas entre las respondibles con el oro dentro de los k fragmentos.

| Modelo | correctas (25) | respondibles correctas | fidelidad | abstención sin respuesta | abstención indebida | tokens entrada (media) | tokens salida (media) | s/pregunta (media) | s/pregunta (máx) | think |
|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3:8b` | 13/25 | 11/20 | 11/19 | 2/5 | 0/20 | 1921.8 | 85.1 | 118.8 | 163.6 | enviado |
| `qwen3:4b-instruct` | 16/25 | 11/20 | 11/19 | 5/5 | 3/20 | 1913.8 | 136.5 | 85.7 | 124.7 | enviado |
