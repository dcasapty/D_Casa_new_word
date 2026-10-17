from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dcasa_whatsapp_number = fields.Char(related='website_id.dcasa_whatsapp_number', readonly=False)
    dcasa_apartado_dias = fields.Integer(
        'Días que se guarda un pedido de la tienda sin cobrar', config_parameter='website_dcasa.apartado_dias',
        default=7, help='Pasado ese plazo sin que el cliente lo reclame, el pedido se anula solo y el inventario '
                        'vuelve a quedar libre. 0 = nunca se anula solo.')

    def _add_missing_default_values(self, values):
        # «Google Merchant Center» (group_gmc_feed, de website_sale) es campo de grupo, así que default_get le da
        # valor, y a la vez related a website_id.enabled_gmc_src. Ese valor por defecto entra después del filtro de
        # create() que descarta lo que no cambió, y el ORM lo escribe en el sitio como el usuario aunque sea el
        # mismo: sin el grupo «Editor y diseñador» (nadie lo tiene, el sitio se edita por código: dcasa_interfaz)
        # ninguna pantalla de Ajustes se podía guardar. Si no cambia, no se escribe; si cambia, sigue igual que en
        # Odoo (y website_sale.set_values lo copia a todos los sitios).
        res = super()._add_missing_default_values(values)
        if 'group_gmc_feed' not in values and 'group_gmc_feed' in res:
            sitio = self.env['website'].browse(res.get('website_id'))
            if bool(res['group_gmc_feed']) == bool(sitio.enabled_gmc_src):
                del res['group_gmc_feed']
        return res
