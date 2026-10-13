"""Ficha del colaborador para la nómina: se apoya en la ficha de empleado de Odoo (``hr``), que ya guarda el
salario mensual con su historial de versiones, la fecha de ingreso y salida, la cédula, el seguro social y
la cuenta bancaria. Aquí solo se agrega lo que la planilla necesita y los saldos de vacaciones y prima."""
from datetime import timedelta

from odoo import api, fields, models

from . import calculo

GRUPO = 'dcasa_nomina.group_nomina'


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    dcasa_en_planilla = fields.Boolean('Incluir en la planilla', default=True, groups=GRUPO,
                                       help='Desmárcalo para quien no cobra por la planilla (socios, honorarios).')
    dcasa_forma_pago = fields.Selection(
        [('transferencia', 'Transferencia (ACH)'), ('efectivo', 'Efectivo'), ('cheque', 'Cheque')],
        'Forma de pago', default='transferencia', groups=GRUPO)
    dcasa_deduccion_isr_anual = fields.Float(
        'Deducciones de ISR al año ($)', groups=GRUPO,
        help='Lo que el contador autoriza deducir a esta persona en el año (dependientes, intereses, etc.). '
             'Se resta de la renta antes de aplicar los tramos.')
    dcasa_vacaciones_ids = fields.One2many('dcasa.nomina.vacacion', 'empleado_id', groups=GRUPO)
    dcasa_vac_ganadas = fields.Float('Vacaciones ganadas (días)', compute='_compute_dcasa_saldos', groups=GRUPO)
    dcasa_vac_tomadas = fields.Float('Vacaciones tomadas (días)', compute='_compute_dcasa_saldos', groups=GRUPO)
    dcasa_vac_saldo = fields.Float('Saldo de vacaciones (días)', compute='_compute_dcasa_saldos', groups=GRUPO)
    dcasa_vac_valor = fields.Float('Valor del saldo ($)', compute='_compute_dcasa_saldos', groups=GRUPO)
    dcasa_prima_acumulada = fields.Float('Prima de antigüedad acumulada ($)', compute='_compute_dcasa_saldos',
                                         groups=GRUPO)

    # ------------------------------------------------------------------
    # Datos de la ficha para la planilla
    # ------------------------------------------------------------------

    def _dcasa_ingreso(self):
        self.ensure_one()
        return self.contract_date_start or False

    def _dcasa_salario_mensual(self, fecha=None):
        """Salario mensual vigente en ``fecha`` (el historial de versiones de la ficha)."""
        self.ensure_one()
        return self._get_version(fecha or fields.Date.context_today(self)).wage or 0.0

    def _dcasa_salario_promedio(self, hasta):
        """Promedio mensual de lo devengado en los últimos 11 meses de planillas confirmadas; sin 11 meses de
        historia en el sistema se usa el salario mensual actual (REQUIERE CONTADOR si hay comisiones)."""
        self.ensure_one()
        desde = hasta - timedelta(days=334)
        lineas = self.env['dcasa.nomina.linea'].search([
            ('empleado_id', '=', self.id), ('planilla_id.tipo', '=', 'quincenal'),
            ('planilla_id.estado', 'in', ('confirmada', 'pagada')),
            ('planilla_id.fecha_hasta', '>=', desde), ('planilla_id.fecha_hasta', '<=', hasta)])
        if len(lineas) >= 22:  # 11 meses con sus dos quincenas
            return calculo.r2(sum(lineas.mapped('devengado')) / (len(lineas) / 2.0))
        return self._dcasa_salario_mensual(hasta)

    def _dcasa_base_decimo(self, desde, hasta, company=None):
        """``(base, cubiertos, trabajados)``: lo devengado entre ``desde`` y ``hasta`` según las planillas
        quincenales confirmadas; los días trabajados sin planilla en el sistema se estiman con el salario."""
        self.ensure_one()
        company = company or self.company_id
        trabajados = calculo.dias_pagados(desde, hasta, self._dcasa_ingreso(), self.contract_date_end)
        historicas = self.env['dcasa.nomina.linea'].search([
            ('empleado_id', '=', self.id), ('planilla_id.tipo', '=', 'quincenal'),
            ('planilla_id.estado', 'in', ('confirmada', 'pagada')), ('planilla_id.company_id', '=', company.id),
            ('planilla_id.fecha_hasta', '>=', desde), ('planilla_id.fecha_hasta', '<=', hasta)])
        cubiertos = sum(historicas.mapped('dias_pagados'))
        base = sum(historicas.mapped('devengado'))
        faltan = max(trabajados - cubiertos, 0)
        if faltan:
            base += calculo.valor_de_los_dias(self._dcasa_salario_mensual(hasta), faltan)
        return calculo.r2(base), cubiertos, trabajados

    def _dcasa_vacaciones(self, hasta=None):
        """``(ganadas, tomadas, saldo)`` en días a la fecha ``hasta``."""
        self.ensure_one()
        hasta = hasta or fields.Date.context_today(self)
        ingreso = self._dcasa_ingreso()
        if not ingreso:
            return 0.0, 0.0, 0.0
        vigencia = self.env['dcasa.nomina.parametros']._vigente(hasta, self.company_id)
        dias_por_dia = (vigencia.vacaciones_dias_de_trabajo_por_dia_de_descanso if vigencia else 0) or 11.0
        servicio = (min(hasta, self.contract_date_end or hasta) - ingreso).days + 1
        ganadas = calculo.vacaciones_ganadas(servicio, dias_por_dia)
        tomadas = sum(self.env['dcasa.nomina.vacacion'].search([
            ('empleado_id', '=', self.id), ('estado', '=', 'confirmada'), ('desde', '<=', hasta)]).mapped('dias'))
        return ganadas, tomadas, round(ganadas - tomadas, 2)

    def _dcasa_prima(self, hasta=None):
        self.ensure_one()
        hasta = hasta or fields.Date.context_today(self)
        ingreso = self._dcasa_ingreso()
        if not ingreso:
            return 0.0
        vigencia = self.env['dcasa.nomina.parametros']._vigente(hasta, self.company_id)
        semanas = (vigencia.prima_semanas_por_anio if vigencia else 0) or 1.0
        por_mes = (vigencia.semanas_por_mes if vigencia else 0) or 4.3333
        anios = calculo.anios_de_servicio(ingreso, min(hasta, self.contract_date_end or hasta))
        return calculo.prima_de_antiguedad(self._dcasa_salario_promedio(hasta), anios, semanas, por_mes)

    @api.depends('contract_date_start', 'contract_date_end', 'wage', 'dcasa_vacaciones_ids.dias',
                 'dcasa_vacaciones_ids.estado')
    def _compute_dcasa_saldos(self):
        hoy = fields.Date.context_today(self)
        for empleado in self:
            ganadas, tomadas, saldo = empleado._dcasa_vacaciones(hoy)
            empleado.dcasa_vac_ganadas = ganadas
            empleado.dcasa_vac_tomadas = tomadas
            empleado.dcasa_vac_saldo = saldo
            empleado.dcasa_vac_valor = calculo.valor_de_los_dias(empleado._dcasa_salario_promedio(hoy), saldo)
            empleado.dcasa_prima_acumulada = empleado._dcasa_prima(hoy)
