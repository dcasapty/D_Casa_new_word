from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

TIPOS_VEND = [
    ('comision', 'Comisión'),
    ('patrocinio', 'Patrocinio'),
    ('canje', 'Canje'),
    ('ajuste', 'Ajuste'),
    ('reverso', 'Reverso'),
]


class DcasaVendMovimiento(models.Model):
    """EL LIBRO MAYOR DE LOS VENDEDORES: la única verdad sobre sus puntos.

    Mismas reglas que el libro de Socios (``dcasa.movimiento``), en otra bolsa: los puntos que un vendedor gana por
    traer ventas no se mezclan con los que gana como cliente. El saldo es SUM(puntos) y no vive en ningún otro sitio;
    un asiento no se edita ni se borra: se corrige con un 'reverso' de la cifra contraria, con motivo y autor.

    Los puntos de una venta esperan unos días (``vendedores.retencion.dias``) por si el cliente devuelve: hasta
    ``disponible_desde`` cuentan en el saldo pero no se pueden canjear.
    """

    _name = 'dcasa.vend.movimiento'
    _description = 'Movimiento de puntos de vendedor (libro mayor)'
    _order = 'ocurrido_en desc, id desc'
    _rec_name = 'motivo'

    partner_id = fields.Many2one('res.partner', string='Vendedor', required=True, readonly=True,
                                 index=True, ondelete='restrict')
    ocurrido_en = fields.Datetime(string='Fecha', required=True, readonly=True, default=fields.Datetime.now,
                                  index=True)
    tipo = fields.Selection(TIPOS_VEND, required=True, readonly=True, index=True)
    puntos = fields.Integer(required=True, readonly=True)
    comision_id = fields.Many2one('dcasa.vend.comision', string='Comisión', readonly=True,
                                  index='btree_not_null', ondelete='restrict')
    canje_id = fields.Many2one('dcasa.vend.canje', string='Canje', readonly=True, index='btree_not_null',
                               ondelete='restrict')
    origen_partner_id = fields.Many2one(
        'res.partner', string='Por la venta de', readonly=True, index='btree_not_null', ondelete='restrict',
        help='En una comisión: el cliente que compró. En un patrocinio: el vendedor directo que vendió.')
    reversa_id = fields.Many2one('dcasa.vend.movimiento', string='Anula a', readonly=True, ondelete='restrict')
    motivo = fields.Char(readonly=True, help='Se le enseña al vendedor tal cual.')
    autor = fields.Char(required=True, readonly=True,
                        help="Usuario que lo registró, o 'sistema' / 'vendedor' para lo automático.")
    disponible_desde = fields.Datetime(
        required=True, readonly=True, default=fields.Datetime.now, index=True,
        help='Desde cuándo se pueden gastar estos puntos (ventana de devoluciones).')

    _puntos_no_cero = models.Constraint(
        'CHECK(puntos <> 0)', 'Un asiento de cero puntos no dice nada: no se registra.')
    _reversa_unica = models.Constraint('UNIQUE(reversa_id)', 'Ese asiento ya fue anulado.')

    @api.constrains('tipo', 'motivo')
    def _check_motivo(self):
        for asiento in self:
            if asiento.tipo in ('ajuste', 'reverso') and not (asiento.motivo or '').strip():
                raise ValidationError(self.env._('Un ajuste o un reverso lleva motivo: el vendedor lo va a leer.'))

    def write(self, vals):
        raise UserError(self.env._(
            'El libro de puntos de vendedores no se edita: una corrección es un asiento contrario con motivo.'))

    def unlink(self):
        raise UserError(self.env._(
            'El libro de puntos de vendedores no se borra: una corrección es un asiento contrario con motivo.'))

    @api.model
    def _asentar(self, partner, tipo, puntos, autor, **extra):
        """Escribe un asiento. Único camino de entrada al libro."""
        return self.sudo().create({
            'partner_id': partner.id,
            'tipo': tipo,
            'puntos': puntos,
            'autor': autor,
            **extra,
        })

    def _reversar(self, motivo, autor):
        """Anula este asiento con otro de la cifra contraria. El reverso se libera a la vez que el original, para
        que el saldo disponible nunca baje dos veces por la misma devolución."""
        self.ensure_one()
        return self._asentar(
            self.partner_id, 'reverso', -self.puntos, autor, motivo=motivo, reversa_id=self.id,
            comision_id=self.comision_id.id, canje_id=self.canje_id.id, disponible_desde=self.disponible_desde,
        )

    @api.model
    def _saldos(self, partners):
        """{partner_id: saldo total} sumando el libro. Los que no tienen asientos, 0."""
        grupos = self.sudo()._read_group([('partner_id', 'in', partners.ids)], ['partner_id'], ['puntos:sum'])
        saldos = dict.fromkeys(partners.ids, 0)
        saldos.update({partner.id: total for partner, total in grupos})
        return saldos

    @api.model
    def _saldos_disponibles(self, partners, ahora=None):
        """{partner_id: puntos que ya se pueden gastar} (los que ya pasaron su ventana de devoluciones)."""
        ahora = ahora or fields.Datetime.now()
        grupos = self.sudo()._read_group(
            [('partner_id', 'in', partners.ids), ('disponible_desde', '<=', ahora)], ['partner_id'], ['puntos:sum'])
        saldos = dict.fromkeys(partners.ids, 0)
        saldos.update({partner.id: total for partner, total in grupos})
        return saldos
