"""La ficha del cliente de las conversaciones es el ``res.partner`` de siempre.

Cliente y socio son la misma ficha y el celular es su llave (docs/SOCIOS.md). Aquí solo se agrega:

* encontrar-o-crear la ficha de quien escribe por un canal SIN duplicar (``_dcasa_conv_ficha``);
* «No contactar»: la persona pidió que no le escriban (frena el seguimiento);
* el acceso a sus conversaciones.
"""
from odoo import api, fields, models

from . import celulares
from .ajustes import CANALES, CANALES_CON_CELULAR

ETIQUETA_CANAL = dict(CANALES)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dcasa_conversacion_ids = fields.One2many('dcasa.conversacion', 'partner_id', string='Conversaciones')
    dcasa_conversaciones_count = fields.Integer(
        'Cantidad de conversaciones', compute='_compute_dcasa_conversaciones_count')
    dcasa_no_contactar = fields.Boolean(
        'No contactar', copy=False, tracking=True,
        help='Pidió que no le escribamos más: no se le hace ningún seguimiento automático.')

    def _compute_dcasa_conversaciones_count(self):
        datos = dict(self.env['dcasa.conversacion'].sudo()._read_group(
            [('partner_id', 'in', self.ids)], ['partner_id'], ['__count']))
        for partner in self:
            partner.dcasa_conversaciones_count = datos.get(partner, 0)

    def action_dcasa_ver_conversaciones(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Conversaciones de %s', self.display_name),
            'res_model': 'dcasa.conversacion',
            'view_mode': 'kanban,list,form',
            'domain': [('partner_id', '=', self.id)],
        }

    # ------------------------------------------------------------------
    # La ficha de quien escribe por un canal
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_conv_buscar(self, celular):
        """La ficha que ya tiene ese celular, o vacío. Nunca crea.

        Un celular de Panamá se busca por la llave del programa (``dcasa_celular``) y, si no, por el
        teléfono de la ficha; uno de otro país, por su teléfono completo. Con ``active_test=False``:
        una ficha archivada también ocupa el celular (no se duplica).
        """
        tipo, valor = celulares.interpretar(celular)
        Partner = self.sudo().with_context(active_test=False)
        if tipo == 'pa':
            ficha = Partner.search([('dcasa_celular', '=', valor)], limit=1)
            return ficha or Partner.search([('dcasa_telefono_digitos', '=', valor)], order='id', limit=1)
        if tipo == 'intl':
            return Partner.search([('phone', 'in', [f'+{valor}', valor])], order='id', limit=1)
        return Partner

    @api.model
    def _dcasa_conv_nombre_provisional(self, canal, id_externo, celular=None):
        tipo, valor = celulares.interpretar(celular or (id_externo if canal in CANALES_CON_CELULAR else ''))
        if tipo:
            return f'{ETIQUETA_CANAL.get(canal, canal)} {celulares.para_mostrar(tipo, valor)}'
        return f'{ETIQUETA_CANAL.get(canal, canal)} {id_externo}'

    @api.model
    def _dcasa_conv_ficha(self, canal, id_externo, nombre=None, celular=None):
        """La ficha de quien escribe: la que ya tiene su celular o una nueva. Nunca duplica.

        ``celular`` es opcional; en WhatsApp el id externo es el celular. Para Telegram, Messenger e
        Instagram sin celular se crea una ficha provisional con el nombre que dé el canal.
        """
        candidato = celular or (id_externo if canal in CANALES_CON_CELULAR else '')
        tipo, valor = celulares.interpretar(candidato)
        ficha = self._dcasa_conv_buscar(candidato) if tipo else self.browse()
        if ficha:
            return ficha
        valores = {
            'name': (nombre or '').strip() or self._dcasa_conv_nombre_provisional(canal, id_externo, celular),
            'dcasa_creado_por': 'juan',
        }
        if tipo:
            valores['phone'] = celulares.para_mostrar(tipo, valor)
        return self.sudo().with_context(
            mail_create_nolog=True, mail_create_nosubscribe=True, tracking_disable=True).create(valores)

    @api.model
    def _dcasa_conv_celular_de_ficha(self, ficha):
        """El celular de la ficha como ``(tipo, valor)`` para compararlo con el de la conversación."""
        ficha = ficha.sudo()
        return celulares.interpretar(ficha.dcasa_celular or ficha.phone or '')

    def _dcasa_conv_ya_compro(self, desde):
        """¿Tiene alguna factura de cliente pagada con fecha de ``desde`` (una fecha) en adelante?

        «Pagada» como en Socios: ``paid`` o ``in_payment``. Es la regla del seguimiento: quien ya
        compró después de empezar la conversación no recibe seguimiento.
        """
        self.ensure_one()
        return bool(self.env['account.move'].sudo().search_count([
            ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
            ('payment_state', 'in', ('paid', 'in_payment')),
            ('commercial_partner_id', '=', self.commercial_partner_id.id),
            ('invoice_date', '>=', desde),
        ], limit=1))
