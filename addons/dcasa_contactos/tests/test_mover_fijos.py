"""Los fijos que quedaron en «Celular» pasan a «Teléfono fijo», una sola vez (decisión de la dueña, 2026-10-22;
models/mover_fijos.py, migración 19.0.1.1.0)."""
from odoo.addons.dcasa_contactos.models.mover_fijos import pasar_fijos_del_celular
from odoo.tests import TransactionCase, new_test_user, tagged

SIN = {'dcasa_sin_duplicados': True, 'dcasa_sin_exigir_contacto': True}


@tagged('post_install', '-at_install')
class TestMoverFijos(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env['res.partner'].with_context(**SIN)  # lo viejo entró sin revisar, como en la carga
        cls.fijo = Partner.create({'name': 'CLIENTE PRUEBA FIJO EN CELULAR', 'phone': '234-5678', 'customer_rank': 1})
        cls.fijo_507 = Partner.create({'name': 'PROVEEDOR PRUEBA FIJO 507', 'phone': '+507 300 0001',
                                       'supplier_rank': 1})
        cls.celular = Partner.create({'name': 'CLIENTE PRUEBA CELULAR', 'phone': '+507 6000-0951'})
        cls.corto = Partner.create({'name': 'CLIENTE PRUEBA CORTO', 'phone': '345-678'})
        cls.de_fuera = Partner.create({'name': 'CLIENTE PRUEBA EXTRANJERO', 'phone': '+1 305 555 1234'})
        cls.lleno = Partner.create({'name': 'CLIENTE PRUEBA FIJO LLENO', 'phone': '234-5679',
                                    'dcasa_telefono_fijo': '+507 734-0001'})
        cls.socio = Partner.create({'name': 'SOCIO PRUEBA FIJO', 'phone': '234-5680',
                                    'dcasa_socio_codigo': 'DCAPRB001'})
        cls.usuario = new_test_user(cls.env, login='usuario_fijo_prueba', groups='base.group_user')
        cls.usuario.partner_id.with_context(**SIN).phone = '234-5681'

    def test_mueve_solo_los_fijos_de_clientes_y_proveedores(self):
        with self.assertLogs('odoo.addons.dcasa_contactos.models.mover_fijos', level='INFO') as registro:
            conteo = pasar_fijos_del_celular(self.env)
        self.assertEqual(conteo, {'movidas': 2, 'del_programa': 1, 'con_fijo': 1, 'de_usuarios': 1})
        self.assertEqual((self.fijo.phone, self.fijo.dcasa_telefono_fijo), (False, '+507 234-5678'))
        self.assertEqual((self.fijo_507.phone, self.fijo_507.dcasa_telefono_fijo), (False, '+507 300-0001'))
        self.assertEqual(self.fijo.dcasa_fijo_digitos, '2345678')
        # Lo demás, igual que estaba.
        self.assertEqual((self.celular.phone, self.celular.dcasa_telefono_fijo), ('+507 6000-0951', False))
        self.assertEqual(self.corto.phone, '345-678')
        self.assertEqual(self.de_fuera.phone, '+1 305 555 1234')
        self.assertEqual((self.lleno.phone, self.lleno.dcasa_telefono_fijo), ('234-5679', '+507 734-0001'))
        self.assertEqual((self.socio.phone, self.socio.dcasa_telefono_fijo), ('234-5680', False))
        self.assertEqual(self.usuario.partner_id.phone, '234-5681')
        # El rastro: una nota en la ficha movida y un resumen sin datos de personas en el registro.
        nota = self.fijo.message_ids.filtered(lambda m: 'de Celular a Teléfono fijo' in (m.body or ''))
        self.assertEqual(len(nota), 1)
        self.assertIn('Se pasó el número 234-5678 de Celular a Teléfono fijo.', nota.body)
        self.assertFalse(self.socio.message_ids.filtered(lambda m: 'Teléfono fijo' in (m.body or '')))
        texto = '\n'.join(registro.output)
        self.assertIn('2 fichas pasaron el número', texto)
        self.assertIn('1 de Socios o vendedores sin tocar', texto)
        for privado in ('234', 'PRUEBA', '300'):
            self.assertNotIn(privado, texto)

    def test_correr_dos_veces_no_hace_nada(self):
        pasar_fijos_del_celular(self.env)
        notas = len(self.fijo.message_ids)
        conteo = pasar_fijos_del_celular(self.env)
        self.assertEqual(conteo['movidas'], 0)
        self.assertEqual(len(self.fijo.message_ids), notas)
        self.assertEqual(self.fijo.dcasa_telefono_fijo, '+507 234-5678')
