from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import SociosCommon


@tagged('post_install', '-at_install')
class TestLibroMayor(SociosCommon):

    def test_saldo_es_la_suma_del_libro(self):
        Mov = self.env['dcasa.movimiento']
        Mov._asentar(self.padrino, 'ajuste', 300, 'test', motivo='Compra vieja')
        Mov._asentar(self.padrino, 'ajuste', -100, 'test', motivo='Corrección')
        self.assertEqual(self.padrino.dcasa_saldo, 200)
        self.assertIn(self.padrino, self.env['res.partner'].search([('dcasa_saldo', '>', 150)]))
        self.assertNotIn(self.padrino, self.env['res.partner'].search([('dcasa_saldo', '>', 250)]))
        self.assertIn(self.cliente, self.env['res.partner'].search([('dcasa_saldo', '=', 0)]))

    def test_nada_se_edita_ni_se_borra(self):
        asiento = self.env['dcasa.movimiento']._asentar(self.padrino, 'ajuste', 50, 'test', motivo='x')
        with self.assertRaises(UserError):
            asiento.sudo().write({'puntos': 5000})
        with self.assertRaises(UserError):
            asiento.sudo().unlink()

    def test_un_reverso_una_sola_vez(self):
        asiento = self.env['dcasa.movimiento']._asentar(self.padrino, 'ajuste', 50, 'test', motivo='x')
        asiento._reversar('Error', 'test')
        self.assertEqual(self.padrino.dcasa_saldo, 0)
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            asiento._reversar('Otra vez', 'test')
            self.env.flush_all()

    def test_asiento_de_cero_no_existe(self):
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.env['dcasa.movimiento']._asentar(self.padrino, 'ajuste', 0, 'test', motivo='x')
            self.env.flush_all()

    def test_ajuste_lleva_motivo_y_no_deja_negativo(self):
        wizard = self.env['dcasa.ajuste.wizard'].create(
            {'partner_id': self.padrino.id, 'puntos': -10, 'motivo': 'Prueba'})
        with self.assertRaises(UserError):
            wizard.action_confirmar()
        wizard.puntos = 40
        wizard.action_confirmar()
        self.assertEqual(self.padrino.dcasa_saldo, 40)

    def test_ficha_por_celular_unica(self):
        self.assertEqual(self.padrino.dcasa_celular, '60000001', 'El celular del contacto pasa a ser la llave')
        otro = self.env['res.partner'].create({'name': 'Otra', 'phone': '6000-0001'})
        otro._dcasa_asegurar_ficha()
        self.assertFalse(otro.dcasa_celular, 'Un celular, una ficha')
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            otro.dcasa_celular = '+507 6000-0001'
            self.env.flush_all()

    def test_padrino_se_escribe_una_vez(self):
        self.cliente.dcasa_referido_por_id = self.padrino
        otro = self.env['res.partner'].create({'name': 'Luis'})
        otro._dcasa_asegurar_ficha()
        with self.assertRaises(UserError):
            self.cliente.dcasa_referido_por_id = otro
        with self.assertRaises(UserError):
            self.cliente.dcasa_referido_por_id = False
