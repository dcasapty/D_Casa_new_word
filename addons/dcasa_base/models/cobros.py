"""Quién cobra, quién deshace y quién devuelve dinero (decisiones de la gerencia, 17 oct 2026).

Ver docs/DECISIONES_CONTABLES.md (A5, A6 y A7) y docs/PERMISOS.md.

* **A5 · El cobro solo en Caja.** Registrar el cobro de un cliente (el asistente «Pagar», un cobro suelto, Brian, el
  Inicio), aplicarle a una factura un cobro que ya estaba, o tocar un cobro hecho, es de **Caja**, **Gerencia**,
  contabilidad (contador o administrador contable) y los administradores. La Vendedora ya no cobra por ningún camino,
  con «Cada vendedora ve solo sus documentos» encendido o apagado (Caja es su propio rol, no «todos los documentos»).
  Sigue cotizando, confirmando y facturando.
* **A6 · Pasar a borrador o anular** una factura, nota o recibo de cliente **publicado**: solo **Gerencia** y los
  administradores. Caja y contabilidad incluidas, el servidor lo niega.
* **A7 · Notas de crédito** de clientes, **devolverle dinero** a un cliente (cobro saliente) y **dejarle saldo a favor**
  (cobrar de más y dejarlo abierto) o dar una factura por pagada con una diferencia: solo **Gerencia** y los
  administradores.
* **A5 también para el pago en línea (R7-1, R8-1, R8-2, R8-6, R9-1 a R9-3; revisiones RV7, RV8 y RV8b).** La
  transacción de un pago en línea (``payment.transaction``, de cualquier proveedor: Yappy, Tilopay…) es lo que el cron
  convierte en cobro y en pedido confirmado. Facturación (que la Vendedora trae implícita) puede escribir y crear en
  ella por el permiso de fábrica de Odoo; con un ``write(state='done')`` dejaba un pedido pagado sin dinero y sin
  pasar por Caja. Ahora, quien no cobra **no escribe NADA ni crea** en la transacción (lista blanca vacía: ningún flujo
  legítimo lo hace; todo lo del sistema corre con ``sudo``), ni la devuelve, captura o anula (``action_refund``,
  ``action_capture`` y ``action_void`` del core corren con ``sudo`` después de mirar solo el ACL). Y la otra mitad de
  la misma relación, ``sale.order.transaction_ids`` y ``account.move.transaction_ids``, tampoco: ligar un cobro ajeno
  a un pedido o a una factura soltaba mercancía sin cobrar o aplicaba el dinero de un cliente a la factura de otro.
  Se niega en ``write`` (mirando ``vals``) y en ``create`` **después de crear**, mirando lo que el documento trae
  (``default_transaction_ids`` del contexto no pasa por ``vals``). Lo que escribe el propio sistema (la pasarela, el
  aviso del proveedor, el cron, ``sale._create_invoices``) corre con ``sudo`` y no cambia.

Todo se comprueba aquí, en el servidor (esconder un botón no basta): asistente, Brian, Inicio, Conversaciones o RPC
llegan a los mismos métodos. El superusuario y lo que corre con ``sudo`` (la tienda web, Juan, el cron, la carga del
sistema anterior) no cambian. Lo de proveedores tampoco: sigue siendo de contabilidad, como antes.
"""
from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import AccessError

CLIENTE = ('out_invoice', 'out_refund', 'out_receipt')
# Quien registra cobros de clientes. Gerencia incluye Caja y contabilidad.
COBRAN = ('dcasa_base.group_caja', 'account.group_account_user', 'account.group_account_manager', 'base.group_system')
# Quien anula, pasa a borrador, hace notas de crédito, devuelve dinero o deja saldo a favor.
GERENCIA = ('dcasa_base.group_gerencia', 'base.group_system')
# Lo que cambia el dinero de un cobro ya hecho (quién, cuánto, cuándo, por dónde, en qué estado).
CAMPOS_DEL_COBRO = {
    'amount', 'payment_type', 'partner_type', 'partner_id', 'journal_id', 'date', 'currency_id',
    'payment_method_line_id', 'destination_account_id', 'state', 'partner_bank_id', 'outstanding_account_id',
}


