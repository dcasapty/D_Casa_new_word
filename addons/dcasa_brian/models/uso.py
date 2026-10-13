"""Consumo del proveedor de IA de Brian: una fila por llamada al modelo.

Sirve para saber cuánto gasta Brian (por persona, canal y modelo) y si la caché de prompts
funciona. Lo escribe solo el sistema (``anotar``, privado, con sudo); el ACL es de solo lectura
y solo para administradores, así que por RPC nadie lo crea, edita ni borra. Sobrevive al borrado
de la conversación (queda con la conversación en blanco), igual que ``brian.accion``.

Los precios por millón de tokens son de la página oficial de Anthropic (consultada en la ronda 6,
2026-10-02). Un modelo que no está en la tabla no tiene costo estimado: se reportan solo tokens
(nunca se inventa una tarifa).
"""
from datetime import datetime
from zoneinfo import ZoneInfo

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


# Un modelo sin tarifa registrada se cuenta con la más cara que conocemos: el tope no queda ciego con un modelo nuevo.
TARIFA_DE_RESERVA = max(PRECIOS.values(), key=lambda precio: precio['entrada'] + precio['salida'])
ZONA = ZoneInfo('America/Panama')

# Topes del gasto de IA de Brian (USD por mes). De fábrica NO hay tope (0): la cifra la pone la dueña en Ajustes › Brian
# (y, más fuerte, el límite del panel de su proveedor de IA). Un valor ilegible tampoco inventa uno: queda en 0.
TOPE_MENSUAL_USD = 0.0
TOPE_POR_PERSONA_USD = 0.0


def costo_para_el_tope(modelo, entrada, salida, cache_lectura, cache_escritura):
    """USD para comparar con el tope: la tarifa del modelo, o la de reserva si no la conocemos."""
    estimado = costo_estimado(modelo, entrada, salida, cache_lectura, cache_escritura)
    if estimado is not None:
        return estimado
    precio = TARIFA_DE_RESERVA
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

    @api.private
    @api.model
    def gasto_del_mes(self, usuario=None):
        """USD estimados que Brian gastó en IA este mes (hora de Panamá), de todos o de ``usuario``."""
        inicio_mes = datetime.now(ZONA).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        desde = fields.Datetime.to_string(inicio_mes.astimezone(ZoneInfo('UTC')).replace(tzinfo=None))
        dominio = [('create_date', '>=', desde)]
        if usuario:
            dominio.append(('usuario_id', '=', usuario.id))
        grupos = self.sudo()._read_group(
            dominio, ['modelo'],
            ['tokens_entrada:sum', 'tokens_salida:sum', 'tokens_cache_lectura:sum', 'tokens_cache_escritura:sum'])
        return sum(costo_para_el_tope(modelo, entrada or 0, salida or 0, cache_l or 0, cache_e or 0)
                   for modelo, entrada, salida, cache_l, cache_e in grupos)

    @api.private
    @api.model
    def topes(self):
        """``(tope mensual de todos, tope mensual por persona)`` en USD; 0 = sin tope."""
        parametros = self.env['ir.config_parameter'].sudo()

        def leer(clave, defecto):
            try:
                return max(0.0, float(parametros.get_param(clave, defecto)))
            except (TypeError, ValueError):
                return defecto

        return (leer('dcasa_brian.tope_mensual_usd', TOPE_MENSUAL_USD),
                leer('dcasa_brian.tope_por_persona_usd', TOPE_POR_PERSONA_USD))
