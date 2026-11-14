"""Revisión adversarial (tercera vuelta, 2026-11-14): la marca ``brian_sin_auditoria`` es solo del chat de la tienda.

FALLABA con 216a2f4: la marca salía del contexto. Ahora ejecutar(..., auditar=False) solo lo pasa la API de Juan.
Datos inventados."""
from odoo.addons.dcasa_brian.models import proveedores
from odoo.tests import tagged

from .common import BrianCase


@tagged('post_install', '-at_install')
class TestRevision3SinAuditoria(BrianCase):

    def test_un_usuario_interno_no_esconde_sus_consultas_poniendo_la_marca_en_el_contexto(self):
        """``registro.ejecutar`` mira la marca en el CONTEXTO. Desde el cliente web, ``call_kw`` pone en el contexto lo
        que mande el navegador (``kwargs.context``): una vendedora que llama ``brian.conversacion.enviar`` con
        ``{"brian_sin_auditoria": true}`` hace que todo lo que Brian consulta por ella no quede en ``brian.accion``."""
        proveedores.fijar_guion([
            {'texto': 'Déjame ver…', 'herramientas': [('prueba_leer', {'texto': 'ficha de Lucía Inventada'})]},
            'Listo.',
        ])
        Conversacion = self.env['brian.conversacion'].with_user(self.usuario)
        conv = Conversacion.browse(Conversacion.nueva('chat')['id'])
        # Lo mismo que hace /web/dataset/call_kw con «context» del navegador.
        resultado = conv.with_context(brian_sin_auditoria=True).enviar('Busca la ficha de Lucía')
        self.assertTrue(resultado['ok'], resultado)
        auditadas = self.env['brian.accion'].sudo().search([('conversacion_id', '=', conv.id)])
        self.assertTrue(auditadas, 'la consulta de la vendedora no quedó en la auditoría')
