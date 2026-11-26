"""Autorización OAuth de las tres plataformas (una vez, o cuando caduque el token).

    python -m app.mcp_servers.autorizar            # las tres
    python -m app.mcp_servers.autorizar gmail      # solo una

Abre el navegador para que el estudiante (cuenta demo) dé su consentimiento. Guarda un token por plataforma
(token_drive.json, token_calendar.json, token_gmail.json), fuera de git. La app de OAuth está en modo prueba:
solo pueden autorizar los usuarios de prueba y el refresh token caduca a los 7 días.
"""
from __future__ import annotations

import json
import sys

from .comun import CREDENCIALES, SCOPES, ruta_token


def autorizar(plataforma: str) -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow
    print(f'\n== {plataforma}: permisos que se piden ==')
    for s in SCOPES[plataforma]:
        print(f'   {s}')
    flujo = InstalledAppFlow.from_client_secrets_file(str(CREDENCIALES), SCOPES[plataforma])
    # prompt=consent + offline: garantiza que Google devuelva refresh_token
    cred = flujo.run_local_server(port=0, prompt='consent', access_type='offline',
                                  authorization_prompt_message='Abriendo el navegador para autorizar... (si no se abre, usa este enlace: {url})',
                                  success_message='Autorización recibida. Ya puedes cerrar esta pestaña.')
    ruta_token(plataforma).write_text(cred.to_json(), encoding='utf-8')
    print(f'[ok] Token guardado en {ruta_token(plataforma).name} (no se sube a git).')


def main(argv: list[str]) -> int:
    if not CREDENCIALES.exists():
        print('No encuentro credentials.json en la raíz del proyecto (cliente OAuth de escritorio de Google).', file=sys.stderr)
        return 1
    try:
        if 'installed' not in json.loads(CREDENCIALES.read_text(encoding='utf-8')):
            print('credentials.json no es un cliente OAuth de tipo «Aplicación de escritorio».', file=sys.stderr)
            return 1
    except ValueError:
        print('credentials.json no es un JSON válido.', file=sys.stderr)
        return 1
    pedidas = [a for a in argv if a in SCOPES] or list(SCOPES)
    desconocidas = [a for a in argv if a not in SCOPES]
    if desconocidas:
        print(f'Plataforma desconocida: {desconocidas}. Opciones: {", ".join(SCOPES)}', file=sys.stderr)
        return 1
    for p in pedidas:
        autorizar(p)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
