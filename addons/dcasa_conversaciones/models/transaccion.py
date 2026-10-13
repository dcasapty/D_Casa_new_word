"""Confirmar la transacción antes (y después) de llamar al Worker de Juan.

Odoo llama al Worker de forma síncrona, dentro de la petición, y el Worker (o el puente de WhatsApp, que baja el adjunto
con una URL firmada) llama DE VUELTA a Odoo mientras Odoo espera. Esas llamadas son otras peticiones, con otra
transacción: solo ven lo que ya está confirmado. Sin confirmar antes:

* el adjunto que una vendedora acaba de mandar no existe todavía para el puente (404) y el envío falla la primera vez;
* ``/seguimiento/hecho`` y ``/mensaje`` escriben la misma fila que el cron tiene abierta y chocan (serialización).

Y al volver hay que cerrar la transacción otra vez: mientras esperaba se abrió con una «foto» de la base anterior a lo
que el Worker confirmó.
"""
from odoo.modules import module as modulo_odoo


def confirmar(env):
    """COMMIT, salvo dentro de un test (Odoo no lo permite: el test deshace todo al terminar)."""
    if not modulo_odoo.current_test:
        env.cr.commit()


def deshacer(env):
    """ROLLBACK, salvo dentro de un test."""
    if not modulo_odoo.current_test:
        env.cr.rollback()
