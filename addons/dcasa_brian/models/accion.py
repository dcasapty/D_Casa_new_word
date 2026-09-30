"""Registro de acciones de Brian (auditoría).

Cada herramienta que Brian ejecuta —o intenta ejecutar— deja un registro con el usuario,
el canal, los argumentos, el resultado y el estado. El registro es INMUTABLE para las
personas: nadie lo edita ni lo borra (ni siquiera un administrador desde la interfaz);
solo el sistema cambia el estado mediante ``marcar``.
"""
import json

from odoo import api, fields, models
from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG
from odoo.exceptions import AccessError

MAX_RESULTADO = 20000

ESTADOS = [
    ('pendiente', 'En curso'),
    ('hecha', 'Hecha'),
    ('error', 'Error'),
    ('bloqueada', 'Bloqueada por la política'),
    ('por_confirmar', 'Por confirmar'),
    ('rechazada', 'Rechazada'),
]

CANALES = [('chat', 'Chat del panel'), ('telegram', 'Telegram'), ('mcp', 'MCP')]

_CLAVE_SISTEMA = 'brian_accion_sistema'


def _json(valor, limite=None):
    texto = json.dumps(valor, ensure_ascii=False, default=str)
    if limite and len(texto) > limite:
        texto = texto[:limite] + '… [truncado]'
    return texto


class BrianAccion(models.Model):
    _name = 'brian.accion'
    _description = 'Acción de Brian'
    _order = 'id desc'
    _rec_name = 'herramienta'

    herramienta = fields.Char(required=True, readonly=True, index=True)
    nivel = fields.Selection(
        [('lectura', 'Lectura'), ('construccion', 'Construcción'), ('sensible', 'Sensible')],
        readonly=True)
    categoria = fields.Char(readonly=True)
    canal = fields.Selection(CANALES, default='chat', required=True, readonly=True, index=True)
    argumentos = fields.Text(readonly=True)
    resultado = fields.Text(readonly=True)
    error = fields.Text(readonly=True)
    resumen = fields.Text(readonly=True, help='Lo que se le mostró al usuario para confirmar.')
    estado = fields.Selection(ESTADOS, default='pendiente', required=True, readonly=True, index=True)
    conversacion_id = fields.Many2one('brian.conversacion', readonly=True, index=True, ondelete='set null')
    usuario_id = fields.Many2one('res.users', related='create_uid', string='Usuario', store=True, index=True)
    fecha_cierre = fields.Datetime('Terminó', readonly=True)

    # ------------------------------------------------------------------
    # API del sistema (usada por registro.py)
    # ------------------------------------------------------------------

    @api.model
    def registrar(self, spec, argumentos, canal='chat', conversacion=None):
        """Crea el registro (estado «pendiente») a nombre del usuario actual."""
        if isinstance(conversacion, models.BaseModel):
            conversacion = conversacion.id
        valores = {
            'herramienta': spec['nombre'],
            'nivel': spec.get('nivel'),
            'categoria': spec.get('categoria'),
            'canal': canal if canal in dict(CANALES) else 'chat',
            'argumentos': _json(argumentos or {}),
            'estado': 'pendiente',
            'conversacion_id': conversacion or False,
        }
        # sudo conserva el uid: create_uid queda como el usuario que conversa.
        return self.sudo().with_context(**{_CLAVE_SISTEMA: True}).create(valores).sudo(False)

    def marcar(self, estado, error=None, resultado=None, resumen=None):
        """Cambia el estado de la acción (solo el sistema)."""
        valores = {'estado': estado}
        if error is not None:
            valores['error'] = str(error)[:MAX_RESULTADO]
        if resultado is not None:
            valores['resultado'] = _json(resultado, MAX_RESULTADO)
        if resumen is not None:
            valores['resumen'] = resumen
        if estado in ('hecha', 'error', 'bloqueada', 'rechazada'):
            valores['fecha_cierre'] = fields.Datetime.now()
        self.sudo().with_context(**{_CLAVE_SISTEMA: True}).write(valores)
        return True

    # ------------------------------------------------------------------
    # Inmutabilidad
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get(_CLAVE_SISTEMA):
            raise AccessError(self.env._('El registro de acciones de Brian solo lo escribe el sistema.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get(_CLAVE_SISTEMA):
            raise AccessError(self.env._('El registro de acciones de Brian no se puede editar.'))
        return super().write(vals)

    def unlink(self):
        if self.env.context.get(MODULE_UNINSTALL_FLAG):
            return super().unlink()
        raise AccessError(self.env._('El registro de acciones de Brian no se puede borrar.'))

    # ------------------------------------------------------------------
    # Para la interfaz
    # ------------------------------------------------------------------

    def argumentos_dict(self):
        self.ensure_one()
        try:
            return json.loads(self.argumentos or '{}')
        except ValueError:
            return {}
