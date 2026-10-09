"""Celulares de los canales: funciones PURAS que dicen de quién es un número.

El celular es la llave del cliente (``docs/SOCIOS.md``): un celular, una ficha. En WhatsApp el id
externo ES el celular (E.164 sin «+», p. ej. ``50760261919``). Reusa las reglas de Socios
(``dcasa_socios.models.reglas``) para los números de Panamá, pero con un cuidado: ``celular_normal``
de Socios se queda con los últimos 8 dígitos de cualquier número, y un número de otro país se
confundiría con uno de Panamá. Aquí solo se normaliza como de Panamá lo que de verdad lo es.
"""
from odoo.addons.dcasa_socios.models import reglas as R

PREFIJO_PANAMA = '507'


def interpretar(texto):
    """Qué número es: ``('pa', '60261919')``, ``('intl', '13055551234')`` o ``(None, '')``.

    * Panamá: 8 dígitos que parecen un celular o teléfono de Panamá, con o sin el prefijo 507.
    * Otro país: 9 a 15 dígitos (E.164) que no son de Panamá; se guardan completos.
    * Cualquier otra cosa (letras, muy corto, muy largo): ``(None, '')``.
    """
    digitos = R.solo_digitos(texto)
    if len(digitos) == 11 and digitos.startswith(PREFIJO_PANAMA):
        nacional = digitos[3:]
        if R.celular_valido(nacional):
            return 'pa', nacional
    if len(digitos) == 8 and R.celular_valido(digitos):
        return 'pa', digitos
    if 9 <= len(digitos) <= 15:
        return 'intl', digitos
    return None, ''


def mismo_numero(a, b):
    """¿Son el mismo celular? Compara lo que cada uno es de verdad (Panamá con Panamá, etc.)."""
    tipo_a, valor_a = interpretar(a)
    tipo_b, valor_b = interpretar(b)
    return bool(tipo_a) and (tipo_a, valor_a) == (tipo_b, valor_b)


def para_mostrar(tipo, valor):
    """('pa', '60261919') → «+507 6026-1919» · ('intl', '13055551234') → «+13055551234»."""
    if tipo == 'pa':
        return f'+{PREFIJO_PANAMA} {R.celular_fmt(valor)}'
    return f'+{valor}' if valor else ''
