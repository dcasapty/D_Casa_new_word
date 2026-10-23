"""Celular y correo bien escritos (pedido de la dueña, 2026-10-16): funciones PURAS, sin base de datos.

«El vendedor siempre, obligatoriamente, captura el número de teléfono y el correo electrónico, pero bien escrito»: ahí
le llegan al cliente su factura y cómo ver sus puntos. Aquí se decide qué es «bien escrito»; quién lo exige y cuándo lo
deciden los módulos (``dcasa_contactos``: la ficha, la venta y la factura; Socios, la tienda, Brian y el importador).

* ``problema_del_correo(texto)`` → ``(código, sugerencia)``. Códigos: ``None`` (bien), ``'vacio'``, ``'varios'`` (dos
  correos en el campo), ``'formato'`` (no es un correo completo), ``'dedo'`` (un error de dedo en un proveedor conocido,
  con la sugerencia) y ``'relleno'`` («sincorreo@…», «no@…»: no es un correo de verdad).
* ``correo_limpio(texto)``: el correo sin el nombre visible, recortado y en minúsculas; ``None`` si tiene un problema.
* ``problema_del_telefono(texto)`` → código: ``None`` (bien), ``'vacio'``, ``'letras'``, ``'varios'``, ``'corto'``,
  ``'largo'``, ``'invalido'`` (8 números que no son de un teléfono de Panamá), ``'fijo'`` (7 números de un teléfono
  fijo de Panamá: va en «Teléfono fijo») o ``'sin_mas'`` (de otro país sin «+»).
* ``telefono_para_guardar(texto)``: «+507 6026-1919» o «+13055551234» (el mismo formato de la llave de contactos: la
  llave no cambia al guardarlo así).
* ``problema_del_fijo(texto)`` y ``fijo_para_guardar(texto)``: lo mismo para el teléfono fijo (2026-10-22: «hubo un
  cliente que no tenía WhatsApp sino teléfono fijo de 7 números»). En Panamá son 7 números (no empiezan por 0, 1 ni 6),
  y se guardan como «+507 234-5678»; de otro país, con su «+». Código ``'celular'``: 8 números de un celular (va en
  «Celular»).
* ``mensaje_del_correo``, ``mensaje_del_telefono`` y ``mensaje_del_fijo``: el texto para la persona del equipo (con
  ``env._``).

El campo del celular sigue siendo solo para un celular de Panamá o un número de otro país con su «+» (es el que recibe
WhatsApp y la llave de Socios); el fijo tiene su propio campo.
"""
import re

from odoo.tools.mail import single_email_re

from . import reglas as R

PANAMA = '507'
# Un teléfono fijo de Panamá: 7 números que no empiezan por 0 ni 1 (servicios) ni por 6 (un celular de antes, al que le
# falta un número).
FIJO_DE_PANAMA = re.compile(r'[2-57-9]\d{6}')

