"""Presupuestos por cuenta contable (y, si se quiere, por cuenta analítica).

Lo planeado lo escribe quien administra; lo real sale siempre de los apuntes publicados del periodo, con el signo
natural de la cuenta (ingresos y gastos en positivo; una nota de crédito resta). Los borradores y los asientos
cancelados nunca cuentan.

Reglas de las cuentas (auditadas contra un cálculo aparte en SQL, ver ``docs/AUDITORIA_CONTABLE.md``):

* **Real** = Σ (debe − haber) de los apuntes publicados de la cuenta con fecha entre «Desde» y «Hasta» (al revés en
  ingresos, pasivos y patrimonio). Con cuenta analítica, solo la parte que cada apunte reparte a esa cuenta.
* **Por ejecutar** = planeado − real. Positivo: queda por gastar (o por vender). Negativo: en un gasto es que te
  pasaste; en un ingreso, que superaste la meta. Por eso el color no sale del signo sino de la ``situacion`` de
  cada línea.
* **% ejecutado** = real ÷ planeado. Con planeado en cero no hay porcentaje: la situación dice «Sin presupuesto» (o «Sin
  movimiento») en vez de mostrar un 0 que no es verdad.
* **Totales**: los ingresos y los gastos se suman por separado y la diferencia es el resultado. Sumar ingresos con
  gastos en un solo «total» no significa nada. Una línea con cuenta analítica que está dentro de otra línea de la
  misma cuenta sin analítica es un detalle de ella: no se suma otra vez.
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Cuentas que se presentan en positivo cuando tienen saldo acreedor (haber > debe).
TIPOS_ACREEDORES = ('income', 'income_other', 'liability_payable', 'liability_credit_card', 'liability_current',
                    'liability_non_current', 'equity', 'equity_unaffected')
TIPOS_INGRESO = ('income', 'income_other')
TIPOS_GASTO = ('expense', 'expense_other', 'expense_depreciation', 'expense_direct_cost')

SITUACIONES = [
    ('sin_movimiento', 'Sin movimiento'),
    ('sin_plan', 'Sin presupuesto'),
    ('dentro', 'Dentro'),
    ('excedido', 'Te pasaste'),
    ('en_camino', 'En camino'),
    ('cumplido', 'Meta cumplida'),
]


class DcasaPresupuesto(models.Model):
    _name = 'dcasa.presupuesto'
    _description = 'Presupuesto'
    _inherit = ['mail.thread', 'dcasa.atajo.fechas']
    _order = 'fecha_desde desc, id desc'

    name = fields.Char(string='Nombre', required=True, tracking=True)
    fecha_desde = fields.Date(string='Desde', required=True,
                              default=lambda self: fields.Date.context_today(self).replace(month=1, day=1))
    fecha_hasta = fields.Date(string='Hasta', required=True,
                              default=lambda self: fields.Date.context_today(self).replace(month=12, day=31))
    state = fields.Selection([('borrador', 'Borrador'), ('aprobado', 'Aprobado'), ('cerrado', 'Cerrado')],
                             string='Estado', default='borrador', required=True, tracking=True)
    company_id = fields.Many2one('res.company', string='Empresa', required=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    line_ids = fields.One2many('dcasa.presupuesto.linea', 'presupuesto_id', string='Líneas', copy=True)
    ingresos_planeado = fields.Monetary(compute='_compute_totales', string='Ingresos planeados')
    ingresos_real = fields.Monetary(compute='_compute_totales', string='Ingresos reales')
    gastos_planeado = fields.Monetary(compute='_compute_totales', string='Gastos planeados')
    gastos_real = fields.Monetary(compute='_compute_totales', string='Gastos reales')
    resultado_planeado = fields.Monetary(compute='_compute_totales', string='Resultado planeado',
                                         help='Ingresos planeados − gastos planeados. Las cuentas de balance no '
                                              'entran.')
    resultado_real = fields.Monetary(compute='_compute_totales', string='Resultado real',
                                     help='Ingresos reales − gastos reales. Las cuentas de balance no entran.')
    avance_tiempo = fields.Float(compute='_compute_avance_tiempo', string='Tiempo transcurrido (%)', digits=(16, 0),
                                 help='Cuánto del periodo ya pasó hoy. Sirve para comparar con el % ejecutado: gastar '
                                      '80 % del presupuesto con 30 % del tiempo es ir muy rápido.')
    aviso = fields.Char(compute='_compute_aviso')
    notas = fields.Html(string='Notas')

    _fechas_ordenadas = models.Constraint('CHECK (fecha_desde <= fecha_hasta)',
                                          'La fecha «Desde» debe ser anterior a «Hasta».')

    @api.depends('line_ids.monto_planeado', 'line_ids.monto_real', 'line_ids.naturaleza', 'line_ids.es_detalle')
    def _compute_totales(self):
        for presupuesto in self:
            lineas = presupuesto.line_ids.filtered(lambda ln: not ln.es_detalle)
            ingresos = lineas.filtered(lambda ln: ln.naturaleza == 'ingreso')
            gastos = lineas.filtered(lambda ln: ln.naturaleza == 'gasto')
            moneda = presupuesto.currency_id or self.env.company.currency_id
            presupuesto.ingresos_planeado = moneda.round(sum(ingresos.mapped('monto_planeado')))
            presupuesto.ingresos_real = moneda.round(sum(ingresos.mapped('monto_real')))
            presupuesto.gastos_planeado = moneda.round(sum(gastos.mapped('monto_planeado')))
            presupuesto.gastos_real = moneda.round(sum(gastos.mapped('monto_real')))
            presupuesto.resultado_planeado = moneda.round(presupuesto.ingresos_planeado - presupuesto.gastos_planeado)
            presupuesto.resultado_real = moneda.round(presupuesto.ingresos_real - presupuesto.gastos_real)

    @api.depends('fecha_desde', 'fecha_hasta')
    def _compute_avance_tiempo(self):
        hoy = self.env['dcasa.reporte.contable']._hoy()
        for presupuesto in self:
            desde, hasta = presupuesto.fecha_desde, presupuesto.fecha_hasta
            if not (desde and hasta):
                presupuesto.avance_tiempo = 0.0
                continue
            dias = (hasta - desde).days + 1
            transcurridos = min(max((hoy - desde).days + 1, 0), dias)       # hoy cuenta como día transcurrido
            presupuesto.avance_tiempo = transcurridos / dias * 100

    @api.depends('line_ids.es_detalle', 'line_ids.account_id', 'line_ids.analytic_account_id')
    def _compute_aviso(self):
        for presupuesto in self:
            detalles = presupuesto.line_ids.filtered('es_detalle')
            presupuesto.aviso = self.env._(
                'Hay %(n)s línea(s) con cuenta analítica que son parte de otra línea de la misma cuenta: no se suman '
                'otra vez al total (ingresos, gastos y resultado).', n=len(detalles)) if detalles else False

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
                       ('date', '<=', self.fecha_hasta), ('account_id', 'in', self.line_ids.account_id.ids),
                       ('company_id', '=', self.company_id.id)],
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
    naturaleza = fields.Selection(
        [('ingreso', 'Ingreso'), ('gasto', 'Gasto'), ('balance', 'Cuenta de balance')], string='Tipo',
        compute='_compute_naturaleza')
    monto_planeado = fields.Monetary(string='Planeado', required=True, default=0.0)
    monto_real = fields.Monetary(string='Real', compute='_compute_real')
    diferencia = fields.Monetary(string='Por ejecutar', compute='_compute_real',
                                 help='Planeado − real. Positivo: queda por gastar o por vender. Negativo: en un '
                                      'gasto, te pasaste; en un ingreso, superaste la meta.')
    porcentaje = fields.Float(string='% ejecutado', compute='_compute_real', digits=(16, 1),
                              help='Real ÷ planeado. Sin planeado no hay porcentaje: mira la situación.')
    situacion = fields.Selection(
        SITUACIONES, string='Situación', compute='_compute_real',
        help='Un gasto se vigila contra un tope: «Dentro» o «Te pasaste». Un ingreso, contra una meta: «En camino» o '
             '«Meta cumplida». «Sin presupuesto»: hay movimiento pero no planeaste nada.')
    es_detalle = fields.Boolean(
        string='Detalle de otra línea', compute='_compute_es_detalle',
        help='Tiene cuenta analítica y hay otra línea de la misma cuenta sin analítica: ya está incluida en esa y no '
             'se suma otra vez al total.')

    @api.constrains('monto_planeado')
    def _check_monto(self):
        if any(linea.monto_planeado < 0 for linea in self):
            raise ValidationError(self.env._('El monto planeado no puede ser negativo.'))

    @api.constrains('presupuesto_id', 'account_id', 'analytic_account_id')
    def _check_sin_repetir(self):
        """La misma cuenta (y la misma analítica) dos veces mostraría el mismo real en las dos y lo contaría doble."""
        for linea in self:
            otras = linea.presupuesto_id.line_ids - linea
            if otras.filtered(lambda o, linea=linea: o.account_id == linea.account_id
                              and o.analytic_account_id == linea.analytic_account_id):
                raise ValidationError(self.env._(
                    'La cuenta %(cuenta)s%(analitica)s ya está en este presupuesto. Suma los montos en una sola '
                    'línea: si no, lo real se contaría dos veces.',
                    cuenta=linea.account_id.display_name,
                    analitica=f' ({linea.analytic_account_id.name})' if linea.analytic_account_id else ''))

    @api.depends('account_id.account_type')
    def _compute_naturaleza(self):
        for linea in self:
            tipo = linea.account_id.account_type
            linea.naturaleza = ('ingreso' if tipo in TIPOS_INGRESO else 'gasto' if tipo in TIPOS_GASTO
                                else 'balance' if tipo else False)

    @api.depends('presupuesto_id.line_ids.account_id', 'presupuesto_id.line_ids.analytic_account_id',
                 'account_id', 'analytic_account_id')
    def _compute_es_detalle(self):
        for linea in self:
            linea.es_detalle = bool(linea.analytic_account_id and linea.account_id and (
                linea.presupuesto_id.line_ids - linea).filtered(
                    lambda o, linea=linea: o.account_id == linea.account_id and not o.analytic_account_id))

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

    def _situacion(self, planeado, real):
        """Cómo va la línea: un gasto (o cuenta de balance) se vigila contra un tope; un ingreso, contra una meta."""
        self.ensure_one()
        if not planeado:
            return 'sin_plan' if real else 'sin_movimiento'
        if self.naturaleza == 'ingreso':
            return 'cumplido' if real >= planeado else 'en_camino'
        return 'excedido' if real > planeado else 'dentro'

    @api.depends('account_id', 'analytic_account_id', 'monto_planeado',
                 'presupuesto_id.fecha_desde', 'presupuesto_id.fecha_hasta', 'presupuesto_id.company_id')
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
            real = moneda.round(real)
            linea.monto_real = real
            linea.diferencia = moneda.round(linea.monto_planeado - real)
            linea.porcentaje = real / linea.monto_planeado * 100 if linea.monto_planeado else 0.0
            linea.situacion = linea._situacion(linea.monto_planeado, real) if linea.account_id else False

    def action_ver_apuntes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.account_id.display_name,
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': self._dominio_real(),
        }
