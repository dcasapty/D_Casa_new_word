"""Panel de Bodega: las entregas pendientes, abrir una (también con el QR de su nota), marcar lo que sale y validarla.

Pedido de la dueña (2026-10-22): «un solo panel que muestre las entregas pendientes por despachar o retirar, que en
bodega puedan abrir muy fácilmente las órdenes de entrega, muy bien optimizado para una tablet, que los trabajadores
abran la orden y fácilmente puedan validar la entrega, que funcione con el QR de la nota de entrega».

Lo que la pantalla «Bodega» (acción de cliente OWL, ``static/src/js/bodega.js``) le pide al servidor:

* ``pendientes()``: las salidas a clientes que no están hechas ni canceladas, con lo que va en cada tarjeta.
* ``abrir(entrega_id)``: la entrega para marcar lo que sale (cliente, teléfono, dirección, pedido, productos).
* ``leer(codigo, entrega_id)``: lo que escribió el lector (o leyó la cámara): el QR de una nota de entrega (o de la
  factura o del pedido: sus entregas pendientes), el número de una entrega o de un pedido, o el código de un producto.
* ``validar(entrega_id, marcas, parcial)``: entrega lo marcado. Si falta algo y no se confirmó, no toca nada y dice
  qué falta; confirmado, Odoo deja lo que falta en una entrega pendiente (la de siempre de Odoo).

Solo pedidos con pago o abono (decisión de la dueña, 2026-10-22: «solo pueden ver el pedido si pagaron o abonaron»):
la lista muestra y el panel abre y valida solo las entregas cuyo pedido tiene al menos un pago de verdad (un cobro
conciliado con su factura, sin contar notas de crédito) o una transacción de pago confirmada o autorizada de la tienda
web. Las demás no salen; si alguien escanea su QR, el panel dice «Este pedido todavía no tiene pago ni abono: no se
entrega». Una entrega que no viene de un pedido de venta tampoco se despacha aquí (no hay pago que mirar). El crédito
autorizado por Gerencia no está registrado en el sistema (docs/DECISIONES_CONTABLES.md, A3): no se adivina.

Envío o retiro: lo dice el método de entrega del pedido (``delivery.carrier``; el que tiene marcado «Es retiro en la
tienda» es retiro, cualquier otro es envío) o, sin método, una línea de flete en el pedido (envío). Si no hay ninguna de
las dos cosas no se adivina: sale «Sin definir».

Permisos (en el servidor, antes de leer o escribir): ser usuario de Inventario (``stock.group_stock_user``: quien puede
validar entregas en Odoo; la Vendedora lo es). Validar corre con los permisos de la persona (sin ``sudo``), así que Odoo
registra quién validó como siempre. El único ``sudo`` lee del pedido su número, su método de entrega, si lleva flete y
si está pagado (sí o no, sin montos), igual que la nota de entrega impresa lee el número de la factura.
"""
import math

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.addons.dcasa_invoice.models import lineas
from odoo.addons.dcasa_invoice.models.documento import leer_url, leer_url_tolerante
from odoo.addons.dcasa_invoice.models.documento_abrir import OK
from odoo.addons.dcasa_invoice.models.entrega_facil import texto_cantidad, texto_unidad
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext

from .barras import limpiar_codigo

ZONA = 'America/Panama'
ESTADOS_PENDIENTES = ('confirmed', 'waiting', 'assigned')
LIMITE_LISTA = 300           # más entregas pendientes que esto no caben en una pantalla: salen las más antiguas
PRODUCTOS_EN_TARJETA = 3
MAXIMO_LINEAS = 200          # una entrega con más renglones no es de una tienda de muebles: se rechaza el envío
COMO = {
    'envio': 'Envío a domicilio',
    'retiro': 'Retira en la tienda',
    'sin_definir': 'Sin definir: envío o retiro',
}
ESTADO = {
    'lista': 'Lista para salir',
    'parcial': 'Falta una parte',
    'esperando': 'Esperando producto',
}
PAGO = {
    'pagada': 'Pagada',
    'abono': 'Con abono: falta una parte',
}
CON_PAGO = tuple(PAGO)
LIMITE_BUSQUEDA = 2000       # pendientes que se revisan para saber cuáles tienen pago (una tienda tiene decenas)


