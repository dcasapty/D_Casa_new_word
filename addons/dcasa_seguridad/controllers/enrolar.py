"""Enrolar la app de códigos AL ENTRAR (solo con ``dcasa_seguridad.2fa_obligatorio`` encendido).

Flujo: /web/login (clave correcta) → la sesión queda a medias (``pre_uid``) → Odoo manda a
``_mfa_url()`` = esta página → la persona escanea el QR, escribe el código de 6 dígitos →
se guarda el secreto, se completa la sesión y entra al panel. Sin código correcto no hay
sesión: el panel nunca se abre sin segundo factor para quien está en el alcance.

Mismas protecciones que /web/login/totp de Odoo: bloqueo por IP (``_assert_can_auth``) y
5 códigos por hora por usuario (``_totp_rate_limit``).
"""
import base64
import io
import logging
import os
import re

import qrcode
import werkzeug.urls

from odoo import http
from odoo.addons.auth_totp.models.totp import ALGORITHM, DIGITS, TIMESTEP, TOTP, TOTP_SECRET_SIZE
from odoo.addons.web.controllers.utils import _get_login_redirect_url
from odoo.exceptions import AccessDenied
from odoo.http import request

from ..models.res_users import RUTA_ENROLAR, _agente, _ip

_logger = logging.getLogger(__name__)

CLAVE_SESION = 'dcasa_2fa_secreto'


def _qr(url):
    datos = io.BytesIO()
    qrcode.make(url.encode(), box_size=5).save(datos, optimise=True, format='PNG')
    return base64.b64encode(datos.getvalue()).decode()


class DcasaEnrolar2FA(http.Controller):

    @http.route(RUTA_ENROLAR, type='http', auth='public', methods=['GET', 'POST'], website=True,
                multilang=False, sitemap=False)
    def dcasa_enrolar_2fa(self, redirect=None, codigo=None, **kwargs):
        if request.session.uid:
            return request.redirect(_get_login_redirect_url(request.session.uid, redirect=redirect))
        pre_uid = request.session.get('pre_uid')
        if not pre_uid:
            return request.redirect('/web/login')
        usuario = request.env['res.users'].browse(pre_uid).sudo()

        if not usuario._dcasa_debe_enrolar():
            # Ya tiene la app (o se apagó la obligatoriedad mientras tanto): el flujo normal.
            url = usuario._mfa_url()
            if url and url != RUTA_ENROLAR:
                return request.redirect(_get_login_redirect_url(pre_uid, redirect=redirect))
            request.session.finalize(request.env)
            request.update_env(user=request.session.uid)
            request.update_context(**request.session.context)
            return request.redirect(_get_login_redirect_url(request.session.uid, redirect=redirect))

        secreto = request.session.get(CLAVE_SESION)
        if not secreto:
            secreto = base64.b32encode(os.urandom(TOTP_SECRET_SIZE // 8)).decode()
            request.session[CLAVE_SESION] = secreto

        error = None
        if request.httprequest.method == 'POST' and codigo:
            try:
                with usuario._assert_can_auth(user=usuario.id):
                    usuario._totp_rate_limit('code_check')
                    coincide = TOTP(base64.b32decode(secreto)).match(int(re.sub(r'\s', '', codigo)))
                    if coincide is None:
                        raise AccessDenied(request.env._(
                            'Ese código no coincide. Revisa que sea el de «D’CASA» en tu app y que la hora '
                            'del teléfono esté en automático.'))
            except AccessDenied as excepcion:
                error = str(excepcion)
                request.env['dcasa.seguridad.acceso']._registrar({
                    'login': usuario.login, 'user_id': usuario.id, 'resultado': 'fallo_2fa',
                    'metodo': 'totp', 'ip': _ip(), 'agente': _agente(), 'es_admin': usuario._is_system(),
                }, aparte=True)
            except ValueError:
                error = request.env._('Escribe solo los 6 números que muestra la app.')
            else:
                usuario.totp_secret = secreto
                usuario.totp_last_counter = coincide
                usuario._totp_rate_limit_purge('code_check')
                request.session.pop(CLAVE_SESION, None)
                request.env.flush_all()
                request.session.finalize(request.env)
                request.update_env(user=request.session.uid)
                request.update_context(**request.session.context)
                request.env['dcasa.seguridad.acceso']._registrar({
                    'login': usuario.login, 'user_id': usuario.id, 'resultado': 'enrolado',
                    'metodo': 'totp', 'ip': _ip(), 'agente': _agente(), 'es_admin': usuario._is_system(),
                })
                _logger.info('Seguridad: %r activó el doble factor al entrar', usuario.login)
                usuario.env['res.users']._dcasa_avisar_admins(usuario, (
                    f'\U0001F510 D’CASA: «{usuario.name}» activó el doble factor (app de códigos) '
                    f'desde la IP {_ip()}, {usuario.env["res.users"]._dcasa_hora()}. Si no fue esa persona, '
                    f'desactívalo en Ajustes › Usuarios y cambia su clave.'))
                return request.redirect(_get_login_redirect_url(request.session.uid, redirect=redirect))

        emisor = "D'CASA"
        url = werkzeug.urls.url_unparse((
            'otpauth', 'totp',
            werkzeug.urls.url_quote(f'{emisor}:{usuario.login}', safe=':'),
            werkzeug.urls.url_encode({
                'secret': secreto, 'issuer': emisor, 'algorithm': ALGORITHM.upper(),
                'digits': DIGITS, 'period': TIMESTEP,
            }), '',
        ))
        respuesta = request.render('dcasa_seguridad.enrolar_2fa', {
            'usuario': usuario,
            'qr': _qr(url),
            'secreto': ' '.join(secreto[i:i + 4] for i in range(0, len(secreto), 4)),
            'error': error,
            'redirect': redirect,
        })
        respuesta.headers['Cache-Control'] = 'no-store'
        return respuesta
