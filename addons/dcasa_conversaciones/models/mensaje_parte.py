"""Cada burbuja o archivo de un mensaje NUESTRO tal como salió por el canal (pedido de la dueña, 2026-11-07).

Juan parte una respuesta en varias burbujas cortas y Odoo la guarda como UN mensaje; WhatsApp, en cambio, le da un id
(``wamid``) a cada burbuja y a cada foto. Con esta tabla:

* las **palomitas** (enviado, entregado, leído, no llegó) que avisa WhatsApp por cada id se anotan en su parte y el
  mensaje muestra el estado de la más atrasada (``dcasa.mensaje._recalcular_estado_canal``);
* cuando el cliente **cita** una burbuja, se encuentra el mensaje y se muestra justo lo que decía esa burbuja;
* una **reacción** a una burbuja queda en su parte y la burbuja de Odoo muestra la última.

Solo la escribe el sistema (nadie tiene permiso de escritura) y se borra con su mensaje.
"""
from odoo import fields, models

from .mensaje import ESTADOS_CANAL, TIPOS_DE_PARTE


class DcasaMensajeParte(models.Model):
    _name = 'dcasa.mensaje.parte'
    _description = 'Parte de un mensaje tal como salió por el canal'
    _order = 'mensaje_id, indice, id'
    _rec_name = 'id_canal'

    mensaje_id = fields.Many2one('dcasa.mensaje', required=True, ondelete='cascade', readonly=True, index=True)
    conversacion_id = fields.Many2one('dcasa.conversacion', required=True, ondelete='cascade', readonly=True)
    id_canal = fields.Char('Id en el canal', required=True, readonly=True)
    indice = fields.Integer('Orden', readonly=True)
    tipo = fields.Selection(TIPOS_DE_PARTE, default='texto', required=True, readonly=True)
    texto = fields.Char('Lo que decía', readonly=True,
                        help='Las primeras letras de la burbuja (para mostrar una cita).')
    estado_canal = fields.Selection(ESTADOS_CANAL, 'Estado en el canal', readonly=True)
    estado_en = fields.Datetime('Último aviso del canal', readonly=True)
    error = fields.Char('Por qué no llegó', readonly=True)
    reaccion = fields.Char('Reacción del cliente', readonly=True)
    reaccion_en = fields.Datetime('Reaccionó el', readonly=True)

    # Las palomitas y las citas buscan por (conversación, id del canal): con esta restricción es una lectura de
    # índice, y un mismo id nunca se anota dos veces.
    _id_canal_unico = models.Constraint(
        'UNIQUE(conversacion_id, id_canal)', 'Esa parte ya está anotada en la conversación.')