# Proveedores de correo conocidos: nombre → los finales que sí existen. El primero es el que se sugiere.
PROVEEDORES = {
    'gmail': ('com',),
    'googlemail': ('com',),
    'hotmail': ('com', 'es', 'it', 'fr', 'de', 'co.uk', 'com.ar', 'com.mx'),
    'outlook': ('com', 'es', 'fr', 'de', 'it', 'com.ar', 'com.mx'),
    'yahoo': ('com', 'es', 'fr', 'de', 'it', 'co.uk', 'com.ar', 'com.mx'),
    'icloud': ('com',),
    'live': ('com', 'com.mx', 'com.ar', 'co.uk', 'fr', 'it', 'nl'),
}
# Errores de dedo frecuentes (y los que salen al escribir rápido en el celular).
VARIANTES = {
    'gmail': ('gmial', 'gmal', 'gmai', 'gamil', 'gmaill', 'gmali', 'gmil', 'gnail', 'gmaik', 'gmsil', 'gimail',
              'gemail', 'gmeil', 'gmaul', 'gmaio', 'gmaiil', 'gmmail', 'ggmail', 'gmaiul', 'gmai1', 'gamail',
              'gmaile'),
    'hotmail': ('hotmial', 'hotmal', 'hotmai', 'hotamil', 'hormail', 'hotmil', 'hotmaill', 'homail', 'hotnail',
                'htmail', 'otmail', 'jotmail', 'hotmali', 'hotmeil', 'hotmaik', 'hoymail', 'hotmsil', 'hotmaul',
                'hitmail', 'hotail', 'hotmall', 'hottmail', 'hootmail', 'hotmaiil', 'hptmail', 'hotmaio'),
    'outlook': ('outlok', 'outllok', 'outloo', 'outlool', 'oulook', 'otlook', 'outlokk', 'outloock', 'outlouk',
                'outllook', 'outlooc', 'putlook', 'iutlook', 'outlookk', 'ooutlook', 'outloook', 'autlook'),
    'yahoo': ('yaho', 'yahho', 'yhoo', 'yahooo', 'yaoo', 'yahpo', 'yahoi', 'yaboo', 'tahoo', 'uahoo', 'yajoo',
              'yahio'),
    'icloud': ('iclod', 'icoud', 'icluod', 'iclould', 'iclud', 'icloid', 'icliud', 'iclouf', 'icould', 'icloude',
               'iclooud', 'icolud'),
    'live': ('lve', 'liev', 'livee', 'llive', 'livr'),
}
DEDO_POR_NOMBRE = {variante: nombre for nombre, variantes in VARIANTES.items() for variante in variantes}
# Finales que no existen y que siempre son un .com mal escrito.
FINALES_ERRADOS = frozenset({'con', 'cmo', 'vom', 'xom', 'comm', 'cim', 'coom', 'ocm', 'cpm', 'clm'})
# Finales cortos que existen (Colombia, Camerún, Omán) pero que en un proveedor conocido son un .com cortado.
FINALES_CORTADOS = frozenset({'co', 'cm', 'om', 'c', 'cc'})
# Lo que la gente escribe cuando el cliente «no tiene» correo.
RELLENO = frozenset({'no', 'na', 'ninguno', 'ninguna', 'notiene', 'sincorreo', 'nocorreo', 'noaplica', 'correo',
                     'email', 'test', 'prueba', 'x', 'xx', 'xxx', 'asdf', 'notengo', 'nohay', 'sinemail',
                     'noemail', 'nomail'})

_NOMBRE_VISIBLE = re.compile(r'^\s*(?:"?[^"<>]*"?\s*)?<([^<>]+)>\s*$')
_VARIOS_CORREOS = re.compile(r'[\s,;/]+')
_DOMINIO = re.compile(r'^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}$')
_LOCAL = re.compile(r"^[a-z0-9!#$%&'*+/=?^_`{|}~.-]+$")


# ---------------------------------------------------------------------------
# Correo
# ---------------------------------------------------------------------------

def _sin_nombre_visible(texto):
    """«Ana <ana@x.com>» → «ana@x.com»; lo demás, tal cual (recortado)."""
    texto = (texto or '').strip()
    coincide = _NOMBRE_VISIBLE.match(texto)
    return coincide.group(1).strip() if coincide else texto


def _sugerir_dominio(dominio):
    """El dominio corregido si es un error de dedo de un proveedor conocido o de un «.com»; si no, ``None``."""
    nombre, _punto, final = dominio.partition('.')
    real = nombre if nombre in PROVEEDORES else DEDO_POR_NOMBRE.get(nombre)
    if final in FINALES_ERRADOS:
        return f'{real or nombre}.com'
    if not real:
        return None
    if real != nombre:  # el nombre del proveedor está mal escrito
        return f'{real}.{final if final in PROVEEDORES[real] else PROVEEDORES[real][0]}'
    if final in FINALES_CORTADOS:
        return f'{real}.{PROVEEDORES[real][0]}'
    return None


