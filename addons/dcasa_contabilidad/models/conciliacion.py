"""Conciliación bancaria de D'CASA.

Cada movimiento del extracto (account.bank.statement.line) nace con su contrapartida
en la cuenta transitoria del diario. Conciliar es reemplazar esa contrapartida por lo
que de verdad es: el cobro de una o varias facturas, el pago a un proveedor o un gasto
(comisión del banco, cargo por Yappy…), y cruzar los apuntes. Todo queda en asientos
publicados y se puede deshacer con «Deshacer conciliación».

Se asume la moneda de la empresa (USD), que es la de todos los bancos de D'CASA.
"""
import re

from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain

GRUPO_CONCILIAR = 'account.group_account_user'  # el del menú Contabilidad › Bancos


def _exigir_contador(env):
    """La conciliación lee y reescribe apuntes: el grupo se exige en el servidor (Odoo expone por
    RPC todo método público; el ACL de account.bank.statement.line es más ancho que el menú)."""
    if not env.su and not env.user.has_group(GRUPO_CONCILIAR):
        raise AccessError(env._('La conciliación bancaria es solo para quien lleva la contabilidad.'))


def _apunte_vals(cuenta, partner, nombre, saldo, moneda, move):
    return {
        'move_id': move.id,
        'account_id': cuenta.id,
        'partner_id': partner.id,
        'name': nombre,
        'currency_id': moneda.id,
        'amount_currency': saldo,
        'debit': saldo if saldo > 0 else 0.0,
        'credit': -saldo if saldo < 0 else 0.0,
    }


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    @api.private
    def dcasa_candidatos(self, busqueda=None, limite=30):
        """Apuntes abiertos que pueden explicar este movimiento, los más probables primero."""
        _exigir_contador(self.env)
        self.ensure_one()
        entra = self.amount > 0
        # Facturas abiertas (por cobrar / por pagar) y pagos ya registrados que esperan el banco
        # (cuentas de recibos y pagos pendientes). Nunca la cuenta del propio banco ni su transitoria.
        propias = (self.journal_id.default_account_id | self.journal_id.suspense_account_id).ids
        dominio = Domain.AND([
            self._get_default_amls_matching_domain(),
            [('account_id', 'not in', propias),
             ('account_id.account_type', 'not in', ('asset_cash', 'liability_credit_card')),
             ('amount_residual', '>' if entra else '<', 0)],
        ])
        if busqueda:
            dominio = Domain.AND([dominio, ['|', '|', ('move_id.name', 'ilike', busqueda),
                                            ('partner_id.name', 'ilike', busqueda), ('ref', 'ilike', busqueda)]])
        apuntes = self.env['account.move.line'].search(dominio, limit=200, order='date desc, id desc')
        moneda = self.company_id.currency_id
        texto = (self.payment_ref or '').upper()

        def puntaje(apunte):
            p = 0
            if moneda.is_zero(abs(apunte.amount_residual) - abs(self.amount)):
                p += 4
            if self.partner_id and apunte.partner_id.commercial_partner_id == self.partner_id.commercial_partner_id:
                p += 3
            referencias = {apunte.move_id.name, apunte.move_id.ref, apunte.move_id.payment_reference}
            if any(r and len(r) > 3 and r.upper() in texto for r in referencias):
                p += 5
            return p

        return sorted(apuntes, key=lambda a: (-puntaje(a), -a.date.toordinal()))[:limite], puntaje

    @api.private
    def dcasa_conciliar(self, apunte_ids=(), cuenta_id=None, etiqueta=None, partner_id=None):
        """Explica lo que falta del movimiento con apuntes abiertos y, si sobra, con una cuenta.

        Solo se reemplaza la línea transitoria (lo pendiente): lo ya conciliado antes, en una
        conciliación parcial, se conserva tal cual.
        """
        _exigir_contador(self.env)
        self.ensure_one()
        moneda = self.company_id.currency_id
        move = self.move_id
        _liquidez, transitoria, otras = self._seek_for_lines()
        pendiente = moneda.round(sum(transitoria.mapped('balance')))
        if self.is_reconciled or moneda.is_zero(pendiente):
            raise UserError(self.env._('Este movimiento ya está conciliado.'))
        partner = self.env['res.partner'].browse(partner_id) if partner_id else self.partner_id
        if partner != self.partner_id and not otras:
            self.partner_id = partner
            _liquidez, transitoria, otras = self._seek_for_lines()
        apuntes = self.env['account.move.line'].browse(apunte_ids)
        nuevas, pares = [], []
        for apunte in apuntes:
            if moneda.is_zero(pendiente):
                break
            saldo = -apunte.amount_residual
            if abs(saldo) > abs(pendiente):
                saldo = pendiente  # conciliación parcial: se aplica solo lo que se movió
            nuevas.append(_apunte_vals(apunte.account_id, apunte.partner_id, apunte.move_id.name or apunte.name,
                                       moneda.round(saldo), moneda, move))
            pares.append(apunte)
            pendiente = moneda.round(pendiente - saldo)
        if cuenta_id and not moneda.is_zero(pendiente):
            nuevas.append(_apunte_vals(self.env['account.account'].browse(cuenta_id), partner,
                                       etiqueta or self.payment_ref, pendiente, moneda, move))
            pendiente = 0.0
        if not nuevas:
            raise UserError(self.env._('Elige al menos una factura o pago, o una cuenta para el movimiento.'))
        if not moneda.is_zero(pendiente):
            # Lo que no se explicó sigue en la cuenta transitoria, a la espera.
            nuevas.append(_apunte_vals(self.journal_id.suspense_account_id, partner, self.payment_ref,
                                       pendiente, moneda, move))

        antes = set(move.line_ids.ids)
        # Se reescriben los apuntes del asiento (no del movimiento: eso los regeneraría).
        move.with_context(force_delete=True, skip_readonly_check=True).write({
            'line_ids': [Command.delete(t.id) for t in transitoria] + [Command.create(v) for v in nuevas],
        })
        creadas = move.line_ids.filtered(lambda ln: ln.id not in antes)
        for apunte in pares:
            contrapartida = creadas.filtered(lambda ln, a=apunte: (
                ln.account_id == a.account_id and ln.partner_id == a.partner_id and not ln.reconciled
                and ln.name == (a.move_id.name or a.name)))[:1]
            (contrapartida | apunte).reconcile()
        return True

    @api.private
    def dcasa_conciliar_automatico(self):
        """Concilia solo lo inequívoco: un único candidato con el mismo monto y referencia o cliente."""
        _exigir_contador(self.env)
        hechos = self.browse()
        for linea in self.filtered(lambda ln: not ln.is_reconciled):
            candidatos, puntaje = linea.dcasa_candidatos(limite=5)
            seguros = [c for c in candidatos if puntaje(c) >= 7]
            if len(seguros) == 1:
                linea.dcasa_conciliar([seguros[0].id])
                hechos |= linea
        return hechos


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    def open_action(self):
        """«Transacciones» de un banco, Yappy, tarjeta o caja abre la conciliación de D'CASA."""
        if (len(self) == 1 and self.type in ('bank', 'cash', 'credit')
                and not self.env.context.get('action_name')
                and self.env.user.has_group('account.group_account_user')):
            return {
                'type': 'ir.actions.client',
                'tag': 'dcasa_conciliacion',
                'name': self.env._('Conciliación bancaria'),
                'params': {'journal_id': self.id},
            }
        return super().open_action()


