"""Las notas de voz de Brian del panel pasan a texto en el Worker de Juan (``dcasa_brian/models/voz.py``).

``POST /odoo/voz`` (``juan/src/odoo-panel-voz.ts``) con ``Authorization: Bearer <JUAN_WORKER_TOKEN>``, el mismo token
de siempre (``_pedir`` de ``cliente_worker_panel.py``: nunca escribe el token ni el cuerpo en un registro). El Worker
cuenta los topes (por persona, por día y el techo del mes), anota el gasto en «Costos de IA» en su propio renglón de
Cloudflare («Cloudflare: notas de voz del panel») y devuelve solo el texto. Odoo manda el id del usuario para el tope
por persona; el Worker lo guarda ofuscado y solo 26 horas.
"""
from odoo import api, models

# El Worker contesta antes de 20 s (PLAZO_VOZ_MS en juan/src/motor/voz.ts), con el texto o un error: Odoo espera más.
TIMEOUT_VOZ = (3.05, 30)


class BrianVozJuan(models.AbstractModel):
    _inherit = 'dcasa.brian.voz'

    @api.model
    def _disponible(self):
        return bool(self.env['dcasa.juan.cliente'].configurado())

    @api.model
    def _pedir_al_worker(self, audio, mime, duracion_ms):
        Cliente = self.env['dcasa.juan.cliente']
        if not Cliente.configurado():
            return {'ok': False, 'causa': 'no_disponible'}
        datos = {'mime': mime, 'base64': audio, 'usuario': self.env.uid}
        if duracion_ms is not None:
            datos['duracion_ms'] = duracion_ms
        respuesta = Cliente._pedir('POST', '/odoo/voz', datos, timeout=TIMEOUT_VOZ)
        cuerpo = respuesta['cuerpo']
        if respuesta['sin_configurar']:
            return {'ok': False, 'causa': 'no_disponible'}
        if not respuesta['conectado']:
            return {'ok': False, 'causa': 'tardo' if respuesta['causa'] == 'tardo' else 'fallo'}
        if respuesta['error'] or cuerpo.get('ok') is not True:
            return {'ok': False, 'causa': str(cuerpo.get('causa') or 'fallo')[:40]}
        return {'ok': True, 'texto': cuerpo.get('texto'), 'recortado': bool(cuerpo.get('recortado'))}