def _correo_sugerido(local, dominio):
    """Para un correo con el formato roto: la versión arreglada, si queda bien. Si no, ``None``."""
    local = local.strip(' .')
    dominio = re.sub(r'[\s,;]+', '.', dominio.strip(' .,;'))
    dominio = re.sub(r'\.{2,}', '.', dominio)
    if '.' not in dominio and dominio.endswith('com') and dominio[:-3] in PROVEEDORES | DEDO_POR_NOMBRE:
        dominio = f'{dominio[:-3]}.com'
    if '.' not in dominio and dominio in PROVEEDORES | DEDO_POR_NOMBRE:
        dominio = f'{dominio}.com'
    dominio = _sugerir_dominio(dominio) or dominio
    candidato = f'{local}@{dominio}'
    return candidato if _formato_valido(candidato) else None


def _formato_valido(correo):
    if correo.count('@') != 1 or '..' in correo:
        return False
    local, dominio = correo.split('@')
    return bool(local and _LOCAL.match(local) and not local.startswith('.') and not local.endswith('.')
                and _DOMINIO.match(dominio) and single_email_re.match(correo))


def problema_del_correo(texto):
    """``(código, sugerencia)`` del correo escrito. ``(None, None)`` si está bien."""
    correo = _sin_nombre_visible(texto).lower()
    if not correo:
        return 'vacio', None
    if sum(1 for parte in _VARIOS_CORREOS.split(correo) if '@' in parte) >= 2:
        return 'varios', None
    if correo.count('@') != 1:
        partes = [p for p in correo.split('@') if p]
        sugerencia = _correo_sugerido(partes[0], partes[-1]) if len(partes) == 2 else None
        return 'formato', sugerencia
    local, dominio = correo.split('@')
    if not _formato_valido(correo):
        sugerencia = _correo_sugerido(local, dominio) if local and dominio else None
        return 'formato', sugerencia if sugerencia != correo else None
    # Sin puntos ni guiones («no.tiene», «sin_correo»), pero con sus números: «prueba2@…» o «ana2015@…» sí valen.
    if re.sub(r'[._+\-]', '', local) in RELLENO:
        return 'relleno', None
    corregido = _sugerir_dominio(dominio)
    if corregido and corregido != dominio:
        return 'dedo', f'{local}@{corregido}'
    return None, None


def correo_limpio(texto):
    """El correo como se guarda (sin nombre visible, recortado y en minúsculas), o ``None`` si no está bien escrito."""
    codigo, _sugerencia = problema_del_correo(texto)
    if codigo:
        return None
    return _sin_nombre_visible(texto).lower()


# ---------------------------------------------------------------------------
# Celular
# ---------------------------------------------------------------------------

def _panama(nacional):
    """Los 8 números nacionales de Panamá: ``('pa', '60261919')`` o el problema. Siete números de un fijo («234-5678»)
    son ``'fijo'``: van en su propio campo."""
    if len(nacional) == 7 and FIJO_DE_PANAMA.fullmatch(nacional):
        return 'fijo', None
    if len(nacional) < 8:
        return 'corto', None
    if len(nacional) > 8:
        return 'largo', None
    return ('pa', nacional) if R.celular_valido(nacional) else ('invalido', None)


def _con_codigo_de_pais(digitos):
    """Lo que viene con «+» o «00»: Panamá (507 + 8 números) u otro país (de 9 a 15 números en total)."""
    if digitos.startswith(PANAMA):
        return _panama(digitos[len(PANAMA):])
    if len(digitos) < 9:
        return 'corto', None
    if len(digitos) > 15:
        return 'largo', None
    return 'intl', digitos


def _sin_codigo_de_pais(digitos):
    """Lo que viene sin «+»: 8 números de Panamá, o 507 delante; lo demás es de otro país sin su «+»."""
    if len(digitos) == 8:
        return _panama(digitos)
    if digitos.startswith(PANAMA) and len(digitos) in (10, 11, 12):
        return _panama(digitos[len(PANAMA):])
    if len(digitos) < 8:
        return _panama(digitos)
    if len(digitos) > 15:
        return 'largo', None
    if len(digitos) == 9 and R.celular_valido(digitos[:8]):
        return 'largo', None  # un número de Panamá con un número de más (o uno de otro país sin el «+»)
    return 'sin_mas', None


