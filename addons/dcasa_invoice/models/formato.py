"""Cómo se escriben las cosas en un documento de D'CASA (funciones puras, sin base).

- Montos en letras en español de Panamá: «Trescientos Cincuenta y Tres Dólares con 09/100».
- Cédula o RUC según la forma del número.
- Teléfonos de Panamá con guion: 6123-4567.
- Si una URL es local (localhost, 127.0.0.1, IP privada): no se imprime en un papel.
"""

import ipaddress
import re
from urllib.parse import urlsplit

_UNIDADES = ['', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve']
_DIEZ_A_VEINTINUEVE = [
    'diez', 'once', 'doce', 'trece', 'catorce', 'quince', 'dieciséis', 'diecisiete', 'dieciocho', 'diecinueve',
    'veinte', 'veintiuno', 'veintidós', 'veintitrés', 'veinticuatro', 'veinticinco', 'veintiséis', 'veintisiete',
    'veintiocho', 'veintinueve',
]
_DECENAS = ['', '', '', 'treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa']
_CENTENAS = ['', 'ciento', 'doscientos', 'trescientos', 'cuatrocientos', 'quinientos', 'seiscientos',
             'setecientos', 'ochocientos', 'novecientos']
_MINUSCULAS = {'y', 'de', 'con'}

# Nombre de la moneda en una factura panameña (singular, plural).
MONEDAS = {'USD': ('Dólar', 'Dólares'), 'PAB': ('Balboa', 'Balboas')}


def _menor_que_mil(n):
    if n == 100:
        return 'cien'
    centenas, resto = divmod(n, 100)
    partes = [_CENTENAS[centenas]] if centenas else []
    if 10 <= resto < 30:
        partes.append(_DIEZ_A_VEINTINUEVE[resto - 10])
    elif resto >= 30:
        decenas, unidades = divmod(resto, 10)
        partes.append(_DECENAS[decenas] + (f' y {_UNIDADES[unidades]}' if unidades else ''))
    elif resto:
        partes.append(_UNIDADES[resto])
    return ' '.join(partes)


def _apocopar(palabras):
    """«uno» delante de un sustantivo se acorta: veintiún mil, un millón, treinta y un dólares."""
    if palabras.endswith('veintiuno'):
        return palabras[:-len('veintiuno')] + 'veintiún'
    if palabras.endswith('uno'):
        return palabras[:-1]
    return palabras


def numero_en_letras(n):
    """Entero no negativo en letras, en minúsculas (hasta 999 999 999 999)."""
    if not isinstance(n, int) or n < 0:
        raise ValueError('Solo enteros no negativos.')
    if n == 0:
        return 'cero'
    millones, resto = divmod(n, 1_000_000)
    miles, unidades = divmod(resto, 1000)
    partes = []
    if millones:
        partes.append('un millón' if millones == 1 else f'{_apocopar(numero_en_letras(millones))} millones')
    if miles:
        partes.append('mil' if miles == 1 else f'{_apocopar(_menor_que_mil(miles))} mil')
    if unidades:
        partes.append(_menor_que_mil(unidades))
    return ' '.join(partes)


def _titulo(texto):
    return ' '.join(p if p in _MINUSCULAS else p[:1].upper() + p[1:] for p in texto.split(' '))


def monto_en_letras(monto, singular='Dólar', plural='Dólares'):
    """«Mil Setenta Dólares con 50/100»: los centavos en cifra, como en un cheque."""
    centavos_totales = int(round(round(abs(float(monto)), 2) * 100))
    entero, centavos = divmod(centavos_totales, 100)
    letras = _apocopar(numero_en_letras(entero))
    if entero and entero % 1_000_000 == 0:
        letras += ' de'  # un millón de dólares
    moneda = singular if entero == 1 else plural
    return f'{_titulo(letras)} {moneda} con {centavos:02d}/100'


# Cédula panameña: provincia (1-13), o E / N / PE, con AV o PI opcionales: 2-723-510, 8-888-8888, PE-9-123.
_CEDULA = re.compile(r'^(?:PE|E|N|1[0-3]|[1-9])(?:AV|PI)?-\d{1,4}-\d{1,6}$', re.IGNORECASE)


def es_cedula(numero):
    return bool(_CEDULA.match((numero or '').strip()))


def etiqueta_identificacion(numero, dv=None, es_empresa=False):
    """«Cédula» para una persona sin DV; «RUC» para empresas o cuando lleva DV."""
    if not es_empresa and not dv and es_cedula(numero):
        return 'Cédula'
    return 'RUC'


def telefono_fmt(telefono):
    """'+507 61234567' → '6123-4567'. Lo que no es un número de Panamá se deja tal cual."""
    digitos = re.sub(r'\D', '', telefono or '')
    if len(digitos) == 11 and digitos.startswith('507'):
        digitos = digitos[3:]
    if len(digitos) == 8:
        return f'{digitos[:4]}-{digitos[4:]}'
    if len(digitos) == 7:
        return f'{digitos[:3]}-{digitos[3:]}'
    return (telefono or '').strip()


def url_es_local(url):
    """True si la URL no sirve fuera del servidor (localhost, 127.x, IP privada, sin dominio)."""
    host = (urlsplit(url or '').hostname or '').lower()
    if not host or host == 'localhost' or host.endswith('.localhost') or host.endswith('.local') or '.' not in host:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified


def url_con_esquema(url):
    url = (url or '').strip().rstrip('/')
    if url and '://' not in url:
        url = f'https://{url}'
    return url
