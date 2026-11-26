# Prompts relevantes

## 2026-11-26 · Sesión 2 · base del proyecto
> Sesión 2. Vamos a montar la base del proyecto final. Contexto: web app «Nota en Claro», asistente para estudiantes de 2.º de Bachillerato en Madrid que preparan la PAU. Reutiliza el RAG del Caso III. El modelo del producto es local con Ollama (qwen3:8b y qwen3:4b-instruct). Windows, 16 GB de RAM, sin GPU, Python 3.14 con «py -3.14».
>
> Arquitectura prevista: agente coordinador (qwen3:4b-instruct) que enruta a agente de normativa (RAG, qwen3:8b sin razonamiento), agente de acciones (MCP a Drive, Calendar y Gmail) y verificador de citas en Python sin modelo. Bucle de agente propio sobre la API de Ollama, sin frameworks. Interfaz en Streamlit. Límite de tokens (num_predict) y razonamiento desactivado salvo donde haga falta.
>
> Pedido: 1) CLAUDE.md con reglas; 2) estructura del repo; 3) RAG a módulos en app/rag/ sin estado global e índice en disco; 4) prueba mínima con una pregunta; 5) git init, commit y push; 6) semillas y README con arranque desde cero en Windows.

## Sesión 2 (continuación) · diagnóstico y evaluación
Dos tareas en orden: (1) diagnosticar por qué la primera ejecución en frío da otra respuesta (comparar fragmentos y prompt byte a byte; si son idénticos, probar P01 3 veces recién cargado con `ollama stop` y 3 en caliente; arreglar y registrar); (2) crear `eval/evaluar.py`: a) solo recuperación (acierto@1/3/5 con y sin reordenador y segundos), b) generación completa con `qwen3:8b` y `qwen3:4b-instruct` con la recuperación ganadora (correctas, abstención en las 5 sin respuesta, abstención indebida en las 20 respondibles, tokens y segundos); mismas métricas que el Caso III; CSV por pregunta y `eval/resultados.md` con fecha, máquina y versiones, todo «medido». Al terminar, commit y push.
