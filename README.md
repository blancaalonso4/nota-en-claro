# Nota en Claro (README provisional)

Asistente para estudiantes de 2.º de Bachillerato en Madrid que preparan la PAU. RAG con cita sobre 20 documentos oficiales, con modelo local en Ollama. Estado: base del proyecto (sesión 2); coordinador, agentes y MCP aún no están implementados.

## Arranque desde cero en Windows (PowerShell)
1. **Instalar Ollama** desde https://ollama.com/download y comprobar `ollama --version`.
2. **Descargar los modelos:**
   ```powershell
   ollama pull qwen3:4b-instruct
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
6. **Prueba mínima** (la primera vez descarga el encoder y construye el índice en `data/indice/`):
   ```powershell
   python eval/prueba_minima.py --id P01
   ```
7. **Lanzar la app:**
   ```powershell
   streamlit run app/web/app.py
   ```

## Reproducibilidad
Semilla 42 en random, numpy y torch; `seed=42`, `temperature=0`, `num_predict` y `think=False` en cada llamada a Ollama. Ver la salvedad medida en `docs/decisiones.md` (la primera ejecución con el modelo en frío dio una respuesta distinta a las siguientes).

## Cifras medidas (portátil sin GPU, P01, qwen3:8b)
- Índice: 256 fragmentos; construir 100,7 s (incluye descarga del encoder), cargar de disco 0,02 s.
- Generar: 1792 tokens de entrada, 115 de salida, unos 33 s con el modelo caliente (178 s en frío).

## Estructura
`app/` (rag, agentes, mcp_servers, web) · `data/` · `eval/` · `docs/` · `CLAUDE.md` con las reglas del proyecto.
