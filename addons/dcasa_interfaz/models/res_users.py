from odoo import api, fields, models

# Pedido de la dueña (2026-10-16): «los vendedores no contestan mis chats».
PARAM_AVISOS_EN_ODOO = 'dcasa_interfaz.avisos_en_odoo'


class ResUsers(models.Model):
    _inherit = 'res.users'

    # Usuarios nuevos sin la conversación de bienvenida de OdooBot.
    odoobot_state = fields.Selection(default='disabled')

    def _compute_tour_enabled(self):
        # Sin el recorrido guiado de Odoo (la «gota» con «¿Está listo para impulsar sus
        # ventas?»): D'CASA tiene su propio Inicio.
        self.tour_enabled = False

    @api.model_create_multi
    def create(self, vals_list):
        # Los avisos del equipo llegan EN ODOO, no al correo: Odoo crea a cada usuario con «Notificación: por correo»
        # y los mensajes y las menciones (@) en un pedido o una ficha se iban al correo, sin sumar en el contador del
        # chat. Quien es del equipo (no del portal) queda «En Odoo», salvo que se pida otra cosa al crearlo. (Odoo 19
        # decide por el grupo «inbox» asignado directamente al usuario, no por uno implícito.)
        usuarios = super().create(vals_list)
        sin_eleccion = self.browse([
            usuario.id for usuario, vals in zip(usuarios, vals_list, strict=True) if 'notification_type' not in vals])
        sin_eleccion.filtered(lambda u: not u.share and u.notification_type == 'email').notification_type = 'inbox'
        return usuarios

    @api.model
    def _dcasa_avisos_en_odoo(self):
        """Una sola vez: los usuarios del equipo que ya existían pasan a «En Odoo». Si después alguien elige el correo
        en sus preferencias, una actualización no se lo cambia."""
        parametros = self.env['ir.config_parameter'].sudo()
        if parametros.get_param(PARAM_AVISOS_EN_ODOO):
            return
        self.sudo().search([('share', '=', False), ('notification_type', '=', 'email')]).notification_type = 'inbox'
        parametros.set_param(PARAM_AVISOS_EN_ODOO, '1')
