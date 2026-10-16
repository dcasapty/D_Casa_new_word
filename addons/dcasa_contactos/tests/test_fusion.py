"""La fusión de contactos con lo de Socios: Gerencia puede, no se pierde el código, el PIN ni quién invitó, y dos
socios distintos no se funden solos (hallazgo del 2026-10-16: Odoo no copiaba los datos de Socios de la ficha que
se borraba)."""
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged

SIN = {'dcasa_sin_duplicados': True}


@tagged('post_install', '-at_install')
class TestFusion(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env['res.partner'].with_context(**SIN)
        cls.vieja = Partner.create({'name': 'Rosa Fusión', 'phone': '+507 6555-0001', 'email': 'fusion@x.com'})
        cls.socia = Partner.create({'name': 'Rosa Fusión', 'phone': '6555-0001', 'email': 'fusion@x.com'})
        # la socia es la más nueva: sin la regla de «la que ya está en el programa queda», Odoo dejaría la vieja
        cls.env.cr.execute("UPDATE res_partner SET create_date = create_date - interval '30 days' WHERE id = %s",
                           [cls.vieja.id])
        cls.padrino = Partner.create({'name': 'Padrino Fusión', 'phone': '6555-0100'})._dcasa_asegurar_ficha()
        cls.socia._dcasa_asegurar_ficha()
        cls.socia.write({'dcasa_referido_por_id': cls.padrino.id})
        cls.socia.write({'dcasa_pin_hash': 'hash-de-prueba', 'dcasa_pin_cambiado_en': fields.Datetime.now(),
                         'dcasa_referido_pagado_en': fields.Datetime.now()})
        cls.env['dcasa.movimiento']._asentar(cls.socia, 'ajuste', 300, 'test', motivo='Saldo de prueba')
        cls.codigo = cls.socia.dcasa_socio_codigo
        cls.celular = cls.socia.dcasa_celular
        cls.gerencia = new_test_user(cls.env, login='ger_fusion', name='Gerencia Fusión',
                                     groups='base.group_user,dcasa_base.group_gerencia')
        cls.vendedora = new_test_user(cls.env, login='vend_fusion', name='Vendedora Fusión',
                                      groups='base.group_user,dcasa_base.group_vendedora')

    def _fusionar(self, usuario, fichas, destino=None):
        asistente = self.env['base.partner.merge.automatic.wizard'].with_user(usuario).create({
            'partner_ids': [(6, 0, fichas.ids)], 'dst_partner_id': destino.id if destino else False})
        return asistente.action_merge()

    def test_gerencia_puede_abrir_el_asistente_y_la_vendedora_no(self):
        Asistente = self.env['base.partner.merge.automatic.wizard']
        self.assertTrue(Asistente.with_user(self.gerencia).has_access('create'))
        self.assertFalse(Asistente.with_user(self.vendedora).has_access('create'))

    def test_por_defecto_queda_la_ficha_que_ya_esta_en_el_programa_aunque_sea_mas_nueva(self):
        ordenadas = self.env['base.partner.merge.automatic.wizard']._get_ordered_partner(
            (self.vieja + self.socia).ids)
        self.assertEqual(ordenadas[-1], self.socia, 'la que queda es la última de la lista')
        saldo = self.socia.sudo().dcasa_saldo
        self._fusionar(self.gerencia, self.vieja + self.socia)
        self.assertFalse(self.vieja.exists())
        socia = self.socia.sudo()
        self.assertEqual(socia.dcasa_socio_codigo, self.codigo)
        self.assertEqual(socia.dcasa_celular, self.celular)
        self.assertEqual(socia.dcasa_saldo, saldo, 'los puntos siguen')

    def test_si_queda_la_ficha_sin_programa_no_se_pierde_nada_de_socios(self):
        """Forzando como destino a la ficha que NO es socia: el código, el celular, el PIN, el padrino y el pago del
        referido pasan a ella antes de que la socia se borre."""
        saldo = self.socia.sudo().dcasa_saldo
        self._fusionar(self.gerencia, self.vieja + self.socia, destino=self.vieja)
        self.assertFalse(self.socia.exists())
        vieja = self.vieja.sudo()
        self.assertEqual(vieja.dcasa_socio_codigo, self.codigo)
        self.assertEqual(vieja.dcasa_celular, self.celular)
        self.assertEqual(vieja.dcasa_pin_hash, 'hash-de-prueba')
        self.assertEqual(vieja.dcasa_referido_por_id, self.padrino)
        self.assertTrue(vieja.dcasa_referido_pagado_en, 'sin esto el padrino podría cobrar dos veces')
        self.assertEqual(vieja.dcasa_saldo, saldo, 'los puntos pasan completos, sin duplicarse ni perderse')
        self.assertTrue(vieja.dcasa_reclamada)

    def test_lo_que_ya_tiene_la_ficha_que_queda_manda(self):
        """Si la que queda ya tenía su propio dato (aquí el cumpleaños), el de la que se va no lo pisa."""
        self.vieja.sudo().write({'dcasa_cumple': '03-04'})
        self.socia.sudo().write({'dcasa_cumple': '12-25'})
        self._fusionar(self.gerencia, self.vieja + self.socia, destino=self.vieja)
        self.assertEqual(self.vieja.sudo().dcasa_cumple, '03-04')

    def test_dos_socios_distintos_no_se_fusionan_solos(self):
        otra = self.env['res.partner'].with_context(**SIN).create(
            {'name': 'Rosa Fusión', 'phone': '6555-0002', 'email': 'fusion@x.com'})._dcasa_asegurar_ficha()
        with self.assertRaisesRegex(UserError, 'más de una ficha con código de socios'):
            self._fusionar(self.gerencia, self.socia + otra)
        self.assertTrue(self.socia.exists() and otra.exists(), 'no se borró ninguna')

    def test_dos_fichas_sin_programa_se_fusionan_como_siempre(self):
        Partner = self.env['res.partner'].with_context(**SIN)
        a = Partner.create({'name': 'Pedro Normal', 'email': 'pedro@x.com'})
        b = Partner.create({'name': 'Pedro Normal', 'email': 'pedro@x.com'})
        self._fusionar(self.gerencia, a + b)
        self.assertEqual(len((a + b).exists()), 1)