def _problema_de_forma(texto):
    """Lo que está mal en cualquier número antes de mirar sus cifras: ``'vacio'``, ``'varios'``, ``'letras'`` o
    ``None``."""
    if not texto:
        return 'vacio'
    if re.search(r'[/,;]', texto) or texto.count('+') > 1 or re.search(r'\d\s+(?:y|o)\s+\+?\d', texto, re.I):
        return 'varios'
    if re.search(r'[^0-9+\-().\s]', texto) or ('+' in texto and not texto.startswith('+')):
        return 'letras'
    return None


def _partes_del_telefono(texto):
    """``('pa', '60261919')``, ``('intl', '13055551234')`` o ``(código del problema, None)``."""
    texto = (texto or '').strip()
    if problema := _problema_de_forma(texto):
        return problema, None
    digitos = R.solo_digitos(texto)
    if texto.startswith('+'):
        return _con_codigo_de_pais(digitos)
    if digitos.startswith('00'):
        return _con_codigo_de_pais(digitos[2:])
    return _sin_codigo_de_pais(digitos)


def problema_del_telefono(texto):
    """El código del problema del número escrito, o ``None`` si está bien."""
    tipo, valor = _partes_del_telefono(texto)
    return None if valor else tipo


def telefono_para_guardar(texto):
    """«+507 6026-1919» (Panamá) o «+13055551234» (otro país); ``None`` si el número no está bien escrito."""
    tipo, valor = _partes_del_telefono(texto)
    if not valor:
        return None
    if tipo == 'pa':
        return f'+{PANAMA} {R.celular_fmt(valor)}'
    return f'+{valor}'


# ---------------------------------------------------------------------------
# Teléfono fijo (2026-10-22)
# ---------------------------------------------------------------------------

def _fijo_de_panama(nacional):
    """Los 7 números de un fijo de Panamá: ``('pa', '2345678')`` o el problema. Ocho números de un celular son
    ``'celular'``: van en «Celular»."""
    if len(nacional) == 7:
        return ('pa', nacional) if FIJO_DE_PANAMA.fullmatch(nacional) else ('invalido', None)
    if len(nacional) == 8 and R.celular_valido(nacional):
        return 'celular', None
    return ('corto', None) if len(nacional) < 7 else ('largo', None)


def _partes_del_fijo(texto):
    """``('pa', '2345678')``, ``('intl', '13055551234')`` o ``(código del problema, None)``."""
    texto = (texto or '').strip()
    if problema := _problema_de_forma(texto):
        return problema, None
    digitos = R.solo_digitos(texto)
    if texto.startswith('+') or digitos.startswith('00'):
        digitos = digitos if texto.startswith('+') else digitos[2:]
        if digitos.startswith(PANAMA):
            return _fijo_de_panama(digitos[len(PANAMA):])
        if len(digitos) < 9:
            return 'corto', None
        return ('largo', None) if len(digitos) > 15 else ('intl', digitos)
    if len(digitos) in (7, 8):
        return _fijo_de_panama(digitos)
    if digitos.startswith(PANAMA) and len(digitos) in (10, 11):
        return _fijo_de_panama(digitos[len(PANAMA):])
    if len(digitos) < 7:
        return 'corto', None
    return 'sin_mas', None


def problema_del_fijo(texto):
    """El código del problema del teléfono fijo escrito, o ``None`` si está bien."""
    tipo, valor = _partes_del_fijo(texto)
    return None if valor else tipo


def fijo_para_guardar(texto):
    """«+507 234-5678» (Panamá) o «+13055551234» (otro país); ``None`` si el número no está bien escrito."""
    tipo, valor = _partes_del_fijo(texto)
    if not valor:
        return None
    if tipo == 'pa':
        return f'+{PANAMA} {valor[:3]}-{valor[3:]}'
    return f'+{valor}'