def dominio_pendientes():
    """Salidas a clientes que no están hechas ni canceladas (ni en borrador: esas todavía no se confirmaron)."""
    return [('picking_type_code', '=', 'outgoing'), ('state', 'in', ESTADOS_PENDIENTES),
            ('location_dest_id.usage', '=', 'customer')]


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    dcasa_es_retiro = fields.Boolean(
        string='Es retiro en la tienda',
        help='El cliente pasa a buscar su compra: en el panel de Bodega estas entregas salen en «Para retirar en '
             'tienda». Los demás métodos salen en «Para despachar (envío)».')

    @api.model
    def _dcasa_marcar_retiro_inicial(self):
        """Al instalar (o actualizar a la versión que trae el panel): el «Retiro en tienda (…)» de la tienda web es
        retiro. Después lo decide quien administra, en el método de entrega."""
        retiros = self.sudo().with_context(active_test=False).search(
            [('name', '=ilike', 'retiro%'), ('dcasa_es_retiro', '=', False)])
        retiros.dcasa_es_retiro = True
        return retiros


class DcasaBodega(models.AbstractModel):
    _name = 'dcasa.bodega'
    _description = "Panel de bodega: entregas pendientes"

    # ------------------------------------------------------------------
    # Permisos
    # ------------------------------------------------------------------
    def _exigir_bodega(self):
        if not self.env.user.has_group('stock.group_stock_user'):
            raise AccessError(self.env._(
                "Solo quien trabaja con Inventario (bodega) puede usar el panel de Bodega."))

    def _entrega(self, entrega_id):
        """La entrega, leída con los permisos de la persona; un aviso sencillo si no existe o no es una salida."""
        if not isinstance(entrega_id, int) or isinstance(entrega_id, bool) or entrega_id <= 0:
            raise UserError(self.env._("Esa entrega no existe."))
        entrega = self.env['stock.picking'].browse(entrega_id).exists()
        if not entrega:
            raise UserError(self.env._("Esa entrega ya no existe."))
        entrega.check_access('read')
        if entrega.picking_type_code != 'outgoing':
            raise UserError(self.env._(
                "%(nombre)s no es una entrega a un cliente (es una recepción o un movimiento interno).",
                nombre=entrega.name))
        return entrega

    # ------------------------------------------------------------------
    # Fechas, envío o retiro, estado y pago
    # ------------------------------------------------------------------
    def _hoy(self):
        return fields.Date.context_today(self.with_context(tz=ZONA))

    def _dia(self, momento):
        if not momento:
            return False
        return fields.Datetime.context_timestamp(self.with_context(tz=ZONA), momento).date()

    def _fecha(self, entrega, pedido):
        """(fecha, tipo): la prometida al cliente (la «Fecha de entrega» del pedido) o, si no hay, la programada.

        Odoo llena la fecha límite de toda entrega con la fecha estimada aunque nadie haya prometido nada: solo es
        «prometida» si el pedido tiene «Fecha de entrega» (o, sin pedido, si alguien puso la fecha límite).
        """
        if pedido:
            if pedido.commitment_date:
                return self._dia(pedido.commitment_date), 'prometida'
        elif entrega.date_deadline:
            return self._dia(entrega.date_deadline), 'prometida'
        return self._dia(entrega.scheduled_date), 'programada'

    def _productos_flete(self, productos):
        """Los ids de los productos que son flete o envío (el mismo criterio de la factura: ``lineas.es_flete``)."""
        if not productos:
            return set()
        categoria = self.env.ref(lineas.XMLID_CATEGORIA_FLETE, raise_if_not_found=False)
        de_transportista = set()
        if 'delivery.carrier' in self.env:
            de_transportista = set(self.env['delivery.carrier'].sudo().with_context(active_test=False).search(
                [('product_id', 'in', productos.ids)]).product_id.ids)
        flete = set()
        for producto in productos:
            codigo = (producto.default_code or '').strip().upper()
            en_categoria = bool(categoria and producto.categ_id
                                and str(categoria.id) in (producto.categ_id.parent_path or '').split('/'))
            if codigo in lineas.CODIGOS_FLETE or en_categoria or producto.id in de_transportista:
                flete.add(producto.id)
        return flete

    def _como(self, entrega, pedido, flete):
        """``envio``, ``retiro`` o ``sin_definir`` (nunca se adivina)."""
        metodo = entrega.sudo().carrier_id or pedido.carrier_id
        if metodo:
            return 'retiro' if metodo.dcasa_es_retiro else 'envio'
        if pedido and any(linea.product_id.id in flete for linea in pedido.order_line):
            return 'envio'
        return 'sin_definir'

    @staticmethod
    def _movimientos(entrega):
        return entrega.move_ids.filtered(lambda m: m.state != 'cancel' and m.product_uom_qty > 0)

    @staticmethod
    def _estado(movimientos):
        """``lista`` (todo apartado en bodega), ``parcial`` (una parte) o ``esperando`` (nada todavía)."""
        if movimientos and all(m.state == 'assigned' for m in movimientos):
            return 'lista'
        if any(m.state in ('assigned', 'partially_available') for m in movimientos):
            return 'parcial'
        return 'esperando'

    @staticmethod
    def _pago(pedido):
        """``pagada``, ``abono`` (pagó una parte), ``sin_pago`` o ``False`` (la entrega no viene de un pedido).

        Cuenta un pago de verdad: un cobro conciliado con una factura publicada del pedido (las notas de crédito no
        son pago) o una transacción de la tienda web confirmada o autorizada. Solo sí o no: nunca un monto.
        ``pedido`` viene con ``sudo`` (bodega no lee facturas): de aquí solo sale esta palabra.
        """
        if not pedido:
            return False
        facturas = pedido.invoice_ids.filtered(lambda f: f.move_type == 'out_invoice' and f.state == 'posted')
        cobrado = any(not pago.get('is_refund') for factura in facturas for pago in factura._dcasa_pagos())
        transacciones = pedido.transaction_ids.filtered(lambda t: t.state in ('authorized', 'done'))
        if not cobrado and not transacciones:
            return 'sin_pago'
        moneda = pedido.currency_id
        if facturas and pedido.invoice_status != 'to invoice' \
                and moneda.is_zero(sum(facturas.mapped('amount_residual'))):
            return 'pagada'
        if not facturas and moneda.compare_amounts(sum(transacciones.mapped('amount')), pedido.amount_total) >= 0:
            return 'pagada'
        return 'abono'

    def _sin_pago_mensaje(self, entrega, pedido):
        if pedido:
            return self.env._("Este pedido (%(pedido)s) todavía no tiene pago ni abono: no se entrega.",
                              pedido=pedido.name)
        return self.env._(
            "%(nombre)s no viene de un pedido de venta: aquí solo se despachan pedidos con pago o abono. Si hay que "
            "entregarla, que la valide Gerencia desde Inventario › Entregas.", nombre=entrega.name)

    def _con_pago(self, entrega):
        return self._pago(entrega.sudo().sale_id) in CON_PAGO

    def _exigir_pago(self, entrega):
        """Una entrega pendiente sin pago ni abono no se abre ni se valida aquí (la ya hecha sí se puede ver)."""
        if entrega.state in ESTADOS_PENDIENTES and not self._con_pago(entrega):
            raise UserError(self._sin_pago_mensaje(entrega, entrega.sudo().sale_id))

    def _despachables(self):
        """Las entregas pendientes que el panel muestra: las de pedidos con pago o abono, de la más antigua a la más
        nueva (con los permisos de la persona)."""
        entregas = self.env['stock.picking'].search(
            dominio_pendientes(), order='scheduled_date asc, id asc', limit=LIMITE_BUSQUEDA)
        return entregas.filtered(self._con_pago)

    def _texto_fecha(self, fecha):
        return fecha.strftime('%d/%m/%Y') if fecha else ''

    def _nombre_producto(self, producto):
        return producto.with_context(display_default_code=False).display_name or ''

    # ------------------------------------------------------------------
    # Lista
    # ------------------------------------------------------------------
    @api.model
    def pendientes(self):
        """Las entregas pendientes para las tarjetas, de la más antigua a la más nueva."""
        self._exigir_bodega()
        despachables = self._despachables()
        cuantas = len(despachables)
        tarjetas = self._tarjetas(despachables[:LIMITE_LISTA])
        tarjetas.sort(key=lambda t: (t['fecha_orden'] or '9999', t['id']))
        ahora = fields.Datetime.context_timestamp(self.with_context(tz=ZONA), fields.Datetime.now())
        return {
            'entregas': tarjetas,
            'cuantas': cuantas,
            'recortada': cuantas > len(tarjetas),
            'hora': ahora.strftime('%H:%M'),
        }

    def _tarjetas(self, entregas):
        hoy = self._hoy()
        pedidos = entregas.sudo().sale_id
        flete = self._productos_flete(pedidos.order_line.product_id)
        tarjetas = []
        for entrega in entregas:
            pedido = entrega.sudo().sale_id
            movimientos = self._movimientos(entrega)
            fecha, tipo_fecha = self._fecha(entrega, pedido)
            como = self._como(entrega, pedido, flete)
            estado = self._estado(movimientos)
            pago = self._pago(pedido)
            por_producto = {}
            for movimiento in movimientos:
                clave = (movimiento.product_id.id, movimiento.product_uom.id)
                linea = por_producto.setdefault(clave, {
                    'nombre': self._nombre_producto(movimiento.product_id), 'cantidad': 0.0})
                linea['cantidad'] += movimiento.product_uom_qty
            resumen = [{'nombre': linea['nombre'], 'cantidad': texto_cantidad(linea['cantidad'])}
                       for linea in por_producto.values()]
            tarjetas.append({
                'id': entrega.id,
                'nombre': entrega.name,
                'cliente': entrega.partner_id.display_name or '',
                'pedido': pedido.name or entrega.origin or '',
                'fecha': self._texto_fecha(fecha),
                'fecha_tipo': tipo_fecha,
                'fecha_orden': fecha.isoformat() if fecha else '',
                'atrasada': bool(fecha and fecha < hoy),
                'como': como,
                'como_texto': COMO[como],
                'estado': estado,
                'estado_texto': ESTADO[estado],
                'pago': pago,
                'pago_texto': PAGO.get(pago, ''),
                'productos': resumen[:PRODUCTOS_EN_TARJETA],
                'mas': max(len(resumen) - PRODUCTOS_EN_TARJETA, 0),
                'producto_ids': movimientos.product_id.ids,
                'buscar': ' '.join([entrega.name, entrega.partner_id.display_name or '', pedido.name or '',
                                    entrega.origin or '', *(linea['nombre'] for linea in resumen)]),
                'pendiente_de': entrega.backorder_id.name or '',
            })
        return tarjetas

    # ------------------------------------------------------------------
    # Una entrega
    # ------------------------------------------------------------------
    @api.model
    def abrir(self, entrega_id):
        """La entrega para marcar lo que sale. Una ya hecha o cancelada se ve, pero no se valida. Una pendiente sin
        pago ni abono no se abre: el aviso lo dice."""
        self._exigir_bodega()
        entrega = self._entrega(entrega_id)
        self._exigir_pago(entrega)
        return self._detalle(entrega)

    def _direccion(self, contacto):
        partes = [contacto.street, contacto.street2, contacto.city, contacto.state_id.name]
        return ', '.join(parte.strip() for parte in partes if parte and parte.strip())

    def _detalle(self, entrega):
        pedido = entrega.sudo().sale_id
        flete = self._productos_flete(pedido.order_line.product_id)
        movimientos = self._movimientos(entrega)
        fecha, tipo_fecha = self._fecha(entrega, pedido)
        como = self._como(entrega, pedido, flete)
        contacto = entrega.partner_id
        pago = self._pago(pedido) if entrega.state not in ('done', 'cancel') else False
        empresa = entrega.company_id
        la_unidad = self.env.ref('uom.product_uom_unit', raise_if_not_found=False)
        lineas_detalle = []
        for movimiento in movimientos:
            producto = movimiento.product_id
            if entrega.state == 'done':
                apartada = movimiento.quantity
            elif movimiento.state == 'assigned':
                apartada = movimiento.product_uom_qty
            elif movimiento.state == 'partially_available':
                apartada = movimiento.quantity
            else:
                apartada = 0.0
            lineas_detalle.append({
                'id': movimiento.id,
                'producto_id': producto.id,
                'nombre': self._nombre_producto(producto),
                'codigo': lineas.codigo_a_imprimir(empresa, producto, producto.default_code) or '',
                'foto': f'/web/image/product.product/{producto.id}/image_128',
                'pedida': movimiento.product_uom_qty,
                'pedida_texto': texto_cantidad(movimiento.product_uom_qty),
                # Nada si es la unidad de siempre (basta el número); si es otra (metros), su nombre.
                'unidad': texto_unidad(bool(la_unidad) and movimiento.product_uom == la_unidad,
                                       movimiento.product_uom.name or ''),
                'apartada': apartada,
                'apartada_texto': texto_cantidad(apartada),
                'salio': movimiento.quantity if entrega.state == 'done' else 0.0,
                'seguimiento': producto.tracking != 'none',
            })
        hecha = entrega.state == 'done'
        if hecha:
            estado, estado_texto = 'hecha', 'Entregada'
        elif entrega.state == 'cancel':
            estado, estado_texto = 'cancelada', 'Cancelada'
        else:
            estado = self._estado(movimientos)
            estado_texto = ESTADO[estado]
        return {
            'id': entrega.id,
            'nombre': entrega.name,
            'cliente': contacto.display_name or '',
            'telefono': contacto.phone or contacto.commercial_partner_id.phone or '',
            'direccion': self._direccion(contacto),
            'pedido': pedido.name or entrega.origin or '',
            'fecha': self._texto_fecha(fecha),
            'fecha_tipo': tipo_fecha,
            'atrasada': bool(fecha and fecha < self._hoy() and not hecha),
            'como': como,
            'como_texto': COMO[como],
            'estado': estado,
            'estado_texto': estado_texto,
            'hecha_el': (fields.Datetime.context_timestamp(self.with_context(tz=ZONA), entrega.date_done)
                         .strftime('%d/%m/%Y %H:%M') if hecha and entrega.date_done else ''),
            'pago': pago,
            'pago_texto': PAGO.get(pago, ''),
            'nota': html2plaintext(entrega.note or '').strip() if entrega.note else '',
            'pendiente_de': entrega.backorder_id.name or '',
            'deja_pendiente': entrega.picking_type_id.create_backorder != 'never',
            'lineas': lineas_detalle,
            'imprimir': self._accion_imprimir(entrega),
        }

    def _accion_imprimir(self, entrega):
        """La nota de entrega (la misma de Inventario, con el QR y la versión fácil de leer si la empresa las usa)."""
        informe = self.env.ref('stock.action_report_delivery', raise_if_not_found=False)
        return informe.report_action(entrega) if informe else False

    # ------------------------------------------------------------------
    # Lo que leyó el lector o la cámara
    # ------------------------------------------------------------------
    @api.model
    def leer(self, codigo, entrega_id=False):
        """Lo que escribió el lector, en este orden: el QR de un documento, el número de una entrega o de un pedido, el
        código de un producto.

        ``{'resultado': 'entrega', 'entrega': {...}}`` (una entrega pendiente para abrir), ``'entregas'`` (varias
        pendientes del mismo pedido: ``ids``), ``'producto'`` (``producto_ids`` y ``nombre``), ``'aviso'``
        (``mensaje``: sin permiso, no existe, ya entregada…) o ``'nada'`` (la pantalla lo usa como búsqueda).
        ``entrega_id``: la entrega abierta (un QR de esa misma entrega no la vuelve a abrir).
        """
        self._exigir_bodega()
        if not isinstance(codigo, str):
            return {'resultado': 'nada', 'texto': ''}
        leido = leer_url(codigo)
        tolerante = False
        if not leido:    # un lector con otra distribución de teclado cambió los símbolos de la dirección
            leido, tolerante = leer_url_tolerante(codigo), True
        if leido:
            return self._leer_documento(*leido, tolerante=tolerante, abierta=entrega_id)
        texto = limpiar_codigo(codigo)
        if not texto:
            return {'resultado': 'nada', 'texto': ''}
        por_numero = self._leer_numero(texto, abierta=entrega_id)
        if por_numero:
            return por_numero
        productos, _forma = self.env['dcasa.barras']._productos_por_codigo(texto)
        if productos:
            return {'resultado': 'producto', 'producto_ids': productos.ids,
                    'nombre': self._nombre_producto(productos[0]), 'texto': texto}
        return {'resultado': 'nada', 'texto': texto}

    def _leer_documento(self, tipo, referencia, tolerante=False, abierta=False):
        documentos = self.env['dcasa.documento']
        estado, registro = documentos._dcasa_buscar_documento(tipo, referencia, tolerante=tolerante)
        if estado != OK:
            return {'resultado': 'aviso', 'mensaje': documentos._dcasa_mensaje_documento(estado, tipo)}
        if tipo == 'ENT':
            return self._resultado_de_entrega(registro, abierta)
        if tipo == 'COM':
            return {'resultado': 'aviso', 'mensaje': self.env._(
                "Ese QR es de un pedido de compra. Aquí se despachan las entregas a clientes: escanea el QR de la nota "
                "de entrega.")}
        # Una factura o un pedido de venta: sus entregas pendientes (el cliente llega con su factura a retirar).
        pedidos = registro.sudo().invoice_line_ids.sale_line_ids.order_id if tipo == 'FAC' else registro.sudo()
        return self._entregas_de_pedidos(pedidos, registro.name, abierta)

    def _resultado_de_entrega(self, entrega, abierta=False):
        if entrega.picking_type_code != 'outgoing':
            return {'resultado': 'aviso', 'mensaje': self.env._(
                "%(nombre)s no es una entrega a un cliente (es una recepción o un movimiento interno).",
                nombre=entrega.name)}
        if entrega.state == 'done':
            cuando = fields.Datetime.context_timestamp(self.with_context(tz=ZONA), entrega.date_done) \
                .strftime('%d/%m/%Y a las %H:%M') if entrega.date_done else ''
            mensaje = self.env._("%(nombre)s ya se entregó el %(cuando)s.", nombre=entrega.name, cuando=cuando) \
                if cuando else self.env._("%(nombre)s ya se entregó.", nombre=entrega.name)
            pendientes = entrega.backorder_ids.filtered(lambda e: e.state in ESTADOS_PENDIENTES)
            if pendientes:
                mensaje += ' ' + self.env._("Lo que faltó está en %(pendientes)s.",
                                            pendientes=', '.join(pendientes.mapped('name')))
            return {'resultado': 'aviso', 'mensaje': mensaje, 'ids': pendientes.ids}
        if entrega.state == 'cancel':
            return {'resultado': 'aviso', 'mensaje': self.env._("%(nombre)s está cancelada.", nombre=entrega.name)}
        if entrega.state == 'draft':
            return {'resultado': 'aviso', 'mensaje': self.env._(
                "%(nombre)s todavía no está confirmada: no se puede despachar.", nombre=entrega.name)}
        if not self._con_pago(entrega):
            return {'resultado': 'aviso', 'sin_pago': True,
                    'mensaje': self._sin_pago_mensaje(entrega, entrega.sudo().sale_id)}
        if abierta and entrega.id == abierta:
            return {'resultado': 'misma', 'mensaje': self.env._("Ya estás en %(nombre)s.", nombre=entrega.name)}
        return {'resultado': 'entrega', 'entrega': self._detalle(entrega)}

    def _entregas_de_pedidos(self, pedidos, referencia, abierta=False):
        if not pedidos:
            return {'resultado': 'aviso', 'mensaje': self.env._(
                "%(documento)s no viene de un pedido con entregas.", documento=referencia)}
        # Las entregas se leen con los permisos de la persona (el pedido, con sudo, solo da sus números).
        entregas = self.env['stock.picking'].search(
            [('id', 'in', pedidos.picking_ids.ids)] + dominio_pendientes(), order='scheduled_date asc, id asc')
        if not entregas:
            return {'resultado': 'aviso', 'mensaje': self.env._(
                "%(documento)s no tiene entregas pendientes: ya salió todo o todavía no hay entrega.",
                documento=referencia)}
        con_pago = entregas.filtered(self._con_pago)
        if len(entregas) == 1 or not con_pago:
            return self._resultado_de_entrega(entregas[:1], abierta)
        if len(con_pago) == 1:
            return self._resultado_de_entrega(con_pago, abierta)
        return {'resultado': 'entregas', 'ids': con_pago.ids, 'mensaje': self.env._(
            "%(documento)s tiene %(cuantas)s entregas pendientes: elige la que vas a despachar.",
            documento=referencia, cuantas=len(con_pago))}

    def _leer_numero(self, texto, abierta=False):
        """El número de una entrega (WH/OUT/00005, el código de barras de la nota de Odoo) o de un pedido (S00007)."""
        escapado = texto.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        entrega = self.env['stock.picking'].search(
            [('name', '=ilike', escapado), ('picking_type_code', '=', 'outgoing')], limit=1)
        if entrega:
            return self._resultado_de_entrega(entrega, abierta)
        entregas = self.env['stock.picking'].search(
            [('origin', '=ilike', escapado)] + dominio_pendientes(), order='scheduled_date asc, id asc')
        con_pago = entregas.filtered(self._con_pago)
        if len(entregas) == 1 or (entregas and not con_pago):
            return self._resultado_de_entrega(entregas[:1], abierta)
        if len(con_pago) == 1:
            return self._resultado_de_entrega(con_pago, abierta)
        if con_pago:
            return {'resultado': 'entregas', 'ids': con_pago.ids, 'mensaje': self.env._(
                "El pedido %(pedido)s tiene %(cuantas)s entregas pendientes: elige la que vas a despachar.",
                pedido=texto.upper(), cuantas=len(con_pago))}
        return None

    # ------------------------------------------------------------------
    # Validar
    # ------------------------------------------------------------------
    def _marcas(self, entrega, marcas):
        """``{movimiento: cantidad}`` de lo que se marcó, revisado contra la entrega (lo que no viene, 0)."""
        movimientos = self._movimientos(entrega)
        if not isinstance(marcas, list) or len(marcas) > MAXIMO_LINEAS:
            raise UserError(self.env._("No se entendió lo marcado. Vuelve a abrir la entrega."))
        cantidades = dict.fromkeys(movimientos, 0.0)
        por_id = {movimiento.id: movimiento for movimiento in movimientos}
        for marca in marcas:
            if not isinstance(marca, dict):
                raise UserError(self.env._("No se entendió lo marcado. Vuelve a abrir la entrega."))
            movimiento = por_id.get(marca.get('id'))
            cantidad = marca.get('cantidad')
            if movimiento is None:
                raise UserError(self.env._(
                    "La entrega cambió mientras la tenías abierta. Vuelve a abrirla para ver lo que hay que sacar."))
            if isinstance(cantidad, bool) or not isinstance(cantidad, (int, float)) or not math.isfinite(cantidad) \
                    or cantidad < 0:
                raise UserError(self.env._("Una cantidad marcada no es válida."))
            if movimiento.product_uom.compare(cantidad, movimiento.product_uom_qty) > 0:
                raise UserError(self.env._(
                    "De «%(producto)s» se pidieron %(pedida)s: no puedes entregar más de lo pedido.",
                    producto=self._nombre_producto(movimiento.product_id),
                    pedida=texto_cantidad(movimiento.product_uom_qty)))
            cantidades[movimiento] = float(cantidad)
        return cantidades

    def _faltantes(self, cantidades):
        return [{
            'nombre': self._nombre_producto(movimiento.product_id),
            'marcada': texto_cantidad(cantidad),
            'pedida': texto_cantidad(movimiento.product_uom_qty),
        } for movimiento, cantidad in cantidades.items()
            if movimiento.product_uom.compare(cantidad, movimiento.product_uom_qty) < 0]

    def _revisar_seguimiento(self, cantidades):
        """Un producto con número de serie o lote solo sale con los números que Odoo ya apartó: aquí no se escriben."""
        for movimiento, cantidad in cantidades.items():
            if not cantidad or movimiento.product_id.tracking == 'none':
                continue
            con_numero = sum(movimiento.move_line_ids.filtered(lambda ml: ml.lot_id or ml.lot_name).mapped('quantity'))
            if movimiento.product_uom.compare(cantidad, con_numero) > 0:
                raise UserError(self.env._(
                    "«%(producto)s» lleva número de serie o de lote y el sistema no tiene apartados los que vas a "
                    "entregar. Pídele a Gerencia que la valide desde Inventario › Entregas.",
                    producto=self._nombre_producto(movimiento.product_id)))

    @api.model
    def validar(self, entrega_id, marcas, parcial=False):
        """Entrega lo marcado. ``marcas``: ``[{'id': id del renglón, 'cantidad': n}]``.

        Todo marcado: valida. Falta algo y ``parcial`` no viene: no toca nada y responde ``confirmar_parcial`` con lo
        que falta. Con ``parcial``: entrega lo marcado y Odoo deja lo demás en una entrega pendiente (salvo que la
        operación esté configurada para no dejar pendientes: entonces lo demás se cancela, y la pantalla lo avisó).
        """
        self._exigir_bodega()
        entrega = self._entrega(entrega_id)
        entrega.check_access('write')
        if entrega.state == 'done':
            raise UserError(self.env._("%(nombre)s ya se entregó: nadie tiene que validarla otra vez.",
                                       nombre=entrega.name))
        if entrega.state not in ESTADOS_PENDIENTES:
            raise UserError(self.env._("%(nombre)s no se puede despachar (está cancelada o sin confirmar).",
                                       nombre=entrega.name))
        self._exigir_pago(entrega)
        cantidades = self._marcas(entrega, marcas)
        if not any(cantidades.values()):
            raise UserError(self.env._("Marca lo que sale antes de validar."))
        faltan = self._faltantes(cantidades)
        if faltan and not parcial:
            return {'resultado': 'confirmar_parcial', 'faltan': faltan,
                    'deja_pendiente': entrega.picking_type_id.create_backorder != 'never'}
        self._revisar_seguimiento(cantidades)
        sin_apartar = [movimiento for movimiento, cantidad in cantidades.items()
                       if cantidad and movimiento.product_id.is_storable
                       and movimiento.product_uom.compare(cantidad, movimiento.quantity) > 0]
        for movimiento, cantidad in cantidades.items():
            if cantidad:
                movimiento.quantity = cantidad
                movimiento.picked = True
            else:
                movimiento.picked = False
        # skip_backorder: la pregunta «¿dejar lo demás pendiente?» ya la contestó la persona en el panel. skip_sms:
        # el aviso de los SMS de Odoo es para quien administra, no para bodega (los SMS siguen su configuración).
        resultado = entrega.with_context(skip_backorder=True, picking_ids_not_to_backorder=[], skip_sms=True) \
            .button_validate()
        if isinstance(resultado, dict) and resultado.get('type') == 'ir.actions.act_window':
            raise UserError(self.env._(
                "Esta entrega pide un paso más que el panel no hace. Pídele a Gerencia que la valide desde "
                "Inventario › Entregas."))
        if entrega.state != 'done':
            raise UserError(self.env._("No se pudo validar %(nombre)s. Vuelve a abrirla e inténtalo otra vez.",
                                       nombre=entrega.name))
        pendiente = entrega.backorder_ids.filtered(lambda e: e.state not in ('done', 'cancel'))[:1]
        self._anotar(entrega, faltan, pendiente, sin_apartar)
        if pendiente:
            mensaje = self.env._("Listo: %(nombre)s quedó entregada. Lo que faltó quedó pendiente en %(pendiente)s.",
                                 nombre=entrega.name, pendiente=pendiente.name)
        elif faltan:
            mensaje = self.env._("Listo: %(nombre)s quedó entregada. Lo que faltó se canceló.", nombre=entrega.name)
        else:
            mensaje = self.env._("Listo: %(nombre)s quedó entregada completa.", nombre=entrega.name)
        return {
            'resultado': 'hecha',
            'nombre': entrega.name,
            'pendiente': pendiente.name or False,
            'pendiente_id': pendiente.id or False,
            'mensaje': mensaje,
            'imprimir': self._accion_imprimir(entrega),
        }

    def _anotar(self, entrega, faltan, pendiente, sin_apartar):
        """Una nota en el historial de la entrega: salió desde el panel, qué faltó y qué salió sin estar en el
        sistema (para que Gerencia cuente ese producto). Quién la validó lo registra Odoo, como siempre."""
        partes = [escape(self.env._("Despachada desde el panel de Bodega por %(persona)s.",
                                    persona=self.env.user.name))]
        if faltan:
            detalle = '; '.join(f"{f['nombre']}: salieron {f['marcada']} de {f['pedida']}" for f in faltan)
            partes.append(escape(self.env._("Entrega a medias (%(detalle)s).", detalle=detalle)))
            if pendiente:
                partes.append(escape(self.env._("Lo que faltó quedó en %(pendiente)s.", pendiente=pendiente.name)))
        if sin_apartar:
            nombres = ', '.join(self._nombre_producto(m.product_id) for m in sin_apartar)
            partes.append(escape(self.env._(
                "Salió sin estar apartado en el sistema: %(productos)s. Gerencia: revisa sus existencias en el "
                "Escáner.", productos=nombres)))
        entrega.message_post(body=Markup('<br/>').join(partes))
