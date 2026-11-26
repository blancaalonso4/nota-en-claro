# Decisiones técnicas

Formato: fecha · decisión · por qué · alternativa descartada.

## 2026-11-26 · Generar con Ollama (`qwen3:8b`, `think=False`) en lugar de transformers
- **Por qué:** el producto es local, en un portátil de 16 GB sin GPU; Ollama gestiona la cuantización y la memoria.
- **Descartada:** Qwen2.5-3B con transformers (como en el Caso III), que necesitaba GPU.

## 2026-11-26 · Índice en disco con huella
- `data/indice/` guarda `embeddings.npy`, `fragmentos.json` y `meta.json`; la huella (sha256 de textos, encoder, ventana y solape) decide si se reindexa.
- **Por qué:** no reindexar en cada arranque. Medido: construir 100,7 s; cargar 0,02 s (256 fragmentos, primera ejecución con descarga del encoder incluida).
- **Descartada:** reindexar siempre, o una base vectorial externa (sobra para 256 fragmentos).

## 2026-11-26 · Troceado por ventana fija (250 palabras, solape 35) por defecto
- **Por qué:** fue el troceado del sistema final del Caso III. El troceado por secciones queda portado en `troceado.py` como alternativa.
- **Descartada:** secciones como valor por defecto, porque el Caso III no lo adoptó en el sistema final.

## 2026-11-26 · Reordenador opcional y desactivado por defecto
- **Por qué:** añade latencia en CPU; se activa con `ConfigRAG(usar_reordenador=True)` cuando se mida que compensa.

## 2026-11-26 · Prompt v2 y regla de abstención del Caso III
- Se portan tal cual (`prompt.py`, `citas.py`). La cita que se muestra es siempre un trozo literal del documento.

## 2026-11-26 · `caso3_referencia/` fuera de git; solo se copian textos, manifiesto y preguntas
- **Por qué:** los PDF pesan y son reproducibles con `descargar_corpus.py`. **Descartada:** subir el Caso III entero.

## 2026-11-26 · Dependencias en Python 3.14
- Medido: instalan sin errores en `.venv` torch 2.15.0, transformers 5.24.1, sentence-transformers 5.7.0, ollama 0.6.3, streamlit 1.67.0, numpy 2.5.5, pypdf 7.1.1.

## Mediciones de la prueba mínima (P01, `qwen3:8b`, k=3)
Todas **medidas** en este portátil (CPU, sin GPU):
- Tokens de entrada 1792 (todas las ejecuciones).
- 1.ª ejecución, modelo en frío: 147 tokens de salida, 178,56 s.
- Ejecuciones 2.ª a 4.ª, modelo caliente: 115 tokens de salida, 32,6–33,9 s, respuesta idéntica en las tres.
- **La 1.ª ejecución dio una respuesta distinta a las otras tres** pese a `seed=42` y `temperature=0`. Hipótesis (no verificada): diferencia de arranque en frío en Ollama. Pendiente de investigar antes de prometer reproducibilidad exacta.
- Calidad de P01: la cita es correcta (doc08, «Días 12, 15 y 16 de junio»), pero la respuesta no da el plazo («tres días hábiles» está en doc13/doc07) y la 1.ª ejecución escribió «del 12 al 16 de junio», que no es lo que dice la cita. Con k=3 no se recuperó el fragmento de doc13/doc07. Pendiente para la evaluación de la próxima sesión.
