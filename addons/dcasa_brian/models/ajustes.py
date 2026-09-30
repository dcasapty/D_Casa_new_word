"""Ajustes de Brian (Ajustes › Brian). Lo que se deja vacío toma las variables de entorno."""
from odoo import api, fields, models

from .proveedores import PROVEEDORES


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dcasa_brian_proveedor = fields.Selection(
        [(clave, datos['nombre']) for clave, datos in PROVEEDORES.items()],
        string='Proveedor de IA', config_parameter='dcasa_brian.proveedor',
        help='Vacío: usa la variable BRIAN_PROVEEDOR (por defecto Anthropic).')
    dcasa_brian_modelo = fields.Char(
        'Modelo', config_parameter='dcasa_brian.modelo',
        help='Ej.: claude-sonnet-5-5 (por defecto), claude-haiku-4-5, gpt-4o-mini, llama-3.3-70b-versatile. '
             'Vacío: BRIAN_MODELO o el modelo por defecto del proveedor.')
    dcasa_brian_base_url = fields.Char(
        'Dirección del API', config_parameter='dcasa_brian.base_url',
        help='Solo si cambia la dirección por defecto (p. ej. un Ollama propio). Vacío: BRIAN_BASE_URL.')
    dcasa_brian_herramientas_max = fields.Integer(
        'Máximo de herramientas por mensaje', config_parameter='dcasa_brian.herramientas_max',
        help='0: todas con modelos grandes y 12 con modelos pequeños.')
    dcasa_brian_clave_nueva = fields.Char(
        'Clave de API nueva', store=False,
        help='Se guarda solo si escribes una. Si existe BRIAN_API_KEY en el servidor, esa tiene prioridad.')
    dcasa_brian_clave_actual = fields.Char('Clave de API', compute='_compute_dcasa_brian_estado')
    dcasa_brian_estado = fields.Char('Estado de Brian', compute='_compute_dcasa_brian_estado')

    @api.depends('dcasa_brian_proveedor', 'dcasa_brian_modelo')
    def _compute_dcasa_brian_estado(self):
        estado = self.env['brian.proveedores'].sudo().estado()
        for ajustes in self:
            ajustes.dcasa_brian_clave_actual = estado['clave'] or self.env._('(sin clave)')
            ajustes.dcasa_brian_estado = estado['mensaje'] or self.env._(
                'Listo: %(p)s · %(m)s', p=estado['nombre'], m=estado['modelo'])

    def set_values(self):
        super().set_values()
        for ajustes in self:
            if ajustes.dcasa_brian_clave_nueva:
                self.env['ir.config_parameter'].sudo().set_param(
                    'dcasa_brian.api_key', ajustes.dcasa_brian_clave_nueva.strip())

    def action_dcasa_brian_probar(self):
        """Guarda los ajustes y hace una llamada mínima al proveedor."""
        self.ensure_one()
        self.set_values()
        resultado = self.env['brian.proveedores'].sudo().probar()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Brian'),
                'message': resultado['mensaje'],
                'type': 'success' if resultado['ok'] else 'danger',
                'sticky': not resultado['ok'],
            },
        }

    def action_dcasa_brian_borrar_clave(self):
        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian.api_key', False)
        return True
