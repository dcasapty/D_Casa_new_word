"""Doble factor obligatorio (configurable), bloqueo progresivo, registro y avisos de acceso.

Todo lo que se agrega a ``res.users`` es privado (``_`` delante): nada nuevo se puede llamar
por RPC (addons/dcasa_base/tests/test_superficie_rpc.py).

Claves de API (Brian por MCP, integraciones): no pasan por ``_login`` ni por el segundo
factor. Con la app enrolada, Odoo deja de aceptar la CLAVE del usuario por RPC
(``_rpc_api_keys_only``) y solo acepta claves de API: es lo que se quiere.
"""
import logging
import threading
import time
from datetime import datetime, timedelta

import pytz

from odoo import SUPERUSER_ID, api, models
from odoo.exceptions import AccessDenied
from odoo.http import request
from odoo.modules.registry import Registry

from .acceso import en_pruebas
from .ir_http import INICIO as INICIO_SESION
from .parametros import ALCANCES, BLOQUEO_TOPE_S, activo, entero, param

_logger = logging.getLogger(__name__)

RUTA_ENROLAR = '/web/login/dcasa-2fa'
MARCA_ESPERA = 'dcasa_seguridad.en_espera'
TZ_PANAMA = pytz.timezone('America/Panama')


def _ip():
    return request.httprequest.environ.get('REMOTE_ADDR', '') if request else ''


def _agente():
    if not request:
        return ''
    ua = request.httprequest.user_agent
    partes = [p for p in ((ua.browser or '').capitalize(), (ua.platform or '').capitalize()) if p]
    return ' en '.join(partes) or (ua.string or '')[:120]


