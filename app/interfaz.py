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

FILAS_NOTAS = 10
FASES = ['', 'acceso', 'admisión']
PONDERACIONES = ['', '0', '0,1', '0,2']


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
    """Entrada manual de notas: alternativa a leerlas de Drive. Devuelve el diccionario o None si no se envió."""
    with st.form('form_notas'):
        media = st.number_input('Nota media de Bachillerato (0-10, sin Religión)', 0.0, 10.0, value=None, step=0.01, format='%.2f')
        st.caption('Una fila por asignatura. De la fase de acceso solo pondera la materia obligatoria de modalidad.')
        filas = []
        for i in range(FILAS_NOTAS):
            c = st.columns([3, 2, 2, 2, 1])
            nombre = c[0].text_input('Asignatura', key=f'n_as_{i}', label_visibility='collapsed', placeholder='Asignatura')
            nota = c[1].number_input('Nota', 0.0, 10.0, value=None, step=0.01, format='%.2f', key=f'n_no_{i}', label_visibility='collapsed', placeholder='Nota')
            fase = c[2].selectbox('Fase', FASES, key=f'n_fa_{i}', label_visibility='collapsed')
            pond = c[3].selectbox('Ponderación', PONDERACIONES, key=f'n_po_{i}', label_visibility='collapsed')
            sl = c[4].checkbox('2.ª leng.', key=f'n_sl_{i}', help='Segunda lengua extranjera')
            filas.append({'asignatura': nombre, 'nota': nota, 'fase': fase, 'ponderacion': pond, 'segunda_lengua': 'sí' if sl else ''})
        enviado = st.form_submit_button('Usar estas notas')
    if enviado:
        return {'nota_media_bachillerato': media, 'materias': [f for f in filas if f['asignatura'].strip()]}
    return None


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
            else:
                st.error(r.mensaje)
        with st.expander('Introducir mis notas a mano'):
            datos = formulario_notas()
            if datos is not None:
                ss.notas_manuales = datos
                st.success('Notas guardadas para esta sesión. Pídeme que calcule tu nota de admisión.')
            if ss.notas_manuales is not None and st.button('Olvidar mis notas'):
                ss.notas_manuales = None
                st.rerun()


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
        st.dataframe([{c: p.get(c) for c in cols} for p in t.pasos], use_container_width=True, hide_index=True)


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
