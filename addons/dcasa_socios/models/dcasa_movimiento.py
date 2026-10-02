from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

TIPOS = [
    ('bienvenida', 'Bienvenida'),
    ('compra', 'Compra'),
    ('referido', 'Referido'),
    ('canje', 'Canje'),
    ('ajuste', 'Ajuste'),
    ('reverso', 'Reverso'),
    ('cumpleanos', 'Cumpleaños'),
    ('vencimiento', 'Vencimiento'),
]


class DcasaMovimiento(models.Model):
    """EL LIBRO MAYOR: la única verdad sobre los puntos de cualquier socio.

    El saldo de un socio es SUM(puntos) de esta tabla y no vive en ningún otro
    sitio: no hay columna de saldo que se pueda despegar del libro que la explica.

    Un asiento es inmutable. Corregir no es editar: es un asiento 'reverso' con la
    cifra contraria, con motivo y autor. El socio lee esa historia en su cuenta.
    """

    _name = 'dcasa.movimiento'
    _description = 'Movimiento de puntos (libro mayor)'
    _order = 'ocurrido_en desc, id desc'
    _rec_name = 'motivo'

    partner_id = fields.Many2one('res.partner', string='Socio', required=True, readonly=True,
                                 index=True, ondelete='restrict')
    # index: el libro se lista y se filtra por fecha (_order, cumpleaños del año); es la tabla que más crece.
    ocurrido_en = fields.Datetime(string='Fecha', required=True, readonly=True, default=fields.Datetime.now,
                                  index=True)
    tipo = fields.Selection(TIPOS, required=True, readonly=True, index=True)
    puntos = fields.Integer(required=True, readonly=True)
    compra_id = fields.Many2one('dcasa.compra', string='Compra', readonly=True, index='btree_not_null',
                                ondelete='restrict')
    canje_id = fields.Many2one('dcasa.canje', string='Canje', readonly=True, index='btree_not_null',
                               ondelete='restrict')
    origen_partner_id = fields.Many2one(
        'res.partner', string='Por la compra de', readonly=True, index='btree_not_null', ondelete='restrict',
        help='En un asiento de referido: quién hizo la compra que lo generó.')
    reversa_id = fields.Many2one('dcasa.movimiento', string='Anula a', readonly=True, ondelete='restrict')
    motivo = fields.Char(readonly=True, help='Se le enseña al socio tal cual.')
    autor = fields.Char(required=True, readonly=True,
                        help="Usuario que lo registró, o 'sistema' / 'socio' para lo automático.")
    vence_en = fields.Datetime(readonly=True)

    _puntos_no_cero = models.Constraint(
        'CHECK(puntos <> 0)', 'Un asiento de cero puntos no dice nada: no se registra.')
    # Un reverso anula UN asiento, y una sola vez.
    _reversa_unica = models.Constraint('UNIQUE(reversa_id)', 'Ese asiento ya fue anulado.')

    @api.constrains('tipo', 'motivo')
    def _check_motivo(self):
        for asiento in self:
            if asiento.tipo in ('ajuste', 'reverso') and not (asiento.motivo or '').strip():
                raise ValidationError(self.env._('Un ajuste o un reverso lleva motivo: el socio lo va a leer.'))

    def write(self, vals):
        raise UserError(self.env._(
            'El libro de puntos no se edita: una corrección es un asiento contrario con motivo.'))

    def unlink(self):
        raise UserError(self.env._(
            'El libro de puntos no se borra: una corrección es un asiento contrario con motivo.'))

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
        """Anula este asiento con otro de la cifra contraria. Devuelve el reverso."""
        self.ensure_one()
        return self._asentar(
            self.partner_id, 'reverso', -self.puntos, autor,
            motivo=motivo, reversa_id=self.id, compra_id=self.compra_id.id, canje_id=self.canje_id.id,
        )

    @api.model
    def _saldos(self, partners):
        """{partner_id: saldo} sumando el libro. Los que no tienen asientos, 0."""
        grupos = self.sudo()._read_group([('partner_id', 'in', partners.ids)], ['partner_id'], ['puntos:sum'])
        saldos = dict.fromkeys(partners.ids, 0)
        saldos.update({partner.id: total for partner, total in grupos})
        return saldos