def mensaje_cobro(env):
    return env._('Los cobros los registra Caja. Pídele a Caja (o a Gerencia) que cobre esta factura.')


def mensaje_cobros_ligados(env):
    return env._('Los cobros ligados a un pedido o a una factura los mueve el sistema o Caja (Caja, Gerencia, '
                 'contabilidad). No se puede cambiar desde aquí.')


def mensaje_tipo_de_documento(env):
    return env._('Cambiar el tipo de un documento de cliente (factura, recibo, nota de crédito) lo hace Caja o '
                 'Gerencia; una nota de crédito, solo Gerencia.')


def exigir_que_ligue_cobros(env):
    """R8-1: quien no cobra (la Vendedora, Facturación) no escribe ``transaction_ids`` de un pedido ni de una factura
    (``sudo`` pasa)."""
    if not env.su and not env.user._dcasa_puede_cobrar():
        raise AccessError(mensaje_cobros_ligados(env))


def mensaje_reembolso(env):
    return env._('Devolverle dinero a un cliente lo registra solo Gerencia. Pídeselo a Gerencia.')


def mensaje_nota(env):
    return env._('Las notas de crédito de clientes las hace solo Gerencia. Pídesela a Gerencia.')


def mensaje_cotizar(env):
    return env._('Las ventas se hacen como cotización: Ventas › Nueva cotización. Al confirmarla, la factura sale del '
                 'pedido y Caja la encuentra para cobrar.')


def mensaje_anular(env, nombre):
    return env._('La factura %s ya está publicada: pasarla a borrador o anularla lo hace solo Gerencia. '
                 'Pídeselo a Gerencia.', nombre)


def monto(valor):
    """107.5 → «$107.50» (USD, la moneda de D'CASA)."""
    return f'${float(valor or 0.0):,.2f}'


def exigir_cobro(env):
    """Lanza ``AccessError`` si quien está conectado no registra cobros de clientes (``sudo`` pasa)."""
    if not env.su and not env.user._dcasa_puede_cobrar():
        raise AccessError(mensaje_cobro(env))


def exigir_gerencia(env, mensaje):
    """Lanza ``AccessError`` con ``mensaje`` si quien está conectado no es Gerencia ni administrador (``sudo`` pasa)."""
    if not env.su and not env.user._dcasa_es_gerencia():
        raise AccessError(mensaje)


def toca_clientes(lineas):
    """¿Algún apunte es de una cuenta por cobrar (lo que deben los clientes)?"""
    return any(linea.account_id.account_type == 'asset_receivable' for linea in lineas.sudo())


def pago_en_linea_de_su_factura(lineas):
    """¿Los cobros entre ``lineas`` son pagos en línea (una transacción de la tienda) de las facturas que también están
    ahí? Es lo que Odoo cruza solo al publicar la factura de un pedido ya pagado en la web (``sale`` ``_post``): el
    dinero ya entró y no lo registra nadie a mano, así que quien factura (la Vendedora) puede publicarla. Sale de los
    datos (la transacción une el pago con la factura), no de algo que se pueda mandar por RPC."""
    lineas = lineas.sudo()
    pagos = lineas.move_id.origin_payment_id
    facturas = lineas.move_id.filtered(lambda m: m.is_invoice(include_receipts=True))
    if not pagos or not facturas or 'transaction_ids' not in facturas._fields:
        return False
    return pagos <= facturas.transaction_ids.payment_id


def sin_nuevo(resultado):
    """El resultado de ``get_view`` sin el botón «Nuevo» (``create="0"`` en la raíz)."""
    nodo = etree.fromstring(resultado['arch'])
    nodo.set('create', '0')
    return dict(resultado, arch=etree.tostring(nodo, encoding='unicode'))


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _dcasa_puede_cobrar(self):
        """¿Registra cobros de clientes? Caja, Gerencia, contabilidad y administradores. Sin registro, quien mira."""
        usuario = self[:1] or self.env.user
        return usuario._is_superuser() or any(usuario.has_group(grupo) for grupo in COBRAN)

    def _dcasa_es_gerencia(self):
        """¿Es Gerencia (o administrador)? Anula, pasa a borrador, hace notas de crédito y devuelve dinero."""
        usuario = self[:1] or self.env.user
        return usuario._is_superuser() or any(usuario.has_group(grupo) for grupo in GERENCIA)


