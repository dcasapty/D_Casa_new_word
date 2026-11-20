"""Liquidaciones de la comisión del sitio web: propuesta → aprobación → pagada. **Nada se paga solo.**

Administración elige el periodo que quiera (desde y hasta, cualquiera: semana, quincena, mes, con atajos); la
liquidación
toma **lo que todavía no se ha liquidado hasta esa fecha** (el saldo del libro de cada persona por concepto) y **nunca
paga dos veces lo mismo**: al aprobar se anota en el libro una fila negativa de «liquidación» por persona y concepto,
así
que lo mismo no puede entrar en otra liquidación, ni aunque los periodos se solapen.

* **Borrador**: se arma y se recalcula las veces que haga falta (lo que se debe puede cambiar mientras tanto).
* **Aprobada**: ya no se edita. La aprueba una persona de Gerencia o de Nómina **que no figura entre quienes cobran en
  ella**: es la única protección y es automática (una frase amable lo explica). Queda quién y cuándo.
* **Pagada**: con la fecha y la referencia del pago. El sistema no mueve dinero: se anota (o se manda a la planilla).
* **Cancelada**: una aprobada que todavía no se pagó se anula con filas contrarias y la plata vuelve al saldo.

Los dos conceptos (porcentaje de las ventas y tarifa fija) salen por separado y **ninguno es salario**: se pagan sin
descuentos de planilla (decisión de Gerencia). Conviene que la contadora deje por escrito su tratamiento.
"""
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError, UserError

from .movimiento import CANDADO_LIQUIDACIONES, CONCEPTOS

GRUPO = 'dcasa_nomina.group_nomina'
# Una llave interna para escribir en una liquidación ya aprobada (solo los botones; por RPC nunca llega).
ESCRIBIR = object()
CLAVE_ESCRIBIR = 'dcasa_comision_web_liquidacion'
ATAJOS = [
    ('este_mes', 'Este mes'), ('mes_pasado', 'El mes pasado'),
    ('quincena_1', 'Primera quincena de este mes (1 al 15)'),
    ('quincena_2_pasada', 'Segunda quincena del mes pasado (16 al fin)'),
    ('quincena_1_pasada', 'Primera quincena del mes pasado (1 al 15)'),
    ('esta_semana', 'Esta semana'), ('semana_pasada', 'La semana pasada'),
]
EDITABLES_EN_BORRADOR = frozenset({'atajo', 'fecha_desde', 'fecha_hasta', 'notas'})
EDITABLES_DEL_PAGO = frozenset({'fecha_pago', 'referencia_pago', 'motivo_cancelacion'})


def rango_del_atajo(atajo, hoy):
    """``(desde, hasta)`` de un atajo, con ``hoy`` (fecha de Panamá). Pura y sin base de datos."""
    primero = hoy.replace(day=1)
    if atajo == 'este_mes':
        return primero, primero + relativedelta(day=31)
    if atajo == 'mes_pasado':
        anterior = primero - relativedelta(months=1)
        return anterior, anterior + relativedelta(day=31)
    if atajo == 'quincena_1':
        return primero, primero.replace(day=15)
    if atajo == 'quincena_2_pasada':
        anterior = primero - relativedelta(months=1)
        return anterior.replace(day=16), anterior + relativedelta(day=31)
    if atajo == 'quincena_1_pasada':
        anterior = primero - relativedelta(months=1)
        return anterior, anterior.replace(day=15)
    lunes = hoy - timedelta(days=hoy.weekday())
    if atajo == 'esta_semana':
        return lunes, lunes + timedelta(days=6)
    if atajo == 'semana_pasada':
        return lunes - timedelta(days=7), lunes - timedelta(days=1)
    return None


