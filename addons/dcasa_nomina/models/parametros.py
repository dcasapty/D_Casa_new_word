"""Tasas y reglas de la planilla, con fecha de vigencia y validación del contador.

La ley cambia (la cuota patronal del seguro social sube por pasos hasta 2029) y D'CASA no es quien la
interpreta: por eso NINGUNA tasa vive en el código. Cada juego de parámetros (*vigencia*) lo carga la
gerencia y lo **valida el contador**; mientras no esté validado la planilla puede calcularse como borrador
para ver cómo queda, pero **no se puede confirmar** (no genera asiento contable).

Una vigencia validada que ya usó una planilla confirmada no se cambia: se crea otra con la fecha nueva.
"""
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

GRUPO = 'dcasa_nomina.group_nomina'
# Todo lo que cambia el resultado de una planilla: se congela al validar.
CAMPOS_CONGELADOS = frozenset({
    'fecha_desde', 'css_trabajador', 'css_patronal', 'se_trabajador', 'se_patronal', 'riesgo_profesional',
    'css_trabajador_decimo', 'css_patronal_decimo', 'se_trabajador_decimo', 'se_patronal_decimo',
    'riesgo_profesional_decimo', 'isr_descuenta_css_se', 'vacaciones_dias_de_trabajo_por_dia_de_descanso',
    'prima_semanas_por_anio', 'semanas_por_mes', 'tramo_ids', 'company_id',
})
# Tasas que todo patrono tiene y que tienen que ser mayores que cero para poder validar.
TASAS_OBLIGATORIAS = (
    ('css_trabajador', 'Seguro social del trabajador'),
    ('css_patronal', 'Seguro social del patrono'),
    ('se_trabajador', 'Seguro educativo del trabajador'),
    ('se_patronal', 'Seguro educativo del patrono'),
    ('riesgo_profesional', 'Riesgo profesional'),
)


