"""Consumo del proveedor de IA de Brian: una fila por llamada al modelo.

Sirve para saber cuánto gasta Brian (por persona, canal y modelo) y si la caché de prompts
funciona. Lo escribe solo el sistema (``anotar``, privado, con sudo); el ACL es de solo lectura
y solo para administradores, así que por RPC nadie lo crea, edita ni borra. Sobrevive al borrado
de la conversación (queda con la conversación en blanco), igual que ``brian.accion``.

Los precios por millón de tokens son de la página oficial de Anthropic (consultada en la ronda 6,
2026-10-02). Un modelo que no está en la tabla no tiene costo estimado: se reportan solo tokens
(nunca se inventa una tarifa).
"""
from odoo import api, fields, models

CANALES = [('chat', 'Chat del panel'), ('telegram', 'Telegram'), ('mcp', 'MCP')]

# USD por millón de tokens: entrada, salida, lectura de caché, escritura de caché (5 min = 1.25 × entrada).
PRECIOS = {
    'claude-sonnet-5-5': {'entrada': 2.00, 'salida': 10.00, 'cache_lectura': 0.20, 'cache_escritura': 2.50},
    'claude-haiku-4-5': {'entrada': 1.00, 'salida': 5.00, 'cache_lectura': 0.10, 'cache_escritura': 1.25},
}


def costo_estimado(modelo, entrada, salida, cache_lectura, cache_escritura):
    """USD estimados, o ``None`` si el modelo no está en ``PRECIOS``."""
    precio = PRECIOS.get((modelo or '').strip().lower())
    if not precio:
        return None
    return (entrada * precio['entrada'] + salida * precio['salida'] + cache_lectura * precio['cache_lectura']
            + cache_escritura * precio['cache_escritura']) / 1_000_000


class BrianUso(models.Model):
    _name = 'brian.uso'
    _description = 'Consumo de IA de Brian'
    _order = 'id desc'
    _rec_name = 'modelo'

    usuario_id = fields.Many2one('res.users', related='create_uid', string='Usuario', store=True, index=True)
    conversacion_id = fields.Many2one('brian.conversacion', readonly=True, index=True, ondelete='set null')
    canal = fields.Selection(CANALES, readonly=True)
    proveedor = fields.Char(readonly=True)
    modelo = fields.Char(readonly=True, index=True)
    tokens_entrada = fields.Integer(readonly=True, help='Entrada sin caché (precio completo).')
    tokens_salida = fields.Integer(readonly=True)
    tokens_cache_lectura = fields.Integer('Leídos de caché', readonly=True, help='Cuestan ~10 % de la entrada.')
    tokens_cache_escritura = fields.Integer('Escritos en caché', readonly=True)

    @api.private
    @api.model
    def anotar(self, proveedor, uso, conversacion=None):
        """Anota el consumo de una llamada. Nunca interrumpe la conversación."""
        uso = uso or {}
        valores = {
            'conversacion_id': conversacion.id if conversacion else False,
            'canal': conversacion.canal if conversacion else False,
            'proveedor': (getattr(proveedor, 'config', None) or {}).get('proveedor') or getattr(proveedor, 'tipo', ''),
            'modelo': getattr(proveedor, 'modelo', '') or '',
            'tokens_entrada': int(uso.get('entrada') or 0),
            'tokens_salida': int(uso.get('salida') or 0),
            'tokens_cache_lectura': int(uso.get('cache_lectura') or 0),
            'tokens_cache_escritura': int(uso.get('cache_escritura') or 0),
        }
        # sudo conserva el uid: create_uid queda como la persona que conversa.
        return self.sudo().create(valores).sudo(False)
