"""Los avisos de la entrega para Brian (el asistente del equipo, también por MCP): lo mismo que los botones de la venta
(models/avisos.py).

* ``pedir_ubicacion_al_cliente``: que la clienta marque su casa en el mapa. Si el asistente puede escribirle por el
  chat, se lo escribe; si no, devuelve el enlace de WhatsApp para que la persona lo mande.
* ``avisar_que_sale_hoy``: «🚚 ¡Hoy le llega su pedido! ¿Habrá alguien en casa?». Una vez por venta y por día.

Devuelven qué pasó, nunca las coordenadas (el resultado queda en la auditoría de Brian).
"""
from odoo import models
from odoo.addons.dcasa_brian.models.registro import BrianError, herramienta

VENDEDORA = ('sales_team.group_sale_salesman',)
PARAM_VENTA = {'type': 'string', 'description': 'El número de la venta (p. ej. S00042).'}


class BrianHerramientasAvisos(models.AbstractModel):
    _inherit = 'brian.herramientas'

    def _aviso_venta(self, venta):
        """La venta (con los permisos de quien pregunta) que va a domicilio, lista para escribirle a la clienta."""
        orden = self._ubic_venta(venta)
        orden.check_access('write')
        if orden.state == 'cancel':
            raise BrianError(f'{orden.name} está cancelada: no se le escribe a la clienta.')
        if not orden._dcasa_va_a_domicilio():
            raise BrianError(f'{orden.name} no va a domicilio: no hace falta.')
        return orden

    @herramienta(
        nombre='pedir_ubicacion_al_cliente',
        descripcion='Le pide al cliente de una venta a domicilio que marque su casa en el mapa. Si el asistente puede '
                    'escribirle por el chat, se lo manda solo; si no, devuelve el enlace de WhatsApp para mandarlo.',
        parametros={'venta': PARAM_VENTA}, requeridos=['venta'],
        nivel='construccion', categoria='ventas', grupos=VENDEDORA,
        ejemplos=['«pídele la ubicación a la clienta de S00042» → pedir_ubicacion_al_cliente(venta=S00042)'],
        privado=True,
    )
    def _brian_pedir_ubicacion_al_cliente(self, venta):
        orden = self._aviso_venta(venta)
        cliente = orden.partner_id.display_name
        destino = orden._dcasa_destino()
        if destino._dcasa_ubic_confiable():
            return {'venta': orden.name, 'cliente': cliente, 'hecho': 'no_hace_falta',
                    'mensaje': f'{cliente} ya tiene su casa marcada en el mapa ({destino.dcasa_ubic_zona or "sin zona"}'
                               '). No hace falta pedírsela.'}
        resultado = orden._dcasa_pedir_ubicacion()
        if resultado['como'] == 'chat':
            return {'venta': orden.name, 'cliente': cliente, 'hecho': 'enviado_por_el_chat',
                    'canal': resultado['canal'],
                    'mensaje': f'Le escribí a {cliente} por el chat ({resultado["canal"]}); sale en un momento. Cuando '
                               'marque su casa, queda en su ficha y en la venta.'}
        if resultado['como'] == 'sin_celular':
            raise BrianError(f'No le puedo escribir por el chat ({resultado["motivo"]}) y {cliente} no tiene un '
                             'celular anotado. Escríbelo en el contacto y vuelve a pedírmelo.')
        return {'venta': orden.name, 'cliente': cliente, 'hecho': 'enlace_whatsapp',
                'mensaje': f'El asistente no le puede escribir ahora ({resultado["motivo"]}). Abre el enlace para '
                           'mandárselo por WhatsApp: el mensaje ya va escrito, con su enlace para marcar la casa.',
                'enlace': resultado['url_whatsapp'],
                'abrir': {'url': resultado['url_whatsapp'], 'titulo': '📲 Pedir ubicación por WhatsApp'}}

    @herramienta(
        nombre='avisar_que_sale_hoy',
        descripcion='Le avisa al cliente que su pedido a domicilio sale hoy y le pregunta si habrá alguien en casa. '
                    'Por el chat si el asistente puede escribirle; si no, devuelve el enlace de WhatsApp.',
        parametros={'venta': PARAM_VENTA}, requeridos=['venta'],
        nivel='construccion', categoria='ventas', grupos=VENDEDORA,
        ejemplos=['«avísale a la de S00042 que hoy le llega» → avisar_que_sale_hoy(venta=S00042)'],
        privado=True,
    )
    def _brian_avisar_que_sale_hoy(self, venta):
        orden = self._aviso_venta(venta)
        cliente = orden.partner_id.display_name
        resultado = orden._dcasa_avisar_sale_hoy()
        estado = resultado['estado']
        if estado == 'no_confirmada':
            raise BrianError(f'{orden.name} todavía no está confirmada: confírmala antes de avisar que sale.')
        if estado == 'ya_avisada':
            return {'venta': orden.name, 'cliente': cliente, 'hecho': 'ya_avisada',
                    'mensaje': f'A {cliente} ya se le avisó hoy por el chat que sale {orden.name}: no se le manda otra '
                               'vez.'}
        if estado == 'chat':
            return {'venta': orden.name, 'cliente': cliente, 'hecho': 'enviado_por_el_chat',
                    'canal': resultado['canal'],
                    'mensaje': f'Le escribí a {cliente} por el chat ({resultado["canal"]}) que hoy sale {orden.name}. '
                               'Si contesta que no habrá nadie o quiere cambiar el día, el asistente la pasa a una '
                               'vendedora.'}
        if estado == 'sin_celular':
            raise BrianError(f'No le puedo escribir por el chat ({resultado["motivo"]}) y {cliente} no tiene un '
                             'celular anotado. Escríbelo en el contacto y vuelve a pedírmelo.')
        return {'venta': orden.name, 'cliente': cliente, 'hecho': 'enlace_whatsapp',
                'mensaje': f'El asistente no le puede escribir ahora ({resultado["motivo"]}). Abre el enlace para '
                           'avisarle por WhatsApp: el mensaje ya va escrito.',
                'enlace': resultado['url_whatsapp'],
                'abrir': {'url': resultado['url_whatsapp'], 'titulo': '🚚 Avisar por WhatsApp'}}
