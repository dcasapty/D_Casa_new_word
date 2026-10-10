"""La ficha de quien escribe se busca por la llave del teléfono (dcasa_contactos): sin confundir países ni duplicar."""
from odoo.tests import tagged

from .common import JuanCase


@tagged('post_install', '-at_install')
class TestFichasUnicasEnElChat(JuanCase):

    def test_encuentra_la_ficha_aunque_su_telefono_este_escrito_de_otra_forma(self):
        for i, escrito in enumerate(('00507-6123-4567', '507 6123 4567', '(507) 6123-4567', '6123 4567')):
            with self.subTest(escrito=escrito):
                ficha = self.Partner.create({'name': f'Ficha {i}', 'phone': escrito}) if i == 0 else None
                if ficha is None:
                    self.Partner.search([('name', '=', 'Ficha 0')]).phone = escrito
                    ficha = self.Partner.search([('name', '=', 'Ficha 0')])
                self.assertEqual(self.Partner._dcasa_conv_buscar('50761234567'), ficha)

    def test_un_numero_de_otro_pais_se_encuentra_solo_por_su_numero_completo(self):
        estadounidense = self.Partner.create({'name': 'Cliente de Miami', 'phone': '+1 (305) 555-6026'})
        panameno = self.Partner.create({'name': 'Cliente de Panamá', 'phone': '5555-6026'})
        self.assertEqual(self.Partner._dcasa_conv_buscar('13055556026'), estadounidense)
        self.assertEqual(self.Partner._dcasa_conv_buscar('50755556026'), panameno)
        self.assertEqual(self.conversacion(id_externo='13055556026').partner_id, estadounidense)
        self.assertEqual(self.conversacion(id_externo='50755556026').partner_id, panameno)

    def test_no_crea_una_ficha_nueva_si_el_celular_ya_esta_en_otra(self):
        existente = self.Partner.create({'name': 'Rosa Chat', 'phone': '+507 6444-1212'})
        antes = self.Partner.with_context(active_test=False).search_count([])
        self.assertEqual(self.conversacion(id_externo='50764441212').partner_id, existente)
        self.assertEqual(self.Partner.with_context(active_test=False).search_count([]), antes)

    def test_por_la_llave_del_programa_de_socios(self):
        socia = self.Partner.create({'name': 'Socia Chat', 'dcasa_celular': '64441313'})
        self.assertEqual(self.Partner._dcasa_conv_buscar('50764441313'), socia)
        self.assertEqual(self.Partner._dcasa_conv_buscar('6444-1313'), socia)

    def test_quien_es_del_equipo_se_encuentra_por_su_contacto_de_trabajo(self):
        empleado = self.env['hr.employee'].create({'name': 'Empleada Chat', 'work_phone': '+507 6444-1414'})
        self.assertEqual(self.Partner._dcasa_conv_buscar('50764441414'), empleado.work_contact_id)

    def test_la_ficha_nueva_del_chat_no_choca_con_ninguna(self):
        conv = self.conversacion(id_externo='50764441515', nombre='Nueva Chat')
        self.assertEqual(conv.partner_id.dcasa_telefono_llave, 'pa:64441515')
        otra = self.conversacion(canal='whatsapp_cloud', id_externo='50764441515')
        self.assertEqual(otra.partner_id, conv.partner_id)

    def test_sin_numero_no_busca_nada(self):
        self.assertFalse(self.Partner._dcasa_conv_buscar(''))
        self.assertFalse(self.Partner._dcasa_conv_buscar('no es un numero'))
