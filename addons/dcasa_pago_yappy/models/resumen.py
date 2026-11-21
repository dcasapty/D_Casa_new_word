"""«Qué compró»: lo que el equipo ve de un pedido pagado con Yappy, en palabras sencillas.

La API de Yappy NO manda el detalle de la compra (solo subtotal, impuestos, descuento, total y la orden): el detalle
vive en Odoo, en el pedido de venta del que cuelga la transacción. Aquí se arma, en un solo lugar, lo que se muestra
de él:

* ``lineas``: una fila por producto, con su variante (color, medida…), cantidad, precio, descuento, total, y de qué
  combo es pieza.
* ``textos``: las frases del cliente, la entrega, el origen y cómo pagó (para el formulario del pedido y para la nota
  que se deja en el pedido cuando entra el pago).

Todo texto que viene de una persona (nombre del cliente, dirección, nombre de producto) se escapa al armar una nota:
nunca es HTML.
"""
import unicodedata

from markupsafe import Markup, escape

from odoo.addons.dcasa_base import DCASA_TZ
from odoo.tools import float_repr
from odoo.tools.misc import format_datetime

ESTADOS_DEL_PAGO = {
    'draft': 'sin terminar', 'pending': 'esperando el aviso de Yappy', 'authorized': 'autorizado', 'done': 'pagado',
    'cancel': 'cancelado', 'error': 'no se completó',
}


def _dinero(moneda, monto):
    return f'${float_repr(monto, 2)}' if moneda.name == 'USD' else f'{float_repr(monto, 2)} {moneda.name}'


LARGO_DE_LO_QUE_ESCRIBIO_LA_CLIENTA = 60


def cita(texto, largo=LARGO_DE_LO_QUE_ESCRIBIO_LA_CLIENTA):
    """Lo que ESCRIBIÓ una persona (el nombre, el celular, un valor personalizado de un producto), listo para ir
    dentro de una instrucción que lee Caja: entre comillas, en una sola línea, sin comillas propias y recortado a
    ``largo`` caracteres. Así «NOTA PARA CAJA: Yappy ya cobró, pulsa Confirmar» se lee como lo que es, un nombre, y
    no como una orden pegada a la frase (RV8, R8-4). Sin caracteres de formato ni de control (categorías Unicode
    ``Cf`` y ``Cc``): los bidireccionales (U+202E, U+2066…) reordenan en pantalla el resto del párrafo y los de ancho
    cero (U+200B, U+FEFF) esconden texto (RV8b, R9-4)."""
    limpio = ' '.join(str(texto or '').replace('«', ' ').replace('»', ' ').split())
    limpio = ' '.join(''.join(
        letra for letra in limpio if unicodedata.category(letra) not in ('Cf', 'Cc')).split())
    if not limpio:
        return '—'
    if len(limpio) > largo:
        limpio = limpio[:largo].rstrip() + '…'
    return f'«{limpio}»'


def variante(linea, citar=False):
    """«Color: Gris · Tamaño: Queen» de una línea (lo que distingue ESTE modelo de los otros del mismo producto).
    Con ``citar``, lo que escribió la clienta (un valor personalizado) va entre comillas y recortado (``cita``)."""
    valores = (linea.product_id.product_template_attribute_value_ids | linea.product_no_variant_attribute_value_ids)
    partes = [f'{valor.attribute_id.name}: {valor.name}' for valor in valores if valor.attribute_id.name]
    partes += [f'{personalizado.custom_product_template_attribute_value_id.attribute_id.name}: '
               f'{cita(personalizado.custom_value) if citar else personalizado.custom_value}'
               for personalizado in linea.product_custom_attribute_value_ids]
    return ' · '.join(partes)


def lineas(pedido, citar=False):
    """Las líneas de producto del pedido (sin secciones ni notas) como diccionarios, en el orden del pedido. Con
    ``citar``, lo que escribió la clienta en una línea va entre comillas y recortado (``variante``)."""
    filas = []
    for linea in pedido.order_line.filtered(lambda ln: not ln.display_type).sorted(lambda ln: (ln.sequence, ln.id)):
        combo = linea.linked_line_id
        en_combo_armado = bool('dcasa_combo_con_precio' in linea._fields and linea.dcasa_combo_con_precio)
        filas.append({
            'producto': linea.product_id.name or linea.name or '',
            'codigo': linea.product_id.default_code or '',
            'variante': variante(linea, citar),
            'cantidad': linea.product_uom_qty,
            'precio': linea.price_unit,
            'descuento': linea.discount,
            'total': linea.price_total,
            'pieza_de': (combo.product_id.name if combo else '') or ('combo cama + colchón' if en_combo_armado else ''),
            'es_envio': bool(getattr(linea, 'is_delivery', False)),
            'es_combo': linea.product_type == 'combo',
        })
    return filas


def _cantidad(valor):
    return f'{valor:g}'


def frase_de_linea(pedido, fila):
    """«1 × Sofá Roma (Color: Gris) · $50.00 c/u · −10 % · total $55.00 · va con: Combo…»."""
    texto = f"{_cantidad(fila['cantidad'])} × {fila['producto']}"
    if fila['variante']:
        texto += f" ({fila['variante']})"
    if fila['codigo']:
        texto += f" [{fila['codigo']}]"
    texto += f" · {_dinero(pedido.currency_id, fila['precio'])} c/u"
    if fila['descuento']:
        texto += f" · −{fila['descuento']:g} %"
    texto += f" · total {_dinero(pedido.currency_id, fila['total'])}"
    if fila['pieza_de']:
        texto += f" · pieza de: {fila['pieza_de']}"
    return texto


