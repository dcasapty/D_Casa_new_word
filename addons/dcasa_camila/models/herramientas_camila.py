"""Brian y Camila: «¿cómo va la campaña de correo?», «¿cuántos clientes tienen permiso?», «¿cuándo puede salir la
próxima?».

Solo lectura y con las mismas cifras de la pantalla Camila (``dcasa.camila``): nada lo calcula la IA. Es de los mismos
grupos que la pantalla (rol Marketing, Gerencia y administradores); el dinero de las ventas que trajo una campaña,
solo para quien ve la ganancia (Gerencia y administradores). Brian no arma ni envía campañas: eso se aprueba en la
pantalla.
"""
from odoo import models
from odoo.addons.dcasa_brian.models.registro import herramienta
from odoo.addons.dcasa_marketing.models.marketing import GRUPOS

MAX_CAMPANAS = 10


class BrianHerramientasCamila(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @herramienta(
        nombre='estado_campanas',
        descripcion='Camila (correo de novedades): el borrador abierto, a cuántos clientes con permiso le llegaría, '
                    'cuándo puede salir la próxima (una cada 15 días) y los resultados de las últimas campañas.',
        parametros={
            'cuantas': {'type': 'integer', 'description': f'Cuántas campañas enviadas mostrar (1 a {MAX_CAMPANAS}). '
                                                         'Por defecto 3.'},
        },
        nivel='lectura', categoria='clientes', grupos=(GRUPOS,),
        ejemplos=['¿cómo va la campaña de correo? → estado_campanas',
                  '¿cuántos clientes reciben las novedades? → estado_campanas',
                  'resultados de las últimas 5 campañas → cuantas=5'],
    )
    def _h_estado_campanas(self, cuantas=3):
        Camila = self.env['dcasa.camila']
        Camila._exigir()
        try:
            cuantas = max(1, min(int(cuantas or 3), MAX_CAMPANAS))
        except (TypeError, ValueError):
            cuantas = 3
        panel = Camila.panel()
        campana = panel['campana']
        respuesta = {
            'clientes_con_permiso': panel['con_permiso'],
            'clave_de_resend': 'cargada' if panel['hay_clave'] else 'falta (no se puede enviar)',
            'ultima_campana': panel['ultima'] or 'todavía no ha salido ninguna',
            'proxima_puede_salir': 'ya' if panel['proxima']['ya'] else f"desde el {panel['proxima']['fecha']}",
            'por_que_no_puede_salir_ahora': panel['bloqueos'],
            'borrador': {
                'nombre': campana['nombre'], 'estado': campana['estado_nombre'], 'asunto': campana['asunto'],
                'productos': [f"{linea['nombre']} ({linea['precio']}{' + ITBMS' if linea['mas_itbms'] else ''})"
                              for linea in campana['lineas']],
                'precios_del': campana['precios_del'],
            } if campana else 'no hay ninguno abierto',
            'resultados': [{
                'campana': fila['nombre'], 'enviada': fila['fecha'], 'enviados': fila['enviados'],
                'chats_que_llegaron': fila['chats'], 'ventas': fila['ventas'],
                **({'monto_sin_itbms': fila['monto']} if fila['monto'] is not None else {}),
                **({'resend': fila['resend']} if fila['resend'] else {}),
            } for fila in panel['historial'][:cuantas]],
            'como_se_cuenta': 'Chats: los que llegaron con la marca de la campaña en su primer mensaje. Ventas: '
                              'facturas pagadas de esos clientes con el chat en los 30 días antes de la factura (como '
                              'las ventas atribuidas de Conversaciones). Aperturas y clics: los que da Resend (las '
                              'aperturas pueden no ser exactas).',
            'donde': 'Marketing › Camila (ahí se revisa, se edita y se aprueba el envío).',
        }
        return respuesta