class AccountMove(models.Model):
    _inherit = 'account.move'

    dcasa_puede_cobrar = fields.Boolean(
        compute='_compute_dcasa_permisos_caja',
        help='Quien mira registra cobros de clientes (Caja, Gerencia, contabilidad o administrador).')
    dcasa_es_gerencia = fields.Boolean(
        compute='_compute_dcasa_permisos_caja',
        help='Quien mira es Gerencia o administrador: anula, pasa a borrador y hace notas de crédito.')

    @api.depends_context('uid')
    def _compute_dcasa_permisos_caja(self):
        puede_cobrar = self.env.user._dcasa_puede_cobrar()
        es_gerencia = self.env.user._dcasa_es_gerencia()
        for move in self:
            move.dcasa_puede_cobrar = puede_cobrar
            move.dcasa_es_gerencia = es_gerencia

    # --- A7: notas de crédito ----------------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            por_defecto = self.env.context.get('default_move_type')
            if any(vals.get('move_type', por_defecto) == 'out_refund' for vals in vals_list):
                exigir_gerencia(self.env, mensaje_nota(self.env))
        moves = super().create(vals_list)
        # R8-1 y R9-2: un documento que quien no cobra acaba de crear no nace con cobros ligados. Se mira DESPUÉS de
        # crear y lo que el documento trae (no ``vals``): ``default_transaction_ids`` del contexto no pasa por
        # ``vals``. La factura de un pedido ya cobrado nace con el cobro de su propio pedido por
        # ``sale._create_invoices``, que corre con ``sudo``: no se afecta. La regla «quien no cobra no hace facturas
        # sueltas» (más abajo) NO basta: solo mira ``out_invoice`` y un recibo de venta (``out_receipt``) se escapaba.
        if not self.env.su and moves.sudo().transaction_ids:
            exigir_que_ligue_cobros(self.env)
        moves._dcasa_exigir_que_salga_del_pedido()
        return moves

    # --- Facturas sueltas: quien no cobra, cotiza ------------------------------------------------------------------
    def _dcasa_sueltas(self):
        """Las facturas de cliente que no salieron de un pedido de venta (ninguna línea con ``sale_line_ids``)."""
        return self.sudo().filtered(lambda m: m.move_type == 'out_invoice' and not m.line_ids.sale_line_ids)

    def _dcasa_exigir_que_salga_del_pedido(self):
        """Quien no cobra solo tiene facturas de cliente que salen de un pedido. Odoo las crea desde el pedido (y los
        anticipos) con ``sudo``: ese camino no cambia."""
        if not self.env.su and not self.env.user._dcasa_puede_cobrar() and self._dcasa_sueltas():
            raise AccessError(mensaje_cotizar(self.env))

    def _post(self, soft=True):
        if not self.env.su and self.filtered(lambda m: m.move_type == 'out_refund'):
            exigir_gerencia(self.env, mensaje_nota(self.env))
        return super()._post(soft=soft)

    def action_reverse(self):
        if self.filtered(lambda m: m.move_type in CLIENTE):
            exigir_gerencia(self.env, mensaje_nota(self.env))
        return super().action_reverse()

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        """Facturas de cliente (Facturación › Facturas y las facturas de un pedido, que abren la misma acción): a quien
        no cobra no le sale «Nuevo», que solo daría el aviso de cotizar. La pantalla no manda el contexto de la acción
        al pedir las vistas (solo ``lang`` y ``*_view_ref``), sí su ``action_id``. Después de la caché de vistas, como
        en los pagos."""
        resultado = super().get_view(view_id, view_type, **options)
        if view_type in ('list', 'form', 'kanban') and not self.env.su and not self.env.user._dcasa_puede_cobrar():
            facturas = self.env.ref('account.action_move_out_invoice_type', raise_if_not_found=False)
            if (self.env.context.get('default_move_type') == 'out_invoice'
                    or (facturas and options.get('action_id') == facturas.id)):
                resultado = sin_nuevo(resultado)
        return resultado

    # --- A6: pasar a borrador o anular -------------------------------------------------------------------------
    def _dcasa_exigir_gerencia_para_deshacer(self):
        publicadas = self.filtered(lambda m: m.move_type in CLIENTE and m.state == 'posted')
        if publicadas:
            exigir_gerencia(self.env, mensaje_anular(self.env, ', '.join(publicadas.mapped('name'))))

    def button_draft(self):
        self._dcasa_exigir_gerencia_para_deshacer()
        return super().button_draft()

    def button_cancel(self):
        self._dcasa_exigir_gerencia_para_deshacer()
        return super().button_cancel()

    def _dcasa_exigir_quien_cambia_el_tipo(self, nuevo):
        """R9-2: cambiar el tipo de un documento de cliente (recibo ↔ factura ↔ nota de crédito) es de Caja o Gerencia,
        y todo lo que toque una nota de crédito, de Gerencia (A7). Sin esto, ``write({'move_type': 'out_invoice'})``
        volvía factura un recibo y ``'out_refund'`` creaba una nota de crédito en borrador sin Gerencia (el botón
        «Pasar a factura/nota de crédito» ya está escondido para quien no es Gerencia; esto es el servidor)."""
        cambian = self.sudo().filtered(lambda m: m.move_type != nuevo)
        tipos = set(cambian.mapped('move_type')) | {nuevo} if cambian else set()
        if not tipos & set(CLIENTE):
            return
        if 'out_refund' in tipos:
            exigir_gerencia(self.env, mensaje_nota(self.env))
        if not self.env.user._dcasa_puede_cobrar():
            raise AccessError(mensaje_tipo_de_documento(self.env))

    def write(self, vals):
        if 'transaction_ids' in vals:
            exigir_que_ligue_cobros(self.env)     # R8-1: la otra mitad de ``payment.transaction.invoice_ids``
        if 'move_type' in vals and not self.env.su:
            self._dcasa_exigir_quien_cambia_el_tipo(vals['move_type'])
        # Por RPC alguien podría escribir el estado a mano: la misma regla que los botones.
        if not self.env.su and vals.get('state') in ('draft', 'cancel'):
            self._dcasa_exigir_gerencia_para_deshacer()
        # Quitarle las líneas del pedido a una factura que salió de uno la dejaría suelta: la misma regla que al crear.
        del_pedido = self.browse()
        if not self.env.su and {'invoice_line_ids', 'line_ids'} & set(vals):
            del_pedido = self - self._dcasa_sueltas()
        resultado = super().write(vals)
        del_pedido._dcasa_exigir_que_salga_del_pedido()
        return resultado

    # --- A5: aplicar o quitar cobros desde la factura --------------------------------------------------------------
    def _dcasa_exigir_quien_toca_cobros(self):
        if self.filtered(lambda m: m.move_type == 'out_refund'):
            exigir_gerencia(self.env, mensaje_reembolso(self.env))
        if self.filtered(lambda m: m.move_type in CLIENTE):
            exigir_cobro(self.env)

    def js_assign_outstanding_line(self, line_id):
        if not pago_en_linea_de_su_factura(self.env['account.move.line'].browse(line_id) | self.line_ids):
            self._dcasa_exigir_quien_toca_cobros()
        return super().js_assign_outstanding_line(line_id)

    def js_remove_outstanding_partial(self, partial_id):
        self._dcasa_exigir_quien_toca_cobros()
        return super().js_remove_outstanding_partial(partial_id)

    def _dcasa_puede_tocar_cobros(self):
        """¿Quien mira puede aplicar o quitar cobros en esta factura? (la pantalla; el servidor lo vuelve a mirar)"""
        self.ensure_one()
        if self.move_type == 'out_refund':
            return self.env.user._dcasa_es_gerencia()
        if self.move_type in CLIENTE:
            return self.env.user._dcasa_puede_cobrar()
        return True

    @api.depends_context('uid')
    def _compute_payments_widget_reconciled_info(self):
        """Los pagos de la factura: a quien no puede quitarlos, el botón «Desconciliar» del globito no le sale."""
        super()._compute_payments_widget_reconciled_info()
        for move in self:
            widget = move.invoice_payments_widget
            if widget and widget.get('content') and not move._dcasa_puede_tocar_cobros():
                for linea in widget['content']:
                    linea['dcasa_sin_desconciliar'] = True


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def action_register_payment(self, ctx=None):
        """El botón «Pagar» (de la factura o de la lista) termina aquí: avisa antes de abrir el asistente."""
        self.move_id._dcasa_exigir_quien_toca_cobros()
        return super().action_register_payment(ctx=ctx)

    def reconcile(self):
        """Cruzar lo que debe un cliente con un cobro es cobrar: también por aquí (RPC), solo quien cobra. Salvo el pago
        en línea que Odoo cruza solo con su factura al publicarla."""
        if not self.env.su and toca_clientes(self) and not pago_en_linea_de_su_factura(self):
            exigir_cobro(self.env)
        return super().reconcile()


