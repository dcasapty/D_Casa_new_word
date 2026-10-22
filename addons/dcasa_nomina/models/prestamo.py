"""Adelantos y préstamos a colaboradores (decisión G7 de la gerencia: «el sistema debe controlarlos»).

Flujo (imita a los reembolsos, G8): quien administra la nómina lo registra (monto, fecha y en cuántas quincenas se
descuenta) → **Gerencia lo autoriza** → se entrega el dinero desde un banco o la caja (queda el pago contra la cuenta
de adelantos al personal) → cada planilla quincenal descuenta sola la cuota que toca → al confirmar la planilla queda
contabilizado (la cuota sale de lo que se le paga y baja lo que el colaborador le debe a la empresa) → con el saldo en
cero queda «Pagado».

Reglas que no se rompen:

* **Nunca se descuenta más de lo que debe**: la cuota de cada quincena es la menor entre la cuota pactada y lo que le
  queda por descontar (contando lo ya reservado en otras planillas sin confirmar), y una restricción lo vigila también
  si alguien escribe a mano.
* **No hay columna de saldo editable**: el saldo es el monto menos los descuentos de planillas confirmadas o pagadas.
* Una planilla cancelada no cuenta (su asiento se reversa): lo que reservaba vuelve a quedar por descontar.
* Las cifras (monto, cuotas) las escribe la persona: el sistema no propone montos ni tasas.
"""
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from . import calculo

GRUPO = 'dcasa_nomina.group_nomina'
GRUPOS_AUTORIZAN = ('dcasa_base.group_gerencia', 'base.group_system')
ESTADOS_CONTABILIZADOS = ('confirmada', 'pagada')
ESTADOS_RESERVAN = ('borrador', 'calculada')
# Lo que se escribe mientras está en borrador (el resto cambia solo con los botones).
CAMPOS_EDITABLES = frozenset({'empleado_id', 'tipo', 'fecha', 'monto', 'cuotas', 'primera_quincena', 'motivo',
                              'diario_id', 'notas', 'company_id'})


