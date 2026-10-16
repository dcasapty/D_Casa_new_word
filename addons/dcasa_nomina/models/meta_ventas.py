"""Bono por meta de ventas de quien vende en la tienda (decisión del jefe, 2026-10-16).

La regla, en palabras del jefe:

* Participa quien está en un departamento marcado «Participa en la meta de ventas» (el de Ventas) y tiene usuario
  en el sistema. Lo marca Gerencia en la ficha del departamento; al instalar se marca solo el que se llama «Ventas».
* Cuenta lo que esa persona vendió (el «Vendedor» de la factura) y el cliente **ya pagó completo**: la venta cuenta en
  el mes en que caja recibió el último pago (también en los apartados), **sin ITBMS**. Las notas de crédito restan.
* Si lo cobrado del mes **llega a la meta** (30,000), el bono es el **1 % de todo** lo cobrado (con 60,000, 600). Si no
  llega, no hay bono.
* Se paga en la **primera planilla quincenal del mes siguiente**, como comisión: paga seguro social, seguro educativo
  e ISR como el salario (la contadora lo confirma, docs/NOMINA.md).
* Cada vendedora ve **solo lo suyo** en su Inicio; nunca lo que vendió la tienda ni sus gastos.

Las cifras (meta, porcentaje y el ritmo diario de guía) viven en «Meta de ventas» (Nómina › Configuración), con
vigencia por mes: se cambian desde un mes en adelante, y un mes ya pagado no cambia.
"""
from datetime import date

from babel.dates import format_date
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from . import calculo

GRUPO = 'dcasa_nomina.group_nomina'
# Un apartado puede completar su pago meses después de facturado: se mira hasta un año atrás.
MESES_ATRAS = 12
PARAM_INICIALIZADA = 'dcasa_nomina.meta_ventas_inicializada'


def fin_de_mes(mes):
    return mes + relativedelta(day=31)


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    dcasa_meta_ventas = fields.Boolean(
        'Participa en la meta de ventas', groups=GRUPO,
        help='Quien esté en este departamento y tenga usuario participa en el bono por meta de ventas '
             '(Nómina › Bono por meta).')

    @api.model
    def _dcasa_marcar_ventas(self):
        """La primera vez marca el departamento que se llama «Ventas» (pedido del jefe). Después lo decide Gerencia
        en la ficha del departamento: esta función no vuelve a marcar nada aunque se desmarque."""
        Param = self.env['ir.config_parameter'].sudo()
        if Param.get_param(PARAM_INICIALIZADA):
            return
        self.sudo().search([('name', '=ilike', 'ventas')]).write({'dcasa_meta_ventas': True})
        Param.set_param(PARAM_INICIALIZADA, '1')


