"""Cerrar los saldos de centavos (decisión D1 de la gerencia: «ajustar los saldos de un centavo»).

Una factura cobrada casi entera que queda debiendo 1 a 5 centavos (el ITBMS se redondea línea por línea, el cliente
pagó la cifra redonda, la caja dio el vuelto con monedas), o un cobro al que le sobran centavos, se quedan abiertos
para siempre y ensucian «Por cobrar». Aquí se ven todos, con vista previa, y se cierran con el ajuste contable de
siempre (como la «diferencia» del asistente de pago de Odoo): un asiento en un diario de operaciones varias contra la
cuenta de **diferencias** de la empresa (``default_cash_difference_expense_account_id`` si la tienda pierde los
centavos, ``default_cash_difference_income_account_id`` si los gana; la contadora puede cambiarlas en Ajustes de
Contabilidad), cruzado con el saldo que quedaba.

**Rango: de 1 a 5 centavos (``MAX_CENTAVOS``), fijo.** No es una cifra del negocio: es redondeo. Con el ITBMS del 7 %
calculado por línea, cada línea puede desviarse medio centavo y una factura de varias líneas llega a 2 o 3; el vuelto
en monedas mueve hasta 5. Más de 5 centavos ya es dinero de verdad (un abono que no cuadra, un cobro equivocado) y se
trata por el camino normal: por eso el tope no se puede cambiar en pantalla.

Qué cuenta: facturas y notas de crédito de clientes publicadas **con algún pago aplicado** (``payment_state`` parcial)
y saldo de 1 a 5 centavos, y cobros de clientes **ya cruzados en parte** a los que les sobran de 1 a 5 centavos. Una
factura de 3 centavos sin ningún pago no es redondeo: no sale.

Lo cierran Gerencia, contabilidad (contador o gerente contable) y los administradores. Cada cierre deja una nota en
el documento con el asiento y quién lo hizo. No borra ni cambia nada publicado: agrega un asiento y lo cruza.
"""
from markupsafe import Markup, escape

from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError

MAX_CENTAVOS = 0.05
QUIENES_CIERRAN = ('dcasa_base.group_gerencia', 'account.group_account_user', 'account.group_account_manager',
                   'base.group_system')
TIPOS = [('factura', 'Factura'), ('nota', 'Nota de crédito'), ('cobro', 'Cobro con sobrante')]


def puede_cerrar(env):
    return env.su or any(env.user.has_group(grupo) for grupo in QUIENES_CIERRAN)


