"""Las cuentas de la comisión del sitio web, en funciones puras (sin base de datos) y en centavos enteros.

Aquí no hay ninguna cifra de fábrica: todo lo que se calcula llega de una versión de las reglas que escribió
Gerencia. Las pruebas usan números de prueba.

Los componentes de una venta (``c``), todos en centavos enteros y sin signo, de las líneas que vienen de pedidos online:

* ``productos``: lo vendido (las líneas de producto con precio mayor que cero), ya con el descuento de cada línea;
* ``descuento_lineas``: lo que se descontó en esas líneas (para poder calcular «antes de los descuentos»);
* ``descuento_negativas``: las líneas que restan (premio de Socios, cupón...) en positivo;
* ``envio``: el cobro de envío o flete;
* ``itbms``: el ITBMS de la parte online;
* ``devuelto`` y ``devuelto_itbms``: lo que las notas de crédito devolvieron, sin y con su ITBMS;
* ``pasarela``: lo que cobró la pasarela de pago, si el pago lo guardó.
"""
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

COMPONENTES = ('productos', 'descuento_lineas', 'descuento_negativas', 'envio', 'itbms', 'devuelto',
               'devuelto_itbms', 'pasarela')

# Los interruptores de la base y sus dos posiciones (la primera es la recomendada de fábrica).
OPCIONES = {
    'base_itbms': ('sin', 'con'),
    'base_envio': ('sin', 'con'),
    'base_descuentos': ('despues', 'antes'),
    'base_devoluciones': ('resta', 'no_resta'),
    'base_pasarela': ('no_resta', 'resta'),
}


def a_centavos(monto):
    """Un importe de Odoo (float con 2 decimales) a centavos enteros sin error de coma flotante."""
    return int((Decimal(str(round(float(monto or 0.0), 2))) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def base_de_la_venta(c, opciones):
    """La base (centavos) sobre la que se calcula el porcentaje, según los interruptores de ``opciones``. Nunca es
    negativa. Cada interruptor es «antes o después» de una cosa:

    * ITBMS: ``sin`` (recomendado) no lo suma; ``con`` suma el ITBMS de la venta;
    * envío: ``sin`` (recomendado) no lo suma; ``con`` suma el cobro de envío;
    * descuentos: ``despues`` (recomendado) usa el precio que de verdad se cobró (con el descuento de cada línea y con
      los premios y cupones ya restados); ``antes`` usa el precio de lista (sin ninguno de los dos);
    * devoluciones: ``resta`` (recomendado) quita lo que el cliente devuelve; ``no_resta`` lo deja;
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
        base += c['itbms']
    if opciones['base_devoluciones'] == 'resta':
        base -= c['devuelto']
        if opciones['base_itbms'] == 'con':
            base -= c['devuelto_itbms']
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
