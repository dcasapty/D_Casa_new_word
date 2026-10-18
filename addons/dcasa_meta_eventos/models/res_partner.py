"""Consentimiento B (la persona): «Aceptó que compartamos sus compras con Meta (anuncios)».

Se guarda en la ficha comercial con fecha, origen (web o tienda) y quién lo registró, todo con seguimiento (queda en
el historial). Con él la compra viaja con el correo y el celular cifrados (SHA-256). Sin él, la compra de la tienda no
se reporta.

* La Vendedora lo MARCA desde la casilla de la ficha (después de preguntarle a la persona). La casilla solo aparece
  con «Ventas de la tienda» o «Ventas de la web» encendido (o si la persona ya aceptó, para poder retirarlo): antes
  de publicar la política de privacidad con la sección de Meta no se le pide a nadie.
* Retirarlo es de Gerencia o del propio flujo (``action_dcasa_meta_retirar_consentimiento``): borra la fecha, cancela
  lo que de esa persona aún no salió hacia Meta (pendiente o con error), borra sus datos cifrados y quita la casilla
  del checkout de sus pedidos web sin pagar.
* Al fusionar dos fichas, los tres datos del consentimiento pasan juntos (``partner_merge.py``), nunca mezclados.
* Los tres campos no se escriben por RPC (solo el sistema, desde la casilla o el botón) y no se copian al duplicar.
"""
from odoo import api, fields, models
from odoo.exceptions import AccessError

from .meta_evento import es_gerencia, leer_config

