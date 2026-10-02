"""Cierre de sesión ABSOLUTO desde el inicio de sesión (``lock_timeout`` de auth_timeout).

auth_timeout de Odoo compara ``lock_timeout`` con ``session['create_time']``, pero Odoo rota la
sesión cada 3 h (``SESSION_ROTATION_INTERVAL``) y la rotación pone ``create_time`` en cero: quien
usa el panel sin parar nunca llegaría a las 12 h. Aquí se cuenta desde el inicio de sesión real
(``session['dcasa_inicio']``, que la rotación conserva) y se usa el mismo valor del grupo, así que
se configura en un solo lugar (Ajustes › Grupos › Administración / Ajustes, o
``DCASA_SESION_ADMIN_HORAS``).

Vencida, la sesión se cierra ANTES de autenticar la ruta: así también lo nota ``/odoo`` (que es
``auth='none'``) y el cliente web no queda en un bucle de «sesión vencida».
"""
import logging
import time

from odoo import models
from odoo.http import request, root

_logger = logging.getLogger(__name__)

INICIO = 'dcasa_inicio'


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _authenticate(cls, endpoint):
        sesion = request.session
        if sesion.uid is not None and cls._dcasa_sesion_vencida(sesion):
            _logger.info('Seguridad: sesión del usuario %s vencida (tope desde el inicio de sesión)', sesion.uid)
            sesion.logout(keep_db=True)
            root.session_store.save(sesion)
        super()._authenticate(endpoint)

    @classmethod
    def _dcasa_sesion_vencida(cls, sesion):
        usuario = request.env(user=sesion.uid).user
        if not usuario.exists():
            return False
        topes = usuario._get_lock_timeouts().get('lock_timeout') or []
        if not topes:
            return False
        inicio = sesion.get(INICIO)
        if not inicio:
            sesion[INICIO] = time.time()  # sesiones de antes de instalar: cuenta desde ahora
            return False
        return time.time() - inicio >= min(segundos for segundos, _mfa in topes)