def _enviar_en_hilo(dbname, chats, texto):
    try:
        with Registry(dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            Enlace = env['brian.telegram.enlace']
            for chat in chats:
                Enlace._enviar(chat, texto)
    except Exception:  # noqa: BLE001 — un aviso que falla no debe tumbar nada
        _logger.exception('Seguridad: no pude enviar el aviso por Telegram')


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ------------------------------------------------------------------
    # Doble factor obligatorio
    # ------------------------------------------------------------------

    def _dcasa_2fa_en_alcance(self):
        self.ensure_one()
        alcance = (param(self.env, '2fa_alcance') or 'admins').strip().lower()
        if alcance not in ALCANCES:
            alcance = 'admins'
        if alcance == 'internos':
            return self._is_internal()
        return self._is_system()

    def _dcasa_debe_enrolar(self):
        """¿Debe enrolar la app ANTES de entrar? Solo con la obligatoriedad encendida.

        Una llave de acceso (passkey) no exime: quien entra con CLAVE necesita la app. Quien
        entra con la llave ya no pasa por aquí (Odoo da ese acceso por completo, ``mfa: skip``).
        """
        self.ensure_one()
        return (activo(self.env, '2fa_obligatorio', False)
                and self._dcasa_2fa_en_alcance()
                and not self.sudo().totp_enabled)

    def _mfa_url(self):
        url = super()._mfa_url()
        if url is not None:
            return url
        if self._dcasa_debe_enrolar():
            return RUTA_ENROLAR
        return None

    # ------------------------------------------------------------------
    # Bloqueo progresivo por IP
    # ------------------------------------------------------------------

    def _on_login_cooldown(self, failures, previous):
        """Como Odoo (``base.login_cooldown_after`` fallos → espera), pero la espera se duplica
        con cada fallo nuevo: 1, 2, 4, 8… minutos, hasta ``dcasa_seguridad.bloqueo_tope_s``.

        El contador es por IP (con ``proxy_mode`` y el Worker, la IP real del visitante) y vive
        en memoria del proceso: un reinicio lo pone en cero. Por usuario no se bloquea a
        propósito: cualquiera podría dejar a la dueña fuera escribiendo mal su clave.
        """
        cfg = self.env['ir.config_parameter'].sudo()
        minimo = int(cfg.get_param('base.login_cooldown_after', 5))
        if minimo == 0 or failures < minimo:
            return False
        base = int(cfg.get_param('base.login_cooldown_duration', 60))
        tope = max(base, entero(self.env, 'bloqueo_tope_s', BLOQUEO_TOPE_S))
        espera = min(base * 2 ** min(failures - minimo, 20), tope)
        en_espera = (datetime.now() - previous) < timedelta(seconds=espera)
        if en_espera and request:
            request.httprequest.environ[MARCA_ESPERA] = True
        return en_espera

    # ------------------------------------------------------------------
    # Registro y avisos
    # ------------------------------------------------------------------

    @api.model
    def _login(self, credential, user_agent_env):
        login = credential.get('login') or ''
        try:
            auth_info = super()._login(credential, user_agent_env)
        except AccessDenied:
            self._dcasa_tras_fallo(login, credential.get('type'))
            raise
        self._dcasa_tras_exito(auth_info, credential.get('type'))
        return auth_info

    def _check_credentials(self, credential, env):
        try:
            return super()._check_credentials(credential, env)
        except AccessDenied:
            if request and credential.get('type') in ('totp', 'totp_mail'):
                usuario = self.env.user
                self.env['dcasa.seguridad.acceso']._registrar({
                    'login': usuario.login, 'user_id': usuario.id, 'resultado': 'fallo_2fa',
                    'metodo': credential.get('type'), 'ip': _ip(), 'agente': _agente(),
                    'es_admin': usuario._is_system(),
                }, aparte=True)
            raise

    @api.model
    def _dcasa_tras_fallo(self, login, tipo):
        if not request:
            return
        ip = _ip()
        if request.httprequest.environ.get(MARCA_ESPERA):
            # IP en espera: ni se intentó la clave. Solo log (un ataque no llena la base).
            _logger.info('Seguridad: intento ignorado (IP en espera) para %r desde %s', login, ip)
            return
        usuario = self.sudo().search(self._get_login_domain(login), limit=1) if login else self.browse()
        es_admin = bool(usuario) and usuario._is_system()
        self.env['dcasa.seguridad.acceso']._registrar({
            'login': login, 'user_id': usuario.id or False, 'resultado': 'fallo',
            'metodo': tipo or 'password', 'ip': ip, 'agente': _agente(), 'es_admin': es_admin,
        }, aparte=True)
        if es_admin:
            minimo = int(self.env['ir.config_parameter'].sudo().get_param('base.login_cooldown_after', 5))
            fallos = (getattr(self.env.registry, '_login_failures', None) or {}).get(ip, (0, None))[0]
            if minimo and fallos == minimo:
                self._dcasa_avisar_admins(usuario, (
                    f'⚠️ D’CASA: {fallos} intentos fallidos seguidos de entrar como '
                    f'«{usuario.name}» desde la IP {ip} ({_agente() or "navegador desconocido"}), '
                    f'{self._dcasa_hora()}. Esa IP queda en espera. Si no eras tú, no hace falta hacer '
                    f'nada más: con el doble factor la clave sola no basta.'))

    @api.model
    def _dcasa_tras_exito(self, auth_info, tipo):
        usuario = self.browse(auth_info['uid']).sudo()
        if request:
            # Inicio real de la sesión (la rotación de Odoo lo conserva): models/ir_http.py.
            request.session[INICIO_SESION] = time.time()
        es_admin = usuario._is_system()
        self.env['dcasa.seguridad.acceso']._registrar({
            'login': usuario.login, 'user_id': usuario.id, 'resultado': 'ok',
            'metodo': auth_info.get('auth_method') or tipo or 'password', 'ip': _ip(), 'agente': _agente(),
            'es_admin': es_admin,
        })
        if es_admin and request:
            falta = (' Falta el código de la app: si no eras tú, cambia tu clave ya.'
                     if usuario.totp_enabled and auth_info.get('mfa') != 'skip' else '')
            self._dcasa_avisar_admins(usuario, (
                f'\U0001F510 D’CASA: inicio de sesión de administrador «{usuario.name}» '
                f'({usuario.login}) desde la IP {_ip()} ({_agente() or "navegador desconocido"}), '
                f'{self._dcasa_hora()}.{falta} Si no fuiste tú, avisa y revisa Ajustes › Usuarios › '
                f'Accesos al panel.'))

    @api.model
    def _dcasa_hora(self):
        ahora = pytz.utc.localize(datetime.utcnow()).astimezone(TZ_PANAMA)
        return ahora.strftime('%d/%m/%Y %H:%M') + ' (hora de Panamá)'

    @api.model
    def _dcasa_avisar_admins(self, usuario, texto):
        """Aviso por el Telegram de Brian al usuario y a los demás administradores vinculados."""
        if not activo(self.env, 'aviso_telegram', True) or 'brian.telegram.enlace' not in self.env:
            return
        admins = self.env.ref('base.group_system').sudo().all_user_ids | usuario
        enlaces = self.env['brian.telegram.enlace'].sudo().search([
            ('user_id', 'in', admins.ids), ('activo', '=', True)])
        chats = sorted(set(enlaces.mapped('chat_id')))
        if chats:
            self._dcasa_enviar_aviso(chats, texto)

    @api.model
    def _dcasa_enviar_aviso(self, chats, texto):
        """En un hilo con su propio cursor: el inicio de sesión no espera a Telegram."""
        if en_pruebas(self.env):
            _logger.info('Seguridad (pruebas): aviso a %s chats: %s', len(chats), texto)
            return
        threading.Thread(target=_enviar_en_hilo, args=(self.env.cr.dbname, list(chats), texto),
                         name='dcasa-aviso-acceso', daemon=True).start()