CAMPOS_CONSENTIMIENTO = frozenset({
    'dcasa_meta_consentimiento_fecha', 'dcasa_meta_consentimiento_origen', 'dcasa_meta_consentimiento_usuario_id'})


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dcasa_meta_consentimiento_fecha = fields.Datetime(
        'Meta: aceptó el', readonly=True, copy=False, tracking=True,
        help='Si tiene fecha, la persona aceptó que compartamos sus compras con Meta (anuncios), con su correo y '
             'celular cifrados.')
    dcasa_meta_consentimiento_origen = fields.Selection(
        [('web', 'Sitio web'), ('tienda', 'Tienda')], string='Meta: dónde aceptó', readonly=True, copy=False,
        tracking=True)
    dcasa_meta_consentimiento_usuario_id = fields.Many2one(
        'res.users', 'Meta: lo registró', readonly=True, copy=False, tracking=True, ondelete='set null')
    dcasa_meta_consentimiento = fields.Boolean(
        'Aceptó que compartamos sus compras con Meta (anuncios)',
        compute='_compute_dcasa_meta_consentimiento', inverse='_inverse_dcasa_meta_consentimiento',
        help='Márcalo solo si la persona dijo que sí. Con esto, sus compras pagadas se reportan a Meta con su correo '
             'y celular cifrados, para medir los anuncios. Retirarlo: botón «Retirar consentimiento» (Gerencia).')
    dcasa_meta_casilla_visible = fields.Boolean(compute='_compute_dcasa_meta_casilla_visible')

    @api.depends('commercial_partner_id.dcasa_meta_consentimiento_fecha')
    def _compute_dcasa_meta_consentimiento(self):
        for partner in self:
            ficha = partner.commercial_partner_id.sudo()
            partner.dcasa_meta_consentimiento = bool(ficha.dcasa_meta_consentimiento_fecha)

    @api.depends('commercial_partner_id.dcasa_meta_consentimiento_fecha')
    def _compute_dcasa_meta_casilla_visible(self):
        config = leer_config(self.env)
        encendido = config['capi_tienda'] or config['capi_web']
        for partner in self:
            partner.dcasa_meta_casilla_visible = encendido or bool(
                partner.commercial_partner_id.sudo().dcasa_meta_consentimiento_fecha)

    def _inverse_dcasa_meta_consentimiento(self):
        for partner in self:
            ficha = partner.commercial_partner_id
            tiene = bool(ficha.sudo().dcasa_meta_consentimiento_fecha)
            if partner.dcasa_meta_consentimiento and not tiene:
                ficha._dcasa_meta_registrar_consentimiento('tienda', self.env.user)
            elif not partner.dcasa_meta_consentimiento and tiene:
                ficha._dcasa_meta_retirar_consentimiento()

    def write(self, vals):
        """Los datos del consentimiento solo los escribe el sistema (casilla, botón o checkout), nunca a mano."""
        if CAMPOS_CONSENTIMIENTO.intersection(vals) and not self.env.su:
            raise AccessError(self.env._(
                'El consentimiento para Meta se marca con su casilla y se retira con su botón; no se escribe a mano.'))
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(CAMPOS_CONSENTIMIENTO.intersection(vals) for vals in vals_list):
            raise AccessError(self.env._('El consentimiento para Meta no se escribe a mano.'))
        return super().create(vals_list)

    def _dcasa_meta_registrar_consentimiento(self, origen, usuario=None):
        """Anota el consentimiento B en la ficha comercial (con quién y cuándo). Exige poder escribir la ficha."""
        if not self.env.su:
            self.check_access('write')
        fichas = self.commercial_partner_id
        usuario = usuario if usuario and not usuario._is_public() else self.env['res.users']
        fichas.sudo().filtered(lambda f: not f.dcasa_meta_consentimiento_fecha).write({
            'dcasa_meta_consentimiento_fecha': fields.Datetime.now(),
            'dcasa_meta_consentimiento_origen': origen,
            'dcasa_meta_consentimiento_usuario_id': usuario.id or False,
        })
        return fichas

    def _dcasa_meta_retirar_consentimiento(self, limpiar_navegador=True):
        """Retira el consentimiento B: solo Gerencia o un administrador (o el sistema, desde un flujo propio).

        Lo que aún no salió de esa persona no sale NUNCA: se cancela lo pendiente y también lo que quedó «con error»
        (si no, «Reintentar ahora» lo mandaría), se borran los datos cifrados de todas sus filas (también de lo ya
        enviado) y se quita la casilla del checkout de sus pedidos web todavía sin pagar (si no, el pago los
        reportaría con su correo y su celular). Con ``limpiar_navegador`` (el botón de Gerencia) también se borran
        los datos del navegador tomados en esos pedidos; la casilla del checkout que se desmarca no los toca (son
        del aviso de cookies, que es otro consentimiento).
        """
        if not es_gerencia(self.env):
            raise AccessError(self.env._(
                'Retirar el consentimiento para Meta lo hace Gerencia (la persona puede pedirlo en la tienda o '
                'escribiendo a info@dcasapty.com).'))
        fichas = self.commercial_partner_id
        fichas.sudo().write(dict.fromkeys(CAMPOS_CONSENTIMIENTO, False))
        Evento = self.env['dcasa.meta.evento'].sudo()
        filas = Evento.search([('move_id.commercial_partner_id', 'in', fichas.ids)])
        filas.filtered(lambda fila: fila.estado in ('pendiente', 'error')).write({
            'estado': 'cancelado', 'proximo_intento': False,
            'motivo': self.env._('La persona retiró su consentimiento')})
        filas.filtered('datos').write({'datos': False})
        Pedido = self.env['sale.order'].sudo()
        casillas = Pedido.search([('partner_id', 'child_of', fichas.ids),
                                  ('dcasa_meta_consentimiento_compra', '!=', False)])
        casillas.write({'dcasa_meta_consentimiento_compra': False})
        if limpiar_navegador:
            Pedido.search([('partner_id', 'child_of', fichas.ids),
                           ('dcasa_meta_consentimiento_navegador', '!=', False)])._dcasa_meta_limpiar_navegador()
        return fichas

    def action_dcasa_meta_retirar_consentimiento(self):
        """Botón de la ficha. Exige Gerencia o administrador en el servidor ANTES de cualquier sudo."""
        self._dcasa_meta_retirar_consentimiento()
        return True
