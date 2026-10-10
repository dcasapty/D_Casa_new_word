"""Vacaciones tomadas. Lo que se «gana» sale solo de la fecha de ingreso (ver hr_employee.py); aquí se anotan
los días que la persona se tomó. Mientras descansa, la planilla sigue pagándole su salario normal; el saldo
que queda sin tomar se paga en la liquidación."""
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class DcasaNominaVacacion(models.Model):
    _name = 'dcasa.nomina.vacacion'
    _description = 'Vacaciones tomadas'
    _inherit = ['mail.thread']
    _order = 'desde desc'

    empleado_id = fields.Many2one('hr.employee', 'Colaborador', required=True, tracking=True, index=True)
    company_id = fields.Many2one(related='empleado_id.company_id', store=True)
    desde = fields.Date(required=True, tracking=True)
    hasta = fields.Date(required=True, tracking=True)
    dias = fields.Float('Días', compute='_compute_dias', store=True, readonly=False, tracking=True,
                        help='Días de calendario del descanso; se pueden ajustar a mano (p. ej. si cae un feriado).')
    estado = fields.Selection([('borrador', 'Borrador'), ('confirmada', 'Confirmada'), ('cancelada', 'Cancelada')],
                              default='borrador', required=True, tracking=True, readonly=True)
    notas = fields.Text()

    @api.depends('desde', 'hasta')
    def _compute_dias(self):
        for vacacion in self:
            vacacion.dias = ((vacacion.hasta - vacacion.desde).days + 1
                             if vacacion.desde and vacacion.hasta and vacacion.hasta >= vacacion.desde else 0.0)

    @api.constrains('desde', 'hasta', 'dias')
    def _check_fechas(self):
        for vacacion in self:
            if vacacion.hasta < vacacion.desde:
                raise ValidationError(self.env._('El último día del descanso no puede ser anterior al primero.'))
            if vacacion.dias <= 0:
                raise ValidationError(self.env._('Los días de vacaciones tienen que ser más que cero.'))

    def action_confirmar(self):
        for vacacion in self:
            if vacacion.estado != 'borrador':
                continue
            otra = self.search_count([
                ('empleado_id', '=', vacacion.empleado_id.id), ('estado', '=', 'confirmada'),
                ('desde', '<=', vacacion.hasta), ('hasta', '>=', vacacion.desde), ('id', '!=', vacacion.id)])
            if otra:
                raise UserError(self.env._(
                    'Esa persona ya tiene vacaciones confirmadas que se cruzan con estas fechas.'))
            _ganadas, _tomadas, saldo = vacacion.empleado_id._dcasa_vacaciones(vacacion.hasta)
            if vacacion.dias > saldo + 0.005:
                raise UserError(self.env._(
                    'Solo tiene %(saldo).2f días de vacaciones ganados a esa fecha y pides %(dias).2f.',
                    saldo=saldo, dias=vacacion.dias))
            vacacion.estado = 'confirmada'
        return True

    def action_cancelar(self):
        self.filtered(lambda v: v.estado != 'cancelada').write({'estado': 'cancelada'})
        return True

    def action_borrador(self):
        self.filtered(lambda v: v.estado == 'cancelada').write({'estado': 'borrador'})
        return True
