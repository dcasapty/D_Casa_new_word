"""Cálculo de liquidación: lo que se le debe a una persona que sale (borrador para el contador).

Reúne en una hoja imprimible: salario pendiente, décimo tercer mes proporcional, vacaciones sin tomar y prima de
antigüedad. NO genera asiento ni pago: lo paga la planilla (como «otros ingresos») o el contador. Lo que depende
del motivo de la salida (indemnización por despido injustificado, preaviso) y el ISR de la liquidación NO se
calculan: los escribe el contador (campos «Indemnización» y «ISR»). Todo lo demás sale de las tasas validadas.
"""
from odoo import api, fields, models
from odoo.exceptions import UserError

from . import calculo

MOTIVOS = [
    ('renuncia', 'Renuncia'), ('despido_justificado', 'Despido con causa justificada'),
    ('despido_injustificado', 'Despido sin causa justificada'), ('mutuo_acuerdo', 'Mutuo acuerdo'),
    ('fin_contrato', 'Fin del contrato'), ('otro', 'Otro'),
]


class DcasaNominaLiquidacion(models.Model):
    _name = 'dcasa.nomina.liquidacion'
    _description = 'Cálculo de liquidación'
    _inherit = ['mail.thread']
    _order = 'fecha_salida desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    empleado_id = fields.Many2one('hr.employee', 'Colaborador', required=True, tracking=True)
    fecha_salida = fields.Date('Último día de trabajo', required=True, tracking=True,
                               default=fields.Date.context_today)
    motivo = fields.Selection(MOTIVOS, required=True, default='renuncia', tracking=True)
    estado = fields.Selection(
        [('borrador', 'Borrador'), ('calculada', 'Calculada'), ('revisada', 'Revisada por el contador')],
        default='borrador', required=True, readonly=True, tracking=True)
    parametros_id = fields.Many2one('dcasa.nomina.parametros', readonly=True)
    parametros_validados = fields.Boolean('Tasas validadas', compute='_compute_parametros_validados')

    ingreso = fields.Date(readonly=True)
    salario_mensual = fields.Monetary(readonly=True)
    salario_promedio = fields.Monetary('Salario promedio mensual', readonly=True)
    anios = fields.Float('Años de servicio', digits=(6, 4), readonly=True)

    dias_pendientes = fields.Integer('Días de salario sin pagar',
                                     help='Desde el día siguiente al último periodo pagado hasta la salida.')
    salario_pendiente = fields.Monetary(readonly=True)
    decimo_proporcional = fields.Monetary('Décimo tercer mes proporcional', readonly=True)
    vacaciones_dias = fields.Float('Vacaciones sin tomar (días)', readonly=True)
    vacaciones_valor = fields.Monetary('Vacaciones sin tomar ($)', readonly=True)
    incluir_prima = fields.Boolean('Corresponde prima de antigüedad', default=True,
                                   help='La decide el contador según el motivo de la salida.')
    prima = fields.Monetary('Prima de antigüedad', readonly=True)
    indemnizacion = fields.Monetary('Indemnización / preaviso (lo escribe el contador)')
    seguro_social = fields.Monetary('Seguro social y educativo sobre salario, décimo y vacaciones', readonly=True)
    isr = fields.Monetary('ISR de la liquidación (lo escribe el contador)')
    total = fields.Monetary('Total a pagar', compute='_compute_total', store=True)
    notas = fields.Text()

    @api.depends('parametros_id.estado')
    def _compute_parametros_validados(self):
        for liq in self:
            liq.parametros_validados = liq.parametros_id.estado == 'validado'

    @api.depends('empleado_id', 'fecha_salida')
    def _compute_name(self):
        for liq in self:
            liq.name = self.env._('Liquidación de %(quien)s al %(fecha)s', quien=liq.empleado_id.name or '?',
                                  fecha=liq.fecha_salida)

    @api.depends('salario_pendiente', 'decimo_proporcional', 'vacaciones_valor', 'prima', 'indemnizacion',
                 'seguro_social', 'isr')
    def _compute_total(self):
        for liq in self:
            liq.total = calculo.r2(liq.salario_pendiente + liq.decimo_proporcional + liq.vacaciones_valor + liq.prima
                                   + liq.indemnizacion - liq.seguro_social - liq.isr)

    def action_calcular(self):
        self.check_access('write')
        for liq in self:
            liq._calcular()
        return True

    def _calcular(self):
        self.ensure_one()
        empleado = self.empleado_id
        ingreso = empleado._dcasa_ingreso()
        if not ingreso:
            raise UserError(self.env._('%s no tiene fecha de ingreso en su ficha.', empleado.name))
        if self.fecha_salida < ingreso:
            raise UserError(self.env._('La salida es anterior al ingreso (%s).', ingreso))
        vigencia = self.env['dcasa.nomina.parametros']._vigente(self.fecha_salida, self.company_id)
        if not vigencia:
            raise UserError(self.env._(
                'No hay tasas cargadas para esa fecha (Nómina › Configuración › Tasas y reglas).'))
        salida = self.fecha_salida
        mensual = empleado._dcasa_salario_mensual(salida)
        promedio = empleado._dcasa_salario_promedio(salida)
        # Salario sin pagar: del día siguiente al último periodo quincenal pagado hasta la salida.
        ultima = self.env['dcasa.nomina.planilla'].search([
            ('company_id', '=', self.company_id.id), ('tipo', '=', 'quincenal'),
            ('estado', 'in', ('confirmada', 'pagada')), ('linea_ids.empleado_id', '=', empleado.id)],
            order='fecha_hasta desc', limit=1)
        desde_pendiente = (ultima.fecha_hasta.toordinal() + 1) if ultima else ingreso.toordinal()
        pendientes = max(salida.toordinal() - desde_pendiente + 1, 0)
        salario_pendiente = calculo.valor_de_los_dias(mensual, pendientes)
        # Décimo proporcional: la partida en curso al día de la salida, hasta la salida.
        _partida, inicio_partida, _fin, _pago = calculo.partida_de(salida)
        base, _cubiertos, _trabajados = empleado._dcasa_base_decimo(inicio_partida, salida, self.company_id)
        decimo = calculo.decimo(base)
        _ganadas, _tomadas, saldo = empleado._dcasa_vacaciones(salida)
        vac_valor = calculo.valor_de_los_dias(promedio, max(saldo, 0.0))
        anios = calculo.anios_de_servicio(ingreso, salida)
        prima = (calculo.prima_de_antiguedad(promedio, anios, vigencia.prima_semanas_por_anio, vigencia.semanas_por_mes)
                 if self.incluir_prima else 0.0)
        seguro = calculo.r2(
            calculo.porcentaje(salario_pendiente + vac_valor, vigencia.css_trabajador + vigencia.se_trabajador)
            + calculo.porcentaje(decimo, vigencia.css_trabajador_decimo + vigencia.se_trabajador_decimo))
        self.write({
            'parametros_id': vigencia.id, 'ingreso': ingreso, 'salario_mensual': mensual, 'salario_promedio': promedio,
            'anios': anios, 'dias_pendientes': pendientes, 'salario_pendiente': salario_pendiente,
            'decimo_proporcional': decimo, 'vacaciones_dias': max(saldo, 0.0), 'vacaciones_valor': vac_valor,
            'prima': prima, 'seguro_social': seguro, 'estado': 'calculada'})

    def action_revisar(self):
        self.check_access('write')
        for liq in self:
            if liq.estado != 'calculada':
                raise UserError(self.env._('Calcula la liquidación antes de marcarla como revisada.'))
            if liq.parametros_id.estado != 'validado':
                raise UserError(self.env._('Las tasas usadas todavía no las valida el contador.'))
        self.sudo().write({'estado': 'revisada'})
        return True

    def action_borrador(self):
        self.check_access('write')
        self.sudo().write({'estado': 'borrador'})
        return True