class DcasaNominaPrestamo(models.Model):
    _name = 'dcasa.nomina.prestamo'
    _description = 'Adelanto o préstamo a un colaborador'
    _inherit = ['mail.thread']
    _order = 'fecha desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    empleado_id = fields.Many2one('hr.employee', 'Colaborador', required=True, tracking=True, index=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    tipo = fields.Selection([('adelanto', 'Adelanto de sueldo'), ('prestamo', 'Préstamo')], required=True,
                            default='adelanto', tracking=True)
    fecha = fields.Date('Fecha de entrega', required=True, default=fields.Date.context_today, tracking=True)
    monto = fields.Monetary('Monto entregado', required=True, tracking=True)
    cuotas = fields.Integer('Quincenas para descontarlo', required=True, default=1, tracking=True,
                            help='En cuántas planillas quincenales se descuenta. 1 = todo en la próxima quincena.')
    cuota = fields.Monetary('Descuento por quincena', compute='_compute_cuota', store=True,
                            help='El monto dividido entre las quincenas. La última quincena descuenta lo que quede.')
    primera_quincena = fields.Date(
        'Se empieza a descontar en la quincena del', compute='_compute_primera_quincena', store=True, readonly=False,
        required=True, precompute=True,
        help='La primera planilla quincenal que termina en esta fecha o después lo descuenta.')
    motivo = fields.Char('Motivo', help='Para qué se lo dieron (lo ve Gerencia al autorizar).')
    notas = fields.Text()
    estado = fields.Selection(
        [('borrador', 'Por autorizar'), ('aprobado', 'Autorizado, por entregar'),
         ('entregado', 'Descontándose'), ('pagado', 'Pagado'), ('cancelado', 'Cancelado')],
        default='borrador', required=True, readonly=True, tracking=True, copy=False)
    aprobado_por = fields.Many2one('res.users', 'Autorizado por', readonly=True, copy=False)
    aprobado_el = fields.Datetime('Autorizado el', readonly=True, copy=False)
    diario_id = fields.Many2one('account.journal', 'Se entrega desde', domain="[('type', 'in', ('bank', 'cash'))]",
                                check_company=True, help='El banco o la caja de donde sale el dinero.')
    payment_id = fields.Many2one('account.payment', 'Pago de la entrega', readonly=True, copy=False)
    descuento_ids = fields.One2many('dcasa.nomina.prestamo.descuento', 'prestamo_id', 'Descuentos en planilla',
                                    readonly=True)
    descontado = fields.Monetary('Ya descontado', compute='_compute_saldos', store=True,
                                 help='Lo descontado en planillas confirmadas o pagadas.')
    en_planilla = fields.Monetary('En una planilla sin confirmar', compute='_compute_saldos', store=True)
    saldo = fields.Monetary('Saldo pendiente', compute='_compute_saldos', store=True,
                            help='Lo que el colaborador todavía le debe a la empresa por este adelanto o préstamo.')
    cuotas_descontadas = fields.Integer('Quincenas descontadas', compute='_compute_saldos', store=True)

    @api.depends('empleado_id', 'tipo', 'monto')
    def _compute_name(self):
        tipos = dict(self._fields['tipo']._description_selection(self.env))
        for prestamo in self:
            prestamo.name = ' · '.join(filter(None, (tipos.get(prestamo.tipo), prestamo.empleado_id.name)))

    @api.depends('monto', 'cuotas')
    def _compute_cuota(self):
        for prestamo in self:
            prestamo.cuota = calculo.r2(prestamo.monto / prestamo.cuotas) if prestamo.cuotas > 0 else 0.0

    @api.depends('fecha')
    def _compute_primera_quincena(self):
        for prestamo in self:
            prestamo.primera_quincena = prestamo.fecha

    @api.depends('monto', 'descuento_ids.monto', 'descuento_ids.planilla_id.estado')
    def _compute_saldos(self):
        for prestamo in self:
            hechos = prestamo.descuento_ids.filtered(lambda d: d.planilla_id.estado in ESTADOS_CONTABILIZADOS)
            reservados = prestamo.descuento_ids.filtered(lambda d: d.planilla_id.estado in ESTADOS_RESERVAN)
            prestamo.descontado = calculo.r2(sum(hechos.mapped('monto')))
            prestamo.en_planilla = calculo.r2(sum(reservados.mapped('monto')))
            prestamo.saldo = calculo.r2(prestamo.monto - prestamo.descontado)
            prestamo.cuotas_descontadas = len(hechos)

    @api.constrains('monto', 'cuotas')
    def _check_monto(self):
        for prestamo in self:
            if prestamo.monto <= 0:
                raise ValidationError(self.env._('El monto tiene que ser más que cero.'))
            if prestamo.cuotas < 1:
                raise ValidationError(self.env._('Se descuenta en una quincena o más.'))

    # ------------------------------------------------------------------
    # Quién puede qué
    # ------------------------------------------------------------------

    def _exigir_nomina(self):
        if not self.env.su and not self.env.user.has_group(GRUPO):
            raise AccessError(self.env._('Solo quien administra la nómina registra adelantos y préstamos.'))

    def _exigir_gerencia(self):
        if not self.env.su and not any(self.env.user.has_group(g) for g in GRUPOS_AUTORIZAN):
            raise AccessError(self.env._('Solo Gerencia autoriza un adelanto o un préstamo.'))

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            self._exigir_nomina()
            for vals in vals_list:
                if set(vals) - CAMPOS_EDITABLES:
                    raise AccessError(self.env._('Ese dato solo cambia con los botones del adelanto.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            self._exigir_nomina()
            if set(vals) - CAMPOS_EDITABLES:
                raise AccessError(self.env._('Ese dato solo cambia con los botones del adelanto.'))
            cambia_cifras = set(vals) - {'notas', 'motivo'}
            if cambia_cifras and any(p.estado != 'borrador' for p in self):
                raise UserError(self.env._(
                    'Un adelanto autorizado ya no cambia de monto, fecha ni cuotas. Cancélalo y registra uno nuevo '
                    '(si ya se entregó, el saldo se corrige con un descuento a mano en la planilla).'))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _solo_borradores(self):
        if any(p.estado not in ('borrador', 'cancelado') or p.payment_id or p.descuento_ids for p in self):
            raise UserError(self.env._('Solo se borra un adelanto por autorizar o cancelado (que nunca se entregó).'))

    # ------------------------------------------------------------------
    # Flujo
    # ------------------------------------------------------------------

    def action_aprobar(self):
        self._exigir_gerencia()
        for prestamo in self:
            if prestamo.estado != 'borrador':
                raise UserError(self.env._('Solo se autoriza un adelanto que está por autorizar.'))
        self.sudo().write({'estado': 'aprobado', 'aprobado_por': self.env.user.id,
                           'aprobado_el': fields.Datetime.now()})
        for prestamo in self:
            prestamo.message_post(body=self.env._('Autorizado por %s.', self.env.user.name))
        return True

    def action_entregar(self):
        """El dinero sale del banco o la caja: un pago al colaborador contra la cuenta de adelantos al personal."""
        self._exigir_nomina()
        self.check_access('write')
        for prestamo in self:
            if prestamo.estado != 'aprobado':
                raise UserError(self.env._('Primero Gerencia autoriza el adelanto; después se entrega.'))
            if not prestamo.diario_id:
                raise UserError(self.env._(
                    'Elige el banco o la caja desde donde se entrega (campo «Se entrega desde»).'))
            config = self.env['dcasa.nomina.config']._de(prestamo.company_id)
            config._exigir('cuenta_prestamos_id')
            socio = prestamo._socio()
            pago = self.env['account.payment'].create({
                'payment_type': 'outbound', 'partner_type': 'supplier', 'partner_id': socio.id,
                'amount': prestamo.monto, 'currency_id': prestamo.currency_id.id,
                'journal_id': prestamo.diario_id.id, 'date': prestamo.fecha, 'memo': prestamo.name,
                'destination_account_id': config.cuenta_prestamos_id.id, 'company_id': prestamo.company_id.id})
            pago.action_post()
            prestamo.sudo().write({'estado': 'entregado', 'payment_id': pago.id})
            prestamo.message_post(body=self.env._(
                'Entregado desde %(diario)s (%(pago)s). Se descuenta en %(cuotas)s quincena(s) desde la del %(desde)s.',
                diario=prestamo.diario_id.name, pago=pago.name, cuotas=prestamo.cuotas,
                desde=prestamo.primera_quincena.strftime('%d/%m/%Y')))
        return True

    def action_cancelar(self):
        self._exigir_nomina()
        for prestamo in self:
            if prestamo.estado not in ('borrador', 'aprobado'):
                raise UserError(self.env._(
                    'Un adelanto ya entregado no se cancela: se descuenta en la planilla (o se corrige con un '
                    'descuento a mano).'))
        self.sudo().write({'estado': 'cancelado'})
        for prestamo in self:
            prestamo.message_post(body=self.env._('Cancelado por %s.', self.env.user.name))
        return True

    def action_borrador(self):
        """Un cancelado o un autorizado sin entregar vuelve a «por autorizar» (para corregir cifras)."""
        self._exigir_nomina()
        for prestamo in self:
            if prestamo.estado not in ('aprobado', 'cancelado') or prestamo.payment_id:
                raise UserError(self.env._('Solo vuelve a «por autorizar» un adelanto que no se ha entregado.'))
        self.sudo().write({'estado': 'borrador', 'aprobado_por': False, 'aprobado_el': False})
        return True

    # ------------------------------------------------------------------
    # Lo que usa la planilla
    # ------------------------------------------------------------------

    def _socio(self):
        """El contacto del colaborador (al que se le entrega el dinero y a cuyo nombre queda la deuda)."""
        self.ensure_one()
        empleado = self.empleado_id.sudo()
        if not empleado.work_contact_id:
            empleado.work_contact_id = self.env['res.partner'].sudo().create(
                {'name': empleado.name, 'company_id': False})
        return empleado.work_contact_id

    def _por_descontar(self, sin_planilla=None):
        """Lo que todavía se puede descontar: el monto menos lo descontado y lo reservado en planillas sin confirmar
        (sin contar ``sin_planilla``, la que se está calculando)."""
        self.ensure_one()
        vivos = self.descuento_ids.filtered(
            lambda d: d.planilla_id.estado != 'cancelada' and d.planilla_id != sin_planilla)
        return calculo.r2(self.monto - sum(vivos.mapped('monto')))

    def _cuota_para(self, planilla):
        """La cuota de esta planilla: la pactada, sin pasar de lo que queda; la última quincena toma todo lo que
        queda (así los centavos del redondeo no dejan un saldo suelto)."""
        self.ensure_one()
        queda = self._por_descontar(sin_planilla=planilla)
        if queda <= 0:
            return 0.0
        usadas = len(self.descuento_ids.filtered(
            lambda d: d.planilla_id.estado != 'cancelada' and d.planilla_id != planilla))
        if self.cuotas - usadas <= 1:
            return queda
        return min(self.cuota, queda)

    def _marcar_pagados(self):
        """Con el saldo en cero, el adelanto queda «Pagado»; si una planilla se cancela, vuelve a descontarse."""
        for prestamo in self.sudo():
            if prestamo.estado == 'entregado' and prestamo.saldo <= 0:
                prestamo.estado = 'pagado'
                prestamo.message_post(body=self.env._('Saldo en cero: el adelanto quedó pagado.'))
            elif prestamo.estado == 'pagado' and prestamo.saldo > 0:
                prestamo.estado = 'entregado'


class DcasaNominaPrestamoDescuento(models.Model):
    _name = 'dcasa.nomina.prestamo.descuento'
    _description = 'Cuota de un adelanto descontada en una planilla'
    _order = 'planilla_id, id'

    prestamo_id = fields.Many2one('dcasa.nomina.prestamo', required=True, ondelete='restrict', index=True)
    linea_id = fields.Many2one('dcasa.nomina.linea', required=True, ondelete='cascade', index=True)
    planilla_id = fields.Many2one(related='linea_id.planilla_id', store=True, string='Planilla')
    empleado_id = fields.Many2one(related='prestamo_id.empleado_id', store=True, string='Colaborador')
    company_id = fields.Many2one(related='prestamo_id.company_id', store=True)
    currency_id = fields.Many2one(related='prestamo_id.currency_id')
    monto = fields.Monetary('Cuota', required=True)

    @api.constrains('monto', 'prestamo_id', 'linea_id')
    def _check_no_pasa_de_lo_que_debe(self):
        for descuento in self:
            if descuento.monto <= 0:
                raise ValidationError(self.env._('La cuota de un adelanto tiene que ser más que cero.'))
            if descuento.linea_id.empleado_id != descuento.prestamo_id.empleado_id:
                raise ValidationError(self.env._('La cuota se descuenta solo al colaborador del adelanto.'))
            prestamo = descuento.prestamo_id
            vivos = prestamo.descuento_ids.filtered(lambda d: d.planilla_id.estado != 'cancelada')
            if calculo.r2(sum(vivos.mapped('monto'))) > calculo.r2(prestamo.monto):
                raise ValidationError(self.env._(
                    'No se puede descontar más de lo que %(nombre)s debe (%(monto)s): revisa las cuotas.',
                    nombre=prestamo.empleado_id.name, monto=f'{prestamo.monto:,.2f}'))

    def _saldo_despues(self):
        """Lo que el colaborador seguirá debiendo de este adelanto después de esta planilla (para el comprobante)."""
        self.ensure_one()
        planilla = self.planilla_id
        anteriores = self.prestamo_id.descuento_ids.filtered(
            lambda d: d.planilla_id.estado != 'cancelada'
            and (d.planilla_id.fecha_hasta, d.id) <= (planilla.fecha_hasta, self.id))
        return calculo.r2(self.prestamo_id.monto - sum(anteriores.mapped('monto')))

    def _numero_de_cuota(self):
        self.ensure_one()
        planilla = self.planilla_id
        return len(self.prestamo_id.descuento_ids.filtered(
            lambda d: d.planilla_id.estado != 'cancelada'
            and (d.planilla_id.fecha_hasta, d.id) <= (planilla.fecha_hasta, self.id)))
