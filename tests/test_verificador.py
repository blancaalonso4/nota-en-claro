"""Pruebas del verificador de argumentos de herramientas (sin Ollama ni Google)."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.agentes.verificador import destinatario_permitido, verificar

MAD = ZoneInfo('Europe/Madrid')
AHORA = datetime(2026, 12, 1, 9, 0, tzinfo=MAD)
HUECOS = [{'inicio': '2026-12-02T16:00:00+01:00', 'fin': '2026-12-02T20:00:00+01:00'},
          {'inicio': '2026-12-03T10:00:00+01:00', 'fin': '2026-12-03T13:00:00+01:00'}]
ORI = 'orientador@ejemplo.com'


def ev(ini='2026-12-02T16:00:00+01:00', fin='2026-12-02T17:30:00+01:00', titulo='Estudiar Física'):
    return {'titulo': titulo, 'inicio': ini, 'fin': fin}


def v(herramienta, args, **kw):
    kw.setdefault('ahora', AHORA)
    kw.setdefault('orientador', ORI)
    return verificar(herramienta, args, **kw)


def eventos(lista, **kw):
    kw.setdefault('huecos', HUECOS)
    return v('crear_eventos_estudio', {'eventos': lista}, **kw)


# --- eventos de estudio ----------------------------------------------------------------------------------------

def test_evento_valido_dentro_de_un_hueco():
    assert eventos([ev(), ev('2026-12-02T18:00:00+01:00', '2026-12-02T19:00:00+01:00', 'Repasar Historia')]).ok


def test_evento_sin_zona_se_interpreta_en_madrid():
    assert eventos([ev('2026-12-02T16:00:00', '2026-12-02T17:00:00')]).ok


def test_exige_haber_consultado_huecos_libres():
    r = eventos([ev()], huecos=None)
    assert not r.ok and 'huecos_libres' in str(r)


def test_evento_fuera_de_hueco():
    r = eventos([ev('2026-12-02T20:00:00+01:00', '2026-12-02T21:00:00+01:00')])
    assert not r.ok and 'hueco' in str(r)


def test_evento_que_se_sale_de_un_hueco_por_el_final():
    assert not eventos([ev('2026-12-02T19:30:00+01:00', '2026-12-02T20:30:00+01:00')]).ok


def test_fecha_invalida_y_fin_anterior_al_inicio():
    assert 'fecha no válida' in str(eventos([ev('2026-13-45T10:00:00', '2026-13-45T11:00:00')]))
    assert 'posterior al inicio' in str(eventos([ev('2026-12-02T17:00:00+01:00', '2026-12-02T16:30:00+01:00')]))
    assert not eventos([{'titulo': 'x', 'inicio': 'mañana', 'fin': 'tarde'}]).ok


def test_evento_en_el_pasado():
    huecos = [{'inicio': '2026-11-30T10:00:00+01:00', 'fin': '2026-11-30T13:00:00+01:00'}]
    r = eventos([ev('2026-11-30T10:00:00+01:00', '2026-11-30T11:00:00+01:00')], huecos=huecos)
    assert not r.ok and 'pasado' in str(r)


def test_duracion_fuera_de_limites():
    assert 'entre 30 y 180' in str(eventos([ev(fin='2026-12-02T16:15:00+01:00')]))
    huecos = [{'inicio': '2026-12-02T08:00:00+01:00', 'fin': '2026-12-02T23:00:00+01:00'}]
    assert not eventos([ev(fin='2026-12-02T20:00:00+01:00')], huecos=huecos).ok   # 4 h


def test_fuera_del_horizonte_pedido():
    huecos = [{'inicio': '2026-12-20T10:00:00+01:00', 'fin': '2026-12-20T13:00:00+01:00'}]
    r = eventos([ev('2026-12-20T10:00:00+01:00', '2026-12-20T11:00:00+01:00')], huecos=huecos, dias=7)
    assert not r.ok and '7 días' in str(r)
    assert eventos([ev('2026-12-20T10:00:00+01:00', '2026-12-20T11:00:00+01:00')], huecos=huecos, dias=30).ok


def test_eventos_solapados():
    r = eventos([ev('2026-12-02T16:00:00+01:00', '2026-12-02T17:30:00+01:00'),
                 ev('2026-12-02T17:00:00+01:00', '2026-12-02T18:00:00+01:00')])
    assert not r.ok and 'solapan' in str(r)


def test_mas_de_diez_eventos():
    r = eventos([ev()] * 11)
    assert not r.ok and 'máximo 10' in str(r)


def test_evento_con_invitados_se_rechaza():
    malo = {**ev(), 'invitados': ['x@ejemplo.com']}
    r = eventos([malo])
    assert not r.ok and 'invitados' in str(r)
    assert not eventos([{**ev(), 'attendees': [{'email': 'x@ejemplo.com'}]}]).ok


def test_titulo_obligatorio_y_con_limite():
    assert not eventos([ev(titulo='')]).ok
    assert not eventos([ev(titulo='x' * 81)]).ok


def test_lista_vacia_o_mal_formada():
    assert not eventos([]).ok
    assert not eventos(['no soy un dict']).ok
    assert not v('crear_eventos_estudio', {'eventos': 'texto'}, huecos=HUECOS).ok


# --- rangos ----------------------------------------------------------------------------------------------------

def test_rangos_de_huecos_y_listado():
    for nombre in ('huecos_libres', 'listar_eventos'):
        assert v(nombre, {'desde': '2026-12-02', 'hasta': '2026-12-09'}).ok
        assert v(nombre, {'desde': '2026-12-02T08:00:00', 'hasta': '2026-12-02T22:00:00'}).ok
        assert not v(nombre, {'desde': '2026-12-09', 'hasta': '2026-12-02'}).ok
        assert not v(nombre, {'desde': '2026-02-30', 'hasta': '2026-12-02'}).ok
        assert not v(nombre, {'desde': '2026-12-01', 'hasta': '2027-02-01'}).ok     # más de 31 días
        assert not v(nombre, {'desde': '2026-11-01', 'hasta': '2026-11-10'}).ok     # en el pasado
        assert not v(nombre, {'desde': '2026-12-02'}).ok


# --- correo ----------------------------------------------------------------------------------------------------

def test_borrador_valido_y_sin_campos_de_destinatario():
    assert v('crear_borrador', {'asunto': 'Duda sobre la PAU', 'cuerpo': 'Hola, quería preguntarte...'}).ok
    for campo in ('destinatario', 'to', 'cc', 'bcc', 'para'):
        r = v('crear_borrador', {'asunto': 'a', 'cuerpo': 'b', campo: 'otro@ejemplo.com'})
        assert not r.ok and 'no permitidos' in str(r)


def test_borrador_sin_orientador_configurado():
    assert not v('crear_borrador', {'asunto': 'a', 'cuerpo': 'b'}, orientador=None).ok


def test_borrador_con_limites():
    assert not v('crear_borrador', {'asunto': '', 'cuerpo': 'b'}).ok
    assert not v('crear_borrador', {'asunto': 'a', 'cuerpo': 'x' * 3001}).ok


def test_destinatario_solo_el_orientador():
    assert destinatario_permitido('Orientador@Ejemplo.com ', ORI)
    assert not destinatario_permitido('otro@ejemplo.com', ORI)
    assert not destinatario_permitido('orientador@ejemplo.com,otro@ejemplo.com', ORI)
    assert not destinatario_permitido('', ORI)
    assert not destinatario_permitido(ORI, None)


def test_enviar_exige_confirmacion():
    assert not v('enviar_borrador', {'borrador_id': 'r123', 'destinatario': ORI}).ok
    assert v('enviar_borrador', {'borrador_id': 'r123', 'destinatario': ORI}, confirmado_por_usuario=True).ok
    assert not v('enviar_borrador', {}, confirmado_por_usuario=True).ok
    assert not v('enviar_borrador', {'borrador_id': 'r123', 'destinatario': ORI}, confirmado_por_usuario=True, orientador=None).ok


def test_leer_correos_con_limite():
    assert v('leer_correos_orientador', {}).ok
    assert v('leer_correos_orientador', {'max': 2}).ok
    for malo in (0, 4, '3', True):
        assert not v('leer_correos_orientador', {'max': malo}).ok


# --- informe y herramientas desconocidas --------------------------------------------------------------------------

def test_informe():
    assert v('guardar_informe', {'titulo': 'Informe de notas', 'contenido': 'Física 6,5...'}).ok
    assert not v('guardar_informe', {'titulo': 'x', 'contenido': ''}).ok
    assert not v('guardar_informe', {'titulo': 'x', 'contenido': 'y' * 6001}).ok
    assert not v('guardar_informe', {'titulo': 'x', 'contenido': 'y', 'compartir_con': 'z'}).ok


def test_herramienta_desconocida_o_argumentos_no_objeto():
    assert 'no es una herramienta conocida' in str(v('borrar_evento', {}))
    assert not v('leer_notas', 'texto').ok
    assert not v('leer_notas', {'carpeta': '/'}).ok
    assert v('leer_notas', None).ok


def test_los_errores_dicen_al_modelo_como_corregir():
    # el modelo 4B usaba el hueco entero (4 h) o una fecha sin hueco y no sabía qué cambiar
    texto = str(eventos([ev(fin='2026-12-02T20:00:00+01:00')]))
    assert 'dura 240 min' in texto and 'fin = inicio + 60 a 120 min' in texto
    texto = str(eventos([ev('2026-12-06T16:00:00+01:00', '2026-12-06T17:00:00+01:00')]))
    assert 'los huecos son: 2026-12-02 16:00-20:00' in texto


# --- marcadores entre corchetes (sesión 6) ---------------------------------------------------------------------------

def test_borrador_con_marcadores_entre_corchetes_se_rechaza():
    for cuerpo in ('Hola [Nombre del orientador], quería preguntarte...', 'Gracias.\n[Tu nombre]', 'Hola [ ]'):
        r = v('crear_borrador', {'asunto': 'Duda', 'cuerpo': cuerpo})
        assert not r.ok and 'corchetes' in str(r), cuerpo
    assert not v('crear_borrador', {'asunto': 'Cita [fecha]', 'cuerpo': 'Hola, Marta.'}).ok     # también en el asunto
    assert v('crear_borrador', {'asunto': 'Duda', 'cuerpo': 'Hola, Marta. Un saludo, Luis.'}).ok


def test_enviar_con_texto_editado_se_verifica():
    assert v('enviar_borrador', {'borrador_id': 'r1', 'destinatario': ORI, 'cuerpo': 'Hola, Marta.'}, confirmado_por_usuario=True).ok
    for malo in ('', '   ', 'Hola [Tu nombre]', 'x' * 3001, None):
        assert not v('enviar_borrador', {'borrador_id': 'r1', 'destinatario': ORI, 'cuerpo': malo}, confirmado_por_usuario=True).ok, malo


# --- el destinatario lo pone el estudiante, nunca el modelo (sesión 6) ---------------------------------------------------

def test_el_modelo_no_puede_proponer_destinatario_ni_remitente():
    assert not v('crear_borrador', {'asunto': 'a', 'cuerpo': 'b', 'destinatario': 'otro@ejemplo.com'}).ok
    assert not v('leer_correos_orientador', {'max': 3, 'remitente': 'otro@ejemplo.com'}).ok


def test_segunda_comprobacion_exige_exactamente_el_correo_del_estudiante():
    base = {'asunto': 'a', 'cuerpo': 'b'}
    assert v('crear_borrador', base | {'destinatario': ORI}, interno=True).ok
    assert v('crear_borrador', base | {'destinatario': ' Orientador@Ejemplo.COM '}, interno=True).ok      # mayúsculas y espacios no cuentan
    for malo in ('otro@ejemplo.com', ORI + '.falso.net', ORI + ',otro@ejemplo.com', 'x' + ORI, '', None, 5):
        r = v('crear_borrador', base | {'destinatario': malo}, interno=True)
        assert not r.ok, malo
    assert not v('crear_borrador', base, interno=True).ok                                                 # sin destinatario
    assert 'exactamente' in str(v('crear_borrador', base | {'destinatario': 'otro@ejemplo.com'}, interno=True))


def test_sin_correo_del_orientador_no_hay_borrador():
    for falta in (None, '', 'no-es-un-correo'):
        r = v('crear_borrador', {'asunto': 'a', 'cuerpo': 'b'}, orientador=falta)
        assert not r.ok and 'falta el correo del orientador' in str(r), falta


def test_lectura_de_correos_solo_del_orientador_del_estudiante():
    assert v('leer_correos_orientador', {'max': 3, 'remitente': ORI}, interno=True).ok
    assert not v('leer_correos_orientador', {'max': 3, 'remitente': 'otro@ejemplo.com'}, interno=True).ok


def test_envio_solo_al_correo_del_estudiante():
    assert not v('enviar_borrador', {'borrador_id': 'r1', 'destinatario': 'otro@ejemplo.com'}, confirmado_por_usuario=True).ok
    assert not v('enviar_borrador', {'borrador_id': 'r1'}, confirmado_por_usuario=True).ok


def test_correo_valido():
    from app.agentes.verificador import correo_valido
    for ok in ('a@b.es', 'marta.gil+pau@instituto.madrid.es', ' a@b.es '):
        assert correo_valido(ok), ok
    for mal in ('', 'a@b', 'a b@c.es', 'a@b.es,c@d.es', 'a@b.es\nBcc: x@y.es', '<a@b.es>', 'Marta <a@b.es>', 'a@b.es;c@d.es', None, 3, 'a@' + 'b' * 120 + '.es'):
        assert not correo_valido(mal), mal
