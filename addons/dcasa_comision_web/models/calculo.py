"""Las cuentas de la comisión del sitio web, en funciones puras (sin base de datos) y en centavos enteros.

Aquí no hay ninguna cifra de fábrica: todo lo que se calcula llega de una versión de las reglas que escribió
Gerencia. Las pruebas usan números de prueba.

Los componentes de una venta (``c``), todos en centavos enteros y sin signo, de las líneas que vienen de pedidos online:

* ``productos``: lo vendido (las líneas de producto con precio mayor que cero), ya con el descuento de cada línea;
* ``descuento_lineas``: lo que se descontó en esas líneas (para poder calcular «antes de los descuentos»);
* ``descuento_negativas``: las líneas que restan (premio de Socios, cupón...) en positivo;
* ``envio``: el cobro de envío o flete;
* ``itbms``: el ITBMS de la parte online;
* ``devuelto``: lo que las notas de crédito devolvieron de lo vendido (sin el envío ni el ITBMS);
* ``devuelto_envio``: lo que las notas devolvieron del cobro de envío (solo resta cuando el envío cuenta);
* ``devuelto_itbms``: el ITBMS de lo que devolvieron las notas;
* ``pasarela``: lo que cobró la pasarela de pago, si el pago lo guardó.
"""
import math
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Context, Decimal

COMPONENTES = ('productos', 'descuento_lineas', 'descuento_negativas', 'envio', 'itbms', 'devuelto',
               'devuelto_envio', 'devuelto_itbms', 'pasarela')

# Los interruptores de la base y sus dos posiciones (la primera es la recomendada de fábrica).
OPCIONES = {
    'base_itbms': ('sin', 'con'),
    'base_envio': ('sin', 'con'),
    'base_descuentos': ('despues', 'antes'),
    'base_devoluciones': ('resta', 'no_resta'),
    'base_pasarela': ('no_resta', 'resta'),
}


# Aguanta cualquier ``float`` finito (hasta 1e308): con la precisión normal (28 dígitos) un 1e30 daba un error.
_PRECISION_AMPLIA = Context(prec=400)


def numero_finito(valor):
    """El ``float`` de ``valor`` (un número o un texto con un número) si es un número FINITO; si no, ``None``.

    Una llamada RPC manda lo que quiera: ``nan``, ``inf``, un texto cualquiera, un entero de 30 cifras. Sin esto, cada
    uno acababa en un error de Python sin traducir (``ValueError``, ``OverflowError``, ``InvalidOperation``). Vacío
    (``None``, ``False``, ``''``) es cero, como lo entiende Odoo; un ``bool`` y cualquier otra cosa no son un número."""
    if valor is None or valor is False or valor == '':
        return 0.0
    if isinstance(valor, bool) or not isinstance(valor, (int, float, Decimal, str)):
        return None
    try:
        numero = float(valor)
    except (ValueError, OverflowError, ArithmeticError):
        return None
    return numero if math.isfinite(numero) else None


def a_centavos(monto):
    """Un importe de Odoo (float con 2 decimales) a centavos enteros sin error de coma flotante. Un número que no es
    finito (``nan``, ``inf``) da ``ValueError``: quien recibe cifras de afuera las valida antes (``numero_finito``)."""
    numero = float(monto or 0.0)
    if not math.isfinite(numero):
        raise ValueError('no es un número finito')
    return int((Decimal(str(round(numero, 2))) * 100).quantize(
        Decimal(1), rounding=ROUND_HALF_UP, context=_PRECISION_AMPLIA))


def a_precio_de_lista(c, opciones, centavos):
    """Lleva a precio de lista (en la misma proporción lista/cobrado) un monto que viene a precio cobrado: lo devuelto
    y el ITBMS, cuando el interruptor de descuentos está en «antes». Con «después» no cambia nada."""
    if opciones['base_descuentos'] != 'antes':
        return centavos
    cobrado = c['productos'] - c['descuento_negativas']
    lista = c['productos'] + c['descuento_lineas']
    if cobrado > 0 and lista > cobrado:
        return int((Decimal(centavos) * Decimal(lista) / Decimal(cobrado)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return centavos


def devuelto_en_la_base(c, opciones):
    """Lo que se resta por devoluciones (centavos), **en la misma base de la venta**. Las notas de crédito vienen a
    precio cobrado; con «Antes de los descuentos» la base es el precio de lista, así que lo devuelto se lleva a precio
    de lista en la misma proporción (devolver todo deja la base en cero y devolver la mitad, en la mitad)."""
    if opciones['base_devoluciones'] != 'resta':
        return 0
    devuelto = a_precio_de_lista(c, opciones, c['devuelto'])
    if opciones['base_envio'] == 'con':
        devuelto += c.get('devuelto_envio', 0)          # devolver el envío solo resta si el envío cuenta
    if opciones['base_itbms'] == 'con':
        devuelto += a_precio_de_lista(c, opciones, c['devuelto_itbms'])
    return devuelto


def base_de_la_venta(c, opciones):
    """La base (centavos) sobre la que se calcula el porcentaje, según los interruptores de ``opciones``. Nunca es
    negativa. Cada interruptor es «antes o después» de una cosa:

    * ITBMS: ``sin`` (recomendado) no lo suma; ``con`` suma el ITBMS de la venta;
    * envío: ``sin`` (recomendado) no lo suma; ``con`` suma el cobro de envío;
    * descuentos: ``despues`` (recomendado) usa el precio que de verdad se cobró (con el descuento de cada línea y con
      los premios y cupones ya restados); ``antes`` usa el precio de lista (sin ninguno de los dos);
    * devoluciones: ``resta`` (recomendado) quita lo que el cliente devuelve (en la misma base: ver
      ``devuelto_en_la_base``); ``no_resta`` lo deja;
    * pasarela: ``no_resta`` (recomendado) deja lo que cobra la pasarela; ``resta`` lo quita.
    """
    base = c['productos']
    if opciones['base_descuentos'] == 'antes':
        base += c['descuento_lineas']
    else:
        base -= c['descuento_negativas']
    if opciones['base_envio'] == 'con':
        base += c['envio']
    if opciones['base_itbms'] == 'con':
        base += a_precio_de_lista(c, opciones, c['itbms'])      # con «antes», el ITBMS del precio de lista
    base -= devuelto_en_la_base(c, opciones)
    if opciones['base_pasarela'] == 'resta':
        base -= c['pasarela']
    return max(base, 0)


def porcentaje_de(centavos, porcentaje):
    """``centavos × porcentaje ÷ 100`` redondeado a centavo, mitad hacia arriba (como la planilla)."""
    return int((Decimal(centavos) * Decimal(str(porcentaje)) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def repartir(total, partes):
    """``{id: centavos}``: reparte ``total`` (centavos, sin signo) entre ``partes`` ([(id, porcentaje)], en el orden que
    llegan) según su porcentaje. Los centavos que sobran van, de uno en uno y siempre en el mismo orden, a las primeras
    personas: la suma de las partes es SIEMPRE el total, ni un centavo más ni uno menos."""
    if not partes:
        return {}
    reparto = {clave: int((Decimal(total) * Decimal(str(pct)) / 100).to_integral_value(rounding=ROUND_FLOOR))
               for clave, pct in partes}
    sobran = total - sum(reparto.values())
    for clave, _pct in partes:
        if sobran <= 0:
            break
        reparto[clave] += 1
        sobran -= 1
    return reparto


def suma_cien(porcentajes):
    """¿Suman exactamente 100 (a dos decimales)?"""
    return sum(Decimal(str(round(float(p), 2))) for p in porcentajes) == Decimal(100)
