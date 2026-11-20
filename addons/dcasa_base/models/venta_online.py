"""Qué es una «venta online»: UNA sola definición para todo el sistema (decisión de Gerencia, 2026-11-19, afinada el
2026-11-20).

La usan tres cosas que NO se parecen: el bono por meta de las vendedoras (``dcasa_nomina``), el avance que ellas ven en
su Inicio (``dcasa_interfaz``) y la comisión del programa de vendedores (``dcasa_socios``), y además la comisión del
sitio web (``dcasa_comision_web``). Por eso vive aquí, en la base: ninguna de ellas depende de las otras.

**Es venta online** (``sale.order.dcasa_venta_online``) un pedido que **nació por un flujo digital real**
(``dcasa_nacio_en_web``) **y** al que **ninguna vendedora llevó** (``dcasa_llevada_por_vendedora``). Los flujos
digitales reales son dos:

1. el carrito de la página web (``website._create_cart``): la compra normal, la cotización hecha en la página y
   llevada a la tienda («Pago en la tienda», apartado: es el mismo pedido) y el carrito de **Andrés**, el chat de la
   tienda, que trabaja sobre el carrito real;
2. la cotización que arma **Juan** (la herramienta de cotizar del chat de WhatsApp) y el cliente paga.

**Una vendedora llevó el pedido** cuando, en los 30 días anteriores a confirmarlo, le escribió al cliente por el chat de
Juan (aunque sea un mensaje: ``dcasa_comision_web`` lo comprueba al confirmar). Entonces es de ella y no es online,
venga del flujo que venga: Andrés que pasa al cliente a una persona que lo atiende y cierra, o la cotización de Juan que
una vendedora retoma. **Que la vendedora solo confirme el pedido, sin haberle escrito por el chat de Juan, no cuenta**
(caso gris que Gerencia puede afinar). ``dcasa_via_andres`` solo dice por dónde llegó la venta: **ya no fuerza** que
sea online.

**NO es venta online**: lo que se arma en la tienda física, en Ventas o en el Punto de Venta (un pedido tecleado por una
persona), ni lo que una vendedora atendió.

Las marcas se escriben UNA vez, **solo por código del flujo real** (el carrito: ``website._create_cart``, en
``website_dcasa``; la herramienta de cotizar de Juan, en ``dcasa_conversaciones``; Andrés marca el suyo;
``dcasa_comision_web`` decide «la llevó una vendedora» al confirmar), y nadie las cambia a mano ni con ``sudo()``: solo
con la llave interna ``ESCRIBIR``, que por RPC nunca llega (el contexto de una llamada es JSON). **Tener ``website_id``
NO basta** (revisión adversarial, 2026-11-19): ese campo se acepta por RPC, así que quien teclea un pedido de mostrador
con él no lo vuelve «de la web»; tampoco lo hace un ``default_*`` del contexto (también viaja por RPC y Odoo lo aplica
después de ``create``: ``default_get`` lo descarta). Tampoco se escribe a mano el campo calculado
``dcasa_venta_online`` que lee todo el sistema. ``dcasa_creada_por_id`` guarda quién abrió el carrito (para que
Gerencia vea si alguien del equipo teclea pedidos de la página). Los pedidos que ya existían se marcaron una sola
vez al instalar (``migrations/19.0.1.10.0``).

**Solo hacia adelante.** La regla «una venta online nunca es de una vendedora» solo rige desde el día en que Gerencia
pone en vigencia la primera versión de las reglas de la comisión web: ``_dcasa_online_desde()`` devuelve ese día (y
``False`` mientras no exista, que es como se comporta el sistema hoy). Lo ya calculado y pagado no se toca.
"""
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import UserError

TESTIGOS = ('dcasa_nacio_en_web', 'dcasa_via_andres', 'dcasa_llevada_por_vendedora', 'dcasa_creada_por_id',
            'dcasa_tocada_por_id')
# Lo derivado de las marcas: se calcula, y escribirlo a mano se ignora (nunca cambia lo que cuenta).
DERIVADOS = ('dcasa_venta_online',)
# Lo que, al cambiarlo en una línea de pedido, deja anotado quién lo hizo.
CAMPOS_VIGILADOS = ('product_id', 'product_uom_qty', 'price_unit', 'discount', 'product_uom_id', 'tax_ids', 'order_id')
PRECIO_SOLO = frozenset({'price_unit', 'technical_price_unit'})
CLAVE_PRECIO = 'dcasa_base_precio_del_sistema'
# Un objeto, no ``True``: el contexto que llega por RPC es JSON y nunca puede traerlo. Solo lo pone el código del
# servidor que repone el precio de una línea (el combo armable); ``sale_write_from_compute`` NO basta.
PRECIO_DEL_SISTEMA = object()
CLAVE_CONTEXTO = 'dcasa_base_escribir_testigo'
# Un objeto, no ``True``: el contexto que llega por RPC es JSON y nunca puede traerlo.
ESCRIBIR = object()


