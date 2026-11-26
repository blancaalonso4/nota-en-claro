# Nota en Claro (README provisional)

Asistente para estudiantes de 2.º de Bachillerato en Madrid que preparan la PAU. RAG con cita sobre 20 documentos oficiales, con modelo local en Ollama. Estado: sesión 4 (coordinador, agente de acciones, calculadora de nota y servidores MCP de Drive, Calendar y Gmail; la parte de Google está probada solo con servicios falsos).

## Arranque desde cero en Windows (PowerShell)
1. **Instalar Ollama** desde https://ollama.com/download y comprobar `ollama --version`.
2. **Descargar el modelo:**
   ```powershell
   ollama pull qwen3:4b-instruct
   ```
3. **Instalar Python 3.14** y comprobar `py -3.14 --version`.
4. **Crear el entorno virtual:**
   ```powershell
   py -3.14 -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
5. **Instalar dependencias:**
   ```powershell
   pip install -r requirements.txt
   ```
6. **Lanzar la app** (un solo comando, desde la raíz del proyecto). Comprueba que Ollama responde y que `qwen3:4b-instruct` está descargado (si no, dice qué hacer), construye el índice en `data/indice/` si falta (la primera vez descarga el encoder) y abre la interfaz de Streamlit:
   ```powershell
   python -m app.app
   ```
   Opcional, prueba mínima por consola: `python eval/prueba_minima.py --id P01`.

## Usar la parte de Google
La app de OAuth está en **modo prueba**: solo pueden autorizarla los **usuarios de prueba** que figuren en el proyecto de Google, y el token caduca a los **7 días** (hay que volver a autorizar antes de la entrega y de la defensa).

- **Profesor/a:** le añadiremos como usuario de prueba y le enviaremos `credentials.json` por un canal privado (nunca por git; está en `.gitignore`).
- **Sin Google** funcionan igualmente la normativa y la calculadora de nota de admisión con las notas introducidas a mano (panel lateral → «Introducir mis notas a mano»).

Pasos con Google:
1. Copia `.env.example` a `.env` y pon `ORIENTADOR_EMAIL` (único destinatario permitido).
2. Deja `credentials.json` (cliente OAuth de escritorio) en la raíz. En el proyecto de Google deben estar activadas las APIs de Drive, Sheets, Calendar y Gmail.
3. Autoriza (abre el navegador; una vez por plataforma, con la cuenta demo):
   ```powershell
   python -m app.mcp_servers.autorizar
   ```
   Se guardan `token_drive.json`, `token_calendar.json` y `token_gmail.json` (fuera de git). Si algo falla con «autorización caducada», repite este paso.
4. Lanza la app (`python -m app.app`); el arranque avisa de lo que falte. Pulsa «Crear mi hoja de notas» en el panel lateral.

Permisos pedidos (mínimos): Drive `drive.file`; Calendar `calendar.app.created` y `calendar.events.freebusy`; Gmail `gmail.readonly` y `gmail.compose`. El correo nunca se envía sin pulsar «Enviar» en la interfaz.

Pruebas sin Google ni Ollama: `python -m pytest -q`.

## ¿Por qué no hay entrenamiento (train.py)?
No ajustamos pesos (no hay fine-tuning) porque al modelo le falta **información**, no **estilo**: no conoce la normativa de la PAU de Madrid ni sus plazos, y eso se resuelve dándole los textos en el momento de responder, es decir, con RAG (según el árbol de decisión del tema B: falta conocimiento → RAG; falta forma o estilo → ajuste). La «fase que se hace una vez» es la **ingesta** (trocear, embeber, indexar), y la hace la app al arrancar si el índice falta o cambió el corpus (huella en `data/indice/meta.json`); después solo se carga de disco.

## Reproducibilidad
Semilla 42 en random, numpy y torch; `seed=42`, `temperature=0`, `num_predict` y `think=False` en cada llamada a Ollama. Ver la salvedad medida en `docs/decisiones.md` (la primera ejecución con el modelo en frío dio una respuesta distinta a las siguientes).

## Cifras medidas (portátil sin GPU, P01, qwen3:8b)
- Índice: 256 fragmentos; construir 100,7 s (incluye descarga del encoder), cargar de disco 0,02 s.
- Generar: 1792 tokens de entrada, 115 de salida, unos 33 s con el modelo caliente (178 s en frío).

## Estructura
`app/` (`app.py` arranque, `interfaz.py` Streamlit, `rag/`, `agentes/`, `mcp_servers/`) · `data/` · `eval/` · `docs/` · `CLAUDE.md` con las reglas del proyecto.
