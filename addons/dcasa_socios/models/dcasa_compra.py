from datetime import datetime, time

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError

from . import reglas as R

TZ_PANAMA = pytz.timezone('America/Panama')

# Por qué no se pagó un referido, cuando no se paga. Queda escrito en la compra.
MOTIVOS_SIN_REFERIDO = [
    ('sin-padrino', 'Nadie lo invitó.'),
    ('ya-pagado', 'Su referido ya se pagó antes.'),
    ('no-califica', 'Esta compra no llegó al mínimo para dar puntos.'),
    ('no-es-la-primera', 'No es su primera compra.'),
    ('padrino-no-vale', 'Quien lo invitó ya no tiene cuenta activa.'),
    ('tope-de-ahijados', 'Quien lo invitó llegó a su tope de referidos.'),
    ('tope-del-mes', 'Quien lo invitó llegó a su tope de este mes.'),
    ('sin-configurar', 'Falta definir cuánto gana quien invita.'),
    ('pagado', 'Referido pagado.'),
]


def inicio_del_mes_en_panama(ahora_utc):
    """El primer instante del mes en curso en Panamá, en UTC sin zona (como guarda Odoo)."""
    local = pytz.utc.localize(ahora_utc).astimezone(TZ_PANAMA)
    inicio = TZ_PANAMA.localize(datetime.combine(local.date().replace(day=1), time.min))
    return inicio.astimezone(pytz.utc).replace(tzinfo=None)


