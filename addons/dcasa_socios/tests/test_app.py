import os
import re
from unittest.mock import patch

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestAppSocio(HttpCase):
    """La app del socio de punta a punta: registro, entrar, candado, reclamar, canjear."""

    def setUp(self):
        super().setUp()
        patcher = patch.dict(os.environ, {'DCASA_PIN_PEPPER': 'pimienta-de-prueba'})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.Partner = self.env['res.partner']
        self.padrino = self.Partner.create({'name': 'Ana Pérez', 'phone': '6000-0001'})
        self.padrino._dcasa_asegurar_ficha()
        self.authenticate(None, None)  # sesión de visitante (la del QR en la tienda)

    def post(self, url, **datos):
        # Como un navegador: el token sale de la página, porque entrar rota la sesión.
        pagina = self.url_open('/socios/terminos').text
        datos['csrf_token'] = re.search(r'csrf_token: "([^"]+)"', pagina).group(1)
        return self.url_open(url, data=datos)

    def registrar(self, **extra):
        datos = {'nombre': 'Luis', 'apellido': 'Mora', 'celular': '6123-4567', 'pin': '482915',
                 'pin2': '482915', 'cumple_dia': '14', 'cumple_mes': '2', 'acepta': 'on', **extra}
        return self.post('/socios/registro', **datos)

    def test_pagina_de_inicio_y_terminos(self):
        self.assertIn('Tus puntos', self.url_open('/socios').text)
        terminos = self.url_open('/socios/terminos').text
        self.assertIn('500', terminos)  # lo que gana el padrino, leído de las reglas reales
        self.assertIn('Ley 81', terminos)

    def test_registro_con_invitacion(self):
        respuesta = self.url_open(f'/r/{self.padrino.dcasa_socio_codigo}')
        self.assertIn('Te invitó', respuesta.text)
        self.assertIn('Ana P.', respuesta.text, 'Del padrino solo sale el nombre y la inicial')
        cuenta = self.registrar(padrino=self.padrino.dcasa_socio_codigo)
        self.assertIn('Ya eres socio', cuenta.text)
        socio = self.Partner.search([('dcasa_celular', '=', '61234567')])
        self.assertTrue(socio.dcasa_socio_codigo.startswith('DCA'))
        self.assertEqual(socio.dcasa_referido_por_id, self.padrino)
        self.assertEqual(socio.dcasa_cumple, '02-14')
        self.assertEqual(socio.dcasa_terminos_version, 1)
        self.assertEqual(socio.dcasa_creado_por, 'qr')
        self.assertEqual(self.padrino.dcasa_saldo, 0, 'Registrarse no paga nada')

    def test_pin_facil_y_terminos_obligatorios(self):
        self.assertIn('fácil de adivinar', self.registrar(pin='123456', pin2='123456').text)
        self.assertIn('aceptar los términos', self.registrar(acepta='').text)
        self.assertFalse(self.Partner.search([('dcasa_celular', '=', '61234567')]))

    def test_entrar_y_candado(self):
        self.registrar()
        self.post('/socios/salir')
        malo = self.post('/socios/entrar', celular='61234567', pin='111222')
        self.assertIn('no coinciden', malo.text)
        # El mismo mensaje para un número que no existe: no es un buscador de clientes.
        self.assertIn('no coinciden', self.post('/socios/entrar', celular='69999999', pin='482915').text)
        for _i in range(4):
            self.post('/socios/entrar', celular='61234567', pin='111222')
        bloqueado = self.post('/socios/entrar', celular='61234567', pin='482915')
        self.assertIn('espera', bloqueado.text)
        socio = self.Partner.search([('dcasa_celular', '=', '61234567')])
        socio.action_dcasa_desbloquear()
        bien = self.post('/socios/entrar', celular='6123-4567', pin='482915')
        self.assertIn(socio.dcasa_socio_codigo, bien.text)

    def test_reclamar_una_ficha_con_puntos_pide_el_codigo(self):
        cliente = self.Partner.create({'name': 'Eric Gómez', 'phone': '6123-4567'})
        ficha = cliente._dcasa_asegurar_ficha()
        self.env['dcasa.movimiento']._asentar(ficha, 'ajuste', 353, 'test', motivo='Compra')
        sin_codigo = self.registrar()
        self.assertIn('tus puntos te esperan', sin_codigo.text)
        con_codigo = self.registrar(codigo=ficha.dcasa_socio_codigo.lower())
        self.assertIn('353', con_codigo.text)
        self.assertEqual(self.Partner.search_count([('dcasa_celular', '=', '61234567')]), 1, 'Una sola ficha')
        self.assertTrue(ficha.dcasa_reclamada)

    def test_pedir_un_premio_desde_la_app(self):
        self.registrar()
        socio = self.Partner.search([('dcasa_celular', '=', '61234567')])
        self.env['dcasa.movimiento']._asentar(socio, 'ajuste', 600, 'test', motivo='Saldo')
        premio = self.env.ref('dcasa_socios.premio_desc_5')
        cuenta = self.post('/socios/canjear', premio_id=premio.id)
        canje = self.env['dcasa.canje'].search([('partner_id', '=', socio.id)])
        self.assertIn(canje.codigo, cuenta.text)
        self.assertEqual(socio.dcasa_saldo, 100)
        self.post(f'/socios/canjes/{canje.codigo}/cancelar')
        self.assertEqual(canje.estado, 'cancelado')
        self.assertEqual(socio.dcasa_saldo, 600)

    def test_reiniciar_pin_cierra_las_sesiones(self):
        self.registrar()
        socio = self.Partner.search([('dcasa_celular', '=', '61234567')])
        self.assertIn(socio.dcasa_socio_codigo, self.url_open('/socios/cuenta').text)
        socio.action_dcasa_reiniciar_pin()
        self.assertNotIn(socio.dcasa_socio_codigo, self.url_open('/socios/cuenta').text)