class SaleOrderOnline(models.Model):
    _inherit = 'sale.order'

    dcasa_nacio_en_web = fields.Boolean(
        'Nació por un flujo digital', readonly=True, copy=False, index=True,
        help='Se escribe una sola vez al crear el pedido, desde el flujo real: el carrito de la página (también el de '
             'Andrés) o la cotización que arma Juan. Nadie lo cambia a mano.')
    dcasa_via_andres = fields.Boolean(
        'Pasó por Andrés', readonly=True, copy=False,
        help='El carrito de este pedido lo armó o lo tocó Andrés, el chat de la tienda. Solo dice por dónde llegó la '
             'venta: si es online lo decide si una vendedora la atendió.')
    dcasa_llevada_por_vendedora = fields.Boolean(
        'La llevó una vendedora', readonly=True, copy=False,
        help='Una vendedora atendió al cliente en el chat de Juan antes de confirmar el pedido: aunque el pedido salga '
             'de la página web, la venta fue de ella y no es venta online.')
    dcasa_creada_por_id = fields.Many2one(
        'res.users', 'Carrito abierto por', readonly=True, copy=False, index='btree_not_null',
        help='Quién abrió el carrito de la página (el visitante o, si es alguien del equipo, quién fue). Sirve para '
             'vigilar si el personal teclea pedidos de la página; no cambia lo que cuenta.')
    dcasa_tocada_por_id = fields.Many2one(
        'res.users', 'Lo cambió el equipo', readonly=True, copy=False, index='btree_not_null',
        help='La última persona del equipo (un usuario interno) que cambió el cliente o las líneas de un pedido que ya '
             'nació por un flujo digital, o quien tecleó el precio de una línea (la tienda pone los precios sola). '
             'Nadie lo escribe a mano. Es vigilancia: no cambia lo que cuenta. Cubre el carrito que abre un visitante '
             'y después arma alguien a mano para cobrarlo como venta del sitio.')
    dcasa_venta_online = fields.Boolean(
        'Venta online', compute='_compute_dcasa_venta_online', store=True, index=True,
        help='La definición única: nació por un flujo digital (la página, Andrés, la cotización de Juan) y no la llevó '
             'una vendedora. Una venta online jamás se atribuye a una vendedora (bono por meta e Inicio; el programa '
             'de vendedores solo paga la compra con un código VEN).')

    @api.depends('dcasa_nacio_en_web', 'dcasa_llevada_por_vendedora')
    def _compute_dcasa_venta_online(self):
        for orden in self:
            orden.dcasa_venta_online = bool(orden.dcasa_nacio_en_web and not orden.dcasa_llevada_por_vendedora)

    @api.model
    def default_get(self, fields_list):
        """Las claves ``default_*`` del contexto llegan por RPC y Odoo las aplica DESPUÉS de que ``create`` limpió los
        valores: sin esto, ``context={'default_dcasa_nacio_en_web': True}`` fabricaba el origen (segunda revisión,
        2026-11-19). Solo la llave interna ``ESCRIBIR`` deja pasar una marca."""
        valores = super().default_get(fields_list)
        if self.env.context.get(CLAVE_CONTEXTO) is not ESCRIBIR:
            for clave in TESTIGOS + DERIVADOS:
                valores.pop(clave, None)
        return valores

    @api.model_create_multi
    def create(self, vals_list):
        # Nadie fabrica el origen al crear (ni con ``website_id``, ni con ``default_website_id``, ni con ningún
        # ``default_*`` del contexto: ver ``default_get``): lo pone el flujo real.
        vals_list = [{k: v for k, v in vals.items() if k not in TESTIGOS + DERIVADOS} for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        if any(clave in vals for clave in TESTIGOS) and self.env.context.get(CLAVE_CONTEXTO) is not ESCRIBIR:
            raise UserError(self.env._(
                'El origen de la venta (si nació en la web, si pasó por Andrés o si la llevó una vendedora) lo pone '
                'el sistema una sola vez: no se cambia a mano.'))
        if any(clave in vals for clave in DERIVADOS):
            # «Venta online» se calcula de las marcas: escribirla a mano no cambia nada (en ningún sentido).
            vals = {k: v for k, v in vals.items() if k not in DERIVADOS}
            if not vals:
                return True
        resultado = super().write(vals)
        if ('partner_id' in vals or 'order_line' in vals) and self.env.context.get(CLAVE_CONTEXTO) is not ESCRIBIR:
            self._dcasa_anotar_quien_toco()
        return resultado

    def _dcasa_anotar_quien_toco(self):
        """Si una persona del equipo (un usuario interno, no un visitante ni un cliente) cambia el cliente o las líneas
        de un pedido que nació por un flujo digital, queda anotado quién: así Gerencia ve el carrito que abrió un
        visitante y después se armó a mano para cobrarlo como venta del sitio. Solo vigilancia."""
        usuario = self.env.user
        if usuario.share:
            return
        self.filtered(lambda o: o.dcasa_nacio_en_web and o.dcasa_tocada_por_id != usuario)._dcasa_escribir_marca(
            dcasa_tocada_por_id=usuario.id)

    def _dcasa_anotar_quien_toco_lineas(self, todos=False):
        """Anota a quien cambia las líneas (si es un usuario interno, o quien sea con ``todos``): ver
        ``SaleOrderLineOnline``."""
        usuario = self.env.user
        if usuario.share and not todos:
            return
        self.exists().filtered(
            lambda o: o.dcasa_nacio_en_web and o.dcasa_tocada_por_id != usuario)._dcasa_escribir_marca(
            dcasa_tocada_por_id=usuario.id)

    def _dcasa_escribir_marca(self, **marcas):
        """Único camino para escribir las marcas de origen (solo código del sistema; ver arriba)."""
        pendientes = self.filtered(lambda o: any(
            (o[clave].id if o._fields[clave].type == 'many2one' else o[clave]) != valor
            for clave, valor in marcas.items()))
        if pendientes:
            pendientes.sudo().with_context(**{CLAVE_CONTEXTO: ESCRIBIR}).write(marcas)
        return pendientes

    @api.model
    def _dcasa_online_desde(self, company=None):
        """El primer día (fecha de Panamá) desde el que una venta online deja de ser de las vendedoras, o ``False``
        si todavía no rige (hoy, el sistema se porta como siempre). ``dcasa_comision_web`` lo devuelve desde la
        primera versión de sus reglas."""
        return False

    @api.model
    def _dcasa_dominio_online_desde(self, campo_dia, company=None):
        """Dominio de las ventas online que ya NO pueden ser de una vendedora (lo contrario del siguiente). Sin regla
        en vigor, no es ninguna."""
        desde = self._dcasa_online_desde(company)
        if not desde:
            return [('id', '=', False)]
        return [('dcasa_venta_online', '=', True), (campo_dia, '>=', fields.Date.to_string(desde))]

    @api.model
    def _dcasa_dominio_no_online_desde(self, campo_dia, company=None):
        """Dominio de pedidos que SÍ pueden ser de una vendedora: no son ventas online o su día (``campo_dia``) es
        anterior a la fecha desde la que rige la regla. Sin regla en vigor, no filtra nada."""
        desde = self._dcasa_online_desde(company)
        if not desde:
            return []
        return ['|', ('dcasa_venta_online', '=', False), (campo_dia, '<', fields.Date.to_string(desde))]


class SaleOrderLineOnline(models.Model):
    _inherit = 'sale.order.line'

    @api.model_create_multi
    def create(self, vals_list):
        lineas = super().create(vals_list)
        lineas._dcasa_anotar_cambio_de_lineas()
        con_precio = lineas.browse(
            [linea.id for linea, vals in zip(lineas, vals_list, strict=True) if 'price_unit' in vals])
        con_precio._dcasa_anotar_cambio_de_lineas(precio_a_mano=True)
        return lineas

    def write(self, vals):
        resultado = super().write(vals)
        if self.env.context.get(CLAVE_PRECIO) is PRECIO_DEL_SISTEMA and set(vals) <= PRECIO_SOLO:
            return resultado        # el precio que repone el propio servidor (el combo armable): nadie lo tecleó
        if 'price_unit' in vals:
            self._dcasa_anotar_cambio_de_lineas(precio_a_mano=True)
        elif any(campo in vals for campo in CAMPOS_VIGILADOS):
            self._dcasa_anotar_cambio_de_lineas()
        return resultado

    def unlink(self):
        ordenes = self._dcasa_lineas_que_cuentan().order_id
        resultado = super().unlink()
        ordenes._dcasa_anotar_quien_toco_lineas()
        return resultado

    def _dcasa_lineas_que_cuentan(self):
        """Las líneas de producto de un pedido que nació por un flujo digital. No cuentan las secciones y notas, el
        anticipo, el envío (lo pone la tienda) ni los premios y descuentos (precio negativo)."""
        # ``exists()``: otro módulo puede haber borrado la línea al crearla (la promoción de envío repone la suya).
        return self.exists().filtered(
            lambda ln: not ln.display_type and not ln.is_downpayment and ln.price_unit >= 0
            and not ('is_delivery' in ln._fields and ln.is_delivery) and ln.order_id.dcasa_nacio_en_web)

    def _dcasa_anotar_cambio_de_lineas(self, precio_a_mano=False):
        """Una persona del equipo (un usuario interno) que crea, cambia (producto, cantidad, precio, descuento) o borra
        una línea de un pedido que nació por un flujo digital lo está armando a mano (para cobrarlo como venta del
        sitio con otras cosas), y eso se vigila: ``dcasa_tocada_por_id``. Se anota el cambio escrito DIRECTO en la
        línea (por RPC, sin pasar por el pedido): la llave ``sale_write_from_compute`` del contexto, que por RPC
        cualquiera manda, ya no lo esquiva; solo vale el precio que repone el propio servidor
        (``PRECIO_DEL_SISTEMA``). Un precio TECLEADO (``precio_a_mano``) se anota quien lo teclee, también el
        visitante o quien abrió el carrito: la tienda pone los precios sola."""
        self._dcasa_lineas_que_cuentan().order_id._dcasa_anotar_quien_toco_lineas(todos=precio_a_mano)


class AccountMoveOnline(models.Model):
    _inherit = 'account.move'

    def _dcasa_online_desde(self, company=None):
        return self.env['sale.order']._dcasa_online_desde(company or self.company_id[:1] or None)

    def _dcasa_factor_online(self):
        """``{id: fracción}``: qué parte (sin ITBMS) de cada factura o nota viene de pedidos online, de 0 a 1.

        Una factura se mide por sus líneas de producto que vienen de un pedido (``sale_line_ids``); una nota de crédito
        enlazada hereda la fracción de la factura que revierte (la copia de las líneas no trae el pedido). Una nota
        aplicada suelta, sin factura enlazada, no se resuelve aquí: quien la usa pasa la factura con que se concilió.
        Una factura sin pedido (hecha a mano) es 0."""
        factores = dict.fromkeys(self.ids, 0.0)
        facturas = self.filtered(lambda m: m.move_type == 'out_invoice')
        notas = self.filtered(lambda m: m.move_type == 'out_refund' and m.reversed_entry_id.move_type == 'out_invoice')
        origen = facturas | notas.reversed_entry_id
        if origen:
            lineas = self.env['account.move.line'].sudo().search_fetch(
                [('move_id', 'in', origen.ids), ('display_type', '=', 'product')],
                ['move_id', 'balance', 'sale_line_ids'])
            online = self.env['sale.order.line'].sudo().search_fetch(
                [('id', 'in', lineas.sale_line_ids.ids), ('order_id.dcasa_venta_online', '=', True)], ['id']).ids
            total, de_la_web = {}, {}
            for linea in lineas:
                importe = -linea.balance
                total[linea.move_id.id] = total.get(linea.move_id.id, 0.0) + importe
                if any(sl.id in online for sl in linea.sale_line_ids):
                    de_la_web[linea.move_id.id] = de_la_web.get(linea.move_id.id, 0.0) + importe
            fraccion = {mid: max(0.0, min(1.0, de_la_web.get(mid, 0.0) / t)) for mid, t in total.items() if t}
            for factura in facturas:
                factores[factura.id] = fraccion.get(factura.id, 0.0)
            for nota in notas:
                factores[nota.id] = fraccion.get(nota.reversed_entry_id.id, 0.0)
        return factores


    @api.model
    def _dcasa_dias_de_cobro_de(self, facturas):
        """``({factura_id: día}, {nota_id: {factura_id}})``: el día en que cada factura quedó pagada completa (su última
        conciliación, pago o nota de crédito, nunca antes de la factura); las que todavía deben algo no salen. Y las
        notas de crédito que se aplicaron a cada una. Una sola definición para el bono por meta, el programa de
        vendedores y la comisión web (sale de una sola lectura de las conciliaciones)."""
        pagadas = facturas.filtered(lambda f: f.payment_state in ('paid', 'in_payment'))
        if not pagadas:
            return {}, {}
        parciales = self.env['account.partial.reconcile'].sudo().search_fetch(
            ['|', ('debit_move_id.move_id', 'in', pagadas.ids), ('credit_move_id.move_id', 'in', pagadas.ids)],
            ['debit_move_id', 'credit_move_id', 'max_date', 'exchange_move_id'])
        diferencias_de_cambio = parciales.exchange_move_id
        dias, notas = {}, {}
        for parcial in parciales:
            for propia, otra in ((parcial.debit_move_id, parcial.credit_move_id),
                                 (parcial.credit_move_id, parcial.debit_move_id)):
                factura, contraparte = propia.move_id, otra.move_id
                if factura not in pagadas or contraparte in diferencias_de_cambio:
                    continue
                dia = max(parcial.max_date, factura.invoice_date or date.min)
                dias[factura.id] = max(dias.get(factura.id, date.min), dia)
                if contraparte.move_type == 'out_refund':
                    notas.setdefault(contraparte.id, set()).add(factura.id)
        return dias, notas
