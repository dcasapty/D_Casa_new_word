from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def color_scheme(self):
        """El modo oscuro del panel lo elige cada persona en su navegador (menú de usuario › «Modo oscuro»).

        Odoo Community trae el andamio (la hoja ``web.assets_web_dark``) pero contesta siempre «light». Aquí manda la
        cookie ``color_scheme``: solo el valor exacto ``dark`` enciende el modo oscuro; sin cookie o con cualquier
        otro valor, el panel sale claro, como siempre.
        """
        if request and request.httprequest.cookies.get('color_scheme') == 'dark':
            return 'dark'
        return super().color_scheme()
