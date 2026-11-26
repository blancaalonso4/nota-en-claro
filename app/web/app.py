"""Interfaz mínima en Streamlit (provisional): una caja de pregunta sobre el RAG."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from app.rag.pipeline import SistemaRAG, formatear  # noqa: E402


@st.cache_resource
def cargar_sistema() -> SistemaRAG:
    sistema = SistemaRAG()
    sistema.calentar()
    return sistema


st.title('Nota en Claro')
st.caption('Dudas sobre la PAU de Madrid, con la fuente citada. Versión provisional.')
pregunta = st.text_input('Tu pregunta')
if pregunta:
    with st.spinner('Buscando y respondiendo (en CPU puede tardar ~30 s)...'):
        r = cargar_sistema().responder(pregunta)
    st.write(formatear(r))
    st.caption(f"Tokens de entrada {r['tokens_entrada']} · salida {r['tokens_salida']} · {r['segundos_generar']} s")
