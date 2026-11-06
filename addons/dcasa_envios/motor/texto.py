"""Números y dinero escritos exactamente como los escribe el navegador (el HTML de la propuesta).

El precio de un envío no puede salir distinto en la pantalla, en Brian o en la web por un redondeo: estas funciones
copian las reglas de JavaScript que usaba el HTML.

* ``js_round`` = ``Math.round`` (al entero más cercano; un medio exacto va hacia arriba). El ``round`` de Python
  redondea los medios al par (``round(2.5) == 2``): no sirve.
* ``to_fixed`` = ``Number.prototype.toFixed`` (sobre el valor exacto del número, un medio exacto se aleja del cero).
* ``numero_js`` = cómo JavaScript convierte un número en texto (``15`` y no ``15.0``).
* ``entero_pa`` y ``km_txt`` = ``toLocaleString('es-PA')``: miles con coma y decimales con punto.
"""
import math
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import quote


def js_round(valor):
    """``Math.round`` de JavaScript para números finitos (los precios nunca son negativos)."""
    valor = float(valor)
    if not math.isfinite(valor):
        return valor
    piso = math.floor(valor)
    return float(piso + 1) if valor - piso >= 0.5 else float(piso)


def js_ceil(valor):
    """``Math.ceil`` de JavaScript (devuelve un número de punto flotante, como en JavaScript)."""
    return float(math.ceil(float(valor)))


def centavos(valor):
    """``Math.round(v * 100) / 100``: lo que el HTML hacía con cada monto."""
    return js_round(float(valor) * 100) / 100


def to_fixed(valor, decimales):
    """``valor.toFixed(decimales)`` (``-0`` se escribe sin signo, como en JavaScript)."""
    valor = float(valor) or 0.0
    exacto = Decimal(valor).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)
    return format(exacto, 'f')


def numero_js(valor):
    """``String(valor)`` de JavaScript: ``15`` → «15», ``7.5`` → «7.5», ``-10`` → «-10»."""
    valor = float(valor)
    if valor == 0:
        return '0'
    if valor.is_integer() and abs(valor) < 1e21:
        return str(int(valor))
    return repr(valor)


def entero_pa(valor):
    """Un entero con los miles separados por coma, como ``toLocaleString('es-PA')``: 11299 → «11,299»."""
    return f'{int(valor):,}'


def dinero(valor):
    """El precio como lo escribía el HTML: «$20» si es entero (o casi) y «$20.50» si tiene centavos."""
    valor = float(valor)
    redondo = js_round(valor)
    if abs(valor - redondo) < 0.005:
        return '$' + entero_pa(redondo)
    return '$' + to_fixed(valor, 2)


def km_txt(valor):
    """Kilómetros con un decimal como máximo: 34.1 → «34.1», 7.0 → «7», 1234.5 → «1,234.5»."""
    redondo = js_round(float(valor) * 10) / 10
    texto = f'{redondo:,.1f}'
    return texto[:-2] if texto.endswith('.0') else texto


def encode_uri_component(texto):
    """``encodeURIComponent`` de JavaScript."""
    return quote(str(texto), safe="-_.!~*'()")