class DcasaCompra(models.Model):
    """Una compra que suma puntos.

    Se crea sola cuando una factura de cliente de Odoo queda pagada: la vendedora
    no vuelve a teclear la venta. Se congelan el monto, la base, los puntos y la
    versión de las reglas: si mañana cambia la economía, esta compra sigue
    explicando los puntos que dio. No se edita ni se borra: se anula.
    """

    _name = 'dcasa.compra'
    _description = 'Compra con puntos'
    _order = 'registrada_en desc, id desc'

    name = fields.Char(string='Factura', required=True, readonly=True)
    factura_normal = fields.Char(required=True, readonly=True, index=True,
                                 help="La factura sin guiones ni ceros de relleno: una factura, una carga.")
    partner_id = fields.Many2one('res.partner', string='Socio', required=True, readonly=True, index=True,
                                 ondelete='restrict')
    # set null: si se borra la factura (solo un borrador se puede borrar) la compra queda en la historia del programa
    # sin bloquear el borrado. El rastro de qué factura fue sigue en ``name`` y ``factura_normal``.
    move_id = fields.Many2one('account.move', string='Factura de Odoo', readonly=True,
                              index='btree_not_null', ondelete='set null')
    currency_id = fields.Many2one('res.currency', readonly=True,
                                  default=lambda self: self.env.company.currency_id)
    monto_centavos = fields.Integer(readonly=True, required=True)
    base_centavos = fields.Integer(readonly=True, required=True)
    monto = fields.Monetary(string='Pagado', compute='_compute_montos', store=True)
    puntos = fields.Integer(readonly=True, required=True)
    reglas_version = fields.Integer(string='Versión de reglas', readonly=True, required=True)
    # index: la lista de compras se ordena por aquí (_order).
    registrada_en = fields.Datetime(readonly=True, required=True, default=fields.Datetime.now, index=True)
    vendedor_id = fields.Many2one('res.users', string='Vendedora', readonly=True, index=True)
    referido = fields.Selection(MOTIVOS_SIN_REFERIDO, string='Referido', readonly=True)
    notas = fields.Char(readonly=True)
    anulada_en = fields.Datetime(readonly=True, copy=False)
    anulada_por = fields.Char(readonly=True, copy=False)
    anulada_motivo = fields.Char(readonly=True, copy=False)
    anulada_por_factura = fields.Boolean(
        readonly=True, copy=False,
        help='Se anuló porque la factura misma se deshizo: volvió a borrador, se canceló o se eliminó. Ese número de '
             'factura puede volver a dar puntos cuando quede pagado otra vez. Una devolución (nota de crédito) o una '
             'anulación a mano no lo reabre: esas facturas no vuelven a dar puntos.')
    estado = fields.Selection([('activa', 'Activa'), ('anulada', 'Anulada')],
                              compute='_compute_estado', store=True)

    # Una factura, una carga ACTIVA. Una compra anulada porque la factura se deshizo (ver ``_factura_libre``) no
    # bloquea la siguiente; cualquier otra anulada sigue bloqueando: eso lo cuida ``_factura_libre``.
    _factura_activa_unica = models.UniqueIndex(
        '(factura_normal) WHERE anulada_en IS NULL',
        message='Esa factura ya dio puntos. Una factura, una carga.')
    _monto_positivo = models.Constraint('CHECK(monto_centavos > 0 AND base_centavos > 0 AND puntos >= 0)',
                                        'El monto de una compra es mayor que cero.')

    @api.depends('monto_centavos')
    def _compute_montos(self):
        for compra in self:
            compra.monto = compra.monto_centavos / 100.0

    @api.depends('anulada_en')
    def _compute_estado(self):
        for compra in self:
            compra.estado = 'anulada' if compra.anulada_en else 'activa'

    # ------------------------------------------------------------------------
    # Registrar
    # ------------------------------------------------------------------------

    @api.model
    def _registrar(self, partner, factura, monto_centavos, vendedor, autor, move=None, notas=''):
        """Registra la compra, acredita sus puntos y paga el referido si toca."""
        reglas = R.cargar_reglas()
        ficha = partner._dcasa_asegurar_ficha()
        if ficha.dcasa_socio_estado != 'activo':
            return self.browse()
        if not self._factura_libre(R.factura_normal(factura), move):
            raise UserError(self.env._('Esa factura ya dio puntos. Una factura, una carga (también si se anuló).'))
        puntos = R.puntos_de_compra(monto_centavos, reglas)
        compra = self.sudo().create({
            'name': factura,
            'factura_normal': R.factura_normal(factura),
            'partner_id': ficha.id,
            'move_id': move.id if move else False,
            'currency_id': (move.company_id.currency_id if move else self.env.company.currency_id).id,
            'monto_centavos': monto_centavos,
            'base_centavos': R.base_de_compra(monto_centavos, reglas),
            'puntos': puntos,
            'reglas_version': reglas['version'],
            'vendedor_id': vendedor.id if vendedor else False,
            'notas': notas,
        })
        if puntos > 0:
            self.env['dcasa.movimiento']._asentar(
                ficha, 'compra', puntos, autor, compra_id=compra.id, motivo=f'Compra {factura}')
        compra.referido = compra._pagar_referido(reglas, autor)
        return compra

    @api.model
    def _factura_libre(self, factura_normal, move=None):
        """¿Esta factura puede dar puntos ahora? «Una factura, una carga».

        Sí, si nunca dio puntos. También si todo lo que dio se anuló porque la factura misma se deshizo (volvió a
        borrador, se canceló o se eliminó): el cliente de una venta real que se corrigió no puede quedarse sin sus
        puntos, y el número de una factura borrada se vuelve a usar en la siguiente. Nunca hay dos compras activas de
        la misma factura. No, si hay una activa, o si alguna se anuló por otra razón (una devolución, o a mano): eso
        sigue bloqueando como siempre. Tampoco una factura que ya tiene una nota de crédito publicada.
        """
        previas = self.sudo().search([('factura_normal', '=', factura_normal)])
        if not previas:
            return True
        if previas.filtered(lambda c: not c.anulada_en or not c.anulada_por_factura):
            return False
        return not (move and move.sudo().reversal_move_ids.filtered(lambda nota: nota.state == 'posted'))

    @api.model
    def _registrar_desde_factura(self, move):
        """Una factura de cliente pagada suma puntos. Idempotente: si ya se cargó, no hace nada."""
        if not self._factura_libre(R.factura_normal(move.name), move):
            return self.browse()
        monto = R.a_centavos(move.amount_total_signed)
        if monto <= 0:
            return self.browse()
        vendedor = move.invoice_user_id or self.env.user
        return self._registrar(move.commercial_partner_id, move.name, monto, vendedor,
                               autor=vendedor.login, move=move)

    def _pagar_referido(self, reglas, autor):
        """El referido se paga con la PRIMERA compra que da puntos, nunca al registrarse.

        Un tope alcanzado nunca hace fallar la venta: queda escrito por qué no se pagó.
        """
        self.ensure_one()
        comprador = self.partner_id
        if not comprador.dcasa_referido_por_id:
            return 'sin-padrino'
        # Una compra que no dio puntos no estrena a nadie (si no, $19.99 pagarían $7.50 en bonos).
        if self.puntos <= 0:
            return 'no-califica'
        if comprador.dcasa_referido_pagado_en:
            return 'ya-pagado'
        ref = reglas['referido']
        al_padrino, al_ahijado = ref.get('puntosAlPadrino'), ref.get('puntosAlAhijado')
        if al_padrino is None:
            return 'sin-configurar'
        # ¿Primera compra que cuenta? Las anuladas y las de cero puntos no cuentan.
        previas = self.sudo().search_count([
            ('partner_id', '=', comprador.id), ('id', '!=', self.id),
            ('anulada_en', '=', False), ('puntos', '>', 0),
        ])
        if previas:
            return 'no-es-la-primera'
        padrino = comprador.dcasa_referido_por_id
        if padrino.dcasa_socio_estado != 'activo' or not padrino.active:
            return 'padrino-no-vale'
        # Solo cuentan los asientos con origen: "me pagaron porque alguien que invité compró".
        Movimiento = self.env['dcasa.movimiento'].sudo()
        cobrados = Movimiento.search([
            ('partner_id', '=', padrino.id), ('tipo', '=', 'referido'), ('origen_partner_id', '!=', False)])
        # Un bono que se deshizo (la compra se anuló) no gasta ni el tope de ahijados ni el del mes.
        cobrados -= Movimiento.search([('reversa_id', 'in', cobrados.ids)]).reversa_id
        del_mes = sum(cobrados.filtered(
            lambda m: m.ocurrido_en >= inicio_del_mes_en_panama(fields.Datetime.now())).mapped('puntos'))
        tope_ahijados = ref.get('topeDeAhijadosPorPadrino')
        if tope_ahijados is not None and len(cobrados) >= tope_ahijados:
            return 'tope-de-ahijados'
        tope_mes = ref.get('topeDePuntosPorPadrinoAlMes')
        if tope_mes is not None and del_mes + al_padrino > tope_mes:
            return 'tope-del-mes'

        Movimiento._asentar(padrino, 'referido', al_padrino, autor, origen_partner_id=comprador.id,
                            compra_id=self.id, motivo=f'Primera compra de {comprador._dcasa_nombre_publico()}')
        if al_ahijado:
            Movimiento._asentar(comprador, 'referido', al_ahijado, autor, compra_id=self.id,
                                motivo='Bono por venir invitado')
        comprador.sudo().dcasa_referido_pagado_en = fields.Datetime.now()
        return 'pagado'

    # ------------------------------------------------------------------------
    # Anular
    # ------------------------------------------------------------------------

    def _anular(self, motivo, autor, por_factura=False):
        """Anula la compra: devuelve sus puntos y deshace el referido que disparó.

        Sin deshacer el referido, emitir una venta a un conocido, cobrar el bono y
        anularla sería un fraude repetible; y el sello quedaría puesto, así que la
        primera compra DE VERDAD de esa persona ya no pagaría a nadie.

        Todo lo que el libro tiene de esta compra se contrarresta: los puntos, el referido y también lo que una
        devolución parcial ya había descontado; si no, el socio quedaría con puntos de menos. ``por_factura``: la
        factura misma se deshizo (borrador, cancelada, eliminada) y no una devolución ni una decisión a mano.
        """
        motivo = (motivo or '').strip()
        if not motivo:
            raise UserError(self.env._('Escribe por qué se anula: el socio lo va a leer en su cuenta.'))
        Movimiento = self.env['dcasa.movimiento'].sudo()
        for compra in self.sudo():
            if compra.anulada_en:
                raise UserError(self.env._('La compra %s ya estaba anulada.', compra.name))
            compra.write({'anulada_en': fields.Datetime.now(), 'anulada_por': autor, 'anulada_motivo': motivo,
                          'anulada_por_factura': por_factura})
            asientos = Movimiento.search([
                ('compra_id', '=', compra.id), ('tipo', 'in', ('compra', 'referido', 'ajuste')),
            ])
            ya_reversados = Movimiento.search([('reversa_id', 'in', asientos.ids)]).reversa_id
            for asiento in asientos - ya_reversados:
                if asiento.tipo == 'compra':
                    texto = motivo
                elif asiento.tipo == 'ajuste':
                    texto = f'Se anuló la compra: se deshace lo que se había descontado por la devolución. {motivo}'
                else:
                    texto = f'Se anuló la compra que lo generó: {motivo}'
                asiento._reversar(texto, autor)
            if asientos.filtered(lambda a: a.tipo == 'referido'):
                # Se suelta el sello para que la primera compra de verdad sí pague.
                compra.partner_id.dcasa_referido_pagado_en = False
        return True

    def action_anular(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Anular compra'),
            'res_model': 'dcasa.anular.compra.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_compra_id': self.id},
        }

    def _devolucion_parcial(self, nota_credito, autor):
        """Una nota de crédito parcial descuenta la parte proporcional de los puntos."""
        self.ensure_one()
        devuelto = R.a_centavos(abs(nota_credito.amount_total_signed))
        puntos = -(self.puntos * devuelto // self.monto_centavos)
        if puntos:
            self.env['dcasa.movimiento']._asentar(
                self.partner_id, 'ajuste', puntos, autor, compra_id=self.id,
                motivo=f'Devolución parcial ({nota_credito.name}) de la compra {self.name}')
