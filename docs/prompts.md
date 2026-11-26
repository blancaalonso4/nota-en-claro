# Prompts relevantes

## 2026-11-26 · Sesión 2 · base del proyecto
> Sesión 2. Vamos a montar la base del proyecto final. Contexto: web app «Nota en Claro», asistente para estudiantes de 2.º de Bachillerato en Madrid que preparan la PAU. Reutiliza el RAG del Caso III. El modelo del producto es local con Ollama (qwen3:8b y qwen3:4b-instruct). Windows, 16 GB de RAM, sin GPU, Python 3.14 con «py -3.14».
>
> Arquitectura prevista: agente coordinador (qwen3:4b-instruct) que enruta a agente de normativa (RAG, qwen3:8b sin razonamiento), agente de acciones (MCP a Drive, Calendar y Gmail) y verificador de citas en Python sin modelo. Bucle de agente propio sobre la API de Ollama, sin frameworks. Interfaz en Streamlit. Límite de tokens (num_predict) y razonamiento desactivado salvo donde haga falta.
>
> Pedido: 1) CLAUDE.md con reglas; 2) estructura del repo; 3) RAG a módulos en app/rag/ sin estado global e índice en disco; 4) prueba mínima con una pregunta; 5) git init, commit y push; 6) semillas y README con arranque desde cero en Windows.

## Sesión 2 (continuación) · diagnóstico y evaluación
Dos tareas en orden: (1) diagnosticar por qué la primera ejecución en frío da otra respuesta (comparar fragmentos y prompt byte a byte; si son idénticos, probar P01 3 veces recién cargado con `ollama stop` y 3 en caliente; arreglar y registrar); (2) crear `eval/evaluar.py`: a) solo recuperación (acierto@1/3/5 con y sin reordenador y segundos), b) generación completa con `qwen3:8b` y `qwen3:4b-instruct` con la recuperación ganadora (correctas, abstención en las 5 sin respuesta, abstención indebida en las 20 respondibles, tokens y segundos); mismas métricas que el Caso III; CSV por pregunta y `eval/resultados.md` con fecha, máquina y versiones, todo «medido». Al terminar, commit y push.

## Sesión 3 · decisiones tras la evaluación y latencia
> Sesión 3. Lee primero CLAUDE.md, docs/decisiones.md y eval/resultados.md.
>
> Decisiones tomadas tras la evaluación. Regístralas en docs/decisiones.md con sus cifras:
> 1. Reordenador activado por defecto: acierto@3 de 19/20 frente a 16/20, a cambio de +2,75 s por pregunta.
> 2. Generador único: qwen3:4b-instruct. Se retira qwen3:8b del producto: 13/25 correctas frente a 16/25, solo 2/5 abstenciones en las preguntas sin respuesta frente a 5/5, y 118,8 s frente a 85,7 s por pregunta. El futuro coordinador también usará qwen3:4b-instruct.
>
> Tarea: reducir la latencia, cambiando una sola cosa cada vez y midiendo antes y después.
> a) Mide cuántos tokens ocupa cada parte del prompt: instrucciones del sistema, ejemplos, fragmentos y pregunta.
> b) Reordena el prompt para que la parte fija (instrucciones y ejemplos) vaya siempre al principio y sea idéntica byte a byte entre preguntas, de modo que Ollama reutilice su caché de prefijo. Mide 5 preguntas seguidas en caliente antes y después del cambio: segundos totales y tokens de prompt realmente evaluados frente a los reutilizados de caché.
> c) Si el orden del prompt cambia, vuelve a lanzar la evaluación completa de las 25 preguntas con qwen3:4b-instruct, con el protocolo de reproducibilidad, para comprobar que la calidad no empeora. Compara con la tanda anterior en eval/resultados.md.
> d) Añade streaming de la respuesta en la app de Streamlit.
>
> No cambies el contenido del prompt; solo su orden. Documenta todo, haz commit y push, y dame el resumen con las cifras.


## Sesión 4 · agentes y plataformas MCP
> Sesión 4. Lee CLAUDE.md, docs/decisiones.md y README.md. Vamos a construir los agentes y las 3 plataformas MCP. Quiero primero un plan; no escribas código hasta que lo apruebe.
>
> Contexto: modelo único qwen3:4b-instruct en Ollama (CPU, ~36 tokens/s de lectura de prompt): diseña para el mínimo número de llamadas y prompts cortos. credentials.json en la raíz; el token va a token.json, fuera de git; cuenta de Google demo. Arquitectura: coordinador que clasifica (normativa, nota de admisión, plan de estudio, informe, correo al orientador, fuera de ámbito) con JSON corto; agente de normativa (RAG sin cambios, nunca ve Drive ni Gmail); agente de acciones (tool calling de Ollama sobre MCP, máximo de vueltas, num_predict acotado, decide de verdad); nota de admisión en Python según el corpus (si faltan fórmulas o tablas, avisar antes de inventar); verificador en Python (citas y argumentos de herramientas). Servidores MCP con FastMCP (stdio), uno por plataforma, permisos mínimos: Drive/Sheets («Mis notas», leer, informe), Calendar (listar, crear eventos), Gmail (leer correos del orientador, borrador, enviar solo tras confirmación en la interfaz). Barandillas: permiso por herramienta (automático/confirmar/prohibido), contenido de Drive y Gmail como datos delimitados, destinatario solo el orientador de .env, un reintento y mensaje claro si falla Google. Traza JSONL en logs/ con herramienta, permiso, tokens y segundos por paso, y panel en la interfaz. En el plan: diagrama, scopes y motivos, herramientas con permiso, pruebas, orden y decisiones discutibles.

Cambios al aprobar el plan:
> 1. Commit y push al terminar cada bloque del orden de construcción, sin esperar a que lo pida, con git status antes de cada commit.
> 2. En el README, un apartado «Usar la parte de Google»: app de OAuth en modo prueba (solo usuarios de prueba); al profesor se le añade como usuario de prueba y se le envía credentials.json por un canal privado (nunca por git); sin Google funcionan la normativa y la calculadora con notas introducidas a mano. Añadir esa entrada manual de notas en la interfaz.
> 3. Anotar en docs/decisiones.md que el refresh token caduca a los 7 días en modo prueba y que hay que reautorizar antes de la entrega y de la defensa.