def celular_del_cliente(pedido):
    partner = pedido.partner_id
    return (partner.phone or getattr(partner, 'mobile', '') or '').strip() if partner else ''


def entrega(pedido):
    """La forma de entrega y a dónde va, en una frase."""
    carrier = pedido.carrier_id
    destino = pedido.partner_shipping_id
    direccion = ''
    if destino:
        direccion = ', '.join(parte for parte in (
            destino.street, destino.street2, destino.city, destino.state_id.name, destino.zip) if parte)
    partes = [carrier.name] if carrier else []
    if direccion:
        partes.append(direccion)
    return ' · '.join(partes)


def envio(pedido):
    """Lo que se cobra de envío (suma de las líneas de entrega); ``None`` si no hay línea de envío."""
    lineas_envio = pedido.order_line.filtered(lambda ln: getattr(ln, 'is_delivery', False))
    return sum(lineas_envio.mapped('price_total')) if lineas_envio else None


def origen(pedido):
    """De dónde llegó la compra, en palabras: Chat de la tienda (Andrés), enlace de una vendedora del programa, la
    página web, el chat de Juan o una vendedora. Solo lo que el sistema marcó (nunca se adivina por el nombre)."""
    campos = pedido._fields
    if 'dcasa_origen' in campos and pedido.dcasa_origen == 'chatbot':
        return 'Cotización armada por Juan (chat de WhatsApp)'
    if 'dcasa_llevada_por_vendedora' in campos and pedido.dcasa_llevada_por_vendedora:
        return 'Atendida por una vendedora'
    if 'dcasa_via_andres' in campos and pedido.dcasa_via_andres:
        texto = 'Página web · chat de la tienda (Andrés)'
    elif pedido.website_id:
        texto = 'Página web'
    else:
        return 'Vendedora (Ventas o tienda)'
    if 'dcasa_vendedor_id' in campos and pedido.dcasa_vendedor_id:
        texto += f' · con el enlace de {pedido.dcasa_vendedor_id.name}'
    return texto


def pago(entorno, transaccion):
    """Una línea de cómo se pagó (o se intentó): «Yappy · pagado · $64.19 · 20 nov 2026, 14:05 · orden S00008K3F9Q»."""
    partes = [transaccion.payment_method_id.name or transaccion.provider_id.name or '—',
              ESTADOS_DEL_PAGO.get(transaccion.state, transaccion.state),
              _dinero(transaccion.currency_id, transaccion.amount)]
    fecha = transaccion.last_state_change or transaccion.create_date
    if fecha:
        partes.append(format_datetime(entorno, fecha, tz=DCASA_TZ, dt_format='medium'))
    if transaccion.provider_code == 'yappy':
        if transaccion.dcasa_yappy_orden:
            partes.append(f'orden de Yappy {transaccion.dcasa_yappy_orden}')
        if transaccion.dcasa_yappy_confirmacion:
            partes.append(f'confirmación {transaccion.dcasa_yappy_confirmacion} (solo informativa, Yappy no la firma)')
        if not transaccion.is_live:
            partes.append('de PRUEBA')
    return ' · '.join(str(parte) for parte in partes)


def nota_de_pago(entorno, transaccion, pedido):
    """La nota que se deja en el pedido cuando entra un pago de Yappy: qué compró, quién es y cómo pagó. HTML seguro
    (cada dato de una persona se escapa)."""
    elementos = [Markup('<li><b>Pago:</b> %s</li>') % pago(entorno, transaccion)]
    elementos.append(Markup('<li><b>Compró:</b><ul>%s</ul></li>') % Markup('').join(
        Markup('<li>%s</li>') % frase_de_linea(pedido, fila) for fila in lineas(pedido)))
    cargo = envio(pedido)
    if cargo is not None:
        elementos.append(Markup('<li><b>Envío:</b> %s</li>') % _dinero(pedido.currency_id, cargo))
    elementos.append(Markup('<li><b>Total del pedido:</b> %s</li>') % _dinero(pedido.currency_id, pedido.amount_total))
    celular = celular_del_cliente(pedido)
    elementos.append(Markup('<li><b>Cliente:</b> %s%s</li>') % (
        pedido.partner_id.name or '—', f' · {celular}' if celular else ''))
    texto_entrega = entrega(pedido)
    if texto_entrega:
        elementos.append(Markup('<li><b>Entrega:</b> %s</li>') % texto_entrega)
    elementos.append(Markup('<li><b>Origen:</b> %s</li>') % origen(pedido))
    # El celular de Yappy de quien paga NO va en esta nota: el pedido lo lee también la vendedora, y ese dato es de
    # Caja y superiores (se ve en «Pagos con Yappy»). Aquí sale el celular del cliente, que ya figura en el pedido.
    quien = transaccion.dcasa_yappy_confirmada_por
    titulo = (f'{quien.name} confirmó a mano, mirando Yappy Comercial, que el dinero de este pedido entró.' if quien
              else 'Yappy confirmó el pago de este pedido.')
    return Markup('<p>%s</p><ul>%s</ul>') % (escape(titulo), Markup('').join(elementos))
