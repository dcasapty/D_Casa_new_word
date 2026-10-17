"""Qué clase lleva cada correo y cuál puede salir (tabla completa, sin base de datos)."""
from odoo.tests import BaseCase, tagged

from ..models import politica as P


@tagged('post_install', '-at_install')
class TestPolitica(BaseCase):

    def test_clase_de_correo(self):
        casos = (
            (('account.move', 'comment', True, 'factura'), 'factura'),
            (('account.move', 'comment', False, 'abono'), 'abono'),
            (('res.partner', 'comment', False, 'bienvenida'), 'bienvenida'),
            (('sale.order', 'comment', False, 'cotizacion'), 'cotizacion'),
            (('res.users', False, False, 'prueba'), 'prueba'),
            (('account.move', 'comment', True, 'inventada'), 'odoo'),
            (('res.users', 'email_outgoing', False, None), 'acceso'),
            (('account.move', 'comment', True, None), 'documento'),
            (('sale.order', 'comment', True, None), 'documento'),
            (('sale.order', 'comment', False, None), 'odoo'),
            (('sale.order', 'notification', True, None), 'odoo'),
            (('crm.lead', 'comment', True, None), 'odoo'),
            ((False, 'email_outgoing', False, None), 'odoo'),
        )
        for argumentos, esperado in casos:
            with self.subTest(argumentos=argumentos):
                self.assertEqual(P.clase_de_correo(*argumentos), esperado)

    def test_puede_salir(self):
        equipo = ['duena@dcasapty.com', 'ventas1@dcasapty.com']
        cliente = ['ana@example.com']
        casos = (
            # (clase, encendido, entorno, destinos) → (sale, motivo)
            (('prueba', False, 'produccion', ['duena@dcasapty.com']), (True, '')),
            (('prueba', False, 'staging', ['DUENA@dcasapty.com']), (True, '')),
            (('prueba', True, 'produccion', ['duena@dcasapty.com', 'ana@example.com']), (False, P.MOTIVO_PRUEBA)),
            (('factura', False, 'produccion', cliente), (False, P.MOTIVO_APAGADO)),
            (('factura', True, 'staging', cliente), (False, P.MOTIVO_STAGING)),
            (('odoo', True, 'produccion', cliente), (False, P.MOTIVO_ODOO)),
            (('odoo', False, 'produccion', cliente), (False, P.MOTIVO_APAGADO)),
            (('factura', True, 'produccion', []), (False, P.MOTIVO_SIN_DESTINO)),
        )
        for argumentos, esperado in casos:
            clase, encendido, entorno, destinos = argumentos
            with self.subTest(argumentos=argumentos):
                self.assertEqual(P.puede_salir(clase, encendido, entorno, destinos, equipo), esperado)
        for clase in P.CLASES_A_CLIENTES:
            with self.subTest(clase=clase):
                self.assertEqual(P.puede_salir(clase, True, 'produccion', cliente, equipo), (True, ''))
