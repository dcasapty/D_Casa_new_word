"""Qué es una «venta online»: UNA sola definición para todo el sistema (decisión de Gerencia, 2026-11-19).

La usan tres cosas que NO se parecen: el bono por meta de las vendedoras (``dcasa_nomina``), el avance que ellas ven en
su Inicio (``dcasa_interfaz``) y la comisión del programa de vendedores (``dcasa_socios``), y además la comisión del
sitio web (``dcasa_comision_web``). Por eso vive aquí, en la base: ninguna de ellas depende de las otras.

**Cuenta como venta online** (``sale.order.dcasa_venta_online``), y por lo tanto nunca es de una vendedora:

1. alguien compra en la página web  → el pedido nació en la tienda en línea (``dcasa_nacio_en_web``);
2. alguien cotiza en la página web y llega a la tienda con esa cotización («Pago en la tienda», apartado) → es el mismo
   pedido, nació en la web;
3. todas las ventas de Andrés, el chat de la tienda (``dcasa_via_andres``): Andrés trabaja sobre el carrito real de la
   tienda; cuentan aunque después las cierre una vendedora;
4. alguien entra al chat de Juan (WhatsApp, etc.), Juan lo manda a la página o al catálogo y la persona decide comprar
   sola por ahí → es un pedido que nació en la web y ninguna vendedora lo llevó.

**NO cuenta**: alguien entra al chat de Juan y lo atiende una vendedora (``dcasa_llevada_por_vendedora``, lo decide
``dcasa_comision_web`` al confirmar el pedido mirando la conversación), aunque después ella le mande el enlace de la
tienda; ni lo que se arma en la tienda física, en Ventas o en el Punto de Venta, ni la cotización que arma Juan (esa no
nació en la web).

Las tres marcas se escriben UNA vez, por código, y nadie las cambia a mano ni con ``sudo()`` (solo con la llave interna
``ESCRIBIR``, que por RPC nunca llega: el contexto de una llamada es JSON). ``website_id`` sí se puede cambiar después;
por eso la marca de origen se guarda aparte al crear el pedido. Los pedidos que ya existían se marcaron una sola vez al
instalar (``migrations/19.0.1.10.0``).

**Solo hacia adelante.** La regla «una venta online nunca es de una vendedora» solo rige desde el día en que Gerencia
pone en vigencia la primera versión de las reglas de la comisión web: ``_dcasa_online_desde()`` devuelve ese día (y
``False`` mientras no exista, que es como se comporta el sistema hoy). Lo ya calculado y pagado no se toca.
"""
from odoo import api, fields, models
from odoo.exceptions import UserError

TESTIGOS = ('dcasa_nacio_en_web', 'dcasa_via_andres', 'dcasa_llevada_por_vendedora')
CLAVE_CONTEXTO = 'dcasa_base_escribir_testigo'
# Un objeto, no ``True``: el contexto que llega por RPC es JSON y nunca puede traerlo.
ESCRIBIR = object()


class SaleOrderOnline(models.Model):
    _inherit = 'sale.order'

    dcasa_nacio_en_web = fields.Boolean(
        'Nació en la tienda en línea', readonly=True, copy=False, index=True,
        help='Se escribe una sola vez al crear el pedido: si nació en la página web. Nadie lo cambia a mano.')
    dcasa_via_andres = fields.Boolean(
        'Pasó por Andrés', readonly=True, copy=False,
        help='El carrito de este pedido lo armó o lo tocó Andrés, el chat de la tienda. Toda venta de Andrés cuenta '
             'como venta online.')
    dcasa_llevada_por_vendedora = fields.Boolean(
        'La llevó una vendedora', readonly=True, copy=False,
        help='Una vendedora atendió al cliente en el chat de Juan antes de confirmar el pedido: aunque el pedido salga '
             'de la página web, la venta fue de ella y no es venta online.')
    dcasa_venta_online = fields.Boolean(
        'Venta online', compute='_compute_dcasa_venta_online', store=True, index=True,
        help='La definición única: nació en la web y no la llevó una vendedora, o pasó por Andrés. Una venta online '
             'jamás se atribuye a una vendedora (bono por meta, Inicio ni programa de vendedores).')

    @api.depends('dcasa_nacio_en_web', 'dcasa_via_andres', 'dcasa_llevada_por_vendedora')
    def _compute_dcasa_venta_online(self):
        for orden in self:
            orden.dcasa_venta_online = bool(
                orden.dcasa_via_andres or (orden.dcasa_nacio_en_web and not orden.dcasa_llevada_por_vendedora))

    @api.model_create_multi
    def create(self, vals_list):
        # Nadie fabrica el origen al crear: las marcas las pone el sistema.
        vals_list = [{k: v for k, v in vals.items() if k not in TESTIGOS} for vals in vals_list]
        ordenes = super().create(vals_list)
        if 'website_id' in self._fields:
            nacidas = ordenes.filtered(lambda o: o.website_id)
            if nacidas:
                nacidas._dcasa_escribir_marca(dcasa_nacio_en_web=True)
        return ordenes

    def _write(self, vals):
        if any(clave in vals for clave in TESTIGOS) and self.env.context.get(CLAVE_CONTEXTO) is not ESCRIBIR:
            raise UserError(self.env._(
                'El origen de la venta (si nació en la web, si pasó por Andrés o si la llevó una vendedora) lo pone '
                'el sistema una sola vez: no se cambia a mano.'))
        return super()._write(vals)

    def _dcasa_escribir_marca(self, **marcas):
        """Único camino para escribir las marcas de origen (solo código del sistema; ver arriba)."""
        pendientes = self.filtered(lambda o: any(o[clave] != valor for clave, valor in marcas.items()))
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
