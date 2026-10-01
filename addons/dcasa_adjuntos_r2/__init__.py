from . import r2
from . import models


def _dcasa_adjuntos_r2_uninstall(env):
    """Antes de desinstalar, el contenido vuelve a la base: sin el módulo nadie sabe leer r2://."""
    Adjunto = env['ir.attachment'].sudo()
    env['ir.config_parameter'].sudo().set_param('ir_attachment.location', 'db')
    env.cr.execute("SELECT count(*) FROM ir_attachment WHERE store_fname LIKE %s", [r2.ESQUEMA + '%'])
    if env.cr.fetchone()[0]:
        Adjunto._dcasa_r2_migrar_todo('db', confirmar=False, estricto=True)
