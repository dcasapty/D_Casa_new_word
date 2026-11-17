from odoo import api, fields, models
from odoo.addons.dcasa_invoice.models import lineas as lineas_factura
from odoo.exceptions import AccessError, UserError

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
            # Última red (revisión adversarial, 2026-11-16): una venta con premio nunca se confirma en negativo, por
            # el camino que sea. Lo normal es que no llegue aquí (_aplicar_en_venta ya lo frena al poner el premio),
            # pero el precio de los productos puede bajar DESPUÉS de aplicarlo.
            if order.order_line.dcasa_canje_id and order.currency_id.compare_amounts(order.amount_total, 0.0) < 0:
                raise UserError(self.env._(
                    'Esta venta queda en negativo (%s) por el premio del programa Socios. Quita el premio o agrega '
                    'productos antes de confirmarla.', order.currency_id.format(order.amount_total)))
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

    def _set_delivery_method(self, delivery_method, rate=None):
        # Al elegir la entrega (en el pago, o /shop/payment al rehacer el carrito) el envío puede cambiar: el premio se
        # vuelve a revisar para que el total nunca quede negativo.
        resultado = super()._set_delivery_method(delivery_method, rate=rate)
        for orden in self:
            aviso = orden._dcasa_limpiar_premios_web()
            if aviso:
                orden.shop_warning = aviso
        return resultado

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
        """Lo que paga el cliente por los PRODUCTOS antes del descuento con puntos (centavos). El envío no cuenta (ni el
        flete): el que suma el chat de la tienda (dcasa_brian_tienda) puede irse al pagar, cuando la tienda vuelve a
        «te cotizamos» ($0), y un premio que solo cabía gracias al envío dejaría el total negativo (revisión
        adversarial, 2026-11-16). Antes de esa suma los carritos web no tenían envío con precio: es lo de siempre."""
        self.ensure_one()
        lineas = self.order_line - self._dcasa_lineas_premio()
        fletes = lineas_factura.productos_de_flete(lineas.product_id)
        productos = lineas.filtered(lambda line: not line.is_delivery and line.product_id not in fletes)
        return R.a_centavos(sum(productos.mapped('price_total')))

    def _dcasa_envio_que_cuesta_el_premio(self, valor_centavos, puesto=False):
        """Lo que el socio pagaría DE MÁS en el envío por usar un premio de ``valor_centavos`` en este carrito,
        porque la compra queda por debajo del mínimo de la promoción de envío. ``0.0`` si no pierde nada.

        Decisión de la dueña (2026-11-17): «avisarle y no dejar canjear». La revisión adversarial encontró que un
        premio podía tirar la compra por debajo del mínimo y hacerle perder el envío gratis: gastaba puntos para
        pagar más. Aquí solo se MIDE; quien llama decide. ``puesto`` dice si el premio ya está en el carrito (al
        limpiar) o todavía no (al canjear).

        El mínimo lo mide ``dcasa_envios``, que es su dueño, y no siempre está instalado (las pruebas de Socios
        corren solas): sin él no hay promoción que perder y esto devuelve ``0.0``."""
        self.ensure_one()
        if not valor_centavos or not hasattr(self, '_dcasa_promocion_si_la_compra_cambia'):
            return 0.0
        # Cuánto mueve la compra medida la línea del premio: la base sin ITBMS y el valor entero con ITBMS, igual que
        # la pone dcasa.canje._aplicar_en_venta. Tomarlos por igual se equivoca por el impuesto y el aviso mentiría.
        valor = valor_centavos / 100.0
        base = self.env['dcasa.canje']._dcasa_impuestos_y_base(valor, self.company_id)[1]
        if puesto:   # ya está en el carrito: «sin premio» es devolverle lo que el premio le bajó
            sin_premio = self._dcasa_promocion_si_la_compra_cambia(base, valor)[1]
            con_premio = self._dcasa_promocion_si_la_compra_cambia()[1]
        else:        # todavía no está: «con premio» es la compra de ahora menos lo que le bajaría
            sin_premio = self._dcasa_promocion_si_la_compra_cambia()[1]
            con_premio = self._dcasa_promocion_si_la_compra_cambia(-base, -valor)[1]
        perdida = sin_premio - con_premio
        return perdida if perdida > 0 else 0.0

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
        # Red: un total negativo nunca (p. ej. si el envío cambió al pagar); los puntos vuelven.
        if vivas and (self._dcasa_total_sin_premios() < R.a_centavos(sum(vivas.dcasa_canje_id.mapped('valor')))
                      or self.currency_id.compare_amounts(self.amount_total, 0.0) < 0):
            self._dcasa_quitar_puntos_web(
                self.env._('Tu carrito quedó por debajo del descuento del premio: te devolvimos los puntos.'))
            aviso = self.env._('Tu carrito quedó por debajo del descuento del premio: te devolvimos los puntos.')
        # Y si el carrito cambió de modo que el premio ahora le cuesta la promoción del envío (y eso le sale igual o
        # más caro que el propio descuento), los puntos vuelven antes de que pague: la dueña eligió que un premio
        # nunca le salga más caro al socio (2026-11-17). Se vuelve a leer porque el bloque de arriba pudo quitarlo.
        puestas = self._dcasa_lineas_premio().sudo().filtered(
            lambda line: line.dcasa_canje_id.estado == 'solicitado')
        if puestas:
            valor = R.a_centavos(sum(puestas.dcasa_canje_id.mapped('valor')))
            if self._dcasa_premio_no_conviene(valor, puesto=True):
                texto = self.env._('Tu carrito cambió y con el premio perderías la promoción del envío: te '
                                   'devolvimos los puntos para que no pagues más.')
                self._dcasa_quitar_puntos_web(texto)
                aviso = texto
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

    def _dcasa_premio_no_conviene(self, valor_centavos, puesto=False):
        """¿Un premio de ``valor_centavos`` en este carrito le sale al socio igual o más caro que su descuento, por
        hacerle perder la promoción del envío? Devuelve lo que pagaría de envío (dinero) o ``0.0``."""
        self.ensure_one()
        perdida = self._dcasa_envio_que_cuesta_el_premio(valor_centavos, puesto=puesto)
        return perdida if perdida and R.a_centavos(perdida) >= valor_centavos else 0.0

    def _dcasa_exigir_que_el_premio_convenga(self, valor_centavos):
        """El premio nunca puede salirle más caro que su descuento (la dueña, 2026-11-17: «avisarle y no dejar
        canjear»): si al usarlo la compra baja del mínimo de la promoción del envío y el envío que pagaría iguala o
        pasa lo que le descuenta el premio, se le avisa y no se canjea. Sus puntos no se mueven: el canje ni se pide.
        Si le sigue conviniendo (el descuento es mayor que el envío que perdería), se deja."""
        self.ensure_one()
        perdida = self._dcasa_premio_no_conviene(valor_centavos)
        if not perdida:
            return
        raise UserError(self.env._(
            'Con ese premio tu compra baja de lo que pide la promoción del envío, así que pagarías %(envio)s de '
            'envío y el premio solo te descuenta %(premio)s: te saldría más caro. Guarda tus puntos para la próxima '
            'o agrega algo al carrito.',
            envio=R.como_dolares(R.a_centavos(perdida)), premio=R.como_dolares(valor_centavos)))

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
        self._dcasa_exigir_que_el_premio_convenga(valor_centavos)
        canje = self.env['dcasa.canje']._pedir(socio, premio, puntos=puntos, origen='web')
        canje._aplicar_en_venta(self)
        return canje

    def _dcasa_quitar_puntos_web(self, motivo=None):
        """El socio quita el premio del carrito: se cancela el canje y los puntos vuelven. Y si con el premio puesto
        la compra había bajado del mínimo de la promoción del envío, se vuelve a ofrecer: el sincronizador de envíos
        solo quita esa línea, nunca la repone, así que sin esto el socio se quedaba sin puntos Y sin envío gratis."""
        self.ensure_one()
        lineas = self._dcasa_lineas_premio().sudo()
        lineas.dcasa_canje_id._cancelar_por_socio(motivo or self.env._('Quitaste el premio del carrito.'))
        lineas.with_context(dcasa_soltar_canje=False).unlink()
        if hasattr(self, '_dcasa_promocion_volver_a_ofrecer'):
            self._dcasa_promocion_volver_a_ofrecer()
        return True


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    dcasa_canje_id = fields.Many2one('dcasa.canje', string='Premio cobrado', readonly=True, copy=False,
                                     index='btree_not_null', ondelete='restrict')

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get('dcasa_canje_id') for vals in vals_list):
            self._dcasa_exigir_servidor_para_el_premio()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('dcasa_canje_id'):
            self._dcasa_exigir_servidor_para_el_premio()
        return super().write(vals)

    @api.model
    def _dcasa_exigir_servidor_para_el_premio(self):
        """La marca «premio cobrado» exime a la línea del tope de descuento: solo la pone el servidor al aplicar un
        canje (``dcasa.canje._aplicar_en_venta``) o Gerencia. Si la vendedora pudiera escribirla a mano, bastaría con
        apuntar a cualquier canje para meter una rebaja sin tope (revisión adversarial, 2026-10-16)."""
        usuario = self.env.user
        if (self.env.su or self.env.context.get('dcasa_aplicando_premio')
                or usuario.has_group('sales_team.group_sale_manager') or usuario.has_group('base.group_system')):
            return
        raise AccessError(self.env._(
            'El premio canjeado lo pone el sistema al aplicar el código, no se escribe a mano.'))

    def _dcasa_exenta_tope_descuento(self):
        # La línea de premio es negativa por diseño: la pagan los puntos, no la vendedora.
        return super()._dcasa_exenta_tope_descuento() or bool(self.dcasa_canje_id)

    def _dcasa_pagada_por_el_programa(self):
        return super()._dcasa_pagada_por_el_programa() or bool(self.dcasa_canje_id)

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

    def _dcasa_etiqueta(self):
        """La línea con que se cobró un premio se imprime identificada como tal."""
        if self.dcasa_canje_id:
            return "Premio Socios D'CASA"
        return super()._dcasa_etiqueta()

    def _dcasa_va_aparte(self):
        """El premio es un descuento, no un servicio que se cobra: se queda entre los muebles."""
        if self.dcasa_canje_id:
            return False
        return super()._dcasa_va_aparte()
