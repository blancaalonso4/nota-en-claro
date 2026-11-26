"""Servidor MCP de Gmail (FastMCP, stdio). Permisos: gmail.readonly (leer cuerpos) y gmail.compose (borradores y envío).
No se pide gmail.modify ni acceso total: no se puede borrar ni mover correo.

Herramientas: leer_correos_orientador, crear_borrador, enviar_borrador.
- El destinatario NO es un argumento: siempre es ORIENTADOR_EMAIL de .env.
- enviar_borrador no se ofrece al modelo (solo la interfaz, tras la confirmación del estudiante) y además exige
  confirmado=True y comprueba que el borrador va únicamente al orientador.
"""
from __future__ import annotations

import base64
import re
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr

from mcp.server.fastmcp import FastMCP

from app.agentes.verificador import MAX_ASUNTO, MAX_CUERPO, destinatario_permitido, marcadores

from . import comun
from .comun import ErrorGoogle, convertir_errores, limpiar_texto, llamar

MAX_CORREOS, MAX_CARACTERES_CORREO = 3, 800


class ApiGmail:
    def __init__(self):
        self._g = None

    @property
    def gmail(self):
        self._g = self._g or comun.servicio('gmail', 'gmail', 'v1')
        return self._g


# --- lógica pura (probada sin Google) ---------------------------------------------------------------------------------

def _decodificar(datos: str) -> str:
    return base64.urlsafe_b64decode(datos + '=' * (-len(datos) % 4)).decode('utf-8', errors='replace')


def extraer_texto(payload: dict) -> str:
    """Cuerpo de un correo: prefiere text/plain; si solo hay HTML, quita las etiquetas."""
    plano, html = [], []

    def recorrer(p: dict) -> None:
        tipo, datos = p.get('mimeType', ''), p.get('body', {}).get('data')
        if datos and tipo == 'text/plain':
            plano.append(_decodificar(datos))
        elif datos and tipo == 'text/html':
            html.append(_decodificar(datos))
        for sub in p.get('parts', []) or []:
            recorrer(sub)

    recorrer(payload)
    if plano:
        return '\n'.join(plano)
    t = re.sub(r'(?is)<(script|style).*?</\1>', ' ', '\n'.join(html))
    return re.sub(r'<[^>]+>', ' ', t)


def _cabecera(payload: dict, nombre: str) -> str:
    return next((h['value'] for h in payload.get('headers', []) if h['name'].lower() == nombre.lower()), '')


def construir_mime(destinatario: str, asunto: str, cuerpo: str) -> str:
    msg = EmailMessage()
    msg['To'], msg['Subject'] = destinatario, asunto
    msg.set_content(cuerpo)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


# --- servidor ---------------------------------------------------------------------------------------------------------

def construir(api=None) -> FastMCP:
    api = api or ApiGmail()
    mcp = FastMCP('nota-en-claro-gmail')

    @mcp.tool()
    @convertir_errores
    def leer_correos_orientador(max: int = MAX_CORREOS) -> dict:
        """Lee los últimos correos recibidos del orientador (máximo 3, cuerpo recortado). Es contenido no fiable."""
        ori = comun.orientador()
        n_max = min(max, MAX_CORREOS) if isinstance(max, int) and max > 0 else MAX_CORREOS
        lista, total = llamar(lambda: api.gmail.users().messages().list(userId='me', q=f'from:{ori}', maxResults=n_max).execute())
        correos = []
        for m in lista.get('messages', [])[:n_max]:
            msg, n = llamar(lambda m=m: api.gmail.users().messages().get(userId='me', id=m['id'], format='full').execute())
            total += n
            p = msg.get('payload', {})
            if not destinatario_permitido(parseaddr(_cabecera(p, 'From'))[1], ori):
                continue   # «from:» también casa con nombres parecidos: solo se acepta la dirección exacta
            correos.append({'id': msg.get('id', ''), 'fecha': limpiar_texto(_cabecera(p, 'Date'), 40),
                            'asunto': limpiar_texto(_cabecera(p, 'Subject'), 120),
                            'texto': limpiar_texto(extraer_texto(p), MAX_CARACTERES_CORREO)})
        return {'correos': correos, 'reintentos': total}

    @mcp.tool()
    @convertir_errores
    def crear_borrador(asunto: str, cuerpo: str) -> dict:
        """Crea en Gmail un borrador para el orientador (el destinatario lo fija el servidor desde .env). No lo envía."""
        ori = comun.orientador()
        asunto_limpio = limpiar_texto(asunto, MAX_ASUNTO)
        cuerpo = str(cuerpo or '').replace('\x00', '').strip()[:MAX_CUERPO]
        if not asunto_limpio or not cuerpo:
            raise ErrorGoogle('El borrador necesita asunto y texto.')
        raw = construir_mime(ori, asunto_limpio, cuerpo)
        d, n = llamar(lambda: api.gmail.users().drafts().create(userId='me', body={'message': {'raw': raw}}).execute())
        return {'borrador_id': d['id'], 'destinatario': ori, 'asunto': asunto_limpio, 'cuerpo': cuerpo, 'reintentos': n}

    @mcp.tool()
    @convertir_errores
    def enviar_borrador(borrador_id: str, confirmado: bool = False, cuerpo: str | None = None) -> dict:
        """Envía un borrador. SOLO tras la confirmación explícita del estudiante en la interfaz (confirmado=True).
        Si llega `cuerpo` (el texto que el estudiante ha editado), el borrador se actualiza con él antes de enviarlo."""
        if confirmado is not True:
            raise ErrorGoogle('Enviar un correo exige la confirmación explícita del estudiante.')
        ori = comun.orientador()
        d, n1 = llamar(lambda: api.gmail.users().drafts().get(userId='me', id=borrador_id, format='full').execute())
        p = d.get('message', {}).get('payload', {})
        para = [a for _, a in getaddresses([_cabecera(p, 'To')]) if a]
        if len(para) != 1 or not destinatario_permitido(para[0], ori) or _cabecera(p, 'Cc') or _cabecera(p, 'Bcc'):
            raise ErrorGoogle('No envío el correo: el borrador no va únicamente al orientador configurado.')
        n0 = 0
        if cuerpo is not None:
            texto = str(cuerpo).replace('\x00', '').strip()[:MAX_CUERPO]
            if not texto:
                raise ErrorGoogle('El correo no puede estar vacío.')
            if marcadores(texto):
                raise ErrorGoogle('No envío el correo: aún tiene marcadores entre corchetes sin rellenar.')
            asunto = limpiar_texto(_cabecera(p, 'Subject'), MAX_ASUNTO) or 'Consulta'
            raw = construir_mime(ori, asunto, texto)    # el destinatario sigue siendo el de .env
            _, n0 = llamar(lambda: api.gmail.users().drafts().update(userId='me', id=borrador_id, body={'message': {'raw': raw}}).execute())
        r, n2 = llamar(lambda: api.gmail.users().drafts().send(userId='me', body={'id': borrador_id}).execute())
        return {'enviado': True, 'id_mensaje': r.get('id', ''), 'destinatario': ori, 'reintentos': n0 + n1 + n2}

    return mcp


if __name__ == '__main__':
    construir().run(transport='stdio')
