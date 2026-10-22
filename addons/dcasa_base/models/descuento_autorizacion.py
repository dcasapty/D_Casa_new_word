"""Descuento con autorización de Gerencia por clave (decisión D1 de la gerencia, 2026-10-17/18).

Quien cobra o vende (Vendedora, Caja) rebaja hasta el tope de Ajustes de Ventas (``sale_order_line.py``). Para un
descuento mayor:

1. Desde la cotización, **«Pedir descuento a Gerencia»**: cuánto (un % sobre el total o un importe fijo) y por qué.
2. A cada persona de Gerencia (quien no tiene tope) le llega por Telegram **su propia clave** de 6 números, con la
   cotización, el cliente, el total antes y después y el motivo (``dcasa_brian`` hace el envío; sin Telegram conectado
   no sale nada y la pantalla dice que hay que pedírselo a Gerencia en persona).
3. Si está de acuerdo, Gerencia le dicta la clave; quien pidió la escribe en la misma pantalla y el descuento **se
   aplica solo** (el descuento global o de importe fijo de Odoo).

La clave vale **una vez**, solo para **esa cotización y ese monto** (si la cotización cambió de total, no sirve) y
vence a los minutos de Ajustes de Ventas (10 de fábrica). Cinco claves equivocadas la bloquean. Se guarda solo su
huella. Todo queda registrado: quién pidió, a quién le llegó, quién autorizó (la clave de cada persona es distinta),
cuánto y cuándo, en la lista **Ventas › Descuentos por autorizar** y en el historial de la cotización.

Gerencia también aprueba desde su usuario, en esa lista («Aprobar y aplicar»), o rechaza.

El descuento se aplica con ``sudo`` después de comprobar que quien lo usa puede editar la cotización: es el único
camino por el que un descuento pasa del tope sin que lo ponga Gerencia. Lo que se haga después en esa cotización se
mide con las reglas de siempre: no se puede empeorar el descuento ya autorizado (``_dcasa_validar_tope_del_pedido``).
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

PARAM_MINUTOS = 'dcasa.descuento_clave_minutos'
MINUTOS_DEFECTO = 10
MAX_INTENTOS = 5
GRUPO_APRUEBA = 'sales_team.group_sale_manager'
TIPOS = [('porcentaje', 'Un % sobre el total'), ('monto', 'Un importe fijo ($)')]
ESTADOS = [
    ('pendiente', 'Esperando la clave'),
    ('usada', 'Aplicado'),
    ('rechazada', 'Rechazado por Gerencia'),
    ('vencida', 'Venció la clave'),
    ('bloqueada', 'Bloqueado (claves equivocadas)'),
    ('cancelada', 'Cancelado'),
]


def dinero(moneda, monto):
    return f'{moneda.symbol or "$"}{monto:,.2f}'


class DcasaDescuentoAutorizacion(models.Model):
    _name = 'dcasa.descuento.autorizacion'
    _description = 'Descuento por autorizar (clave de Gerencia)'
    _order = 'id desc'
    _rec_name = 'order_id'

    order_id = fields.Many2one('sale.order', string='Cotización', required=True, readonly=True, index=True,
                               ondelete='cascade')
    partner_id = fields.Many2one(related='order_id.partner_id', string='Cliente')
    company_id = fields.Many2one(related='order_id.company_id')
    currency_id = fields.Many2one(related='order_id.currency_id')
    solicitante_id = fields.Many2one('res.users', string='Lo pidió', required=True, readonly=True, index=True)
    aprobador_id = fields.Many2one('res.users', string='Lo autorizó', readonly=True)
    canal = fields.Selection([('telegram', 'Clave por Telegram'), ('persona', 'Gerencia desde su usuario')],
                             string='Cómo se autorizó', readonly=True)
    tipo = fields.Selection(TIPOS, string='Descuento', required=True, readonly=True)
    porcentaje = fields.Float('Porcentaje', readonly=True, digits=(16, 2))
    monto = fields.Monetary('Importe fijo', readonly=True)
    motivo = fields.Char('Motivo', required=True, readonly=True)
    total_antes = fields.Monetary('Total antes', readonly=True,
                                  help='El total de la cotización (con ITBMS) cuando se pidió: si cambia, la clave ya '
                                       'no sirve.')
    rebaja_estimada = fields.Monetary('Rebaja', readonly=True, help='Cuánto baja el total (con ITBMS).')
    total_despues = fields.Monetary('Total después', readonly=True)
    estado = fields.Selection(ESTADOS, default='pendiente', required=True, readonly=True, index=True)
    vence = fields.Datetime('La clave vence', readonly=True)
    intentos = fields.Integer('Claves equivocadas', readonly=True, default=0)
    enviada_a = fields.Char('Se le mandó la clave a', readonly=True)
    aplicada_en = fields.Datetime('Aplicado el', readonly=True)
    clave_ids = fields.One2many('dcasa.descuento.clave', 'autorizacion_id', readonly=True, groups='base.group_system')

    # ------------------------------------------------------------------
    # Reglas
    # ------------------------------------------------------------------

    @api.model
    def _minutos(self):
        valor = self.env['ir.config_parameter'].sudo().get_param(PARAM_MINUTOS, MINUTOS_DEFECTO)
        try:
            minutos = int(float(valor))
        except (TypeError, ValueError):
            minutos = MINUTOS_DEFECTO
        return min(max(minutos, 1), 60)

    @api.model
    def _aprobadores(self):
        """Quienes autorizan: los usuarios internos activos sin tope (Gerencia o Ventas administrador)."""
        grupo = self.env.ref(GRUPO_APRUEBA)
        return self.env['res.users'].sudo().search([
            ('share', '=', False), ('active', '=', True), ('all_group_ids', 'in', grupo.ids)])

    @api.model
    def _hash(self, autorizacion_id, usuario_id, codigo):
        sal = self.env['ir.config_parameter'].sudo().get_param('database.secret', '')
        return hashlib.sha256(f'{sal}:descuento:{autorizacion_id}:{usuario_id}:{codigo}'.encode()).hexdigest()

    @api.model
    def _rebaja(self, orden, tipo, porcentaje, monto):
        """Cuánto baja el total (con ITBMS) con ese descuento: lo que ve Gerencia antes de dar la clave."""
        moneda = orden.currency_id
        if tipo == 'porcentaje':
            return moneda.round(orden.amount_total * porcentaje / 100)
        return moneda.round(monto)

    @api.model
    def _validar_pedido(self, orden, tipo, porcentaje, monto, motivo):
        """Lo que se puede pedir: una cotización que la persona puede editar, un descuento que pasa su tope."""
        if orden.state not in ('draft', 'sent'):
            raise UserError(self.env._('Solo se pide descuento para una cotización que todavía no se confirma.'))
        orden.check_access('write')
        if not (motivo or '').strip():
            raise UserError(self.env._('Escribe por qué necesitas el descuento: Gerencia lo lee antes de decidir.'))
        moneda = orden.currency_id
        if moneda.compare_amounts(orden.amount_total, 0) <= 0:
            raise UserError(self.env._('La cotización no tiene nada que cobrar todavía.'))
        tope = self.env['sale.order.line']._dcasa_descuento_max()
        if tipo == 'porcentaje':
            if not 0 < porcentaje < 100:
                raise UserError(self.env._('El porcentaje va de más de 0 a menos de 100.'))
            if porcentaje <= tope:
                raise UserError(self.env._(
                    'Hasta %s %% lo puedes poner tú, sin clave: usa el botón «Descuento».', f'{tope:g}'))
        else:
            if moneda.compare_amounts(monto, 0) <= 0 or moneda.compare_amounts(monto, orden.amount_total) >= 0:
                raise UserError(self.env._('El importe va de más de 0 a menos del total de la cotización.'))
            if moneda.compare_amounts(monto, moneda.round(orden.amount_total * tope / 100)) <= 0:
                raise UserError(self.env._(
                    'Ese importe está dentro de tu tope (%s %%): ponlo tú con el botón «Descuento».', f'{tope:g}'))

    # ------------------------------------------------------------------
    # Pedir (desde el asistente o Brian)
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_pedir(self, orden, tipo, porcentaje=0.0, monto=0.0, motivo=''):
        """Crea la solicitud y le manda a cada persona de Gerencia su clave. Devuelve la solicitud.

        Corre como quien pide: comprueba que puede editar la cotización ANTES de escribir con sudo."""
        if self.env['sale.order.line']._dcasa_sin_tope():
            raise UserError(self.env._('Tú no tienes tope de descuento: ponlo directo con el botón «Descuento».'))
        orden = orden.with_env(self.env)
        self._validar_pedido(orden, tipo, porcentaje, monto, motivo)
        # Una sola solicitud viva por cotización: la nueva reemplaza a la anterior.
        self.sudo().search([('order_id', '=', orden.id), ('estado', '=', 'pendiente')]).write({'estado': 'cancelada'})
        rebaja = self._rebaja(orden, tipo, porcentaje, monto)
        solicitud = self.sudo().create({
            'order_id': orden.id, 'solicitante_id': self.env.uid, 'tipo': tipo,
            'porcentaje': porcentaje if tipo == 'porcentaje' else 0.0,
            'monto': monto if tipo == 'monto' else 0.0, 'motivo': motivo.strip()[:200],
            'total_antes': orden.amount_total, 'rebaja_estimada': rebaja,
            'total_despues': orden.currency_id.round(orden.amount_total - rebaja),
            'vence': fields.Datetime.now() + timedelta(minutes=self._minutos()),
        })
        claves = {}
        for usuario in self._aprobadores() - self.env.user:
            codigo = f'{secrets.randbelow(10 ** 6):06d}'
            claves[usuario] = codigo
            self.env['dcasa.descuento.clave'].sudo().create({
                'autorizacion_id': solicitud.id, 'user_id': usuario.id,
                'clave_hash': self._hash(solicitud.id, usuario.id, codigo)})
        enviados = solicitud.sudo()._dcasa_enviar_claves(claves) if claves else self.env['res.users']
        solicitud.sudo().write({'enviada_a': ', '.join(enviados.mapped('name')) or False})
        orden.sudo().message_post(body=solicitud._dcasa_nota(self.env._('Se pidió un descuento a Gerencia')),
                                  subtype_xmlid='mail.mt_note', author_id=self.env.user.partner_id.id)
        return solicitud

    def _dcasa_enviar_claves(self, claves):
        """Manda a cada persona su clave. Devuelve a quiénes les llegó. Sin un canal instalado, a nadie: dcasa_brian
        lo hace por Telegram."""
        return self.env['res.users']

    def _dcasa_texto_para_gerencia(self, codigo):
        """El mensaje de Telegram (texto plano)."""
        self.ensure_one()
        moneda = self.currency_id
        if self.tipo == 'porcentaje':
            cuanto = self.env._('%s %% sobre el total', f'{self.porcentaje:g}')
        else:
            cuanto = self.env._('importe fijo de %s', dinero(moneda, self.monto))
        hora = fields.Datetime.context_timestamp(self.with_context(tz='America/Panama'), self.vence).strftime('%H:%M')
        return self.env._(
            'Descuento por autorizar · %(orden)s\n'
            'Pide: %(quien)s\n'
            'Cliente: %(cliente)s\n'
            'Descuento: %(cuanto)s\n'
            'Total: %(antes)s → %(despues)s (rebaja de %(rebaja)s, con ITBMS)\n'
            'Motivo: %(motivo)s\n\n'
            'Tu clave: %(codigo)s\n'
            'Vale una vez, solo para esta cotización y este monto, hasta las %(hora)s.\n'
            'Si estás de acuerdo, dásela a %(quien)s. Si no, no hagas nada: vence sola.',
            orden=self.order_id.name, quien=self.solicitante_id.name, cliente=self.partner_id.display_name or '',
            cuanto=cuanto, antes=dinero(moneda, self.total_antes), despues=dinero(moneda, self.total_despues),
            rebaja=dinero(moneda, self.rebaja_estimada), motivo=self.motivo, codigo=codigo, hora=hora)

    # ------------------------------------------------------------------
    # Usar la clave
    # ------------------------------------------------------------------

    def _dcasa_vigente(self):
        """Pone «vencida» si ya pasó la hora. Devuelve si sigue esperando la clave."""
        self.ensure_one()
        if self.estado == 'pendiente' and self.vence and fields.Datetime.now() > self.vence:
            self.sudo().write({'estado': 'vencida'})
        return self.estado == 'pendiente'

    def _dcasa_usar_clave(self, codigo):
        """Prueba la clave que escribió quien pidió. Devuelve ``(True, '')`` si se aplicó o ``(False, motivo)``.

        No lanza error con una clave equivocada: así el intento queda contado (un error desharía la cuenta)."""
        self.ensure_one()
        if self.solicitante_id != self.env.user:
            raise AccessError(self.env._('Esta clave es para quien pidió el descuento.'))
        self.order_id.check_access('write')
        if not self._dcasa_vigente():
            return False, self._dcasa_motivo_no_vigente()
        codigo = ''.join(c for c in str(codigo or '') if c.isdigit())
        clave = self.sudo().clave_ids.filtered(
            lambda c: hmac.compare_digest(c.clave_hash, self._hash(self.id, c.user_id.id, codigo)))[:1]
        if len(codigo) != 6 or not clave:
            intentos = self.intentos + 1
            valores = {'intentos': intentos}
            if intentos >= MAX_INTENTOS:
                valores['estado'] = 'bloqueada'
            self.sudo().write(valores)
            if intentos >= MAX_INTENTOS:
                return False, self.env._('Escribiste %s claves equivocadas: la solicitud se bloqueó. Pide una nueva.',
                                         MAX_INTENTOS)
            return False, self.env._('Esa clave no es. Te quedan %s intentos.', MAX_INTENTOS - intentos)
        self._dcasa_aplicar(clave.user_id, 'telegram')
        return True, ''

    def _dcasa_motivo_no_vigente(self):
        return {
            'vencida': self.env._('La clave ya venció. Pide una nueva.'),
            'usada': self.env._('Este descuento ya se aplicó.'),
            'rechazada': self.env._('Gerencia rechazó este descuento.'),
            'bloqueada': self.env._('Esta solicitud se bloqueó por claves equivocadas. Pide una nueva.'),
            'cancelada': self.env._('Esta solicitud se canceló (hay una más nueva).'),
        }.get(self.estado, self.env._('Esta solicitud ya no está esperando la clave.'))

    def _dcasa_aplicar(self, aprobador, canal):
        """Aplica el descuento autorizado (con sudo: es el único camino que pasa del tope) y lo deja registrado."""
        self.ensure_one()
        orden = self.order_id.sudo()
        moneda = orden.currency_id
        if orden.state not in ('draft', 'sent'):
            raise UserError(self.env._('La cotización %s ya no está en borrador: el descuento no se aplica.',
                                       orden.name))
        if moneda.compare_amounts(orden.amount_total, self.total_antes) != 0:
            raise UserError(self.env._(
                'La cotización cambió desde que se pidió el descuento (era %(antes)s, ahora %(ahora)s): esta clave ya '
                'no sirve. Pide uno nuevo.', antes=dinero(moneda, self.total_antes),
                ahora=dinero(moneda, orden.amount_total)))
        asistente = self.env['sale.order.discount'].sudo().with_company(orden.company_id).create({
            'sale_order_id': orden.id,
            'discount_type': 'so_discount' if self.tipo == 'porcentaje' else 'amount',
            'discount_percentage': self.porcentaje / 100 if self.tipo == 'porcentaje' else 0.0,
            'discount_amount': self.monto if self.tipo == 'monto' else 0.0,
        })
        asistente.action_apply_discount()
        self.sudo().write({'estado': 'usada', 'aprobador_id': aprobador.id, 'canal': canal,
                           'aplicada_en': fields.Datetime.now(), 'total_despues': orden.amount_total})
        orden.message_post(body=self._dcasa_nota(self.env._('Descuento autorizado por Gerencia y aplicado')),
                           subtype_xmlid='mail.mt_note', author_id=self.env.user.partner_id.id)

    def _dcasa_nota(self, titulo):
        self.ensure_one()
        moneda = self.currency_id
        cuanto = (f'{self.porcentaje:g} %' if self.tipo == 'porcentaje' else dinero(moneda, self.monto))
        filas = [
            (self.env._('Pidió'), self.solicitante_id.name),
            (self.env._('Descuento'), cuanto),
            (self.env._('Total'), f'{dinero(moneda, self.total_antes)} → {dinero(moneda, self.total_despues)}'),
            (self.env._('Motivo'), self.motivo),
        ]
        if self.aprobador_id:
            filas.append((self.env._('Autorizó'), self.aprobador_id.name))
            filas.append((self.env._('Cómo'), dict(self._fields['canal'].selection).get(self.canal, '')))
        elif self.enviada_a:
            filas.append((self.env._('Clave enviada por Telegram a'), self.enviada_a))
        else:
            filas.append((self.env._('Clave'),
                          self.env._('Telegram no está conectado: lo aprueba Gerencia en persona')))
        cuerpo = ''.join(f'<li>{escape(k)}: {escape(v or "")}</li>' for k, v in filas)
        return Markup(f'<p><strong>{escape(titulo)}</strong></p><ul>{cuerpo}</ul>')

    # ------------------------------------------------------------------
    # Botones de la lista (Gerencia) y de quien pidió
    # ------------------------------------------------------------------

    def _dcasa_exigir_gerencia(self):
        if not (self.env.su or self.env.user.has_group(GRUPO_APRUEBA) or self.env.user.has_group('base.group_system')):
            raise AccessError(self.env._('Aprobar o rechazar un descuento lo hace solo Gerencia.'))

    def action_aprobar(self):
        """Gerencia aprueba desde su usuario (sin clave) y el descuento se aplica."""
        self._dcasa_exigir_gerencia()
        for solicitud in self:
            if solicitud.estado not in ('pendiente', 'vencida'):
                raise UserError(solicitud._dcasa_motivo_no_vigente())
            solicitud._dcasa_aplicar(self.env.user, 'persona')
        return True

    def action_rechazar(self):
        self._dcasa_exigir_gerencia()
        for solicitud in self.filtered(lambda s: s.estado in ('pendiente', 'vencida')):
            solicitud.sudo().write({'estado': 'rechazada', 'aprobador_id': self.env.uid})
            solicitud.order_id.sudo().message_post(
                body=solicitud._dcasa_nota(self.env._('Gerencia rechazó el descuento')),
                subtype_xmlid='mail.mt_note', author_id=self.env.user.partner_id.id)
        return True

    def action_ver_cotizacion(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'sale.order', 'res_id': self.order_id.id,
                'view_mode': 'form', 'target': 'current'}


class DcasaDescuentoClave(models.Model):
    """La huella de la clave de cada persona de Gerencia (nunca la clave). Solo la ve el sistema."""
    _name = 'dcasa.descuento.clave'
    _description = 'Clave de un descuento por autorizar (huella)'

    autorizacion_id = fields.Many2one('dcasa.descuento.autorizacion', required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', string='Para', required=True, ondelete='cascade')
    clave_hash = fields.Char(required=True)


class DcasaDescuentoPedir(models.TransientModel):
    """La pantalla de quien pide: cuánto y por qué; después, dónde escribir la clave."""
    _name = 'dcasa.descuento.pedir'
    _description = 'Pedir un descuento a Gerencia'

    order_id = fields.Many2one('sale.order', string='Cotización', required=True, readonly=True)
    currency_id = fields.Many2one(related='order_id.currency_id')
    total = fields.Monetary(related='order_id.amount_total', string='Total de la cotización (con ITBMS)')
    tope = fields.Float('Tu tope', compute='_compute_tope')
    tipo = fields.Selection(TIPOS, string='Descuento', default='porcentaje', required=True)
    porcentaje = fields.Float('Porcentaje', digits=(16, 2))
    monto = fields.Monetary('Importe ($)')
    motivo = fields.Char('¿Por qué?', help='Lo lee Gerencia antes de decidir, p. ej. «lleva la sala y el comedor».')
    rebaja = fields.Monetary('Baja', compute='_compute_estimado')
    total_despues = fields.Monetary('Quedaría en', compute='_compute_estimado')
    paso = fields.Selection([('pedir', 'Pedir'), ('clave', 'Clave'), ('listo', 'Listo')], default='pedir')
    autorizacion_id = fields.Many2one('dcasa.descuento.autorizacion', readonly=True)
    enviada_a = fields.Char(related='autorizacion_id.enviada_a')
    vence = fields.Datetime(related='autorizacion_id.vence')
    clave = fields.Char('Clave de Gerencia', size=12)
    aviso = fields.Char(readonly=True)

    @api.depends_context('uid')
    def _compute_tope(self):
        tope = self.env['sale.order.line']._dcasa_descuento_max()
        for asistente in self:
            asistente.tope = tope

    @api.depends('tipo', 'porcentaje', 'monto', 'order_id.amount_total')
    def _compute_estimado(self):
        Autorizacion = self.env['dcasa.descuento.autorizacion']
        for asistente in self:
            if not asistente.order_id:
                asistente.rebaja = asistente.total_despues = 0.0
                continue
            rebaja = Autorizacion._rebaja(asistente.order_id, asistente.tipo, asistente.porcentaje or 0.0,
                                          asistente.monto or 0.0)
            asistente.rebaja = rebaja
            asistente.total_despues = asistente.order_id.amount_total - rebaja

    @api.constrains('porcentaje', 'monto')
    def _check_cifras(self):
        for asistente in self:
            if asistente.porcentaje < 0 or asistente.monto < 0:
                raise ValidationError(self.env._('El descuento no puede ser negativo.'))

    def _reabrir(self):
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id, 'view_mode': 'form',
                'target': 'new', 'name': self.env._('Descuento con autorización de Gerencia')}

    def action_pedir(self):
        self.ensure_one()
        solicitud = self.env['dcasa.descuento.autorizacion']._dcasa_pedir(
            self.order_id, self.tipo, self.porcentaje or 0.0, self.monto or 0.0, self.motivo or '')
        self.write({'autorizacion_id': solicitud.id, 'paso': 'clave', 'aviso': False})
        return self._reabrir()

    def action_aplicar(self):
        self.ensure_one()
        if not self.autorizacion_id:
            raise UserError(self.env._('Primero pide el descuento.'))
        listo, motivo = self.autorizacion_id._dcasa_usar_clave(self.clave)
        if not listo:
            self.write({'aviso': motivo, 'clave': False})
            return self._reabrir()
        self.write({'paso': 'listo', 'aviso': False})
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'title': self.env._('Descuento aplicado'),
            'message': self.env._('Gerencia lo autorizó y ya está en la cotización.'),
            'next': {'type': 'ir.actions.act_window_close'}}}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dcasa_pide_descuento = fields.Boolean(
        compute='_compute_dcasa_pide_descuento',
        help='Quien mira tiene tope de descuento: para pasarlo, pide la clave a Gerencia.')
    dcasa_descuento_ids = fields.One2many('dcasa.descuento.autorizacion', 'order_id',
                                          string='Descuentos pedidos a Gerencia')

    @api.depends_context('uid')
    def _compute_dcasa_pide_descuento(self):
        pide = not self.env['sale.order.line']._dcasa_sin_tope()
        for orden in self:
            orden.dcasa_pide_descuento = pide

    def action_dcasa_pedir_descuento(self):
        """Abre «Pedir descuento a Gerencia». Solo devuelve la acción; lo que se pide lo revisa ``_dcasa_pedir``."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'dcasa.descuento.pedir', 'view_mode': 'form',
            'target': 'new', 'name': self.env._('Descuento con autorización de Gerencia'),
            'context': {'default_order_id': self.id},
        }


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dcasa_descuento_clave_minutos = fields.Integer(
        string='Minutos que vale la clave de un descuento', config_parameter=PARAM_MINUTOS,
        default=MINUTOS_DEFECTO,
        help='La clave que Gerencia recibe por Telegram para autorizar un descuento mayor al tope vence a los minutos '
             'que digas aquí (de 1 a 60).')

    @api.constrains('dcasa_descuento_clave_minutos')
    def _check_dcasa_descuento_clave_minutos(self):
        for ajustes in self:
            if not 1 <= ajustes.dcasa_descuento_clave_minutos <= 60:
                raise ValidationError(self.env._('La clave vale de 1 a 60 minutos.'))