class DcasaConciliacion(models.AbstractModel):
    """API de la pantalla «Conciliación bancaria». Pública (la llama el JS), pero cada método
    exige ``account.group_account_user`` en el servidor: es un AbstractModel sin ACL."""
    _name = 'dcasa.conciliacion'
    _description = "Conciliación bancaria de D'CASA"

    @api.model
    def _apunte(self, apunte):
        return {
            'id': apunte.id, 'asiento': apunte.move_id.name, 'fecha': str(apunte.date),
            'vence': str(apunte.date_maturity or apunte.date), 'tercero': apunte.partner_id.display_name or '',
            'referencia': next((r for r in (apunte.move_id.ref, apunte.move_id.payment_reference)
                                if r and r != apunte.move_id.name), ''),
            'pendiente': apunte.amount_residual, 'cuenta': apunte.account_id.display_name,
            'tipo': 'pago' if apunte.payment_id else 'factura',
        }

    @api.model
    def diarios(self):
        _exigir_contador(self.env)
        diarios = self.env['account.journal'].search([('type', 'in', ('bank', 'cash')),
                                                      ('company_id', 'in', self.env.companies.ids)])
        Linea = self.env['account.bank.statement.line']
        return [{'id': d.id, 'nombre': d.name, 'tipo': d.type,
                 'pendientes': Linea.search_count([('journal_id', '=', d.id), ('is_reconciled', '=', False)])}
                for d in diarios]

    @api.model
    def pendientes(self, journal_id):
        _exigir_contador(self.env)
        lineas = self.env['account.bank.statement.line'].search(
            [('journal_id', '=', journal_id), ('is_reconciled', '=', False)], order='date desc, id desc', limit=300)
        return [{'id': ln.id, 'fecha': str(ln.date), 'concepto': ln.payment_ref or '', 'monto': ln.amount,
                 'tercero': ln.partner_id.display_name or '', 'tercero_id': ln.partner_id.id,
                 'pendiente': -ln.amount_residual} for ln in lineas]

    @api.model
    def candidatos(self, linea_id, busqueda=None):
        _exigir_contador(self.env)
        linea = self.env['account.bank.statement.line'].browse(linea_id)
        apuntes, puntaje = linea.dcasa_candidatos(busqueda=busqueda)
        return [{**self._apunte(a), 'sugerido': puntaje(a) >= 7} for a in apuntes]

    @api.model
    def cuentas_rapidas(self):
        """Cuentas para registrar un movimiento sin factura (comisiones, cargos, intereses, otros)."""
        _exigir_contador(self.env)
        cuentas = self.env['account.account'].search([
            ('company_ids', 'in', self.env.company.ids),
            ('account_type', 'in', ('expense', 'expense_other', 'income_other', 'liability_current',
                                    'asset_current', 'equity')),
        ], order='code')
        grupos = {'expense': 'Gastos', 'expense_other': 'Gastos', 'income_other': 'Otros ingresos'}
        orden = ['Gastos', 'Otros ingresos', 'Otras cuentas']
        filas = [{'id': c.id, 'nombre': c.display_name, 'tipo': c.account_type,
                  'grupo': grupos.get(c.account_type, 'Otras cuentas')} for c in cuentas]
        return [{'grupo': g, 'cuentas': [f for f in filas if f['grupo'] == g]}
                for g in orden if any(f['grupo'] == g for f in filas)]

    @api.model
    def conciliar(self, linea_id, apunte_ids=(), cuenta_id=None, etiqueta=None):
        _exigir_contador(self.env)
        linea = self.env['account.bank.statement.line'].browse(linea_id)
        linea.dcasa_conciliar(apunte_ids=apunte_ids, cuenta_id=cuenta_id, etiqueta=etiqueta)
        return {'conciliado': linea.is_reconciled}

    @api.model
    def automatico(self, journal_id):
        _exigir_contador(self.env)
        lineas = self.env['account.bank.statement.line'].search(
            [('journal_id', '=', journal_id), ('is_reconciled', '=', False)])
        return len(lineas.dcasa_conciliar_automatico())

    @api.model
    def deshacer(self, linea_id):
        _exigir_contador(self.env)
        self.env['account.bank.statement.line'].browse(linea_id).action_undo_reconciliation()
        return True


# ---------------------------------------------------------------------------
# Lectura de extractos (CSV)
# ---------------------------------------------------------------------------

_FORMATOS_FECHA = ('%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y')


def leer_fecha(texto):
    from datetime import datetime
    texto = (texto or '').strip()
    for formato in _FORMATOS_FECHA:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ValueError(texto)


def leer_monto(texto):
    """'1,234.56' · '1.234,56' · '(45.00)' · '-45' · '$ 45.00' → número."""
    texto = (texto or '').strip().replace('$', '').replace('B/.', '').replace(' ', '')
    if not texto:
        return 0.0
    negativo = texto.startswith('(') and texto.endswith(')') or texto.startswith('-')
    texto = texto.strip('()-+')
    if re.search(r',\d{1,2}$', texto):  # coma decimal
        texto = texto.replace('.', '').replace(',', '.')
    else:
        texto = texto.replace(',', '')
    valor = float(texto)
    return -valor if negativo else valor


def fecha_iso(valor):
    return fields.Date.to_string(valor)