class DcasaNominaParametros(models.Model):
    _name = 'dcasa.nomina.parametros'
    _description = 'Tasas y reglas de la planilla (con vigencia)'
    _inherit = ['mail.thread']
    _order = 'fecha_desde desc, id desc'

    name = fields.Char('Vigencia', compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, tracking=True)
    fecha_desde = fields.Date('Rige desde', required=True, tracking=True,
                              help='Primer día en que aplican estas tasas. La planilla usa la vigencia más '
                                   'reciente cuya fecha sea anterior al último día del periodo que se paga.')
    estado = fields.Selection([('borrador', 'Por validar'), ('validado', 'Validado por el contador')],
                              default='borrador', required=True, readonly=True, tracking=True)
    validado_por = fields.Many2one('res.users', readonly=True, tracking=True)
    validado_el = fields.Datetime(readonly=True)
    notas_contador = fields.Text('Notas del contador', help='Qué revisó el contador y contra qué documento.')
    fuente = fields.Text('De dónde salieron las cifras', help='Ley, decreto o documento de donde se tomó cada tasa.')

    # --- planilla quincenal -------------------------------------------------------------------------
    css_trabajador = fields.Float('Seguro social: trabajador (%)', digits=(6, 4), tracking=True)
    css_patronal = fields.Float('Seguro social: patrono (%)', digits=(6, 4), tracking=True)
    se_trabajador = fields.Float('Seguro educativo: trabajador (%)', digits=(6, 4), tracking=True)
    se_patronal = fields.Float('Seguro educativo: patrono (%)', digits=(6, 4), tracking=True)
    riesgo_profesional = fields.Float(
        'Riesgo profesional: patrono (%)', digits=(6, 4), tracking=True,
        help='Depende de la actividad de la empresa (clase de riesgo que le asigna la CSS). Lo pone el contador.')
    isr_descuenta_css_se = fields.Boolean(
        'El ISR se calcula después de restar el seguro social y el educativo', tracking=True,
        help='Si está marcado, la renta sobre la que se aplica el ISR es el salario menos los aportes del '
             'trabajador. Lo decide el contador.')

    # --- décimo tercer mes (sus aportes pueden ser distintos a los de la quincena) ---------------------------
    css_trabajador_decimo = fields.Float('Décimo, seguro social: trabajador (%)', digits=(6, 4), tracking=True)
    css_patronal_decimo = fields.Float('Décimo, seguro social: patrono (%)', digits=(6, 4), tracking=True)
    se_trabajador_decimo = fields.Float('Décimo, seguro educativo: trabajador (%)', digits=(6, 4), tracking=True)
    se_patronal_decimo = fields.Float('Décimo, seguro educativo: patrono (%)', digits=(6, 4), tracking=True)
    riesgo_profesional_decimo = fields.Float('Décimo, riesgo profesional: patrono (%)', digits=(6, 4), tracking=True)
    decimo_listo = fields.Boolean(
        'Las tasas del décimo están confirmadas', tracking=True,
        help='Sin esta marca no se puede calcular el décimo tercer mes: obliga al contador a mirar esas cifras '
             '(también cuando alguna es cero a propósito).')

    # --- vacaciones y prima ---------------------------------------------------------------------------
    vacaciones_dias_de_trabajo_por_dia_de_descanso = fields.Float(
        'Vacaciones: días de trabajo por cada día de descanso', default=11.0, tracking=True,
        help='Código de Trabajo: 30 días de vacaciones por cada 11 meses de trabajo = un día de descanso por '
             'cada 11 días trabajados.')
    prima_semanas_por_anio = fields.Float('Prima de antigüedad: semanas de salario por año', default=1.0,
                                          tracking=True)
    semanas_por_mes = fields.Float('Semanas por mes', default=4.3333, digits=(6, 4), tracking=True,
                                   help='Para convertir el salario mensual en salario semanal.')

    tramo_ids = fields.One2many('dcasa.nomina.isr.tramo', 'parametros_id', string='Tramos del ISR', copy=True)
    pendientes = fields.Text('Falta para poder validar', compute='_compute_pendientes')
    planillas_usadas = fields.Integer(compute='_compute_planillas_usadas')

    @api.depends('fecha_desde')
    def _compute_name(self):
        for vigencia in self:
            vigencia.name = (self.env._('Tasas desde %s', fields.Date.to_string(vigencia.fecha_desde))
                             if vigencia.fecha_desde else self.env._('Tasas nuevas'))

    def _compute_planillas_usadas(self):
        Planilla = self.env['dcasa.nomina.planilla']
        for vigencia in self:
            vigencia.planillas_usadas = Planilla.sudo().search_count([('parametros_id', '=', vigencia.id),
                                                                      ('estado', 'in', ('confirmada', 'pagada'))])

    # ------------------------------------------------------------------
    # Qué falta
    # ------------------------------------------------------------------

    def _problemas(self):
        """Lista de textos con lo que impide validar (vacía = se puede validar)."""
        self.ensure_one()
        faltan = []
        for campo, nombre in TASAS_OBLIGATORIAS:
            if not self[campo] or self[campo] <= 0:
                faltan.append(self.env._('%s: falta la tasa', nombre))
        tramos = self.tramo_ids.sorted('desde')
        if not tramos:
            faltan.append(self.env._('ISR: faltan los tramos'))
        else:
            if tramos[0].desde != 0:
                faltan.append(self.env._('ISR: el primer tramo tiene que empezar en 0'))
            for anterior, siguiente in zip(tramos, tramos[1:], strict=False):
                if not anterior.hasta or anterior.hasta != siguiente.desde:
                    faltan.append(self.env._('ISR: los tramos tienen que ser seguidos, sin huecos ni cruces'))
                    break
            if tramos[-1].hasta:
                faltan.append(self.env._('ISR: el último tramo no puede tener tope (déjalo vacío)'))
        return faltan

    @api.depends('css_trabajador', 'css_patronal', 'se_trabajador', 'se_patronal', 'riesgo_profesional',
                 'tramo_ids.desde', 'tramo_ids.hasta', 'tramo_ids.tasa')
    def _compute_pendientes(self):
        for vigencia in self:
            vigencia.pendientes = '\n'.join(vigencia._problemas())

    def _tramos(self):
        self.ensure_one()
        return [(t.desde, t.hasta or None, t.tasa) for t in self.tramo_ids.sorted('desde')]

    @api.model
    def _vigente(self, fecha, company=None):
        """La vigencia que rige en ``fecha``: la de fecha más reciente que no pase de ella, esté validada o no.

        Si la que rige todavía no la valida el contador, la planilla se calcula como borrador y no se puede
        confirmar: nunca se aplican por omisión las tasas validadas de una ley anterior."""
        company = company or self.env.company
        return self.search([('company_id', '=', company.id), ('fecha_desde', '<=', fecha)], limit=1)

    # ------------------------------------------------------------------
    # Validación del contador
    # ------------------------------------------------------------------

    def action_validar(self):
        for vigencia in self:
            problemas = vigencia._problemas()
            if problemas:
                raise UserError(self.env._('Todavía no se puede validar:\n- %s', '\n- '.join(problemas)))
        self.check_access('write')
        self.sudo().write({  # con sudo: «estado» solo cambia por este botón (write() lo exige)
            'estado': 'validado', 'validado_por': self.env.user.id, 'validado_el': fields.Datetime.now()})
        for vigencia in self:
            vigencia.message_post(body=self.env._('Validado por %s.', self.env.user.name))
        return True

    def action_reabrir(self):
        for vigencia in self:
            if vigencia.planillas_usadas:
                raise UserError(self.env._(
                    'Estas tasas ya se usaron en una planilla confirmada: no se reabren. Crea una vigencia nueva '
                    'con la fecha desde la que cambian (botón Duplicar).'))
        self.check_access('write')
        self.sudo().write({'estado': 'borrador', 'validado_por': False, 'validado_el': False})
        for vigencia in self:
            vigencia.message_post(body=self.env._('Reabierto por %s: vuelve a estar por validar.',
                                                  self.env.user.name))
        return True

    # ------------------------------------------------------------------
    # Integridad
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Una copia no nace validada.
            for campo in ('estado', 'validado_por', 'validado_el'):
                vals.pop(campo, None)
        return super().create(vals_list)

    def write(self, vals):
        if 'estado' in vals and not self.env.su:
            raise UserError(self.env._('El estado solo cambia con los botones «Validar» y «Reabrir».'))
        if CAMPOS_CONGELADOS.intersection(vals) and not self.env.su:
            if self.filtered(lambda v: v.estado == 'validado'):
                raise UserError(self.env._('Estas tasas están validadas: reábrelas para cambiarlas.'))
            if any(v.planillas_usadas for v in self):
                raise UserError(self.env._('Estas tasas ya se usaron en una planilla confirmada: crea una '
                                           'vigencia nueva en vez de cambiarlas.'))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _no_borrar_usadas(self):
        for vigencia in self:
            if vigencia.estado == 'validado' or vigencia.planillas_usadas:
                raise UserError(self.env._('Una vigencia validada o ya usada no se borra: reábrela si hace falta.'))

    _unica_por_fecha = models.Constraint(
        'UNIQUE(company_id, fecha_desde)', 'Ya hay unas tasas que rigen desde esa fecha.')


