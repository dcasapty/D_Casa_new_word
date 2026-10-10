"""«Posibles duplicados»: lo que quedó repetido de antes, para limpiar y fusionar."""
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

SIN = {'dcasa_sin_duplicados': True}


@tagged('post_install', '-at_install')
class TestDuplicados(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env['res.partner'].with_context(**SIN)
        cls.a1 = Partner.create({'name': 'Rosa Repetida 1', 'phone': '+507 6444-0001', 'email': 'rosa@x.com',
                                 'vat': '9-111-222'})
        cls.a2 = Partner.create({'name': 'Rosa Repetida 2', 'phone': '64440001', 'email': 'ROSA@x.com'})
        cls.a3 = Partner.create({'name': 'Rosa Repetida 3', 'phone': '+1 305 555 9999', 'vat': '9 111 222'})
        cls.unica = Partner.create({'name': 'Persona única', 'phone': '6444-0099', 'email': 'unica@x.com'})
        # una dirección de entrega con el mismo celular no es un duplicado
        Partner.create({'name': 'Entrega de Rosa', 'parent_id': cls.a1.id, 'type': 'delivery',
                        'phone': '+507 6444-0001'})
        cls.Duplicado = cls.env['dcasa.contacto.duplicado']
        cls.gerencia = new_test_user(cls.env, login='ger_dup_contactos', name='Gerencia Duplicados',
                                     groups='base.group_user,dcasa_base.group_gerencia')

    def _fila(self, tipo, valor):
        return self.Duplicado.search([('tipo', '=', tipo), ('valor', '=', valor)])

    def test_lista_lo_repetido_por_celular_correo_y_ruc(self):
        celular = self._fila('celular', 'pa:64440001')
        self.assertEqual(celular.cantidad, 2)
        self.assertIn('Rosa Repetida 1', celular.nombres)
        self.assertIn('Rosa Repetida 2', celular.nombres)
        self.assertEqual(self._fila('correo', 'rosa@x.com').cantidad, 2)
        self.assertEqual(self._fila('ruc', '9-111-222').cantidad, 2)

    def test_no_lista_lo_que_no_esta_repetido_ni_las_direcciones(self):
        self.assertFalse(self._fila('celular', 'pa:64440099'))
        self.assertFalse(self._fila('celular', 'intl:13055559999'))
        # la dirección de entrega no cuenta: el celular de Rosa sigue siendo de 2 fichas, no de 3
        self.assertEqual(self._fila('celular', 'pa:64440001').cantidad, 2)

    def test_el_id_de_una_fila_no_cambia_cuando_otras_se_arreglan(self):
        celular = self._fila('celular', 'pa:64440001')
        correo = self._fila('correo', 'rosa@x.com')
        ids = (celular.id, correo.id)
        self.assertNotEqual(*ids)
        self.a3.with_context(**SIN).write({'vat': False})  # se arregla el RUC repetido: esa fila desaparece
        self.assertEqual((self._fila('celular', 'pa:64440001').id, self._fila('correo', 'rosa@x.com').id), ids)

    def test_ver_las_fichas_y_fusionarlas(self):
        fila = self._fila('celular', 'pa:64440001')
        accion = fila.action_ver()
        self.assertEqual(accion['res_model'], 'res.partner')
        self.assertEqual(set(self.env['res.partner'].with_context(active_test=False).search(accion['domain'])),
                         set(self.a1 + self.a2))
        fusion = fila.action_fusionar()
        self.assertEqual(fusion['res_model'], 'base.partner.merge.automatic.wizard')
        self.assertEqual(set(fusion['context']['active_ids']), set((self.a1 + self.a2).ids))

    def test_no_se_fusiona_si_ya_no_hay_dos_o_si_son_demasiadas(self):
        fila = self._fila('celular', 'pa:64440001')
        self.a2.with_context(**SIN).write({'phone': '6444-0002'})
        fila.invalidate_recordset()
        with self.assertRaisesRegex(UserError, 'Ya no quedan dos fichas'):
            fila.action_fusionar()
        Partner = self.env['res.partner'].with_context(**SIN)
        for i in range(3):
            Partner.create({'name': f'Muchas {i}', 'email': 'muchas@x.com'})
        Partner.create({'name': 'Muchas 4', 'email': 'MUCHAS@x.com'})
        with self.assertRaisesRegex(UserError, 'hasta 3'):
            self._fila('correo', 'muchas@x.com').action_fusionar()

    def test_solo_gerencia_la_ve(self):
        self.assertTrue(self.Duplicado.with_user(self.gerencia).search([('tipo', '=', 'ruc')]))
        vendedora = new_test_user(self.env, login='vend_dup_contactos', name='Vendedora Duplicados',
                                  groups='base.group_user,dcasa_base.group_vendedora')
        with self.assertRaises(AccessError):
            self.Duplicado.with_user(vendedora).search([])
