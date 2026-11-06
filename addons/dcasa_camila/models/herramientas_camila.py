"""Brian y Camila: «¿cómo van las campañas de correo?», «¿cuántos clientes tienen permiso?», «¿a cuántos les llegaría
la de los quietos?».

Solo lectura y con las mismas cifras de la pantalla Camila (``dcasa.camila``): nada lo calcula la IA. Es de los mismos
grupos que la pantalla (rol Marketing, Gerencia y administradores); el dinero de las ventas que trajo una campaña,
solo para quien ve la ganancia (Gerencia y administradores). Brian no arma ni envía campañas: eso se aprueba en la
pantalla. Desde la etapa 2 puede haber varias campañas abiertas y el tope de 15 días es por cliente.
"""
from odoo import models
from odoo.addons.dcasa_brian.models.registro import herramienta
from odoo.addons.dcasa_marketing.models.marketing import GRUPOS

MAX_CAMPANAS = 10


class BrianHerramientasCamila(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @herramienta(
        nombre='estado_campanas',
        descripcion='Camila (correo de novedades): las campañas abiertas, a cuántos clientes les llegaría cada una '
                    '(una cada 15 días por cliente), cuántos tienen permiso y los resultados de las enviadas.',
        parametros={
            'cuantas': {'type': 'integer', 'description': f'Cuántas campañas enviadas mostrar (1 a {MAX_CAMPANAS}). '
                                                         'Por defecto 3.'},
        },
        nivel='lectura', categoria='clientes', grupos=(GRUPOS,),
        ejemplos=['¿cómo van las campañas de correo? → estado_campanas',
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
        abiertas = []
        for campana in Camila._abiertas()[:MAX_CAMPANAS]:
            datos = Camila.panel(campana.id)['campana']
            publico = datos['publico']
            abiertas.append({
                'nombre': datos['nombre'], 'estado': datos['estado_nombre'], 'asunto': datos['asunto'],
                'a_quien_va': [chip['nombre'] for chip in publico['chips'] if chip['activo']],
                'le_llegaria_a': publico['total'],
                'quedan_fuera': {fuera['texto']: fuera['n'] for fuera in publico['fuera']},
                'productos': [f"{linea['nombre']} ({linea['precio']}{' + ITBMS' if linea['mas_itbms'] else ''})"
                              for linea in datos['lineas']],
                'precios_del': datos['precios_del'],
            })
        return {
            'clientes_con_permiso': panel['con_permiso'],
            'clave_de_resend': 'cargada' if panel['hay_clave'] else 'falta (no se puede enviar)',
            'ultima_campana': panel['ultima'] or 'todavía no ha salido ninguna',
            'tope': f"a cada cliente le llega como mucho un correo de campaña cada {panel['dias']} días",
            'por_que_no_puede_salir_ahora': panel['bloqueos'],
            'campanas_abiertas': abiertas or 'no hay ninguna abierta',
            'resultados': [{
                'campana': fila['nombre'], 'enviada': fila['fecha'], 'enviados': fila['enviados'],
                'chats_que_llegaron': fila['chats'], 'ventas': fila['ventas'], 'ventas_en_la_web': fila['web'],
                **({'monto_sin_itbms': fila['monto']} if fila['monto'] is not None else {}),
                **({'resend': fila['resend']} if fila['resend'] else {}),
            } for fila in panel['historial'][:cuantas]],
            'como_se_cuenta': 'Chats: los que llegaron con la marca de la campaña en su primer mensaje. Ventas: '
                              'facturas pagadas de esos clientes con el chat en los 30 días antes de la factura (como '
                              'las ventas atribuidas de Conversaciones). Aperturas y clics: los que da Resend (las '
                              'aperturas pueden no ser exactas).',
            'donde': 'Marketing › Camila (ahí se revisa, se edita y se aprueba el envío).',
        }
