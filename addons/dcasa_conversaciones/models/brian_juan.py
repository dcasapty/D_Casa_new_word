"""Juan en el registro de Brian: un canal propio en la auditoría y el límite por minuto del usuario técnico.

Las herramientas de Juan se registran en ``brian.herramientas`` con ``grupos=('dcasa_conversaciones.group_juan',)``:
solo las ve y las ejecuta el usuario técnico ``juan`` (sin los grupos internos), y cada ejecución queda
auditada en ``brian.accion`` (herramienta, canal ``juan``, argumentos, resultado, conversación).

* **El PIN nunca se guarda**: ``registrar`` reemplaza los argumentos secretos por ``***`` en la auditoría.
* **Límite por minuto**: el de Brian (30) es por usuario, y ``juan`` es UN usuario para todos los clientes;
  tendría 30 acciones por minuto entre todos. Para él se usa un tope propio (parámetro
  ``dcasa_conversaciones.herramientas_por_minuto``, 240 por defecto).
"""
from odoo import api, fields, models
from odoo.addons.dcasa_brian.models.accion import _CLAVE_SISTEMA

GRUPO_JUAN = 'dcasa_conversaciones.group_juan'
USUARIO_JUAN = 'dcasa_conversaciones.user_juan'
ARGUMENTOS_SECRETOS = ('pin',)
LIMITE_POR_MINUTO_JUAN = 240


class BrianAccion(models.Model):
    _inherit = 'brian.accion'

    canal = fields.Selection(selection_add=[('juan', 'Juan (clientes)')], ondelete={'juan': 'set default'})
    dcasa_conversacion_id = fields.Many2one(
        'dcasa.conversacion', 'Conversación', readonly=True, index='btree_not_null', ondelete='set null',
        help='La conversación con el cliente en la que Juan usó la herramienta.')

    @api.private
    @api.model
    def registrar(self, spec, argumentos, canal='chat', conversacion=None):
        """Auditoría de Juan: canal ``juan``, conversación de Odoo y los secretos tapados."""
        if canal != 'juan':
            return super().registrar(spec, argumentos, canal=canal, conversacion=conversacion)
        tapados = {k: ('***' if k in ARGUMENTOS_SECRETOS else v) for k, v in (argumentos or {}).items()}
        accion = super().registrar(spec, tapados, canal='chat', conversacion=None)
        conversacion_id = self.env.context.get('juan_conversacion_id')
        accion.sudo().with_context(**{_CLAVE_SISTEMA: True}).write({
            'canal': 'juan', 'dcasa_conversacion_id': conversacion_id or False})
        return accion


class BrianHerramientas(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @api.model
    def _disponible(self, spec):
        """El usuario técnico ``juan`` solo ve y ejecuta las herramientas de Juan.

        Brian trae herramientas «generales» sin grupo (``abrir``, ``buscar_en_todo``, ``pantalla_actual``,
        ``ayuda``) que cualquiera ve; para el asistente de clientes no existen. ``ejecutar`` también pasa por aquí.
        """
        usuario = self.env.ref(USUARIO_JUAN, raise_if_not_found=False)
        if usuario and self.env.user == usuario and not spec['nombre'].startswith('juan_'):
            return False
        return super()._disponible(spec)


class BrianPolitica(models.AbstractModel):
    _inherit = 'brian.politica'

    @api.model
    def _limite(self):
        usuario = self.env.ref(USUARIO_JUAN, raise_if_not_found=False)
        if usuario and self.env.user == usuario:
            try:
                valor = int(self.env['ir.config_parameter'].sudo().get_param(
                    'dcasa_conversaciones.herramientas_por_minuto', LIMITE_POR_MINUTO_JUAN))
            except (TypeError, ValueError):
                valor = LIMITE_POR_MINUTO_JUAN
            return max(valor, 1)
        return super()._limite()

