"""Interfaz Streamlit de Nota en Claro: chat -> coordinador -> trabajador. No se lanza a mano: la arranca `python -m app.app`.

- Chat con streaming para la normativa; para las acciones, un aviso de espera.
- Correo al orientador: se muestra el borrador y solo «Enviar» (confirmación explícita) lo manda.
- Notas: se pueden leer de la hoja «Mis notas» de Drive o introducir a mano (funciona sin Google).
- Panel «Traza de la sesión» con cada paso: agente, herramienta, permiso, tokens, segundos y fallos.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from app import servicios  # noqa: E402
from app.agentes.traza import Traza  # noqa: E402
from app.tabla_notas import FASES, PONDERACIONES, tabla_a_notas, tabla_vacia  # noqa: E402



INSTRUCCIONES_HOJA = ('Ábrela con la cuenta de Google conectada, rellénala y luego pídeme «calcula mi nota de admisión».')


@st.cache_resource
def cargar_recursos():
    return servicios.crear_recursos()


def iniciar_sesion():
    ss = st.session_state
    if 'traza' not in ss:
        ss.traza = Traza()
        ss.mensajes = []          # [(rol, texto)]
        ss.borrador = None        # borrador pendiente de confirmar
        ss.notas_manuales = None


def formulario_notas():
    """Entrada manual de notas en el área principal: alternativa a leerlas de Drive. Devuelve el diccionario o None si no se envió."""
    with st.form('form_notas'):
        st.caption('Una fila por asignatura (con el botón + o la última fila puedes añadir más). '
                   'La ponderación (0, 0,1 o 0,2) solo cuenta en la fase de admisión y en la materia obligatoria de modalidad de la fase de acceso.')
        media = st.number_input('Nota media de Bachillerato (0-10, sin Religión)', 0.0, 10.0, value=None, step=0.01, format='%.2f',
                                key='media_notas')
        tabla = st.data_editor(
            tabla_vacia(), key='editor_notas', num_rows='dynamic', hide_index=True, width='stretch',
            column_config={
                'Asignatura': st.column_config.TextColumn('Asignatura', help='Por ejemplo: Matemáticas II', width='large'),
                'Nota': st.column_config.NumberColumn('Nota', min_value=0.0, max_value=10.0, step=0.01, format='%.2f'),
                'Fase': st.column_config.SelectboxColumn('Fase', options=FASES),
                'Ponderación': st.column_config.SelectboxColumn('Ponderación', options=PONDERACIONES),
                'Segunda lengua': st.column_config.CheckboxColumn('Segunda lengua', help='Marca la segunda lengua extranjera'),
            })
        enviado = st.form_submit_button('Usar estas notas')
    if enviado:
        return tabla_a_notas(tabla, media)
    return None


def zona_notas_manuales():
    ss = st.session_state
    with st.expander('Introducir mis notas a mano', expanded=ss.notas_manuales is None):
        datos = formulario_notas()
        if datos is not None:
            ss.notas_manuales = datos
            st.success('Notas guardadas para esta sesión. Pídeme que calcule tu nota de admisión.')
        if ss.notas_manuales is not None and st.button('Olvidar mis notas'):
            ss.notas_manuales = None
            st.rerun()


def barra_lateral(recursos):
    ss = st.session_state
    g = servicios.estado_google()
    with st.sidebar:
        st.header('Tus notas')
        if g['lista']:
            st.success('Google conectado')
        else:
            faltan = [p for p, ok in g['tokens'].items() if not ok]
            st.warning('La parte de Google no está lista. La normativa y la calculadora con notas a mano funcionan igual.')
            if not g['credenciales']:
                st.caption('Falta `credentials.json` en la raíz del proyecto.')
            elif faltan:
                st.caption(f'Falta autorizar: {", ".join(faltan)}. Ejecuta `python -m app.mcp_servers.autorizar`.')
            if g['orientador'] is None:
                st.caption('Falta `ORIENTADOR_EMAIL` en el archivo `.env` (mira `.env.example`).')
        if st.button('Crear mi hoja de notas', disabled=not g['credenciales']):
            r = recursos.puente.llamar('crear_plantilla_notas')
            ss.traza.registrar('herramienta', 'interfaz', herramienta='crear_plantilla_notas', permiso='automatico',
                               segundos=r.segundos, fallo=not r.ok, error=(r.detalle or r.mensaje) if not r.ok else '',
                               reintento=r.reintentos > 0)
            if r.ok:
                st.success(('Hoja creada: ' if r.datos.get('creada') else 'Ya tenías tu hoja: ') + r.datos['url'])
                st.markdown(INSTRUCCIONES_HOJA)
            else:
                st.error(r.mensaje)
        st.caption('Sin Google, rellena la tabla «Introducir mis notas a mano» de la página principal.')


def tarjeta_borrador(recursos):
    ss, b = st.session_state, st.session_state.borrador
    if not b:
        return
    with st.container(border=True):
        st.subheader('Borrador pendiente (aún NO enviado)')
        st.markdown(f"**Para:** {b['destinatario']}  \n**Asunto:** {b['asunto']}")
        st.text(b['cuerpo'])
        c1, c2 = st.columns(2)
        if c1.button('Enviar al orientador', type='primary'):
            t0 = time.perf_counter()
            r = recursos.puente.enviar_correo_confirmado(b['borrador_id'], b['destinatario'])
            ss.traza.registrar('herramienta', 'interfaz', herramienta='enviar_borrador', permiso='confirmar',
                               segundos=time.perf_counter() - t0, fallo=not r.ok, error=(r.detalle or r.mensaje) if not r.ok else '',
                               reintento=r.reintentos > 0, confirmado_por_usuario=True)
            if r.ok:
                ss.mensajes.append(('assistant', f"Correo enviado a {b['destinatario']}."))
                ss.borrador = None
                st.rerun()
            else:
                st.error(r.mensaje)
        if c2.button('Descartar'):
            ss.mensajes.append(('assistant', 'No lo he enviado. El borrador sigue en tus borradores de Gmail por si lo quieres usar.'))
            ss.borrador = None
            st.rerun()


def panel_traza():
    t = st.session_state.traza
    with st.expander('Traza de la sesión'):
        if not t.pasos:
            st.caption('Todavía no hay pasos.')
            return
        tot = t.totales()
        st.caption(f"{tot['pasos']} pasos · {tot['llamadas_modelo']} llamadas al modelo · {tot['tokens_entrada']} tokens de entrada · "
                   f"{tot['tokens_salida']} de salida · {tot['segundos']} s · {tot['fallos']} fallos · registro: `logs/{t.archivo.name}`")
        cols = ['paso', 'agente', 'tipo', 'herramienta', 'permiso', 'tokens_entrada', 'tokens_salida', 'segundos', 'fallo', 'reintento', 'error']
        st.dataframe([{c: p.get(c) for c in cols} for p in t.pasos], width='stretch', hide_index=True)


def atender(recursos, peticion: str):
    ss = st.session_state
    orq = servicios.crear_orquestador(recursos, ss.traza)
    hueco = st.empty()
    parcial, resultado = '', None
    with st.spinner('Pensando... (en CPU puede tardar uno o dos minutos)'):
        for ev in orq.atender(peticion, notas_manuales=ss.notas_manuales):
            if 'trozo' in ev:
                parcial += ev['trozo']
                hueco.markdown(parcial)       # texto crudo del modelo mientras llega; luego se sustituye por el validado
            elif 'resultado' in ev:
                resultado = ev['resultado']
    hueco.markdown(resultado['texto'])
    if resultado.get('intencion'):
        st.caption(f"Tipo de petición: {resultado['intencion']}")
    if resultado.get('borrador'):
        ss.borrador = resultado['borrador']
    ss.mensajes.append(('assistant', resultado['texto']))
    return resultado


def main():
    st.set_page_config(page_title='Nota en Claro', page_icon='📝')
    iniciar_sesion()
    recursos = cargar_recursos()
    st.title('Nota en Claro')
    st.caption('Dudas sobre la PAU de Madrid con la fuente citada, cálculo de tu nota de admisión, plan de estudio, informes y correo a tu orientador.')
    barra_lateral(recursos)
    zona_notas_manuales()
    for rol, texto in st.session_state.mensajes:
        with st.chat_message(rol):
            st.markdown(texto)
    peticion = st.chat_input('Escribe tu petición')
    if peticion:
        st.session_state.mensajes.append(('user', peticion))
        with st.chat_message('user'):
            st.markdown(peticion)
        with st.chat_message('assistant'):
            atender(recursos, peticion)
    tarjeta_borrador(recursos)
    panel_traza()


main()
