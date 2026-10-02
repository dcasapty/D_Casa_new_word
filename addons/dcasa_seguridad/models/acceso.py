"""Registro de inicios de sesión al panel (``dcasa.seguridad.acceso``).

Solo lectura para el grupo «Administración / Ajustes»; nadie lo edita ni lo borra a mano
(lo escribe el servidor con sudo). Un cron purga lo que tiene más de 180 días.

Los intentos fallidos se guardan con un cursor aparte: el de la petición puede deshacerse
al rechazar el acceso. Para que un ataque no llene la base, con más de
``TOPE_FALLOS_HORA`` fallos en la última hora se dejan de guardar (siguen en el log).
"""
import logging
from datetime import timedelta

from odoo import api, fields, models, modules

_logger = logging.getLogger(__name__)

TOPE_FALLOS_HORA = 500
DIAS_RETENCION = 180

RESULTADOS = [
    ('ok', 'Correcto'),
    ('fallo', 'Clave incorrecta'),
    ('fallo_2fa', 'Código incorrecto'),
    ('enrolado', 'Activó el doble factor'),
]


def en_pruebas(env):
    """En los tests no se abren cursores ni hilos propios (todo va en la transacción del test)."""
    return bool(modules.module.current_test)


class DcasaSeguridadAcceso(models.Model):
    _name = 'dcasa.seguridad.acceso'
    _description = 'Inicio de sesión al panel'
    _order = 'id desc'
    _rec_name = 'login'
    _log_access = True

    login = fields.Char(string='Usuario escrito', readonly=True, index=True)
    user_id = fields.Many2one('res.users', string='Usuario', readonly=True, ondelete='set null', index=True)
    resultado = fields.Selection(RESULTADOS, readonly=True, required=True, index=True)
    metodo = fields.Char(string='Método', readonly=True,
                         help='password = clave, totp = app de códigos, webauthn = llave de acceso')
    ip = fields.Char(string='IP', readonly=True, index=True)
    agente = fields.Char(string='Navegador', readonly=True)
    es_admin = fields.Boolean(string='Administrador', readonly=True, index=True)

    @api.model
    def _registrar(self, valores, aparte=False):
        """Guarda una fila. ``aparte``: en un cursor propio (para fallos que deshacen la petición)."""
        if aparte and not en_pruebas(self.env):
            try:
                with self.env.registry.cursor() as cr:
                    self.env(cr=cr, su=True)[self._name]._crear(valores)
            except Exception:  # noqa: BLE001 — registrar nunca debe romper el acceso
                _logger.exception('Seguridad: no pude registrar el intento de acceso')
            return self.browse()
        return self.sudo()._crear(valores)

    @api.model
    def _crear(self, valores):
        if valores.get('resultado') != 'ok':
            hace_una_hora = fields.Datetime.now() - timedelta(hours=1)
            recientes = self.search_count([('create_date', '>=', hace_una_hora), ('resultado', '!=', 'ok')])
            if recientes >= TOPE_FALLOS_HORA:
                _logger.warning('Seguridad: más de %s fallos en una hora; no se guardan más (sí en el log).',
                                TOPE_FALLOS_HORA)
                return self.browse()
        valores = dict(valores)
        for campo in ('login', 'agente', 'metodo'):
            if valores.get(campo):
                valores[campo] = str(valores[campo])[:256]
        return self.create(valores)

    @api.model
    def _purgar(self):
        limite = fields.Datetime.now() - timedelta(days=DIAS_RETENCION)
        viejos = self.sudo().search([('create_date', '<', limite)])
        cantidad = len(viejos)
        viejos.unlink()
        _logger.info('Seguridad: purgados %s registros de acceso de más de %s días', cantidad, DIAS_RETENCION)
        return cantidad