class DcasaNominaMetaRegla(models.Model):
    _name = 'dcasa.nomina.meta.regla'
    _description = 'Meta de ventas y bono (con vigencia por mes)'
    _order = 'company_id, fecha_desde desc'

    name = fields.Char(compute='_compute_name')
    company_id = fields.Many2one('res.company', 'Empresa', required=True, index=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    fecha_desde = fields.Date('Rige desde el mes', required=True,
                              help='Primer día del mes desde el que rige esta meta.')
    meta_mensual = fields.Monetary('Meta del mes (sin ITBMS)', required=True,
                                   help='Lo que cada vendedora tiene que cobrar en el mes para ganar el bono.')
    porcentaje = fields.Float('Bono (% de lo cobrado)', required=True, digits=(5, 2),
                              help='Si llega a la meta, el bono es este porcentaje de TODO lo cobrado en el mes.')
    meta_diaria = fields.Monetary('Ritmo diario (guía)',
                                  help='Solo se le muestra a la vendedora como guía del día; no cambia el bono.')
    notas = fields.Char()

    _una_por_mes = models.Constraint('UNIQUE(company_id, fecha_desde)', 'Ya hay una meta que rige desde ese mes.')

    @api.depends('fecha_desde', 'meta_mensual', 'porcentaje')
    def _compute_name(self):
        for regla in self:
            desde = regla.fecha_desde.strftime('%m/%Y') if regla.fecha_desde else '—'
            regla.name = self.env._('Desde %(desde)s: meta %(meta)s, bono %(pct)s %%', desde=desde,
                                    meta=f'{regla.meta_mensual:,.2f}', pct=f'{regla.porcentaje:g}')

    @api.constrains('fecha_desde', 'meta_mensual', 'porcentaje', 'meta_diaria')
    def _check_cifras(self):
        for regla in self:
            if regla.fecha_desde.day != 1:
                raise ValidationError(self.env._('La meta rige desde el primer día de un mes.'))
            if regla.meta_mensual <= 0 or regla.meta_diaria < 0:
                raise ValidationError(self.env._('La meta del mes tiene que ser mayor que cero.'))
            if not 0 < regla.porcentaje <= 100:
                raise ValidationError(self.env._('El bono es un porcentaje entre 0 y 100.'))
            pagados = self.env['dcasa.nomina.meta.bono'].sudo().search_count([
                ('company_id', '=', regla.company_id.id), ('mes', '>=', regla.fecha_desde),
                ('estado', 'in', ('en_planilla', 'pagado'))])
            if pagados:
                raise ValidationError(self.env._(
                    'Desde ese mes ya hay bonos en una planilla: la meta solo cambia hacia adelante. Crea una nueva '
                    'que rija desde el mes siguiente.'))

    @api.ondelete(at_uninstall=False)
    def _no_borrar_usadas(self):
        if self.env['dcasa.nomina.meta.bono'].sudo().search_count([
                ('regla_id', 'in', self.ids), ('estado', 'in', ('en_planilla', 'pagado'))]):
            raise UserError(self.env._('Esa meta ya se usó para pagar bonos: no se borra.'))

    @api.model
    def _vigente(self, mes, company):
        return self.sudo().search([('company_id', '=', company.id), ('fecha_desde', '<=', mes)],
                                  order='fecha_desde desc', limit=1)


class DcasaNominaMetaBono(models.Model):
    _name = 'dcasa.nomina.meta.bono'
    _description = 'Bono por meta de ventas (una persona, un mes)'
    _order = 'mes desc, empleado_id'

    empleado_id = fields.Many2one('hr.employee', 'Colaborador', required=True, index=True, readonly=True,
                                  ondelete='restrict')
    user_id = fields.Many2one('res.users', 'Usuario', readonly=True)
    company_id = fields.Many2one('res.company', 'Empresa', required=True, index=True, readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    mes = fields.Date('Mes', required=True, readonly=True, index=True)
    regla_id = fields.Many2one('dcasa.nomina.meta.regla', 'Meta aplicada', readonly=True, ondelete='restrict')
    meta = fields.Monetary('Meta', readonly=True)
    porcentaje = fields.Float('Bono (%)', readonly=True, digits=(5, 2))
    cobrado = fields.Monetary('Cobrado en el mes (sin ITBMS)', readonly=True)
    cumplio = fields.Boolean('Llegó a la meta', readonly=True)
    monto = fields.Monetary('Bono', readonly=True)
    factura_ids = fields.Many2many('account.move', 'dcasa_meta_bono_factura_rel', 'bono_id', 'move_id',
                                   'Facturas que cuentan', readonly=True)
    nota_ids = fields.Many2many('account.move', 'dcasa_meta_bono_nota_rel', 'bono_id', 'move_id',
                                'Notas de crédito que restan', readonly=True)
    linea_id = fields.Many2one('dcasa.nomina.linea', 'Línea de planilla', readonly=True, index=True,
                               ondelete='set null')
    # Sale de la planilla en la que está (sin guardarse: una planilla borrada o cancelada lo suelta sola).
    estado = fields.Selection([('abierto', 'Por pagar'), ('en_planilla', 'En planilla'), ('pagado', 'Pagado')],
                              compute='_compute_estado', search='_search_estado')
    actualizado = fields.Datetime('Calculado el', readonly=True)

    _uno_por_mes = models.Constraint('UNIQUE(empleado_id, mes)', 'Cada persona tiene un solo bono por mes.')

    ESTADOS_PLANILLA = {'pagado': ('confirmada', 'pagada'), 'en_planilla': ('borrador', 'calculada')}

    def _search_estado(self, operator, value):
        valores = [value] if isinstance(value, str) else list(value or [])
        if operator not in ('=', 'in'):
            raise UserError(self.env._('Solo se filtra el estado del bono por igual a.'))
        dominio = []
        for valor in valores:
            if valor == 'abierto':
                parte = ['|', ('linea_id', '=', False), ('linea_id.planilla_id.estado', '=', 'cancelada')]
            else:
                parte = [('linea_id.planilla_id.estado', 'in', self.ESTADOS_PLANILLA.get(valor, ()))]
            dominio = ['|', *dominio, *parte] if dominio else parte
        return dominio or [('id', '=', False)]

    @api.depends('linea_id', 'linea_id.planilla_id.estado')
    def _compute_estado(self):
        for bono in self:
            estado_planilla = bono.linea_id.planilla_id.estado
            if estado_planilla in ('confirmada', 'pagada'):
                bono.estado = 'pagado'
            elif estado_planilla in ('borrador', 'calculada'):
                bono.estado = 'en_planilla'
            else:
                bono.estado = 'abierto'

    # ------------------------------------------------------------------
    # Lo cobrado
    # ------------------------------------------------------------------

    @api.model
    def _participantes(self, company):
        return self.env['hr.employee'].sudo().search([
            ('company_id', '=', company.id), ('department_id.dcasa_meta_ventas', '=', True),
            ('user_id', '!=', False)])

    @api.model
    def _cobro_completo(self, factura):
        """El día en que la factura quedó pagada completa (el último pago, y nunca antes de la factura), o False si
        todavía debe algo."""
        if factura.payment_state not in ('paid', 'in_payment'):
            return False
        fechas = [fields.Date.to_date(pago['date'])
                  for pago in (factura.sudo().invoice_payments_widget or {}).get('content', [])
                  if pago.get('date') and not pago.get('is_exchange')]
        if not fechas:
            return False
        return max([*fechas, factura.invoice_date or date.min])

    @api.model
    def _cobrado(self, user, desde, hasta, company):
        """``(total, facturas, notas)``: lo que ``user`` vendió y quedó pagado completo entre ``desde`` y ``hasta``,
        sin ITBMS, menos sus notas de crédito (una nota resta en el mes de la nota o, si llegó antes de completarse el
        pago, en el mes en que se completó)."""
        Move = self.env['account.move'].sudo()
        tope = desde - relativedelta(months=MESES_ATRAS)
        comun = [('state', '=', 'posted'), ('company_id', '=', company.id)]
        facturas = Move.search(comun + [
            ('move_type', '=', 'out_invoice'), ('invoice_user_id', '=', user.id), ('dcasa_historica', '=', False),
            ('payment_state', 'in', ('paid', 'in_payment')),
            ('invoice_date', '>=', tope), ('invoice_date', '<=', hasta)])
        cuentan = facturas.filtered(lambda f: desde <= (self._cobro_completo(f) or date.min) <= hasta)

        def resta(nota):
            completo = self._cobro_completo(nota.reversed_entry_id)
            return bool(completo) and desde <= max(nota.date, completo) <= hasta

        notas = Move.search(comun + [
            ('move_type', '=', 'out_refund'), ('reversed_entry_id', '!=', False),
            ('reversed_entry_id.invoice_user_id', '=', user.id), ('reversed_entry_id.dcasa_historica', '=', False),
            ('date', '>=', tope), ('date', '<=', hasta)]).filtered(resta)
        total = calculo.r2(sum(cuentan.mapped('amount_untaxed_signed')) + sum(notas.mapped('amount_untaxed_signed')))
        return total, cuentan, notas

    # ------------------------------------------------------------------
    # El bono de un mes
    # ------------------------------------------------------------------

    @api.model
    def _calcular(self, empleado, mes, company):
        """El bono de ``empleado`` en ``mes`` (se crea o se pone al día). Un bono ya pagado no cambia. Sin meta que
        rija ese mes, no hay bono."""
        mes = mes.replace(day=1)
        bono = self.sudo().search([('empleado_id', '=', empleado.id), ('mes', '=', mes)], limit=1)
        if bono.estado == 'pagado':
            return bono
        regla = self.env['dcasa.nomina.meta.regla']._vigente(mes, company)
        if not regla or not empleado.user_id:
            return bono
        total, facturas, notas = self._cobrado(empleado.user_id, mes, fin_de_mes(mes), company)
        cumplio = total >= regla.meta_mensual
        valores = {
            'user_id': empleado.user_id.id, 'regla_id': regla.id, 'meta': regla.meta_mensual,
            'porcentaje': regla.porcentaje, 'cobrado': total, 'cumplio': cumplio,
            'monto': calculo.porcentaje(total, regla.porcentaje) if cumplio else 0.0,
            'factura_ids': [fields.Command.set(facturas.ids)], 'nota_ids': [fields.Command.set(notas.ids)],
            'actualizado': fields.Datetime.now(),
        }
        if bono:
            bono.sudo().write(valores)
            return bono
        return self.sudo().create({'empleado_id': empleado.id, 'company_id': company.id, 'mes': mes, **valores})

    @api.model
    def _actualizar(self, company, meses):
        """Pone al día los bonos de ``meses`` de quienes participan (los pagados no cambian)."""
        for empleado in self._participantes(company):
            for mes in meses:
                self._calcular(empleado, mes, company)

    @api.model
    def _cron_actualizar(self):
        """Cada día: el mes en curso y el anterior, para que Gerencia los vea al día en Nómina › Bono por meta."""
        hoy = fields.Date.context_today(self.with_context(tz='America/Panama'))
        mes = hoy.replace(day=1)
        for company in self.env['dcasa.nomina.meta.regla'].sudo().search([]).company_id:
            self._actualizar(company, [mes - relativedelta(months=1), mes])

    @api.model
    def _accion_bonos(self):
        """Nómina › Bono por meta: pone al día el mes en curso y el anterior y abre la lista."""
        hoy = fields.Date.context_today(self.with_context(tz='America/Panama'))
        mes = hoy.replace(day=1)
        for company in self.env.companies:
            self._actualizar(company, [mes - relativedelta(months=1), mes])
        accion = self.env['ir.actions.actions']._for_xml_id('dcasa_nomina.accion_meta_bonos_lista')
        return accion

    # ------------------------------------------------------------------
    # Lo que ve la vendedora en su Inicio (solo lo suyo)
    # ------------------------------------------------------------------

    @api.model
    def _para_inicio(self, user, hoy):
        """La tarjeta «Tu meta del mes» de ``user``, o None si no participa. Solo sus cifras: nunca las de la
        tienda ni las de otra vendedora."""
        company = self.env.company
        if not self._participantes(company).filtered(lambda e: e.user_id == user):
            return None
        mes = hoy.replace(day=1)
        regla = self.env['dcasa.nomina.meta.regla']._vigente(mes, company)
        if not regla:
            return None
        cobrado, _facturas, _notas = self._cobrado(user, mes, hoy, company)
        de_hoy, _facturas, _notas = self._cobrado(user, hoy, hoy, company)
        cumplio = cobrado >= regla.meta_mensual
        return {
            'mes': format_date(mes, 'MMMM', locale='es'),
            'meta': regla.meta_mensual,
            'porcentaje': f'{regla.porcentaje:g}',
            'cobrado': cobrado,
            'faltan': calculo.r2(max(regla.meta_mensual - cobrado, 0.0)),
            'avance': round(min(max(cobrado, 0.0) / regla.meta_mensual * 100.0, 100.0), 1),
            'cumplio': cumplio,
            'bono': calculo.porcentaje(cobrado, regla.porcentaje) if cumplio else 0.0,
            'hoy': de_hoy,
            'meta_diaria': regla.meta_diaria,
        }
