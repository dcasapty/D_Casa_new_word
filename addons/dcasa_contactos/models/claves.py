"""Las «llaves» con que se reconoce a una persona: celular, correo y RUC o cédula, ya normalizados.

Funciones PURAS (sin base de datos): dos escrituras distintas de lo mismo dan la MISMA llave. Si la llave está vacía,
ese dato no identifica a nadie (un correo mal escrito, un «N/A» en el RUC) y no cuenta para detectar duplicados.
"""
import re

from odoo.addons.dcasa_socios.models import reglas as R
from odoo.tools import email_normalize

# Separadores que se escriben distinto en un RUC o una cédula (espacio, raya larga, punto, barra, guion bajo).
_SEPARADORES = re.compile(r'[\s–—−_./]+')
MINIMO_RUC = 5  # caracteres que identifican: «N/A», «0» o «-» no son un RUC


def llave_telefono(texto):
    """``'pa:60261919'`` (Panamá, con o sin +507 / 00507), ``'intl:13055551234'`` (otro país, completo) o ``None``.

    Un número de otro país NUNCA se recorta a sus últimos 8 dígitos: así no se confunde con uno de Panamá.
    """
    digitos = R.solo_digitos(texto)
    if digitos.startswith('00'):
        digitos = digitos[2:]
    if len(digitos) == 11 and digitos.startswith('507') and R.celular_valido(digitos[3:]):
        return f'pa:{digitos[3:]}'
    if len(digitos) == 8 and R.celular_valido(digitos):
        return f'pa:{digitos}'
    if 9 <= len(digitos) <= 15:
        return f'intl:{digitos}'
    return None


def llave_correo(texto):
    """El correo en minúsculas y sin el nombre («Ana <ANA@x.com>» → ``ana@x.com``) o ``None`` si no es un correo."""
    return email_normalize(texto or '', strict=False) or None


def llave_vat(texto):
    """RUC o cédula en mayúsculas con los separadores unificados («8 123 456», «8.123.456» y «8-123-456» son lo mismo).

    Se conservan los guiones: «8-123-456» y «8-12-3456» son cédulas distintas aunque tengan los mismos dígitos.
    """
    valor = _SEPARADORES.sub('-', (texto or '').strip().upper())
    valor = re.sub(r'-{2,}', '-', valor).strip('-')
    if len(re.sub(r'[^0-9A-Z]', '', valor)) < MINIMO_RUC:
        return None
    return valor


def telefono_legible(llave):
    """``'pa:60261919'`` → «6026-1919» · ``'intl:13055551234'`` → «+13055551234»."""
    tipo, _, valor = (llave or '').partition(':')
    if tipo == 'pa':
        return R.celular_fmt(valor)
    return f'+{valor}' if valor else ''
