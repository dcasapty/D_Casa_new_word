"""Reembolsos en nómina: gastos que paga un colaborador de su bolsillo y se le devuelven en la planilla.

Flujo: el colaborador lo registra con la foto del recibo (Borrador) → lo envía → la administración lo aprueba
o lo rechaza con un motivo → la siguiente planilla quincenal lo suma al neto de esa persona (En planilla) →
al confirmar la planilla queda contabilizado (gasto contra sueldos por pagar). Un reembolso no paga
seguro social, educativo ni ISR.
"""
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

GRUPO = 'dcasa_nomina.group_nomina'
# Lo único que una persona sin el grupo Nómina puede cambiar, y solo en borrador.
CAMPOS_DEL_COLABORADOR = frozenset({'concepto', 'fecha', 'monto', 'cuenta_gasto_id', 'recibo_ids', 'empleado_id',
                                    'notas', 'company_id'})


class DcasaNominaReembolso(models.Model):
    _name = 'dcasa.nomina.reembolso'
    _description = 'Reembolso en nómina'
    _inherit = ['mail.thread']
    _order = 'fecha desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    empleado_id = fields.Many2one('hr.employee', 'Colaborador', required=True, tracking=True, index=True,
                                  default=lambda self: self.env['hr.employee'].search(
                                      [('user_id', '=', self.env.uid), ('company_id', '=', self.env.company.id)],
                                      limit=1))
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    fecha = fields.Date('Fecha del gasto', required=True, default=fields.Date.context_today)
    concepto = fields.Char('¿En qué se gastó?', required=True, tracking=True)
    monto = fields.Monetary('Monto', required=True, tracking=True)
    cuenta_gasto_id = fields.Many2one(
        'account.account', 'Cuenta de gasto', check_company=True,
        domain="[('account_type', 'in', ('expense', 'expense_direct_cost', 'expense_other'))]",
        help='La elige la administración al aprobar si el colaborador no sabe cuál es.')
    recibo_ids = fields.Many2many('ir.attachment', 'dcasa_nomina_reembolso_recibo_rel', 'reembolso_id', 'recibo_id',
                                  string='Foto del recibo')
    notas = fields.Text()
    estado = fields.Selection(
        [('borrador', 'Borrador'), ('enviado', 'Enviado'), ('aprobado', 'Aprobado'), ('rechazado', 'Rechazado'),
         ('en_planilla', 'En planilla'), ('contabilizado', 'Pagado en planilla')],
        default='borrador', required=True, readonly=True, tracking=True, copy=False)
    aprobado_por = fields.Many2one('res.users', readonly=True, copy=False)
    aprobado_el = fields.Datetime(readonly=True, copy=False)
    motivo_rechazo = fields.Text('Motivo del rechazo')
    linea_id = fields.Many2one('dcasa.nomina.linea', 'Línea de planilla', readonly=True, copy=False,
                               ondelete='set null')
    planilla_id = fields.Many2one(related='linea_id.planilla_id', string='Planilla', store=True)

    @api.depends('empleado_id', 'concepto')
    def _compute_name(self):
        for reembolso in self:
            reembolso.name = ' · '.join(filter(None, (reembolso.empleado_id.name, reembolso.concepto)))

    @api.constrains('monto')
    def _check_monto(self):
        for reembolso in self:
            if reembolso.monto <= 0:
                raise ValidationError(self.env._('El monto del reembolso tiene que ser más que cero.'))

    @api.onchange('empleado_id')
    def _onchange_empleado(self):
        if not self.cuenta_gasto_id:
            self.cuenta_gasto_id = self.env['dcasa.nomina.config']._de().cuenta_reembolsos_id

    # ------------------------------------------------------------------
    # Quién puede qué
    # ------------------------------------------------------------------

    def _es_nomina(self):
        return self.env.user.has_group(GRUPO)

    def _exigir_nomina(self):
        if not self._es_nomina():
            raise AccessError(self.env._('Solo quien administra la nómina aprueba o rechaza reembolsos.'))

    def _exigir_propio_o_nomina(self):
        if self._es_nomina():
            return
        if any(r.empleado_id.user_id != self.env.user for r in self):
            raise AccessError(self.env._('Solo puedes enviar tus propios reembolsos.'))

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and not self._es_nomina():
            propio = self.env['hr.employee'].search([('user_id', '=', self.env.uid)]).ids
            for vals in vals_list:
                if vals.get('empleado_id') not in propio:
                    raise AccessError(self.env._('Solo puedes registrar reembolsos a tu nombre.'))
                if set(vals) - CAMPOS_DEL_COLABORADOR:
                    raise AccessError(self.env._('Ese dato lo pone la administración.'))
        for vals in vals_list:
            if not vals.get('cuenta_gasto_id'):
                vals['cuenta_gasto_id'] = self.env['dcasa.nomina.config']._de().cuenta_reembolsos_id.id or False
        reembolsos = super().create(vals_list)
        reembolsos._adoptar_recibos()
        return reembolsos

    def write(self, vals):
        if not self.env.su:
            protegidos = set(vals) - CAMPOS_DEL_COLABORADOR - {'motivo_rechazo'}
            if protegidos:
                raise AccessError(self.env._('Ese dato solo cambia con los botones del reembolso.'))
            if not self._es_nomina():
                if any(r.estado != 'borrador' for r in self):
                    raise UserError(self.env._(
                        'Un reembolso enviado ya no se edita: pide que lo devuelvan a borrador.'))
                if 'motivo_rechazo' in vals:
                    raise AccessError(self.env._('Ese dato lo pone la administración.'))
                if any(r.empleado_id.user_id != self.env.user for r in self):
                    raise AccessError(self.env._('Solo puedes cambiar tus propios reembolsos.'))
            elif any(r.estado in ('en_planilla', 'contabilizado') for r in self):
                raise UserError(self.env._(
                    'Un reembolso que ya está en una planilla no se edita: cancela la planilla.'))
        resultado = super().write(vals)
        if 'recibo_ids' in vals:
            self._adoptar_recibos()
        return resultado

    def _adoptar_recibos(self):
        """La foto que sube el colaborador nace sin dueño (solo la ve quien la subió): se le asigna este reembolso
        para que la administración también la vea. Solo las que subió la propia persona y aún no tienen dueño."""
        for reembolso in self:
            suyos = reembolso.recibo_ids.sudo().filtered(
                lambda a: not a.res_id and not a.res_model and a.create_uid == self.env.user)
            suyos.write({'res_model': self._name, 'res_id': reembolso.id})

    @api.ondelete(at_uninstall=False)
    def _solo_borradores(self):
        if any(r.estado not in ('borrador', 'rechazado') for r in self):
            raise UserError(self.env._('Solo se borra un reembolso en borrador o rechazado.'))

    # ------------------------------------------------------------------
    # Flujo
    # ------------------------------------------------------------------

    def action_enviar(self):
        self.check_access('write')
        self._exigir_propio_o_nomina()
        for reembolso in self:
            if reembolso.estado not in ('borrador', 'rechazado'):
                raise UserError(self.env._('Ese reembolso ya se envió.'))
            if not reembolso.recibo_ids:
                raise UserError(self.env._('Adjunta la foto del recibo antes de enviarlo.'))
        self.sudo().write({'estado': 'enviado', 'motivo_rechazo': False})
        for reembolso in self:
            reembolso.message_post(body=self.env._('%s envió el reembolso.', self.env.user.name))
        return True

    def action_aprobar(self):
        self._exigir_nomina()
        for reembolso in self:
            if reembolso.estado != 'enviado':
                raise UserError(self.env._('Solo se aprueba un reembolso enviado.'))
            if not reembolso.cuenta_gasto_id:
                raise UserError(self.env._('Elige la cuenta de gasto de «%s» antes de aprobarlo.', reembolso.name))
        self.sudo().write({'estado': 'aprobado', 'aprobado_por': self.env.user.id,
                           'aprobado_el': fields.Datetime.now()})
        for reembolso in self:
            reembolso.message_post(body=self.env._('Aprobado por %s: entra en la siguiente planilla.',
                                                   self.env.user.name))
        return True

    def action_rechazar(self):
        self._exigir_nomina()
        for reembolso in self:
            if reembolso.estado != 'enviado':
                raise UserError(self.env._('Solo se rechaza un reembolso enviado.'))
            if not (reembolso.motivo_rechazo or '').strip():
                raise UserError(self.env._('Escribe el motivo del rechazo para que el colaborador lo vea.'))
        self.sudo().write({'estado': 'rechazado'})
        for reembolso in self:
            reembolso.message_post(body=self.env._('Rechazado por %(quien)s: %(motivo)s', quien=self.env.user.name,
                                                   motivo=reembolso.motivo_rechazo))
        return True

    def action_borrador(self):
        self._exigir_propio_o_nomina()
        for reembolso in self:
            if reembolso.estado not in ('enviado', 'aprobado', 'rechazado'):
                raise UserError(self.env._('Solo vuelve a borrador un reembolso enviado, aprobado o rechazado.'))
            if reembolso.estado == 'aprobado' and not self._es_nomina():
                raise AccessError(self.env._('Un reembolso aprobado solo lo devuelve la administración.'))
        self.sudo().write({'estado': 'borrador', 'aprobado_por': False, 'aprobado_el': False})
        return True