class DcasaSaldosCentavos(models.TransientModel):
    _name = 'dcasa.saldos.centavos'
    _description = 'Cerrar saldos de centavos (redondeo)'

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    linea_ids = fields.One2many('dcasa.saldos.centavos.linea', 'asistente_id', string='Saldos')
    cantidad = fields.Integer('Saldos', compute='_compute_totales')
    pierde = fields.Monetary('La tienda deja de cobrar', compute='_compute_totales')
    gana = fields.Monetary('La tienda se queda con', compute='_compute_totales')
    diario_id = fields.Many2one('account.journal', string='Diario', compute='_compute_cuentas')
    cuenta_perdida_id = fields.Many2one('account.account', string='Cuenta (lo que no se cobró)',
                                        compute='_compute_cuentas')
    cuenta_ganancia_id = fields.Many2one('account.account', string='Cuenta (lo que sobró)',
                                         compute='_compute_cuentas')
    falta = fields.Char(compute='_compute_cuentas')

    @api.model
    def default_get(self, fields_list):
        resultado = super().default_get(fields_list)
        if 'linea_ids' in fields_list:
            resultado['linea_ids'] = [Command.create(valores) for valores in self._dcasa_buscar()]
        return resultado

    @api.depends('linea_ids.saldo')
    def _compute_totales(self):
        for asistente in self:
            saldos = asistente.linea_ids.mapped('saldo')
            asistente.cantidad = len(saldos)
            asistente.pierde = sum(s for s in saldos if s > 0)
            asistente.gana = -sum(s for s in saldos if s < 0)

    @api.depends('company_id')
    def _compute_cuentas(self):
        for asistente in self:
            empresa = asistente.company_id.sudo()
            asistente.diario_id = asistente._dcasa_diario()
            asistente.cuenta_perdida_id = empresa.default_cash_difference_expense_account_id
            asistente.cuenta_ganancia_id = empresa.default_cash_difference_income_account_id
            faltan = []
            if not asistente.diario_id:
                faltan.append(self.env._('un diario de operaciones varias'))
            if not asistente.cuenta_perdida_id or not asistente.cuenta_ganancia_id:
                faltan.append(self.env._('las cuentas de diferencias (Ajustes de Contabilidad)'))
            asistente.falta = (self.env._('Falta %s: pídeselo a la contadora.', ' y '.join(faltan))
                               if faltan else False)

    @api.model
    def _dcasa_diario(self):
        return self.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', self.env.company.id)], order='sequence, id', limit=1)

    # ------------------------------------------------------------------
    # Buscar
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_buscar(self):
        """Los saldos de 1 a 5 centavos que son redondeo (ver arriba), como valores de línea."""
        if not puede_cerrar(self.env):
            raise AccessError(self.env._('Cerrar saldos de centavos lo hacen Gerencia y contabilidad.'))
        empresa = self.env.company
        moneda = empresa.currency_id
        apuntes = self.env['account.move.line'].search([
            ('company_id', '=', empresa.id), ('parent_state', '=', 'posted'), ('reconciled', '=', False),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('amount_residual', '>=', -MAX_CENTAVOS - 0.001), ('amount_residual', '<=', MAX_CENTAVOS + 0.001),
            ('amount_residual', '!=', 0.0),
        ], order='date, id')
        lineas = []
        for apunte in apuntes:
            tipo = self._dcasa_tipo(apunte, moneda)
            if tipo:
                lineas.append({'move_line_id': apunte.id, 'tipo': tipo, 'saldo': apunte.amount_residual})
        return lineas

    @api.model
    def _dcasa_tipo(self, apunte, moneda):
        """``factura``/``nota``/``cobro`` si ese saldo es un redondeo que se puede cerrar; si no, ``False``."""
        if apunte.currency_id and apunte.currency_id != moneda:
            return False
        if moneda.is_zero(apunte.amount_residual) or abs(apunte.amount_residual) > MAX_CENTAVOS + 0.0001:
            return False
        documento = apunte.move_id
        if documento.move_type in ('out_invoice', 'out_receipt', 'out_refund'):
            if documento.payment_state != 'partial':
                return False
            return 'nota' if documento.move_type == 'out_refund' else 'factura'
        cruzado = apunte.matched_debit_ids or apunte.matched_credit_ids
        if (documento.origin_payment_id or documento.statement_line_id) and cruzado:
            return 'cobro'
        return False

    # ------------------------------------------------------------------
    # Cerrar
    # ------------------------------------------------------------------

    def action_cerrar(self):
        self.ensure_one()
        if not puede_cerrar(self.env):
            raise AccessError(self.env._('Cerrar saldos de centavos lo hacen Gerencia y contabilidad.'))
        if self.falta:
            raise UserError(self.falta)
        moneda = self.currency_id
        cerrados = 0
        for linea in self.linea_ids:
            apunte = linea.move_line_id
            # Lo que se vio en la vista previa tiene que seguir igual: si cambió (alguien cobró o cruzó), se salta.
            if (not apunte or apunte.reconciled or moneda.compare_amounts(apunte.amount_residual, linea.saldo) != 0
                    or self._dcasa_tipo(apunte, moneda) != linea.tipo):
                continue
            self._dcasa_cerrar_uno(apunte)
            cerrados += 1
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'title': self.env._('Saldos de centavos'),
            'message': self.env._('Se cerraron %s saldos con su ajuste por redondeo.', cerrados),
            'next': {'type': 'ir.actions.act_window_close'}}}

    def _dcasa_cerrar_uno(self, apunte):
        """Un asiento de ajuste por redondeo y el cruce con el saldo que quedaba."""
        saldo = apunte.amount_residual
        cuenta = self.cuenta_perdida_id if saldo > 0 else self.cuenta_ganancia_id
        etiqueta = self.env._('Ajuste por redondeo %s', apunte.move_id.name)
        asiento = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.diario_id.id, 'date': fields.Date.context_today(self),
            'ref': etiqueta,
            'line_ids': [
                Command.create({'account_id': apunte.account_id.id, 'partner_id': apunte.partner_id.id,
                                'name': etiqueta, 'debit': max(-saldo, 0.0), 'credit': max(saldo, 0.0)}),
                Command.create({'account_id': cuenta.id, 'partner_id': apunte.partner_id.id, 'name': etiqueta,
                                'debit': max(saldo, 0.0), 'credit': max(-saldo, 0.0)}),
            ],
        })
        asiento.action_post()
        contraparte = asiento.line_ids.filtered(lambda linea: linea.account_id == apunte.account_id)
        (apunte | contraparte).reconcile()
        nota = Markup('<p>%s</p>') % escape(self.env._(
            'Se cerró el saldo de %(monto)s por redondeo (asiento %(asiento)s), por %(quien)s.',
            monto=f'${abs(saldo):,.2f}', asiento=asiento.name, quien=self.env.user.name))
        apunte.move_id.message_post(body=nota, subtype_xmlid='mail.mt_note')
        return asiento


class DcasaSaldosCentavosLinea(models.TransientModel):
    _name = 'dcasa.saldos.centavos.linea'
    _description = 'Saldo de centavos por cerrar'
    _order = 'fecha, id'

    asistente_id = fields.Many2one('dcasa.saldos.centavos', required=True, ondelete='cascade')
    move_line_id = fields.Many2one('account.move.line', required=True, readonly=True)
    tipo = fields.Selection(TIPOS, readonly=True)
    saldo = fields.Float('Saldo', readonly=True, digits=(16, 2),
                         help='Positivo: el cliente debía esos centavos. Negativo: le sobraban al cliente.')
    documento = fields.Char(related='move_line_id.move_id.name', string='Documento')
    partner_id = fields.Many2one(related='move_line_id.partner_id', string='Cliente')
    fecha = fields.Date(related='move_line_id.date', string='Fecha', store=True)