class AccountPartialReconcile(models.Model):
    _inherit = 'account.partial.reconcile'

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            ids = {vals.get(campo) for vals in vals_list for campo in ('debit_move_id', 'credit_move_id')} - {None}
            lineas = self.env['account.move.line'].browse([i for i in ids if isinstance(i, int)])
            if toca_clientes(lineas) and not pago_en_linea_de_su_factura(lineas):
                exigir_cobro(self.env)
        return super().create(vals_list)

    def unlink(self):
        if not self.env.su and toca_clientes(self.sudo().debit_move_id | self.sudo().credit_move_id):
            exigir_cobro(self.env)
        return super().unlink()


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    dcasa_puede_tocar = fields.Boolean(
        compute='_compute_dcasa_puede_tocar',
        help='Quien mira puede publicar, pasar a borrador o cancelar este cobro (de un cliente: quien cobra; una '
             'devolución a un cliente: Gerencia). Los botones se esconden a los demás; el servidor lo vuelve a mirar.')

    @api.depends_context('uid')
    @api.depends('payment_type', 'partner_type')
    def _compute_dcasa_puede_tocar(self):
        puede_cobrar = self.env.user._dcasa_puede_cobrar()
        es_gerencia = self.env.user._dcasa_es_gerencia()
        for pago in self:
            if pago.partner_type != 'customer':
                pago.dcasa_puede_tocar = True
            elif pago.payment_type == 'outbound':
                pago.dcasa_puede_tocar = es_gerencia
            else:
                pago.dcasa_puede_tocar = puede_cobrar

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        """A quien no registra cobros (la Vendedora) las listas y el formulario de pagos no le ofrecen «Nuevo»: un
        botón que solo daría error. Se hace después de la caché de vistas (que es la misma para todos), como Odoo
        hace con los permisos del modelo."""
        resultado = super().get_view(view_id, view_type, **options)
        if view_type in ('list', 'form', 'kanban') and not self.env.su and not self.env.user._dcasa_puede_cobrar():
            resultado = sin_nuevo(resultado)
        return resultado

    @api.model
    def _dcasa_exigir_por_tipos(self, tipos):
        """``tipos`` [(payment_type, partner_type)]: cobro de cliente (entrante), quien cobra; devolución a un cliente
        (saliente), Gerencia."""
        if self.env.su:
            return
        de_clientes = [tipo for tipo, socio in tipos if socio == 'customer']
        if 'outbound' in de_clientes:
            exigir_gerencia(self.env, mensaje_reembolso(self.env))
        if de_clientes:
            exigir_cobro(self.env)

    def _dcasa_exigir_permiso(self):
        # El tipo se lee con sudo: el mensaje claro va antes que el «no tienes permiso» genérico de las reglas.
        self._dcasa_exigir_por_tipos([(p.payment_type, p.partner_type) for p in self.sudo()])

    @api.model_create_multi
    def create(self, vals_list):
        # Antes de crear (las reglas de Caja solo dejan cobros entrantes: el mensaje claro va primero) y después.
        contexto = self.env.context
        self._dcasa_exigir_por_tipos([
            (vals.get('payment_type') or contexto.get('default_payment_type') or 'inbound',
             vals.get('partner_type') or contexto.get('default_partner_type') or 'customer') for vals in vals_list])
        pagos = super().create(vals_list)
        pagos._dcasa_exigir_permiso()
        return pagos

    def write(self, vals):
        if not self.env.su and CAMPOS_DEL_COBRO & set(vals):
            self._dcasa_exigir_permiso()
            resultado = super().write(vals)
            self._dcasa_exigir_permiso()  # también como queda (p. ej. si pasó de proveedor a cliente)
            return resultado
        return super().write(vals)

    def unlink(self):
        self._dcasa_exigir_permiso()
        return super().unlink()

    def action_post(self):
        self._dcasa_exigir_permiso()
        return super().action_post()

    def action_draft(self):
        self._dcasa_exigir_permiso()
        return super().action_draft()

    def action_cancel(self):
        self._dcasa_exigir_permiso()
        return super().action_cancel()


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    dcasa_es_gerencia = fields.Boolean(
        compute='_compute_dcasa_es_gerencia',
        help='Quien cobra es Gerencia: puede dejar saldo a favor o dar la factura por pagada con una diferencia.')
    dcasa_aviso_saldo_a_favor = fields.Char(
        'Aviso del saldo a favor', compute='_compute_dcasa_aviso_saldo_a_favor',
        help='Cobrar más de lo que falta deja saldo a favor: lo autoriza solo Gerencia.')

    @api.depends_context('uid')
    def _compute_dcasa_es_gerencia(self):
        self.dcasa_es_gerencia = self.env.user._dcasa_es_gerencia()

    @api.depends('amount', 'payment_difference', 'can_edit_wizard', 'partner_type', 'payment_type')
    @api.depends_context('uid')
    def _compute_dcasa_aviso_saldo_a_favor(self):
        gerencia = self.env.user._dcasa_es_gerencia()
        for wizard in self:
            de_mas = (not gerencia and wizard.partner_type == 'customer' and wizard.payment_type == 'inbound'
                      and wizard.can_edit_wizard and wizard.currency_id
                      and wizard.currency_id.compare_amounts(wizard.payment_difference, 0) < 0)
            falta = monto(wizard.amount + wizard.payment_difference) if de_mas else ''
            wizard.dcasa_aviso_saldo_a_favor = self.env._(
                'Estás cobrando más de lo que falta (%s). Dejarle saldo a favor lo autoriza solo Gerencia: cobra '
                'hasta %s.', falta, falta) if de_mas else False

    def _dcasa_exigir_permiso(self):
        """El asistente «Pagar» de un cliente: quien cobra; devolver dinero, dejar saldo a favor o dar la factura por
        pagada con una diferencia, Gerencia. Corre antes de crear nada (también cuando lo llama Brian)."""
        self.ensure_one()
        if self.env.su or self.partner_type != 'customer':
            return
        if self.payment_type == 'outbound':
            exigir_gerencia(self.env, mensaje_reembolso(self.env))
        exigir_cobro(self.env)
        if not self.can_edit_wizard or self.early_payment_discount_mode:
            return
        moneda = self.currency_id
        diferencia = self.payment_difference
        if moneda.is_zero(diferencia):
            return
        if self.payment_difference_handling == 'reconcile':
            exigir_gerencia(self.env, self.env._(
                'Dar la factura por pagada con una diferencia lo autoriza solo Gerencia. Registra lo que el cliente '
                'pagó y deja el resto pendiente.'))
        elif moneda.compare_amounts(diferencia, 0) < 0:
            exigir_gerencia(self.env, self.env._(
                'Estás cobrando más de lo que falta (%s). Dejarle saldo a favor al cliente lo autoriza solo Gerencia: '
                'cobra hasta %s.', monto(self.amount + diferencia), monto(self.amount + diferencia)))

    def _create_payments(self):
        self._dcasa_exigir_permiso()
        return super()._create_payments()


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model_create_multi
    def create(self, vals_list):
        if any('transaction_ids' in vals for vals in vals_list):
            exigir_que_ligue_cobros(self.env)
        pedidos = super().create(vals_list)
        # R9-1: ``default_transaction_ids`` del contexto (por RPC cualquiera lo manda) no pasa por ``vals`` y Odoo lo
        # aplica al crear: se mira lo que el pedido trae DESPUÉS de crear, como ``enlace_factura.py`` hace con
        # ``sale_line_ids``. Un pedido que quien no cobra acaba de crear nunca nace con cobros.
        if not self.env.su and pedidos.sudo().transaction_ids:
            exigir_que_ligue_cobros(self.env)
        return pedidos

    def write(self, vals):
        """R8-1: ligar o soltar el cobro de un pedido (``transaction_ids``, que la Vendedora puede escribir por
        Facturación) lo hace el sistema o Caja. Un cobro ajeno ligado hacía que Bodega viera «pagada» una entrega que no
        se cobró; soltar el propio escondía un pago hecho (y el apartado nocturno anulaba el pedido)."""
        if 'transaction_ids' in vals:
            exigir_que_ligue_cobros(self.env)
        return super().write(vals)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _dcasa_exigir_que_la_mueva_el_sistema_o_caja(self, que):
        """Quien no cobra no escribe ni crea NADA en una transacción de pago en línea. Es una lista BLANCA y está
        vacía: ningún flujo legítimo de quien no cobra escribe aquí (la pasarela, el aviso del proveedor, el cron y el
        botón de Caja corren con ``sudo``), y una lista negra de campos dejaba abiertos el cliente al que se acredita el
        dinero, la ruta a la que se manda el navegador de la clienta y el mensaje que ella lee (RV8, R8-2)."""
        if not self.env.su and not self.env.user._dcasa_puede_cobrar():
            raise AccessError(self.env._(
                'Los pagos en línea los mueve el sistema, con el aviso de la pasarela, o Caja, Gerencia y '
                'contabilidad. No se puede cambiar: %s.', que))

    @api.model_create_multi
    def create(self, vals_list):
        """R8-6: tampoco se CREA una transacción (antes solo se negaba por casualidad, porque leer el proveedor es de
        administrador; con la caché «tibia» de un proveedor ya leído el mismo ``create`` pasaba)."""
        if vals_list:
            self._dcasa_exigir_que_la_mueva_el_sistema_o_caja(self.env._('crear una transacción'))
        return super().create(vals_list)

    def write(self, vals):
        """R7-1 y R8-2: quien no cobra (la Vendedora, que por Facturación puede escribir en la transacción) no
        escribe nada. Sin esto, un ``write(state='done')`` hacía que el cron confirmara el pedido y creara el cobro sin
        dinero y sin pasar por Caja."""
        if vals:
            self._dcasa_exigir_que_la_mueva_el_sistema_o_caja(', '.join(sorted(vals)))
        return super().write(vals)

    # R9-3: métodos PÚBLICOS del core que corren con ``sudo`` después de mirar solo el ACL: sin esto, quien no cobra
    # (Facturación) creaba transacciones hijas de devolución («R-…», -107.00) con ``action_refund``.
    def action_refund(self, amount_to_refund=None):
        self._dcasa_exigir_que_la_mueva_el_sistema_o_caja(self.env._('devolver un cobro'))
        return super().action_refund(amount_to_refund=amount_to_refund)

    def action_capture(self):
        self._dcasa_exigir_que_la_mueva_el_sistema_o_caja(self.env._('capturar un cobro'))
        return super().action_capture()

    def action_void(self):
        self._dcasa_exigir_que_la_mueva_el_sistema_o_caja(self.env._('anular un cobro'))
        return super().action_void()
