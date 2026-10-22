"""Planillas: la quincenal y el décimo tercer mes, con su asiento contable y su pago.

Flujo: Borrador → Calculada → Confirmada (asiento publicado) → Pagada. Calcular se puede repetir cuantas
veces haga falta mientras no esté confirmada (conserva lo que se escribió a mano: otros ingresos, descuentos).
Confirmar exige tasas VALIDADAS por el contador y las cuentas configuradas; sin eso la planilla es solo un
borrador para ver cómo queda.
"""
from collections import defaultdict
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from . import calculo

GRUPO = 'dcasa_nomina.group_nomina'
ESTADOS_EDITABLES = ('borrador', 'calculada')


def _ultima_quincena(hoy):
    """Última quincena completa antes de ``hoy``."""
    if hoy.day > 15:
        return hoy.replace(day=1), hoy.replace(day=15)
    fin = hoy.replace(day=1) - timedelta(days=1)
    return fin.replace(day=16), fin


class DcasaNominaPlanilla(models.Model):
    _name = 'dcasa.nomina.planilla'
    _description = 'Planilla de pago'
    _inherit = ['mail.thread']
    _order = 'fecha_hasta desc, id desc'

    name = fields.Char('Planilla', compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    tipo = fields.Selection([('quincenal', 'Quincenal'), ('decimo', 'Décimo tercer mes')], required=True,
                            default='quincenal', tracking=True)
    estado = fields.Selection(
        [('borrador', 'Borrador'), ('calculada', 'Calculada'), ('confirmada', 'Confirmada'),
         ('pagada', 'Pagada'), ('cancelada', 'Cancelada')],
        default='borrador', required=True, readonly=True, tracking=True, copy=False)
    anio = fields.Integer('Año', default=lambda self: fields.Date.context_today(self).year,
                          help='Solo para el décimo tercer mes.')
    partida = fields.Selection([('1', '1.ª partida (se paga el 15 de abril)'), ('2', '2.ª partida (15 de agosto)'),
                                ('3', '3.ª partida (15 de diciembre)')], string='Partida')
    fecha_desde = fields.Date('Desde', compute='_compute_fechas', store=True, readonly=False, required=True,
                              precompute=True, tracking=True)
    fecha_hasta = fields.Date('Hasta', compute='_compute_fechas', store=True, readonly=False, required=True,
                              precompute=True, tracking=True)
    fecha_pago = fields.Date('Fecha de pago', compute='_compute_fechas', store=True, readonly=False, required=True,
                             precompute=True)
    parametros_id = fields.Many2one('dcasa.nomina.parametros', 'Tasas usadas', readonly=True, copy=False)
    parametros_validados = fields.Boolean(compute='_compute_parametros_validados')
    linea_ids = fields.One2many('dcasa.nomina.linea', 'planilla_id', string='Colaboradores', copy=False)
    avisos = fields.Text(readonly=True, copy=False)
    move_id = fields.Many2one('account.move', 'Asiento', readonly=True, copy=False)
    move_reverso_id = fields.Many2one('account.move', 'Asiento de reverso', readonly=True, copy=False)
    diario_pago_id = fields.Many2one('account.journal', 'Pagar desde', domain="[('type', 'in', ('bank', 'cash'))]",
                                     check_company=True)

    total_devengado = fields.Monetary(compute='_compute_totales', store=True)
    total_descuentos = fields.Monetary('Descuentos', compute='_compute_totales', store=True)
    total_reembolsos = fields.Monetary('Reembolsos', compute='_compute_totales', store=True)
    total_prestamos = fields.Monetary('Adelantos y préstamos', compute='_compute_totales', store=True,
                                      help='Lo que se descuenta en esta planilla de adelantos y préstamos.')
    total_neto = fields.Monetary('Neto a pagar', compute='_compute_totales', store=True)
    total_patronal = fields.Monetary('Aportes del patrono', compute='_compute_totales', store=True)
    colaboradores = fields.Integer('N.º de colaboradores', compute='_compute_totales', store=True)

    @api.depends('tipo', 'fecha_desde', 'fecha_hasta', 'anio', 'partida')
    def _compute_name(self):
        for planilla in self:
            if planilla.tipo == 'decimo':
                planilla.name = self.env._('Décimo tercer mes %(anio)s · partida %(partida)s',
                                           anio=planilla.anio, partida=planilla.partida or '?')
            elif planilla.fecha_desde and planilla.fecha_hasta:
                planilla.name = self.env._('Quincena del %(desde)s al %(hasta)s', desde=planilla.fecha_desde,
                                           hasta=planilla.fecha_hasta)
            else:
                planilla.name = self.env._('Planilla nueva')

    @api.depends('tipo', 'anio', 'partida')
    def _compute_fechas(self):
        hoy = fields.Date.context_today(self)
        for planilla in self:
            desde, hasta, pago = planilla.fecha_desde, planilla.fecha_hasta, planilla.fecha_pago
            if planilla.tipo == 'decimo' and planilla.anio and planilla.partida:
                desde, hasta, pago = calculo.fechas_de_la_partida(planilla.partida, planilla.anio)
            elif not desde or not hasta:
                desde, hasta = _ultima_quincena(hoy)
                pago = hasta
            elif not pago:
                pago = hasta
            planilla.fecha_desde, planilla.fecha_hasta, planilla.fecha_pago = desde, hasta, pago

    @api.depends('parametros_id.estado')
    def _compute_parametros_validados(self):
        for planilla in self:
            planilla.parametros_validados = planilla.parametros_id.estado == 'validado'

    @api.depends('linea_ids.devengado', 'linea_ids.css_trabajador', 'linea_ids.se_trabajador', 'linea_ids.isr',
                 'linea_ids.otros_descuentos', 'linea_ids.reembolsos', 'linea_ids.neto', 'linea_ids.costo_patronal',
                 'linea_ids.prestamos')
    def _compute_totales(self):
        for planilla in self:
            lineas = planilla.linea_ids
            planilla.colaboradores = len(lineas)
            planilla.total_devengado = sum(lineas.mapped('devengado'))
            planilla.total_descuentos = sum(
                ln.css_trabajador + ln.se_trabajador + ln.isr + ln.otros_descuentos + ln.prestamos for ln in lineas)
            planilla.total_reembolsos = sum(lineas.mapped('reembolsos'))
            planilla.total_prestamos = sum(lineas.mapped('prestamos'))
            planilla.total_neto = sum(lineas.mapped('neto'))
            planilla.total_patronal = sum(lineas.mapped('costo_patronal'))

    # ------------------------------------------------------------------
    # Reglas
    # ------------------------------------------------------------------

    @api.constrains('tipo', 'fecha_desde', 'fecha_hasta', 'partida', 'anio', 'estado', 'company_id')
    def _check_periodo(self):
        for planilla in self:
            if planilla.fecha_hasta < planilla.fecha_desde:
                raise ValidationError(self.env._('El periodo termina antes de empezar.'))
            if planilla.estado == 'cancelada':
                continue
            if planilla.tipo == 'decimo':
                if not planilla.partida:
                    raise ValidationError(self.env._('Elige la partida del décimo tercer mes.'))
                dominio = [('tipo', '=', 'decimo'), ('anio', '=', planilla.anio), ('partida', '=', planilla.partida)]
            else:
                dominio = [('tipo', '=', 'quincenal'), ('fecha_desde', '<=', planilla.fecha_hasta),
                           ('fecha_hasta', '>=', planilla.fecha_desde)]
            otras = self.sudo().search(dominio + [('company_id', '=', planilla.company_id.id),
                                                  ('estado', '!=', 'cancelada'), ('id', '!=', planilla.id)])
            if otras:
                raise ValidationError(self.env._('Ya existe la planilla «%s» para ese periodo: no se paga dos veces.',
                                                 otras[0].name))

    def write(self, vals):
        if 'estado' in vals and not self.env.su:
            raise AccessError(self.env._('El estado de la planilla solo cambia con sus botones.'))
        bloqueados = {'fecha_desde', 'fecha_hasta', 'anio', 'partida', 'tipo', 'company_id'}
        if bloqueados.intersection(vals) and not self.env.su and self.filtered(
                lambda p: p.estado not in ESTADOS_EDITABLES):
            raise UserError(self.env._('Una planilla confirmada o pagada no cambia de periodo.'))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _no_borrar_contabilizadas(self):
        if self.filtered(lambda p: p.estado not in ESTADOS_EDITABLES + ('cancelada',) or p.move_id):
            raise UserError(self.env._('Una planilla contabilizada no se borra: se reversa (queda el historial).'))

    # ------------------------------------------------------------------
    # Cálculo
    # ------------------------------------------------------------------

    def _elegibles(self):
        """``(empleados, avisos)``: quién entra en este periodo y a quién no (con el motivo)."""
        self.ensure_one()
        avisos = []
        elegibles = self.env['hr.employee']
        empleados = self.env['hr.employee'].with_company(self.company_id).search(
            [('company_id', '=', self.company_id.id), ('dcasa_en_planilla', '=', True)])
        for empleado in empleados.sorted('name'):
            ingreso, salida = empleado._dcasa_ingreso(), empleado.contract_date_end
            if not ingreso:
                avisos.append(self.env._('%s: no tiene fecha de ingreso (pestaña Nómina de su ficha).', empleado.name))
                continue
            if ingreso > self.fecha_hasta or (salida and salida < self.fecha_desde):
                continue
            if not empleado._dcasa_salario_mensual(self.fecha_hasta):
                avisos.append(self.env._('%s: no tiene salario mensual en su ficha.', empleado.name))
                continue
            elegibles |= empleado
        return elegibles, avisos

    def _base_decimo(self, empleado):
        """``(base, aviso|None)``: lo devengado por la persona en el periodo de la partida (planillas
        confirmadas; lo que no tiene planilla en el sistema se estima con su salario y se avisa)."""
        self.ensure_one()
        base, cubiertos, trabajados = empleado._dcasa_base_decimo(self.fecha_desde, self.fecha_hasta, self.company_id)
        aviso = None
        if cubiertos < trabajados:
            aviso = self.env._(
                '%(nombre)s: el sistema solo tiene planillas confirmadas de %(cubiertos)s de los %(trabajados)s días '
                'del periodo; el resto se estimó con su salario (revisa la base).',
                nombre=empleado.name, cubiertos=cubiertos, trabajados=trabajados)
        return base, aviso

    def _calcular(self):
        self.ensure_one()
        if self.estado not in ESTADOS_EDITABLES:
            raise UserError(self.env._('Solo se calcula una planilla en borrador o ya calculada.'))
        vigencia = self.env['dcasa.nomina.parametros']._vigente(self.fecha_hasta, self.company_id)
        if not vigencia:
            raise UserError(self.env._(
                'No hay tasas cargadas para esa fecha. Créalas en Nómina › Configuración › Tasas y reglas y '
                'pídele al contador que las valide.'))
        if self.tipo == 'decimo' and not vigencia.decimo_listo:
            raise UserError(self.env._(
                'Faltan confirmar las tasas del décimo tercer mes en «%s» (Nómina › Configuración › Tasas y reglas).',
                vigencia.name))
        elegibles, avisos = self._elegibles()
        existentes = {ln.empleado_id: ln for ln in self.linea_ids}
        self.linea_ids.filtered(lambda ln: ln.empleado_id not in elegibles)._liberar_reembolsos()
        self.linea_ids.filtered(lambda ln: ln.empleado_id not in elegibles)._liberar_bonos()
        self.linea_ids.filtered(lambda ln: ln.empleado_id not in elegibles).unlink()
        crear = []
        for empleado in elegibles:
            valores = {'dias_periodo': calculo.dias_del_periodo(self.fecha_desde, self.fecha_hasta)}
            if self.tipo == 'quincenal':
                valores.update({
                    'dias_pagados': calculo.dias_pagados(self.fecha_desde, self.fecha_hasta,
                                                         empleado._dcasa_ingreso(), empleado.contract_date_end),
                    'salario_mensual': empleado._dcasa_salario_mensual(self.fecha_hasta)})
            else:
                base, aviso = self._base_decimo(empleado)
                if aviso:
                    avisos.append(aviso)
                valores.update({
                    'dias_pagados': calculo.dias_pagados(self.fecha_desde, self.fecha_hasta,
                                                         empleado._dcasa_ingreso(), empleado.contract_date_end),
                    'salario_mensual': empleado._dcasa_salario_mensual(self.fecha_hasta), 'base_decimo': base})
            linea = existentes.get(empleado)
            if linea:
                linea.write(valores)
            else:
                crear.append({**valores, 'planilla_id': self.id, 'empleado_id': empleado.id})
        if crear:
            self.env['dcasa.nomina.linea'].create(crear)
        avisos += self._enlazar_bonos()
        self.sudo().write({'parametros_id': vigencia.id, 'avisos': '\n'.join(avisos) or False, 'estado': 'calculada'})
        if self.tipo == 'quincenal':
            self._enlazar_reembolsos()
        avisos_prestamos = self._enlazar_prestamos()
        if avisos_prestamos:
            self.sudo().avisos = '\n'.join(filter(None, [self.avisos, *avisos_prestamos]))
        # Recalcular también revierte un salario escrito a mano y toma los reembolsos recién enlazados.
        self.linea_ids._compute_salario()
        self.linea_ids._compute_importes()

    def action_calcular(self):
        self.check_access('write')
        for planilla in self:
            planilla._calcular()
        return True

    def _enlazar_bonos(self):
        """El bono por meta de ventas entra en la PRIMERA planilla quincenal del mes (del 1 al 15), como comisión
        (decisión del jefe, 2026-10-16; ``meta_ventas.py``): el del mes anterior y cualquiera que haya quedado por pagar
        de antes. Cada bono se pone al día y se enlaza a la línea de su colaborador, también el que dio cero: así su mes
        queda cerrado y lo que llegue tarde cuenta en el mes siguiente. Devuelve los avisos: quien ganó bono y no está
        en esta planilla (le falta salario o fecha de ingreso) sigue con su bono por pagar para la próxima.

        Cualquier otra planilla (segunda quincena, décimo) suelta los bonos que tuviera y no lleva comisión."""
        self.ensure_one()
        self.linea_ids._liberar_bonos()
        avisos = []
        if self.tipo == 'quincenal' and self.fecha_desde.day == 1:
            Bono = self.env['dcasa.nomina.meta.bono'].sudo()
            mes_anterior = self.fecha_desde - relativedelta(months=1)
            Bono._actualizar(self.company_id, [mes_anterior])
            lineas = {ln.empleado_id: ln for ln in self.linea_ids}
            abiertos = Bono.search([('company_id', '=', self.company_id.id), ('mes', '<=', mes_anterior),
                                    ('estado', '=', 'abierto')], order='mes, id')
            for bono in abiertos:
                Bono._calcular(bono.empleado_id, bono.mes, self.company_id)    # lo pone al día (es el mismo registro)
                if bono.empleado_id in lineas:
                    bono.write({'linea_id': lineas[bono.empleado_id].id})
                elif bono.monto:
                    avisos.append(self.env._(
                        '%(nombre)s ganó %(monto)s de bono por la meta de ventas de %(mes)s, pero no entra en esta '
                        'planilla (le falta salario o fecha de ingreso en su ficha): el bono queda por pagar y entra '
                        'en la próxima primera quincena que la incluya.',
                        nombre=bono.empleado_id.name, monto=f'{bono.monto:,.2f}', mes=bono.mes.strftime('%m/%Y')))
            for bono in Bono.search([('empleado_id', 'in', [e.id for e in lineas]), ('mes', '<=', mes_anterior),
                                     ('estado', '=', 'en_planilla'), ('linea_id.planilla_id', '!=', self.id)]):
                avisos.append(self.env._('%(nombre)s: su bono por meta de %(mes)s ya está en la planilla %(otra)s.',
                                         nombre=bono.empleado_id.name, mes=bono.mes.strftime('%m/%Y'),
                                         otra=bono.linea_id.planilla_id.name))
        for linea in self.linea_ids:
            comision = calculo.r2(sum(linea.bono_ids.mapped('monto')))
            if linea.comision_meta != comision:
                linea.comision_meta = comision
        return avisos

    def _enlazar_reembolsos(self):
        """Los reembolsos aprobados de cada colaborador entran en su línea de esta planilla quincenal."""
        self.ensure_one()
        Reembolso = self.env['dcasa.nomina.reembolso']
        lineas = {ln.empleado_id.id: ln for ln in self.linea_ids}
        pendientes = Reembolso.search([('estado', '=', 'aprobado'), ('company_id', '=', self.company_id.id),
                                       ('empleado_id', 'in', list(lineas)), ('fecha', '<=', self.fecha_hasta)])
        for reembolso in pendientes:
            reembolso.sudo().write({'linea_id': lineas[reembolso.empleado_id.id].id, 'estado': 'en_planilla'})

    def _enlazar_prestamos(self):
        """Los adelantos y préstamos entregados de cada colaborador descuentan su cuota en esta planilla quincenal
        (G7). Se rehace en cada cálculo: la cuota nunca pasa de lo que le queda por descontar, contando lo reservado
        en otras planillas sin confirmar. El décimo tercer mes no descuenta adelantos. Devuelve avisos."""
        self.ensure_one()
        self.linea_ids.prestamo_descuento_ids.sudo().unlink()
        if self.tipo != 'quincenal':
            return []
        lineas = {ln.empleado_id.id: ln for ln in self.linea_ids}
        prestamos = self.env['dcasa.nomina.prestamo'].sudo().search([
            ('estado', '=', 'entregado'), ('company_id', '=', self.company_id.id),
            ('empleado_id', 'in', list(lineas)), ('primera_quincena', '<=', self.fecha_hasta)], order='fecha, id')
        crear, avisos = [], []
        for prestamo in prestamos:
            cuota = prestamo._cuota_para(self)
            if cuota > 0:
                crear.append({'prestamo_id': prestamo.id, 'linea_id': lineas[prestamo.empleado_id.id].id,
                              'monto': cuota})
        if crear:
            self.env['dcasa.nomina.prestamo.descuento'].sudo().create(crear)
        sin_planilla = self.env['dcasa.nomina.prestamo'].sudo().search([
            ('estado', '=', 'entregado'), ('company_id', '=', self.company_id.id),
            ('empleado_id', 'not in', list(lineas)), ('primera_quincena', '<=', self.fecha_hasta)])
        for prestamo in sin_planilla:
            avisos.append(self.env._(
                '%(nombre)s tiene un adelanto por descontar (saldo %(saldo)s) pero no entra en esta planilla: se '
                'descuenta en la próxima que lo incluya.', nombre=prestamo.empleado_id.name,
                saldo=f'{prestamo.saldo:,.2f}'))
        return avisos

    # ------------------------------------------------------------------
    # Contabilidad
    # ------------------------------------------------------------------

    def _sumas(self):
        lineas = self.linea_ids
        return {
            'devengado': sum(lineas.mapped('devengado')), 'css': sum(lineas.mapped('css_trabajador')),
            'se': sum(lineas.mapped('se_trabajador')), 'isr': sum(lineas.mapped('isr')),
            'otros': sum(lineas.mapped('otros_descuentos')), 'css_p': sum(lineas.mapped('css_patronal')),
            'se_p': sum(lineas.mapped('se_patronal')), 'rp': sum(lineas.mapped('riesgo_profesional')),
            'prestamos': sum(lineas.mapped('prestamos')),
        }

    def _cuentas_necesarias(self, sumas, provisiona):
        """Las cuentas de la configuración que este asiento va a usar (sin ellas no se confirma)."""
        necesarias = ['cuenta_gasto_sueldos_id', 'cuenta_sueldos_pagar_id']
        condiciones = (
            (sumas['css'] or sumas['css_p'], 'cuenta_css_pagar_id'),
            (sumas['se'] or sumas['se_p'], 'cuenta_se_pagar_id'),
            (sumas['rp'], 'cuenta_rp_pagar_id'),
            (sumas['css_p'] or sumas['se_p'] or sumas['rp'], 'cuenta_gasto_cargas_id'),
            (sumas['isr'], 'cuenta_isr_pagar_id'),
            (sumas['otros'], 'cuenta_otros_descuentos_id'),
            (sumas['prestamos'], 'cuenta_prestamos_id'),
            (provisiona, 'cuenta_decimo_id'),
        )
        return necesarias + [cuenta for hace_falta, cuenta in condiciones if hace_falta]

    def _lineas_del_asiento(self, config):
        """Apuntes del asiento de la planilla (siempre cuadran: ver la cuenta en docs/NOMINA.md)."""
        self.ensure_one()
        moneda = self.currency_id
        s = self._sumas()
        provisiona = config.provisionar_decimo
        reembolsos = defaultdict(float)
        for ln in self.linea_ids:
            for reembolso in ln.reembolso_ids:
                reembolsos[reembolso.cuenta_gasto_id] += reembolso.monto
        config._exigir(*self._cuentas_necesarias(s, provisiona))
        if any(not cuenta for cuenta in reembolsos):
            raise UserError(self.env._('Hay reembolsos sin cuenta de gasto: ábrelos y elige la cuenta.'))

        apuntes = []

        def apunte(cuenta, debe=0.0, haber=0.0, nombre=None, socio=None):
            debe, haber = moneda.round(debe), moneda.round(haber)
            if not debe and not haber:
                return
            apuntes.append(Command.create({
                'account_id': cuenta.id, 'debit': debe, 'credit': haber, 'name': nombre or self.name,
                'partner_id': socio.id if socio else False}))

        def texto(motivo):
            return self.env._('%(planilla)s: %(motivo)s', planilla=self.name, motivo=motivo)

        if self.tipo == 'decimo' and provisiona:
            apunte(config.cuenta_decimo_id, debe=s['devengado'], nombre=texto(self.env._('se paga lo provisionado')))
        else:
            apunte(config.cuenta_gasto_sueldos_id, debe=s['devengado'])
        apunte(config.cuenta_gasto_cargas_id, debe=s['css_p'] + s['se_p'] + s['rp'],
               nombre=texto(self.env._('aportes del patrono')))
        for cuenta, monto in reembolsos.items():
            apunte(cuenta, debe=monto, nombre=texto(self.env._('reembolsos')))
        for ln in self.linea_ids:
            apunte(config.cuenta_sueldos_pagar_id, haber=ln.neto, nombre=ln.empleado_id.name, socio=ln._socio())
        apunte(config.cuenta_css_pagar_id, haber=s['css'] + s['css_p'], nombre=texto(self.env._('seguro social')))
        apunte(config.cuenta_se_pagar_id, haber=s['se'] + s['se_p'], nombre=texto(self.env._('seguro educativo')))
        apunte(config.cuenta_rp_pagar_id, haber=s['rp'], nombre=texto(self.env._('riesgo profesional')))
        apunte(config.cuenta_isr_pagar_id, haber=s['isr'], nombre=texto(self.env._('ISR retenido')))
        apunte(config.cuenta_otros_descuentos_id, haber=s['otros'], nombre=texto(self.env._('otros descuentos')))
        # Cada cuota baja lo que esa persona le debe a la empresa (a su nombre, para seguir su saldo en contabilidad).
        for ln in self.linea_ids.filtered('prestamos'):
            apunte(config.cuenta_prestamos_id, haber=ln.prestamos, socio=ln._socio(),
                   nombre=texto(self.env._('adelanto de %s', ln.empleado_id.name)))
        if self.tipo == 'quincenal' and provisiona:
            parte = moneda.round(s['devengado'] / calculo.DIVISOR_DECIMO)
            apunte(config.cuenta_gasto_sueldos_id, debe=parte, nombre=texto(self.env._('provisión del décimo')))
            apunte(config.cuenta_decimo_id, haber=parte, nombre=texto(self.env._('provisión del décimo')))
        return apuntes

    def action_confirmar(self):
        self.check_access('write')
        for planilla in self:
            if planilla.estado != 'calculada':
                raise UserError(self.env._('Calcula la planilla antes de confirmarla.'))
            if not planilla.linea_ids:
                raise UserError(self.env._('La planilla no tiene colaboradores.'))
            vigencia = self.env['dcasa.nomina.parametros']._vigente(planilla.fecha_hasta, planilla.company_id)
            if vigencia != planilla.parametros_id:
                raise UserError(self.env._('Las tasas que rigen para este periodo cambiaron desde el cálculo: '
                                           'vuelve a calcular.'))
            if vigencia.estado != 'validado':
                raise UserError(self.env._(
                    'Las tasas «%s» todavía no las valida el contador: la planilla queda como borrador. Pídele que '
                    'las valide en Nómina › Configuración › Tasas y reglas.', vigencia.name))
            negativos = planilla.linea_ids.filtered(lambda ln: ln.neto < 0)
            if negativos:
                raise UserError(self.env._('Los descuentos de %s superan lo que se le paga: revisa la planilla.',
                                           ', '.join(negativos.mapped('empleado_id.name'))))
            config = self.env['dcasa.nomina.config']._de(planilla.company_id)
            apuntes = planilla._lineas_del_asiento(config)
            asiento = self.env['account.move'].create({
                'move_type': 'entry', 'date': planilla.fecha_hasta, 'journal_id': config.diario_id.id,
                'company_id': planilla.company_id.id, 'ref': planilla.name, 'line_ids': apuntes})
            asiento.action_post()
            planilla.linea_ids.reembolso_ids.sudo().write({'estado': 'contabilizado'})
            planilla.sudo().write({'estado': 'confirmada', 'move_id': asiento.id})
            planilla.linea_ids.prestamo_descuento_ids.prestamo_id._marcar_pagados()
            planilla.message_post(body=self.env._('Planilla confirmada. Asiento %s.', asiento.name))
        return True

    # ------------------------------------------------------------------
    # Pago
    # ------------------------------------------------------------------

    def action_pagar(self):
        """Un pago por colaborador, contra la cuenta de sueldos por pagar (se concilia con el banco como
        cualquier pago)."""
        self.check_access('write')
        for planilla in self:
            if planilla.estado != 'confirmada':
                raise UserError(self.env._('Solo se paga una planilla confirmada.'))
            if not planilla.diario_pago_id:
                raise UserError(self.env._('Elige el banco o la caja desde donde se paga (campo «Pagar desde»).'))
            config = self.env['dcasa.nomina.config']._de(planilla.company_id)
            config._exigir('cuenta_sueldos_pagar_id')
            for linea in planilla.linea_ids.filtered(lambda ln: ln.neto > 0 and not ln.payment_id):
                socio = linea._socio()
                pago = self.env['account.payment'].create({
                    'payment_type': 'outbound', 'partner_type': 'supplier', 'partner_id': socio.id,
                    'amount': linea.neto, 'currency_id': planilla.currency_id.id,
                    'journal_id': planilla.diario_pago_id.id, 'date': planilla.fecha_pago,
                    'memo': planilla.name, 'destination_account_id': config.cuenta_sueldos_pagar_id.id,
                    'company_id': planilla.company_id.id})
                pago.action_post()
                linea.sudo().write({'payment_id': pago.id})
                cuenta = config.cuenta_sueldos_pagar_id
                if cuenta.reconcile:
                    deuda = planilla.move_id.line_ids.filtered(
                        lambda ln, cuenta=cuenta, socio=socio: ln.account_id == cuenta and ln.partner_id == socio
                        and not ln.reconciled)
                    abono = pago.move_id.line_ids.filtered(
                        lambda ln, cuenta=cuenta: ln.account_id == cuenta and not ln.reconciled)
                    (deuda + abono).reconcile()
            if all(ln.payment_id or ln.neto <= 0 for ln in planilla.linea_ids):
                planilla.sudo().write({'estado': 'pagada'})
                planilla.message_post(body=self.env._('Planilla pagada desde %s.', planilla.diario_pago_id.name))
        return True

    # ------------------------------------------------------------------
    # Volver atrás
    # ------------------------------------------------------------------

    def action_borrador(self):
        self.check_access('write')
        for planilla in self:
            if planilla.estado not in ('calculada', 'cancelada'):
                raise UserError(self.env._('Solo vuelve a borrador una planilla calculada o cancelada sin asiento.'))
            if planilla.move_id:
                raise UserError(self.env._('Esta planilla ya tuvo asiento: no vuelve a borrador.'))
            planilla.sudo().write({'estado': 'borrador'})
        return True

    def action_cancelar(self):
        """Borrador o calculada: se cancela y sus reembolsos quedan libres. Confirmada: se reversa el asiento
        (si ya se pagó, primero se anulan los pagos)."""
        self.check_access('write')
        for planilla in self:
            if planilla.estado == 'cancelada':
                continue
            if planilla.estado == 'pagada' or any(ln.payment_id for ln in planilla.linea_ids):
                raise UserError(self.env._('Esta planilla ya tiene pagos: anúlalos primero en Facturación › Pagos.'))
            if planilla.estado == 'confirmada':
                reverso = planilla.move_id._reverse_moves(
                    default_values_list=[{'ref': self.env._('Reverso de %s', planilla.name),
                                          'date': fields.Date.context_today(planilla)}], cancel=True)
                planilla.sudo().write({'move_reverso_id': reverso.id})
                planilla.linea_ids.reembolso_ids.sudo().write({'estado': 'aprobado', 'linea_id': False})
            else:
                planilla.linea_ids._liberar_reembolsos()
            planilla.linea_ids._liberar_bonos()
            prestamos = planilla.linea_ids.prestamo_descuento_ids.prestamo_id
            if planilla.estado != 'confirmada':
                # Sin asiento: la reserva se suelta. Con asiento, las cuotas quedan como historia (no cuentan: la
                # planilla está cancelada y su asiento, reversado).
                planilla.linea_ids.prestamo_descuento_ids.sudo().unlink()
            planilla.sudo().write({'estado': 'cancelada'})
            prestamos._marcar_pagados()
            planilla.message_post(body=self.env._('Planilla cancelada por %s.', self.env.user.name))
        return True


class DcasaNominaLinea(models.Model):
    _name = 'dcasa.nomina.linea'
    _description = 'Línea de planilla (un colaborador)'
    _order = 'planilla_id, empleado_id'

    planilla_id = fields.Many2one('dcasa.nomina.planilla', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='planilla_id.company_id', store=True)
    currency_id = fields.Many2one(related='planilla_id.currency_id')
    estado = fields.Selection(related='planilla_id.estado')
    tipo = fields.Selection(related='planilla_id.tipo')
    empleado_id = fields.Many2one('hr.employee', 'Colaborador', required=True, index=True)
    dias_periodo = fields.Integer('Días del periodo')
    dias_pagados = fields.Integer('Días pagados')
    salario_mensual = fields.Monetary('Salario mensual')
    base_decimo = fields.Monetary('Devengado del periodo (base del décimo)',
                                  help='Suma de lo devengado en los 4 meses de la partida. Se puede corregir a mano.')
    salario = fields.Monetary('Salario / décimo', compute='_compute_salario', store=True, readonly=False)
    otros_ingresos = fields.Monetary('Otros ingresos', help='Horas extras, bonos, comisiones: pagan seguro social, '
                                                           'educativo e ISR como el salario.')
    # Lo escribe la planilla al enlazar los bonos (no se recalcula solo: una planilla cancelada no cambia).
    comision_meta = fields.Monetary('Bono por meta', readonly=True,
                                    help='El bono por meta de ventas del mes anterior (Nómina › Bono por meta): '
                                         'paga seguro social, educativo e ISR como el salario.')
    devengado = fields.Monetary(compute='_compute_importes', store=True)
    css_trabajador = fields.Monetary('Seguro social', compute='_compute_importes', store=True)
    se_trabajador = fields.Monetary('Seguro educativo', compute='_compute_importes', store=True)
    isr = fields.Monetary('ISR', compute='_compute_importes', store=True)
    otros_descuentos = fields.Monetary(
        'Otros descuentos', help='Descuentos escritos a mano (hay que configurar su cuenta). Los adelantos y préstamos '
                                 'registrados en Nómina › Adelantos y préstamos se descuentan solos.')
    reembolsos = fields.Monetary(compute='_compute_importes', store=True)
    neto = fields.Monetary('Neto a pagar', compute='_compute_importes', store=True)
    css_patronal = fields.Monetary('Seguro social (patrono)', compute='_compute_importes', store=True)
    se_patronal = fields.Monetary('Seguro educativo (patrono)', compute='_compute_importes', store=True)
    riesgo_profesional = fields.Monetary('Riesgo profesional (patrono)', compute='_compute_importes', store=True)
    costo_patronal = fields.Monetary('Aportes del patrono', compute='_compute_importes', store=True)
    reembolso_ids = fields.One2many('dcasa.nomina.reembolso', 'linea_id', readonly=True)
    prestamo_descuento_ids = fields.One2many('dcasa.nomina.prestamo.descuento', 'linea_id', 'Cuotas de adelantos',
                                             readonly=True)
    prestamos = fields.Monetary('Adelantos y préstamos', compute='_compute_importes', store=True,
                                help='La cuota de los adelantos y préstamos que se descuenta en esta planilla.')
    comprobante_enviado_el = fields.Datetime('Comprobante enviado el', readonly=True, copy=False)
    comprobante_enviado_a = fields.Char('Comprobante enviado a', readonly=True, copy=False)
    bono_ids = fields.One2many('dcasa.nomina.meta.bono', 'linea_id', 'Bonos por meta', readonly=True)
    payment_id = fields.Many2one('account.payment', 'Pago', readonly=True, copy=False)
    notas = fields.Char()

    _uno_por_planilla = models.Constraint('UNIQUE(planilla_id, empleado_id)',
                                          'Cada colaborador aparece una sola vez por planilla.')

    def _socio(self):
        """El contacto del colaborador (a quien se le debe el sueldo); si no tiene, se le crea."""
        self.ensure_one()
        empleado = self.empleado_id.sudo()
        if not empleado.work_contact_id:
            empleado.work_contact_id = self.env['res.partner'].sudo().create({
                'name': empleado.name, 'company_id': False})
        return empleado.work_contact_id

    @api.depends('dias_pagados', 'dias_periodo', 'salario_mensual', 'base_decimo', 'planilla_id.tipo')
    def _compute_salario(self):
        for linea in self:
            if linea.planilla_id.tipo == 'decimo':
                linea.salario = calculo.decimo(linea.base_decimo)
            else:
                linea.salario = calculo.salario_del_periodo(linea.salario_mensual, linea.dias_pagados,
                                                            linea.dias_periodo)

    @api.depends('salario', 'otros_ingresos', 'otros_descuentos', 'reembolso_ids.monto', 'comision_meta',
                 'prestamo_descuento_ids.monto',
                 'planilla_id.parametros_id', 'planilla_id.tipo', 'dias_pagados', 'dias_periodo',
                 'empleado_id.dcasa_deduccion_isr_anual')
    def _compute_importes(self):
        for linea in self:
            vigencia = linea.planilla_id.parametros_id
            decimo = linea.planilla_id.tipo == 'decimo'
            # El bono por meta de ventas es una comisión: suma a lo devengado y paga aportes e ISR como lo extra.
            bono = 0.0 if decimo else linea.comision_meta
            extras = calculo.r2(linea.otros_ingresos + bono)
            devengado = calculo.r2(linea.salario + (0.0 if decimo else extras))
            reembolsos = calculo.r2(sum(linea.reembolso_ids.mapped('monto')))
            tasas = {
                'css_t': vigencia.css_trabajador_decimo if decimo else vigencia.css_trabajador,
                'se_t': vigencia.se_trabajador_decimo if decimo else vigencia.se_trabajador,
                'css_p': vigencia.css_patronal_decimo if decimo else vigencia.css_patronal,
                'se_p': vigencia.se_patronal_decimo if decimo else vigencia.se_patronal,
                'rp': vigencia.riesgo_profesional_decimo if decimo else vigencia.riesgo_profesional,
            }
            linea.devengado = devengado
            linea.css_trabajador = calculo.porcentaje(devengado, tasas['css_t'])
            linea.se_trabajador = calculo.porcentaje(devengado, tasas['se_t'])
            linea.css_patronal = calculo.porcentaje(devengado, tasas['css_p'])
            linea.se_patronal = calculo.porcentaje(devengado, tasas['se_p'])
            linea.riesgo_profesional = calculo.porcentaje(devengado, tasas['rp'])
            linea.costo_patronal = calculo.r2(linea.css_patronal + linea.se_patronal + linea.riesgo_profesional)
            if decimo or not vigencia or not linea.dias_periodo:
                linea.isr = 0.0  # el décimo tercer mes no retiene ISR (REQUIERE CONTADOR: confirmarlo)
            else:
                fraccion = linea.dias_pagados / linea.dias_periodo
                completa = linea.salario / fraccion if fraccion else 0.0
                linea.isr = calculo.isr_del_periodo(
                    completa, fraccion, extras, vigencia._tramos(),
                    (vigencia.css_trabajador + vigencia.se_trabajador) if vigencia.isr_descuenta_css_se else 0.0,
                    linea.empleado_id.sudo().dcasa_deduccion_isr_anual)
            linea.reembolsos = reembolsos
            linea.prestamos = calculo.r2(sum(linea.prestamo_descuento_ids.mapped('monto')))
            linea.neto = calculo.r2(devengado - linea.css_trabajador - linea.se_trabajador - linea.isr
                                    - linea.otros_descuentos - linea.prestamos + reembolsos)

    def _liberar_reembolsos(self):
        self.reembolso_ids.sudo().write({'estado': 'aprobado', 'linea_id': False})

    def _liberar_bonos(self):
        """Los bonos por meta de estas líneas vuelven a quedar por pagar (la línea sale o la planilla se cancela)."""
        self.bono_ids.sudo().write({'linea_id': False})

    @api.constrains('otros_ingresos', 'otros_descuentos', 'dias_pagados')
    def _check_valores(self):
        for linea in self:
            if linea.otros_ingresos < 0 or linea.otros_descuentos < 0 or linea.dias_pagados < 0:
                raise ValidationError(self.env._('Los ingresos, descuentos y días no pueden ser negativos.'))

    def write(self, vals):
        if not self.env.su and any(ln.estado not in ESTADOS_EDITABLES for ln in self):
            if set(vals) - {'notas'}:
                raise UserError(self.env._('La planilla ya está confirmada: la línea no cambia.'))
        if 'payment_id' in vals and not self.env.su:
            raise AccessError(self.env._('El pago solo se anota con el botón «Pagar».'))
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        planillas = self.env['dcasa.nomina.planilla'].browse([v['planilla_id'] for v in vals_list])
        if not self.env.su and planillas.filtered(lambda p: p.estado not in ESTADOS_EDITABLES):
            raise UserError(self.env._('La planilla ya está confirmada: no se agregan colaboradores.'))
        return super().create(vals_list)

    @api.ondelete(at_uninstall=False)
    def _no_borrar_confirmadas(self):
        if not self.env.su and any(ln.estado not in ESTADOS_EDITABLES for ln in self):
            raise UserError(self.env._('La planilla ya está confirmada: no se quitan colaboradores.'))