# ---------------------------------------------------------------------------
# Mensajes para el equipo (y para quien se registra)
# ---------------------------------------------------------------------------

def mensaje_del_correo(env, valor, codigo, sugerencia=None, vuelve_a=None):
    """Qué está mal en el correo, en palabras sencillas. ``vuelve_a`` («confirmar», «publicarla»): para las puertas de
    la venta y la factura, que piden corregirlo en la ficha y volver a intentarlo."""
    valor = (valor or '').strip()
    if codigo == 'dedo' and sugerencia:
        if vuelve_a:
            return env._('El correo %(correo)s parece mal escrito. ¿Quisiste decir %(sugerencia)s? Corrígelo en la '
                         'ficha del cliente y vuelve a %(accion)s.', correo=valor, sugerencia=sugerencia,
                         accion=vuelve_a)
        return env._('El correo %(correo)s parece mal escrito. ¿Quisiste decir %(sugerencia)s? Corrígelo en la '
                     'ficha del cliente.', correo=valor, sugerencia=sugerencia)
    if codigo == 'relleno':
        texto = env._('%(correo)s no es un correo de verdad. Pídele su correo al cliente; si de verdad no tiene, borra '
                      'lo escrito y marca «Cliente no tiene correo electrónico».', correo=valor)
        return texto + ' ' + env._('Después vuelve a %s.', vuelve_a) if vuelve_a else texto
    if codigo == 'equipo':
        texto = env._("Ese correo es de D'CASA o de alguien del equipo: escribe el del cliente.")
    else:
        texto = env._('%(correo)s no es un correo completo. Debe verse así: nombre@gmail.com (una sola @, sin espacios '
                      'ni comas).', correo=valor)
        if sugerencia:
            texto += ' ' + env._('¿Quisiste decir %s?', sugerencia)
    return _y_vuelve_a(env, texto, vuelve_a)


def mensaje_del_telefono(env, valor, codigo, vuelve_a=None):
    """Qué está mal en el celular, en palabras sencillas."""
    valor = (valor or '').strip()
    if codigo == 'varios':
        if vuelve_a:
            return _y_vuelve_a(env, env._('En el celular %s hay más de un número: deja uno solo.', valor), vuelve_a)
        return env._('Escribe un solo número en este campo.')
    if codigo == 'fijo':
        texto = env._('%s tiene 7 números: es un teléfono fijo. Escríbelo en «Teléfono fijo»; el celular en Panamá '
                      'tiene 8 números, como 6123-4567.', valor)
        return _y_vuelve_a(env, texto, vuelve_a)
    texto = env._('El celular %s no está completo: en Panamá son 8 números, como 6123-4567. Si es de otro país, '
                  'escríbelo con + y el código del país (p. ej. +1 305 555 1234).', valor)
    return _y_vuelve_a(env, texto, vuelve_a)


def mensaje_del_fijo(env, valor, codigo, vuelve_a=None):
    """Qué está mal en el teléfono fijo, en palabras sencillas."""
    valor = (valor or '').strip()
    if codigo == 'varios':
        return _y_vuelve_a(env, env._('En el teléfono fijo %s hay más de un número: deja uno solo.', valor), vuelve_a)
    if codigo == 'celular':
        texto = env._('%s tiene 8 números: es un celular. Escríbelo en «Celular»; el teléfono fijo en Panamá tiene 7 '
                      'números, como 234-5678.', valor)
        return _y_vuelve_a(env, texto, vuelve_a)
    texto = env._('El teléfono fijo %s no está bien: en Panamá son 7 números, como 234-5678. Si es de otro país, '
                  'escríbelo con + y el código del país (p. ej. +1 305 555 1234).', valor)
    return _y_vuelve_a(env, texto, vuelve_a)


def _y_vuelve_a(env, texto, vuelve_a):
    if not vuelve_a:
        return texto
    return texto + ' ' + env._('Corrígelo en la ficha del cliente y vuelve a %s.', vuelve_a)
