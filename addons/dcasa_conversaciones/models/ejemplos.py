"""Conversaciones de ejemplo para el entorno de PRUEBA (staging): que la pantalla no se vea vacía.

Solo Gerencia y solo donde hay existencias de prueba (``dcasa_catalogo.stock_prueba``): en producción el
botón no existe y el método se niega. Todo es ficticio (nombres con «(ejemplo)», celulares 5076000000X), no
trae precios ni cifras inventadas y no sale por ningún canal: son filas en la base, nada más.
"""
from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.dcasa_catalogo.catalogo import PARAM_STOCK_PRUEBA
from odoo.exceptions import AccessError, UserError

PREFIJO_ID = '5076000000'

# (canal, número, nombre, estado, etiquetas, [(autor, texto)]): lo que dice el cliente y lo que respondería el bot.
EJEMPLOS = [
    ('whatsapp_qr', '1', 'Karen S. (ejemplo)', 'bot', [], [
        ('cliente', 'Hola, buenas tardes. ¿Tienen camas queen?'),
        ('bot', 'Hola, soy Juan de D\'CASA. Sí, tenemos camas queen en varios modelos. '
                '¿La buscas con cabecero tapizado o de metal?'),
        ('cliente', 'Tapizada, de color claro'),
    ]),
    ('telegram', '2', 'Luis P. (ejemplo)', 'humano', ['Socios'], [
        ('cliente', 'Hola, ¿cómo funcionan los puntos del programa de Socios?'),
        ('bot', 'Ganas 1 punto por cada $1 de tu compra, cuando la factura queda pagada. Con 100 puntos '
                'obtienes $1 de descuento y puedes canjear premios que define la tienda. ¿Quieres que una '
                'vendedora te inscriba?'),
        ('cliente', 'Sí, por favor, y quiero ver los premios'),
    ]),
    ('whatsapp_qr', '3', 'Marta R. (ejemplo)', 'bot', ['Pidió precio'], [
        ('cliente', 'Buenas, ¿cuánto cuesta la cama de felpa twin con cabecero curvo?'),
        ('bot', 'Con gusto. Esa cama la tenemos disponible. Los precios van con + ITBMS y el total te lo '
                'confirma una vendedora; la dejo avisada para que te escriba.'),
    ]),
    ('instagram', '4', 'Andrés M. (ejemplo)', 'bot', ['Reclamo'], [
        ('cliente', 'Compré un colchón hace unos días y llegó con un problema'),
        ('bot', 'Lamento eso. Para ayudarte bien, una vendedora revisa tu caso y te escribe. '
                '¿Me compartes tu número de factura?'),
    ]),
]


class JuanAjustesEjemplos(models.Model):
    _inherit = 'dcasa.juan.ajustes'

    es_entorno_de_prueba = fields.Boolean(compute='_compute_es_entorno_de_prueba')

    @api.model
    def _hay_existencias_de_prueba(self):
        valor = (self.env['ir.config_parameter'].sudo().get_param(PARAM_STOCK_PRUEBA) or '').strip().lower()
        return valor not in ('', '0', 'false')

    def _compute_es_entorno_de_prueba(self):
        prueba = self._hay_existencias_de_prueba()
        for registro in self:
            registro.es_entorno_de_prueba = prueba

    def action_cargar_ejemplos(self):
        """Botón «Cargar conversaciones de ejemplo» (solo staging, solo Gerencia, repetible sin duplicar)."""
        if not self.env.su and not self.env.user.has_group('sales_team.group_sale_manager'):
            raise AccessError(self.env._('Solo Gerencia carga los ejemplos.'))
        if not self._hay_existencias_de_prueba():
            raise UserError(self.env._(
                'Los ejemplos solo se cargan en el entorno de prueba, nunca con clientes reales.'))
        creadas = self.env['dcasa.conversacion']._cargar_ejemplos()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': self.env._('Ejemplos listos'), 'type': 'success', 'sticky': False,
                       'message': self.env._('%s conversaciones de ejemplo. Ábrelas en Conversaciones.', creadas)},
        }


class ConversacionEjemplos(models.Model):
    _inherit = 'dcasa.conversacion'

    @api.model
    def _cargar_ejemplos(self):
        """Crea (o completa) las conversaciones de ejemplo. Devuelve cuántas hay. Idempotente."""
        ahora = fields.Datetime.now()
        etiquetas = {e.name: e for e in self.env['dcasa.conversacion.etiqueta'].sudo().search([])}
        for canal, numero, nombre, estado, nombres_etiquetas, mensajes in EJEMPLOS:
            id_externo = PREFIJO_ID + numero
            for orden, (autor, texto) in enumerate(mensajes):
                ts = ahora - timedelta(hours=3, minutes=len(mensajes) * 7 - orden * 7)
                self._registrar_mensaje({
                    'canal': canal, 'id_externo': id_externo, 'id_mensaje': f'ejemplo-{numero}-{orden}',
                    'direccion': 'entrante' if autor == 'cliente' else 'saliente', 'autor': autor, 'texto': texto,
                    'ts': ts, 'nombre': nombre, 'celular': None if canal != 'whatsapp_qr' else id_externo,
                    'adjuntos': [],
                })
            conv = self.sudo().search([('canal', '=', canal), ('id_externo', '=', id_externo)], limit=1)
            valores = {'etiqueta_ids': [(6, 0, [etiquetas[n].id for n in nombres_etiquetas if n in etiquetas])]}
            if estado == 'humano' and not conv.asignada_a:
                valores.update({'estado': 'humano', 'asignada_a': self.env.user.id,
                                'pausada_hasta': ahora + timedelta(hours=2)})
                self.env['dcasa.mensaje'].sudo()._crear_interno(
                    conv, 'nota', 'Ejemplo: quiere ver los premios del programa de Socios.', self.env.user)
            conv.sudo().write(valores)
        return len(EJEMPLOS)