class DcasaWebLiquidacion(models.Model):
    _name = 'dcasa.web.liquidacion'
    _description = 'Liquidación de la comisión del sitio web'
    _order = 'id desc'

    name = fields.Char('Número', readonly=True, copy=False, default='Nueva')
    company_id = fields.Many2one('res.company', 'Empresa', required=True, readonly=True, index=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    estado = fields.Selection([('borrador', 'Propuesta'), ('aprobada', 'Aprobada'), ('pagada', 'Pagada'),
                               ('cancelada', 'Cancelada')], required=True, readonly=True, default='borrador',
                              copy=False, index=True)
    atajo = fields.Selection(ATAJOS, 'Atajo del periodo')
    fecha_desde = fields.Date(
        'Periodo: desde', required=True, default=lambda self: self._hoy().replace(day=1),
        help='El periodo que se quiere pagar. El monto sale de TODO lo que se debe hasta la fecha «hasta» y todavía no '
             'se había liquidado: si hay algo anotado antes de este día, se avisa para que no sorprenda.')
    fecha_hasta = fields.Date('Periodo: hasta', required=True, default=lambda self: self._hoy(),
                              help='Se liquida todo lo que se anotó hasta este día y todavía no se había liquidado.')
    linea_ids = fields.One2many('dcasa.web.liquidacion.linea', 'liquidacion_id', 'Por persona y concepto',
                                readonly=True)
    total = fields.Monetary(compute='_compute_total', store=True)
    avisos = fields.Text('Avisos', readonly=True)
    notas = fields.Char('Notas')
    aprobada_por = fields.Many2one('res.users', 'Aprobada por', readonly=True, copy=False)
    aprobada_el = fields.Datetime('Aprobada el', readonly=True, copy=False)
    fecha_pago = fields.Date('Fecha del pago', copy=False)
    referencia_pago = fields.Char('Referencia del pago', copy=False,
                                  help='El número de la transferencia, del cheque o del recibo con que se pagó.')
    pagada_por = fields.Many2one('res.users', 'Marcada como pagada por', readonly=True, copy=False)
    cancelada_por = fields.Many2one('res.users', 'Cancelada por', readonly=True, copy=False)
    cancelada_el = fields.Datetime('Cancelada el', readonly=True, copy=False)
    motivo_cancelacion = fields.Char('Motivo de la cancelación', copy=False)
    quien_cobra = fields.Many2many('hr.employee', string='Quiénes cobran en ella', compute='_compute_quien_cobra')
    tu_cobras = fields.Boolean('Tú cobras en ella', compute='_compute_quien_cobra')

    @api.model
    def _hoy(self):
        return fields.Date.context_today(self.with_context(tz='America/Panama'))

    @api.depends('linea_ids.centavos')
    def _compute_total(self):
        for liquidacion in self:
            liquidacion.total = sum(liquidacion.linea_ids.mapped('centavos')) / 100.0

    @api.depends('linea_ids.empleado_id')
    @api.depends_context('uid')
    def _compute_quien_cobra(self):
        for liquidacion in self:
            liquidacion.quien_cobra = liquidacion.linea_ids.empleado_id
            liquidacion.tu_cobras = liquidacion._cobra_el_usuario(self.env.user)

    def _cobra_el_usuario(self, usuario):
        """¿Este usuario es una de las personas que cobran en esta liquidación? Se mira lo que la ficha de cada persona
        dice hoy (usuario y contacto de trabajo) y los usuarios que tenía ligados cuando se guardó la versión del
        reparto donde figura: cambiar la ficha después no deja a quien cobra aprobar lo suyo."""
        empleados = self.sudo().linea_ids.empleado_id
        return bool(empleados) and usuario.id in self.env['dcasa.web.reparto']._usuarios_de(empleados)

    @api.onchange('atajo')
    def _onchange_atajo(self):
        rango = rango_del_atajo(self.atajo, self._hoy()) if self.atajo else None
        if rango:
            self.fecha_desde, self.fecha_hasta = rango

    # ------------------------------------------------------------------
    # Quién puede qué
    # ------------------------------------------------------------------

    def _exigir_nomina(self):
        if not self.env.user.has_group(GRUPO):
            raise AccessError(self.env._('Solo Gerencia y quien administra la nómina manejan estas liquidaciones.'))

    @api.model
    def _empleados_del_usuario(self, usuario=None):
        """Las fichas de empleado de una persona (por su usuario o por su contacto de trabajo), de todas las
        empresas."""
        usuario = usuario or self.env.user
        return self.env['hr.employee'].sudo().with_context(active_test=False).search([
            '|', ('user_id', '=', usuario.id), ('work_contact_id', '=', usuario.partner_id.id)])

    # ------------------------------------------------------------------
    # Lo aprobado no se edita
    # ------------------------------------------------------------------

    def write(self, vals):
        if self.env.context.get(CLAVE_ESCRIBIR) is not ESCRIBIR:
            for liquidacion in self:
                permitidos = EDITABLES_EN_BORRADOR if liquidacion.estado == 'borrador' else (
                    EDITABLES_DEL_PAGO if liquidacion.estado == 'aprobada' else frozenset())
                if set(vals) - permitidos:
                    raise UserError(self.env._(
                        'Una liquidación aprobada no se edita: si hay un error, se cancela (antes de pagarla) y se '
                        'arma otra.'))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _solo_borradores(self):
        if any(liq.estado not in ('borrador', 'cancelada') for liq in self):
            raise UserError(self.env._('Una liquidación aprobada o pagada no se borra: se cancela.'))

    def _escribir(self, valores):
        """Único camino para cambiar el estado: lo usan los botones, después de comprobar el permiso."""
        return self.sudo().with_context(**{CLAVE_ESCRIBIR: ESCRIBIR}).write(valores)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.pop('estado', None)
            vals['name'] = self.env['ir.sequence'].next_by_code('dcasa.web.liquidacion') or 'Nueva'
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Armar la propuesta
    # ------------------------------------------------------------------

    def _pendientes(self):
        """``({(empleado_id, concepto): centavos}, avisos)`` de lo que se debe hasta la fecha del periodo. Solo lo
        positivo se paga; un saldo negativo (devoluciones que superaron lo ganado) se avisa y sigue al siguiente.

        **Nunca se paga más de lo que de verdad se debe hoy**: una devolución o un pago revertido se anota con la fecha
        de hoy, que casi siempre cae DESPUÉS del periodo que se liquida (el del mes pasado). Si solo se mirara hasta el
        fin del periodo, se pagaría una venta que ya se reversó. Por eso a cada persona se le paga lo menor entre lo
        que se debe hasta «hasta» y lo que se debe con todo lo anotado hasta hoy."""
        self.ensure_one()
        Libro = self.env['dcasa.web.movimiento'].sudo()
        empleados = Libro.search([('company_id', '=', self.company_id.id)]).empleado_id
        saldos = Libro._saldos(empleados, hasta=self.fecha_hasta, company=self.company_id)
        actuales = Libro._saldos(empleados, company=self.company_id)
        nombres = {e.id: e.name for e in empleados}
        pagar, avisos = {}, []
        for (empleado_id, concepto), centavos in sorted(saldos.items()):
            if centavos > 0:
                tope = max(actuales.get((empleado_id, concepto), 0), 0)
                if tope:
                    pagar[(empleado_id, concepto)] = min(centavos, tope)
                if tope < centavos:
                    avisos.append(self.env._(
                        'A %(persona)s se le paga %(pago)s en vez de %(monto)s por «%(concepto)s»: después del periodo '
                        'se anotó una devolución o un reverso (por ejemplo, un pago revertido) que ya lo cubre.',
                        persona=nombres.get(empleado_id, '?'), pago=f'{min(centavos, tope) / 100:,.2f}',
                        monto=f'{centavos / 100:,.2f}', concepto=dict(CONCEPTOS)[concepto]))
            elif centavos < 0:
                avisos.append(self.env._(
                    '%(persona)s tiene un saldo en contra de %(monto)s por «%(concepto)s» (devoluciones que superaron '
                    'lo ganado): hoy se le paga cero y el saldo sigue para la próxima liquidación.',
                    persona=nombres.get(empleado_id, '?'), monto=f'{-centavos / 100:,.2f}',
                    concepto=dict(CONCEPTOS)[concepto]))
        return pagar, avisos

    def _saldo_anterior_al_periodo(self):
        """Centavos por pagar que se anotaron antes de «desde» (solo lo positivo): una liquidación toma todo lo no
        liquidado hasta «hasta», así que se avisa cuando arrastra algo de antes del periodo."""
        self.ensure_one()
        Libro = self.env['dcasa.web.movimiento'].sudo()
        antes = self.fecha_desde - timedelta(days=1)
        empleados = Libro.search([('company_id', '=', self.company_id.id)]).empleado_id
        saldos = Libro._saldos(empleados, hasta=antes, company=self.company_id)
        return sum(centavos for centavos in saldos.values() if centavos > 0)

    def _armar(self):
        self.ensure_one()
        if self.estado != 'borrador':
            raise UserError(self.env._('Solo se arma una propuesta en borrador.'))
        if self.fecha_hasta < self.fecha_desde:
            raise UserError(self.env._('El periodo termina antes de empezar.'))
        self.env['dcasa.web.venta']._poner_al_dia()
        pagar, avisos = self._pendientes()
        anterior = self._saldo_anterior_al_periodo()
        if anterior:
            avisos.append(self.env._(
                'Incluye %(monto)s anotados antes del %(desde)s que todavía no se habían liquidado.',
                monto=f'{anterior / 100:,.2f}', desde=self.fecha_desde.strftime('%d/%m/%Y')))
        self.linea_ids.sudo().unlink()
        self.env['dcasa.web.liquidacion.linea'].sudo().create([
            {'liquidacion_id': self.id, 'empleado_id': empleado_id, 'concepto': concepto, 'centavos': centavos}
            for (empleado_id, concepto), centavos in sorted(pagar.items())])
        self._escribir({'avisos': '\n'.join(avisos) or False})

    def action_armar(self):
        self.check_access('write')
        self._exigir_nomina()
        for liquidacion in self:
            liquidacion._armar()
        return True

    # ------------------------------------------------------------------
    # Aprobar, pagar, cancelar
    # ------------------------------------------------------------------

    def action_aprobar(self):
        if self.env.uid == SUPERUSER_ID:
            raise UserError(self.env._('Una liquidación solo la aprueba una persona, con su propio usuario.'))
        self.check_access('write')
        self._exigir_nomina()
        for liquidacion in self:
            if liquidacion.estado != 'borrador':
                raise UserError(self.env._('Solo se aprueba una propuesta en borrador.'))
            if liquidacion._cobra_el_usuario(self.env.user):
                raise UserError(self.env._(
                    'Tú figuras entre quienes cobran en esta liquidación, así que la aprueba otra persona de '
                    'Gerencia o de Nómina. Pídele que la revise y la apruebe: así todos quedamos tranquilos.'))
            # El candado se ESCRIBE (no basta avisar): dos aprobaciones a la vez chocan y la segunda se repite con una
            # foto nueva de la base, donde ya ve lo que la primera liquidó (REPEATABLE READ).
            self.env['dcasa.web.candado']._tomar(CANDADO_LIQUIDACIONES)
            self.env['dcasa.web.venta']._poner_al_dia()
            lineas = liquidacion.sudo().linea_ids
            if not lineas:
                raise UserError(self.env._('No hay nada que liquidar en esta propuesta. Toca «Armar» para calcularla.'))
            pagar, _avisos = liquidacion._pendientes()
            armado = {(ln.empleado_id.id, ln.concepto): ln.centavos for ln in lineas}
            if pagar != armado:
                raise UserError(self.env._(
                    'Lo que se debe cambió desde que armaste esta propuesta (hubo ventas, devoluciones u otra '
                    'liquidación). Toca «Armar» otra vez y revísala antes de aprobar.'))
            Libro = self.env['dcasa.web.movimiento']
            for linea in lineas:
                Libro._asentar(linea.empleado_id, 'liquidacion', -linea.centavos, liquidacion.company_id,
                               autor=self.env.user.login, concepto=linea.concepto, liquidacion_id=liquidacion.id,
                               motivo=self.env._('Liquidación %s', liquidacion.name))
            liquidacion._escribir({'estado': 'aprobada', 'aprobada_por': self.env.user.id,
                                   'aprobada_el': fields.Datetime.now()})
        return True

    def action_pagar(self):
        self.check_access('write')
        self._exigir_nomina()
        for liquidacion in self:
            if liquidacion.estado != 'aprobada':
                raise UserError(self.env._('Solo se marca como pagada una liquidación aprobada.'))
            if not liquidacion.fecha_pago or not (liquidacion.referencia_pago or '').strip():
                raise UserError(self.env._('Escribe la fecha y la referencia del pago antes de marcarla como pagada.'))
            liquidacion._escribir({'estado': 'pagada', 'pagada_por': self.env.user.id})
        return True

    def action_cancelar(self):
        self.check_access('write')
        self._exigir_nomina()
        self.env['dcasa.web.candado']._tomar(CANDADO_LIQUIDACIONES)
        for liquidacion in self:
            if liquidacion.estado == 'pagada':
                raise UserError(self.env._('Una liquidación ya pagada no se cancela: se corrige con un ajuste.'))
            if liquidacion.estado == 'cancelada':
                continue
            if liquidacion.estado == 'aprobada':
                if not (liquidacion.motivo_cancelacion or '').strip():
                    raise UserError(self.env._('Escribe el motivo de la cancelación.'))
                filas = self.env['dcasa.web.movimiento'].sudo().search([
                    ('liquidacion_id', '=', liquidacion.id), ('tipo', '=', 'liquidacion'), ('centavos', '<', 0)])
                for fila in filas:
                    fila._contraria(self.env._('Se canceló la liquidación %(num)s: %(motivo)s', num=liquidacion.name,
                                               motivo=liquidacion.motivo_cancelacion), autor=self.env.user.login)
            liquidacion._escribir({'estado': 'cancelada', 'cancelada_por': self.env.user.id,
                                   'cancelada_el': fields.Datetime.now()})
        return True


class DcasaWebLiquidacionLinea(models.Model):
    _name = 'dcasa.web.liquidacion.linea'
    _description = 'Renglón de una liquidación de la comisión del sitio web'
    _order = 'liquidacion_id, empleado_id, concepto'

    liquidacion_id = fields.Many2one('dcasa.web.liquidacion', required=True, readonly=True, index=True,
                                     ondelete='cascade')
    company_id = fields.Many2one(related='liquidacion_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    empleado_id = fields.Many2one('hr.employee', 'Persona', required=True, readonly=True, ondelete='restrict')
    concepto = fields.Selection(CONCEPTOS, required=True, readonly=True)
    centavos = fields.Integer(required=True, readonly=True)
    monto = fields.Monetary('A pagar', compute='_compute_monto', store=True)

    _unico = models.Constraint('UNIQUE(liquidacion_id, empleado_id, concepto)',
                               'Cada persona sale una vez por concepto en una liquidación.')
    _positivo = models.Constraint('CHECK(centavos > 0)', 'Un renglón de liquidación es siempre más que cero.')

    @api.depends('centavos')
    def _compute_monto(self):
        for linea in self:
            linea.monto = linea.centavos / 100.0

    def write(self, vals):
        raise UserError(self.env._('Los renglones de una liquidación los arma el sistema y no se editan.'))

    def unlink(self):
        if any(ln.liquidacion_id.estado != 'borrador' for ln in self):
            raise UserError(self.env._('Una liquidación aprobada no se edita.'))
        return super().unlink()
