"""D3: el recordatorio del abono queda listo como los otros correos (el interruptor general sigue como esté).

Una sola vez, en la base que ya tenía el correo instalado: si nadie lo guardó todavía, se enciende el recordatorio (en
una base nueva lo hace el post_init_hook). No manda nada: sin la clave de Resend, el interruptor general encendido y
DCASA_ENTORNO=produccion no sale ningún correo.

F5: la confirmación del pedido y el carrito abandonado pasan a nombrar los productos en formato título.
"""
from odoo import SUPERUSER_ID, api
from odoo.addons.dcasa_correo.nombres_correo import nombres_en_correos


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ICP = env['ir.config_parameter']
    if not ICP.get_param('dcasa_correo.recordatorio_abono'):
        ICP.set_param('dcasa_correo.recordatorio_abono', 'True')
    nombres_en_correos(env)
