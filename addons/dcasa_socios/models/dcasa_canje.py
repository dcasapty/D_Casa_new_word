from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from . import reglas as R
from .dcasa_compra import TZ_PANAMA

ESTADOS_CANJE = [
    ('solicitado', 'Pendiente de entregar'),
    ('entregado', 'Entregado'),
    ('vencido', 'Vencido'),
    ('cancelado', 'Cancelado'),
]


class DcasaPremio(models.Model):
    """El catálogo de premios. Vive en la base (no en puntos.json) porque es
    inventario: Marcial lo cambia con la temporada sin abrir un pull request."""

    _name = 'dcasa.premio'
    _description = 'Premio del programa de socios'
    _order = 'sequence, puntos, id'

    name = fields.Char(string='Premio', required=True)
    descripcion = fields.Char()
    tipo = fields.Selection([('descuento', 'Descuento en una compra'), ('producto', 'Producto')],
                            required=True, default='descuento',
                            help='Un descuento obliga a volver a comprar; un producto se entrega y ya.')
    puntos = fields.Integer(required=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    valor = fields.Monetary(help='Lo que el socio cree que recibe (el importe del descuento).')
    costo = fields.Monetary(help='Lo que de verdad le cuesta a D’CASA. Es lo que responde '
                                 '«¿cuánto nos ha costado el programa?».')
    stock_limitado = fields.Boolean(string='Stock limitado')
    stock = fields.Integer(help='Cuántos quedan. En 0 deja de ofrecerse solo.')
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    image_512 = fields.Image(max_width=512, max_height=512)

    _puntos_positivos = models.Constraint('CHECK(puntos > 0)', 'Un premio cuesta más de cero puntos.')
    _importes = models.Constraint('CHECK(valor >= 0 AND costo >= 0 AND stock >= 0)',
                                  'Los importes y el stock no pueden ser negativos.')

    def _disponible(self):
        self.ensure_one()
        return self.active and (not self.stock_limitado or self.stock > 0)


class DcasaCanje(models.Model):
    """Un premio pedido. Los puntos salen AL PEDIR, como una reserva: si salieran
    al entregar, con saldo para uno se podrían pedir tres. Si el código vence o se
    cancela, un asiento contrario devuelve los puntos enteros."""

    _name = 'dcasa.canje'
    _description = 'Canje de puntos'
    _order = 'solicitado_en desc, id desc'
    _rec_name = 'codigo'

    codigo = fields.Char(required=True, readonly=True, index=True, copy=False)
    partner_id = fields.Many2one('res.partner', string='Socio', required=True, readonly=True, index=True,
                                 ondelete='restrict')
    premio_id = fields.Many2one('dcasa.premio', required=True, readonly=True, ondelete='restrict')
    # Lo que se le prometió queda congelado aunque el catálogo cambie mañana.
    premio_nombre = fields.Char(string='Nombre del premio', required=True, readonly=True)
    premio_tipo = fields.Selection(related='premio_id.tipo', store=True)
    puntos = fields.Integer(required=True, readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True, default=lambda self: self.env.company.currency_id)
    valor = fields.Monetary(readonly=True)
    costo = fields.Monetary(readonly=True)
    estado = fields.Selection(ESTADOS_CANJE, required=True, readonly=True, default='solicitado', index=True)
    # index: la lista de canjes se ordena por aquí (_order); sin índice, cada página ordena la tabla entera.
    solicitado_en = fields.Datetime(required=True, readonly=True, default=fields.Datetime.now, index=True)
    expira_en = fields.Datetime(string='Vence', required=True, readonly=True)
    entregado_en = fields.Datetime(readonly=True)
    entregado_por = fields.Char(readonly=True)
    sale_order_id = fields.Many2one('sale.order', string='Cobrado en la venta', readonly=True,
                                    index='btree_not_null')
    cerrado_en = fields.Datetime(readonly=True)
    cerrado_motivo = fields.Char(readonly=True)

    _codigo_unico = models.Constraint('UNIQUE(codigo)', 'Ese código de canje ya existe.')

    # ------------------------------------------------------------------------
    # Pedir
    # ------------------------------------------------------------------------

    @api.model
    def _pedir(self, partner, premio):
        """El socio pide un premio: se reservan los puntos y sale un código."""
        reglas = R.cargar_reglas()
        ficha = partner.commercial_partner_id.sudo()
        premio = premio.sudo()
        # Serializa los pedidos del mismo socio: dos toques seguidos en un móvil
        # lento no pueden gastar dos veces el mismo saldo.
        self.env.cr.execute('SELECT id FROM res_partner WHERE id = %s FOR UPDATE', [ficha.id])
        if ficha.dcasa_socio_estado != 'activo':
            raise UserError(self.env._('Tu cuenta está suspendida. Escríbenos por WhatsApp y lo revisamos.'))
        if not premio._disponible():
            raise UserError(self.env._('Ese premio se agotó o ya no está disponible. Elige otro.'))
        minimo = reglas['canje'].get('saldoMinimoParaCanjear')
        if minimo is not None and premio.puntos < minimo:
            raise UserError(self.env._('El canje mínimo es de %s puntos.', R.como_puntos(minimo)))
        pendiente = self.sudo().search([('partner_id', '=', ficha.id), ('premio_id', '=', premio.id),
                                        ('estado', '=', 'solicitado')], limit=1)
        if pendiente:
            raise UserError(self.env._(
                'Ya tienes ese premio pedido (código %s). Enséñalo en la tienda antes de que venza.',
                pendiente.codigo))
        saldo = ficha.dcasa_saldo
        if saldo < premio.puntos:
            raise UserError(self.env._('Te faltan %s puntos para ese premio.',
                                       R.como_puntos(R.faltan_para(saldo, premio.puntos))))

        ahora = fields.Datetime.now()
        for _intento in range(10):
            codigo = R.nuevo_codigo_canje()
            if not self.sudo().search_count([('codigo', '=', codigo)], limit=1):
                break
        canje = self.sudo().create({
            'codigo': codigo,
            'partner_id': ficha.id,
            'premio_id': premio.id,
            'premio_nombre': premio.name,
            'puntos': premio.puntos,
            'valor': premio.valor,
            'costo': premio.costo,
            'solicitado_en': ahora,
            'expira_en': ahora + timedelta(hours=reglas['canje']['vigenciaDelCodigoHoras']),
        })
        self.env['dcasa.movimiento']._asentar(ficha, 'canje', -premio.puntos, 'socio', canje_id=canje.id,
                                             motivo=f'Pediste: {premio.name}')
        if premio.stock_limitado:
            premio.stock -= 1
        return canje

    # ------------------------------------------------------------------------
    # Entregar, vencer, cancelar
    # ------------------------------------------------------------------------

    def _entregar(self, quien, sale_order=None, partner=None):
        for canje in self.sudo():
            if partner and canje.partner_id != partner:
                raise UserError(self.env._(
                    'El premio %s es de otro cliente. Solo lo puede usar quien lo ganó.', canje.codigo))
            if canje.estado != 'solicitado':
                raise UserError(self.env._(
                    'El premio %(codigo)s ya no está pendiente (%(estado)s).',
                    codigo=canje.codigo, estado=dict(ESTADOS_CANJE)[canje.estado]))
            canje.write({
                'estado': 'entregado',
                'entregado_en': fields.Datetime.now(),
                'entregado_por': quien,
                'sale_order_id': sale_order.id if sale_order else False,
            })
        return True

    def _exigir_vendedora(self):
        """Los botones de canje escriben con ``sudo()``: el grupo se comprueba antes, en el servidor
        (Odoo expone por RPC todo método público, y el CSV solo da lectura a la vendedora)."""
        if not self.env.su and not self.env.user.has_group('sales_team.group_sale_salesman'):
            raise AccessError(self.env._('Solo el equipo de ventas entrega o cancela premios.'))

    def action_entregar(self):
        """Entrega en el mostrador (premios de producto)."""
        self._exigir_vendedora()
        return self._entregar(self.env.user.login)

    def _cerrar(self, estado, motivo, autor):
        Movimiento = self.env['dcasa.movimiento'].sudo()
        for canje in self.sudo().filtered(lambda c: c.estado == 'solicitado'):
            canje.write({'estado': estado, 'cerrado_en': fields.Datetime.now(), 'cerrado_motivo': motivo})
            asiento = Movimiento.search([('canje_id', '=', canje.id), ('tipo', '=', 'canje')], limit=1)
            if asiento:
                asiento._reversar(motivo, autor)
            if canje.premio_id.stock_limitado:
                canje.premio_id.stock += 1

    def action_cancelar(self):
        self._exigir_vendedora()
        self._cerrar('cancelado', self.env._('Lo canceló la tienda. Te devolvimos los puntos.'), self.env.user.login)
        return True

    def _cancelar_por_socio(self):
        self._cerrar('cancelado', 'Lo cancelaste tú.', 'socio')

    @api.model
    def _cron_programa(self):
        """Cada hora: vence los códigos que nadie buscó y felicita a los que cumplen hoy.

        Los dos pasos son repetibles y corren por separado: si uno falla, el otro se hace igual.
        """
        vencidos = self.sudo().search([('estado', '=', 'solicitado'), ('expira_en', '<=', fields.Datetime.now())],
                                      limit=500)
        vencidos._cerrar('vencido', 'Venció el código sin pasar por la tienda. Te devolvimos los puntos.', 'sistema')
        self._felicitar_a_los_de_hoy()

    @api.model
    def _felicitar_a_los_de_hoy(self, ahora=None):
        """Regalo de cumpleaños: una vez por año, y solo a quien ya compró alguna vez."""
        puntos = R.cargar_reglas()['cumpleanos'].get('puntos')
        if not puntos:
            return self.env['res.partner']
        ahora = ahora or fields.Datetime.now()
        local = pytz.utc.localize(ahora).astimezone(TZ_PANAMA)  # el día que es en La Chorrera, no en UTC
        inicio_anio = TZ_PANAMA.localize(datetime.combine(local.date().replace(month=1, day=1), time.min))
        inicio_anio = inicio_anio.astimezone(pytz.utc).replace(tzinfo=None)
        Movimiento = self.env['dcasa.movimiento'].sudo()
        candidatos = self.env['res.partner'].sudo().search([
            ('dcasa_cumple', '=', local.strftime('%m-%d')),
            ('dcasa_socio_estado', '=', 'activo'),
            ('dcasa_socio_codigo', '!=', False),
        ])
        felicitados = self.env['res.partner']
        for socio in candidatos:
            if not socio._dcasa_compras_con_puntos():
                continue
            if Movimiento.search_count([('partner_id', '=', socio.id), ('tipo', '=', 'cumpleanos'),
                                        ('ocurrido_en', '>=', inicio_anio)], limit=1):
                continue
            Movimiento._asentar(socio, 'cumpleanos', puntos, 'sistema',
                                motivo='¡Feliz cumpleaños! Un regalo de parte de D’CASA.')
            felicitados |= socio
        return felicitados
