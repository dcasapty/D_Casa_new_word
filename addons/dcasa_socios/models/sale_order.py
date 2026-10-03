from odoo import api, fields, models
from odoo.exceptions import UserError

from . import reglas as R

# Cómo pueden usarse los puntos en el carrito de la tienda web (parámetro
# ``dcasa_socios.puntos_en_carrito``). La dueña todavía no decidió: los dos modos están probados.
#   'premios': solo los premios de descuento del catálogo que edita Gerencia (por defecto).
#   'todo':    además, el socio elige cuántos puntos usar contra cualquier producto; el descuento
#              sale de canje.puntosPorDolar en puntos.json.
PARAM_PUNTOS_EN_CARRITO = 'dcasa_socios.puntos_en_carrito'
MODOS_PUNTOS_EN_CARRITO = ('premios', 'todo')


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dcasa_socio_codigo = fields.Char(related='partner_id.commercial_partner_id.dcasa_socio_codigo',
                                     string='Código de socio')
    dcasa_socio_saldo = fields.Integer(related='partner_id.commercial_partner_id.dcasa_saldo',
                                       string='Puntos del cliente')
    dcasa_referido_por_id = fields.Many2one(
        'res.partner', string='Invitado por', copy=False, index='btree_not_null',
        compute='_compute_dcasa_referido_por_id', store=True, readonly=False, precompute=True,
        domain="[('dcasa_socio_codigo', '!=', False)]",
        help='Quién invitó a este cliente (escribe su código DCA… o su nombre). Solo se registra si el '
             'cliente todavía no tiene padrino y no ha comprado con puntos; después no se cambia nunca.')
    dcasa_padrino_fijo = fields.Boolean(compute='_compute_dcasa_padrino_fijo')

    @api.depends('partner_id')
    def _compute_dcasa_referido_por_id(self):
        for order in self:
            padrino = order.partner_id.commercial_partner_id.dcasa_referido_por_id
            # El padrino ya registrado manda; si no hay, se conserva la propuesta (p. ej. el link web).
            order.dcasa_referido_por_id = padrino or order.dcasa_referido_por_id

    @api.depends('partner_id')
    def _compute_dcasa_padrino_fijo(self):
        for order in self:
            order.dcasa_padrino_fijo = bool(order.partner_id.commercial_partner_id.dcasa_referido_por_id)

    def action_confirm(self):
        # Los premios se sellan en la misma transacción que la venta: si alguno ya
        # no está disponible, la venta entera no se confirma. El permiso de escribir la
        # venta se comprueba ANTES de sellar premios con sudo (método público por RPC).
        self.check_access('write')
        for order in self:
            order.order_line.dcasa_canje_id._entregar(
                self.env.user.login, sale_order=order, partner=order.partner_id.commercial_partner_id)
        res = super().action_confirm()
        for order in self.filtered('dcasa_referido_por_id'):
            if not order.partner_id.commercial_partner_id._is_public():
                order.partner_id._dcasa_asignar_padrino(order.dcasa_referido_por_id)
        return res

    def _action_cancel(self):
        """Un pedido cancelado nunca consumió sus premios: los puntos vuelven con un asiento contrario
        (el libro no se edita). Vale para el carrito web y para la venta del mostrador."""
        for order in self:
            canjes = order.order_line.dcasa_canje_id
            if canjes:
                canjes._devolver_por_pedido(
                    self.env._('Se canceló el pedido %s. Te devolvimos los puntos.', order.name),
                    self.env.user.login)
        return super()._action_cancel()

    def _get_update_prices_lines(self):
        # La línea del premio la paga el socio con puntos: la tarifa no la toca.
        return super()._get_update_prices_lines().filtered(lambda line: not line.dcasa_canje_id)

    def action_dcasa_cobrar_premio(self):
        self.ensure_one()
        if self.state not in ('draft', 'sent'):
            raise UserError(self.env._('Los premios se cobran antes de confirmar la venta.'))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Cobrar premio'),
            'res_model': 'dcasa.cobrar.premio.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    # ------------------------------------------------------------------------
    # Puntos en el carrito de la tienda web
    # ------------------------------------------------------------------------

    @api.depends('order_line.product_uom_qty', 'order_line.product_id')
    def _compute_cart_info(self):
        super()._compute_cart_info()
        # El premio no es un producto más en la bolsa: no cuenta en el globo del carrito.
        for order in self:
            premios = order.website_order_line.filtered('dcasa_canje_id')
            if premios:
                order.cart_quantity -= int(sum(premios.mapped('product_uom_qty')))

    def _cart_update_line_quantity(self, line_id, quantity, **kwargs):
        """La línea del premio solo se quita (y eso devuelve los puntos): cambiarle la cantidad
        multiplicaría el descuento. El botón de la tienda no lo permite; esta guarda cubre la RPC."""
        linea = self.order_line.filtered(lambda sol: sol.id == line_id and sol.dcasa_canje_id)
        if linea and quantity > 0:
            return {
                'added_qty': 0,
                'line_id': linea.id,
                'quantity': linea.product_uom_qty,
                'warning': self.env._('El premio se usa una sola vez. Si no lo quieres, quítalo.'),
            }
        return super()._cart_update_line_quantity(line_id, quantity, **kwargs)

    def _verify_cart_after_update(self):
        res = super()._verify_cart_after_update()
        # Si la bolsa se achicó por debajo del premio o el código venció, el premio sale solo
        # y los puntos vuelven (se avisa en la página del carrito).
        aviso = self._dcasa_limpiar_premios_web()
        if aviso:
            self.shop_warning = aviso
        return res

    @api.model
    def _dcasa_modo_puntos_en_carrito(self):
        modo = self.env['ir.config_parameter'].sudo().get_param(PARAM_PUNTOS_EN_CARRITO, 'premios')
        return modo if modo in MODOS_PUNTOS_EN_CARRITO else 'premios'

    def _dcasa_socio_del_carrito(self):
        """La ficha de socio con la que paga este carrito, o vacío: hace falta sesión de la tienda
        (no el visitante público) y una ficha reclamada con PIN y activa. La misma ficha es cliente
        y socio (llave = celular)."""
        self.ensure_one()
        ficha = self.partner_id.commercial_partner_id.sudo()
        if not ficha or ficha._is_public() or not ficha.dcasa_socio_codigo or not ficha.dcasa_reclamada \
                or ficha.dcasa_socio_estado != 'activo':
            return self.env['res.partner']
        return ficha

    def _dcasa_lineas_premio(self):
        return self.order_line.filtered('dcasa_canje_id')

    def _dcasa_total_sin_premios(self):
        """Lo que paga el cliente antes del descuento con puntos (centavos)."""
        self.ensure_one()
        return R.a_centavos(sum((self.order_line - self._dcasa_lineas_premio()).mapped('price_total')))

    def _dcasa_limpiar_premios_web(self):
        """Antes de enseñar o cobrar el carrito: fuera las líneas de premios que ya no están pendientes
        (vencieron o se cancelaron) y, si el carrito se achicó por debajo del premio, se quita el
        premio y sus puntos vuelven. Devuelve el aviso para el socio, si lo hay."""
        self.ensure_one()
        if self.state != 'draft' or not self.website_id:
            return None
        aviso = None
        lineas = self._dcasa_lineas_premio().sudo()
        caducas = lineas.filtered(lambda line: line.dcasa_canje_id.estado != 'solicitado')
        if caducas:
            caducas.with_context(dcasa_soltar_canje=False).unlink()
            aviso = self.env._('El código de tu premio venció o se canceló: lo quitamos del carrito.')
        vivas = lineas - caducas
        if vivas and self._dcasa_total_sin_premios() < R.a_centavos(sum(vivas.dcasa_canje_id.mapped('valor'))):
            self._dcasa_quitar_puntos_web(
                self.env._('Tu carrito quedó por debajo del descuento del premio: te devolvimos los puntos.'))
            aviso = self.env._('Tu carrito quedó por debajo del descuento del premio: te devolvimos los puntos.')
        return aviso

    def _dcasa_valores_puntos_web(self):
        """Lo que necesita el carrito para pintar el paso «Usar mis puntos»."""
        self.ensure_one()
        reglas = R.cargar_reglas()
        socio = self._dcasa_socio_del_carrito()
        minimo = reglas['canje'].get('saldoMinimoParaCanjear') or 0
        valores = {
            'dcasa_socio': socio,
            'dcasa_modo_puntos': self._dcasa_modo_puntos_en_carrito(),
            'dcasa_reglas': reglas,
            'dcasa_fmt_puntos': R.como_puntos,
            'dcasa_fmt_dolares': R.como_dolares,
            'dcasa_premio_aplicado': self._dcasa_lineas_premio().dcasa_canje_id.filtered(
                lambda c: c.estado == 'solicitado')[:1],
            'dcasa_premios': self.env['dcasa.premio'],
            'dcasa_puntos_libres_max': 0,
            'dcasa_saldo': 0,
            'dcasa_minimo': minimo,
            'dcasa_total_centavos': 0,
        }
        if not socio or self.state != 'draft':
            return valores
        saldo = socio.dcasa_saldo
        total = self._dcasa_total_sin_premios()
        valores['dcasa_saldo'] = saldo
        valores['dcasa_total_centavos'] = total
        valores['dcasa_premios'] = self.env['dcasa.premio']._catalogo('descuento').filtered(
            lambda p: p.puntos >= minimo and R.a_centavos(p.valor) <= total)
        if valores['dcasa_modo_puntos'] == 'todo':
            try:
                cabe = min(saldo, R.puntos_que_caben(total, reglas))
            except R.FaltaConfigurar:
                cabe = 0  # sin la cifra en puntos.json, el canje libre no existe
            valores['dcasa_puntos_libres_max'] = cabe if cabe >= minimo else 0
        return valores

    def _dcasa_usar_puntos_web(self, premio=None, puntos=None):
        """El socio usa sus puntos en su carrito: se pide el canje (reserva los puntos, código de
        72 h) y se aplica a la orden como una línea negativa. Nunca deja saldo negativo ni un total
        negativo: solo cabe un premio por carrito y su valor no pasa del carrito."""
        self.ensure_one()
        socio = self._dcasa_socio_del_carrito()
        if not socio:
            raise UserError(self.env._('Para usar tus puntos entra a tu cuenta de socio.'))
        if self.state != 'draft':
            raise UserError(self.env._('Este pedido ya no es un carrito.'))
        self._dcasa_limpiar_premios_web()
        if self._dcasa_lineas_premio().filtered(lambda line: line.dcasa_canje_id.estado == 'solicitado'):
            raise UserError(self.env._('Ya tienes un premio en este carrito. Quítalo para elegir otro.'))
        reglas = R.cargar_reglas()
        total = self._dcasa_total_sin_premios()
        if total <= 0:
            raise UserError(self.env._('Tu carrito está vacío: agrega productos antes de usar tus puntos.'))
        Premio = self.env['dcasa.premio'].sudo()
        if not premio:
            if self._dcasa_modo_puntos_en_carrito() != 'todo':
                raise UserError(self.env._('En la tienda web los puntos se usan con los premios del catálogo.'))
            premio = Premio.search([('libre', '=', True)], limit=1)
            if not premio:
                raise UserError(self.env._('El canje libre no está configurado.'))
            if not isinstance(puntos, int) or isinstance(puntos, bool) or puntos <= 0:
                raise UserError(self.env._('Escribe cuántos puntos quieres usar.'))
            try:
                valor_centavos = R.centavos_de_puntos(puntos, reglas)
            except R.FaltaConfigurar as error:
                raise UserError(self.env._('El canje libre no está configurado.')) from error
        else:
            premio = premio.sudo()
            if premio.libre or premio.tipo != 'descuento' or premio not in Premio._catalogo('descuento'):
                raise UserError(self.env._('Ese premio no se puede usar en la tienda web.'))
            puntos = None
            valor_centavos = R.a_centavos(premio.valor)
        if valor_centavos > total:
            raise UserError(self.env._(
                'Ese descuento (%s) es mayor que tu carrito. Elige uno más pequeño.', R.como_dolares(valor_centavos)))
        canje = self.env['dcasa.canje']._pedir(socio, premio, puntos=puntos, origen='web')
        canje._aplicar_en_venta(self)
        return canje

    def _dcasa_quitar_puntos_web(self, motivo=None):
        """El socio quita el premio del carrito: se cancela el canje y los puntos vuelven."""
        self.ensure_one()
        lineas = self._dcasa_lineas_premio().sudo()
        lineas.dcasa_canje_id._cancelar_por_socio(motivo or self.env._('Quitaste el premio del carrito.'))
        lineas.with_context(dcasa_soltar_canje=False).unlink()
        return True


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    dcasa_canje_id = fields.Many2one('dcasa.canje', string='Premio cobrado', readonly=True, copy=False,
                                     index='btree_not_null', ondelete='restrict')

    def _dcasa_exenta_tope_descuento(self):
        # La línea de premio es negativa por diseño: la pagan los puntos, no la vendedora.
        return super()._dcasa_exenta_tope_descuento() or bool(self.dcasa_canje_id)

    def _is_sellable(self):
        # En el carrito, la línea del premio no enlaza a ningún producto ni cambia de cantidad.
        return super()._is_sellable() and not self.dcasa_canje_id

    def unlink(self):
        # En un carrito web, quitar la línea del premio (el botón «Quitar» de la tienda) devuelve los
        # puntos: si no, quedarían reservados hasta que el código venza. En el mostrador la vendedora
        # puede quitar la línea y el código sigue valiendo (se cobra en otra venta).
        if self.env.context.get('dcasa_soltar_canje', True):
            web = self.filtered(lambda line: line.dcasa_canje_id and line.order_id.website_id
                                and line.order_id.state == 'draft')
            web.sudo().dcasa_canje_id._cancelar_por_socio(self.env._('Quitaste el premio del carrito.'))
        return super().unlink()