class DcasaNominaIsrTramo(models.Model):
    _name = 'dcasa.nomina.isr.tramo'
    _description = 'Tramo del impuesto sobre la renta'
    _order = 'parametros_id, desde'

    parametros_id = fields.Many2one('dcasa.nomina.parametros', required=True, ondelete='cascade')
    desde = fields.Float('Renta anual desde ($)', required=True)
    hasta = fields.Float('Hasta ($)', help='Vacío = sin tope (último tramo).')
    tasa = fields.Float('Tasa (%)', digits=(6, 4), required=True)

    @api.constrains('desde', 'hasta', 'tasa')
    def _check_tramo(self):
        for tramo in self:
            if tramo.desde < 0 or tramo.tasa < 0 or tramo.tasa > 100:
                raise ValidationError(self.env._('El tramo tiene un valor imposible (negativo o más de 100 %).'))
            if tramo.hasta and tramo.hasta <= tramo.desde:
                raise ValidationError(self.env._('El «hasta» de un tramo tiene que ser mayor que su «desde».'))

    def _bloqueado(self):
        return self.parametros_id.filtered(lambda v: v.estado == 'validado' or v.planillas_usadas)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            padres = self.env['dcasa.nomina.parametros'].browse(
                [v['parametros_id'] for v in vals_list if v.get('parametros_id')])
            if padres.filtered(lambda v: v.estado == 'validado' or v.planillas_usadas):
                raise UserError(self.env._('Esas tasas están validadas o ya se usaron: no se agregan tramos.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and self._bloqueado():
            raise UserError(self.env._('Esas tasas están validadas o ya se usaron: no se cambian los tramos.'))
        return super().write(vals)

    def unlink(self):
        if not self.env.su and self._bloqueado():
            raise UserError(self.env._('Esas tasas están validadas o ya se usaron: no se quitan tramos.'))
        return super().unlink()
