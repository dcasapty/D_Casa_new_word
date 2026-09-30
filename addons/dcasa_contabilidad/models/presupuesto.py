"""Presupuestos por cuenta contable (y, si se quiere, por cuenta analítica).

Lo planeado lo escribe quien administra; lo real sale siempre de los apuntes publicados
del periodo, con el signo natural de la cuenta (ingresos en positivo, gastos en positivo).
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Cuentas que se presentan en positivo cuando tienen saldo acreedor (haber > debe).
TIPOS_ACREEDORES = ('income', 'income_other', 'liability_payable', 'liability_credit_card', 'liability_current',
                    'liability_non_current', 'equity', 'equity_unaffected')


class DcasaPresupuesto(models.Model):
    _name = 'dcasa.presupuesto'
    _description = 'Presupuesto'
    _inherit = ['mail.thread']
    _order = 'fecha_desde desc, id desc'

    name = fields.Char(string='Nombre', required=True, tracking=True)
    fecha_desde = fields.Date(string='Desde', required=True,
                              default=lambda self: fields.Date.context_today(self).replace(month=1, day=1))
    fecha_hasta = fields.Date(string='Hasta', required=True,
                              default=lambda self: fields.Date.context_today(self).replace(month=12, day=31))
    state = fields.Selection([('borrador', 'Borrador'), ('aprobado', 'Aprobado'), ('cerrado', 'Cerrado')],
                             string='Estado', default='borrador', required=True, tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    line_ids = fields.One2many('dcasa.presupuesto.linea', 'presupuesto_id', string='Líneas', copy=True)
    total_planeado = fields.Monetary(compute='_compute_totales', string='Planeado')
    total_real = fields.Monetary(compute='_compute_totales', string='Real')
    notas = fields.Html(string='Notas')

    _fechas_ordenadas = models.Constraint('CHECK (fecha_desde <= fecha_hasta)',
                                          'La fecha «Desde» debe ser anterior a «Hasta».')

    @api.depends('line_ids.monto_planeado', 'line_ids.monto_real')
    def _compute_totales(self):
        for presupuesto in self:
            presupuesto.total_planeado = sum(presupuesto.line_ids.mapped('monto_planeado'))
            presupuesto.total_real = sum(presupuesto.line_ids.mapped('monto_real'))

    def action_aprobar(self):
        self.write({'state': 'aprobado'})

    def action_cerrar(self):
        self.write({'state': 'cerrado'})

    def action_borrador(self):
        self.write({'state': 'borrador'})

    def action_ver_apuntes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': [('parent_state', '=', 'posted'), ('date', '>=', self.fecha_desde),
                       ('date', '<=', self.fecha_hasta), ('account_id', 'in', self.line_ids.account_id.ids)],
            'context': {'search_default_group_by_account': 1},
        }


class DcasaPresupuestoLinea(models.Model):
    _name = 'dcasa.presupuesto.linea'
    _description = 'Línea de presupuesto'
    _order = 'presupuesto_id, sequence, id'

    presupuesto_id = fields.Many2one('dcasa.presupuesto', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    account_id = fields.Many2one('account.account', string='Cuenta contable', required=True,
                                 domain="[('account_type', '!=', 'off_balance')]")
    analytic_account_id = fields.Many2one('account.analytic.account', string='Cuenta analítica')
    currency_id = fields.Many2one(related='presupuesto_id.currency_id')
    monto_planeado = fields.Monetary(string='Planeado', required=True, default=0.0)
    monto_real = fields.Monetary(string='Real', compute='_compute_real')
    diferencia = fields.Monetary(string='Diferencia', compute='_compute_real',
                                 help='Planeado − real: positivo es lo que queda por ejecutar.')
    porcentaje = fields.Float(string='% ejecutado', compute='_compute_real', digits=(16, 1))

    @api.constrains('monto_planeado')
    def _check_monto(self):
        if any(linea.monto_planeado < 0 for linea in self):
            raise ValidationError(self.env._('El monto planeado no puede ser negativo.'))

    def _dominio_real(self):
        self.ensure_one()
        dominio = [
            ('parent_state', '=', 'posted'),
            ('account_id', '=', self.account_id.id),
            ('date', '>=', self.presupuesto_id.fecha_desde),
            ('date', '<=', self.presupuesto_id.fecha_hasta),
            ('company_id', '=', self.presupuesto_id.company_id.id),
        ]
        if self.analytic_account_id:
            dominio.append(('analytic_distribution', 'in', self.analytic_account_id.ids))
        return dominio

    @api.depends('account_id', 'analytic_account_id', 'monto_planeado',
                 'presupuesto_id.fecha_desde', 'presupuesto_id.fecha_hasta')
    def _compute_real(self):
        Linea = self.env['account.move.line']
        for linea in self:
            real = 0.0
            if linea.account_id and linea.presupuesto_id.fecha_desde and linea.presupuesto_id.fecha_hasta:
                apuntes = Linea.search(linea._dominio_real())
                if linea.analytic_account_id:
                    clave = str(linea.analytic_account_id.id)
                    saldo = sum(a.balance * sum(float(p) for c, p in (a.analytic_distribution or {}).items()
                                                if clave in c.split(',')) / 100 for a in apuntes)
                else:
                    saldo = sum(apuntes.mapped('balance'))
                real = -saldo if linea.account_id.account_type in TIPOS_ACREEDORES else saldo
            moneda = linea.currency_id or self.env.company.currency_id
            linea.monto_real = moneda.round(real)
            linea.diferencia = moneda.round(linea.monto_planeado - real)
            linea.porcentaje = real / linea.monto_planeado * 100 if linea.monto_planeado else 0.0

    def action_ver_apuntes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.account_id.display_name,
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': self._dominio_real(),
        }
