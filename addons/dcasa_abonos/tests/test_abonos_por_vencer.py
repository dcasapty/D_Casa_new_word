"""D3: el vencimiento del abono queda guardado en la factura, la lista «Abonos por vencer» muestra los que vencen
pronto o ya vencieron, y el botón de WhatsApp abre el mensaje listo (lo manda una persona)."""
from datetime import timedelta
from urllib.parse import unquote

from lxml import etree

from odoo import Command, fields
from odoo.addons.dcasa_base.tests.test_roles import crear_usuario
from odoo.tests import TransactionCase, tagged

from ..models.abono_vencimiento import whatsapp_de


@tagged('post_install', '-at_install')
class TestAbonosPorVencer(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        env['ir.config_parameter'].sudo().set_param('dcasa_invoice.abono_dias', '30')
        cls.caja = crear_usuario(env, 'abv_caja', 'dcasa_base.group_caja')
        cls.cliente = env['res.partner'].create({
            'name': 'CLIENTE DE PRUEBA ABONO', 'phone': '6000-0061', 'email': 'cliente.abono@example.com'})
        cls.producto = env['product.product'].create({'name': 'Cama abono', 'list_price': 200.0,
                                                      'taxes_id': [Command.clear()]})
        cls.diario = env['account.journal'].search(
            [('type', '=', 'cash'), ('company_id', '=', env.company.id)], limit=1)
        cls.hoy = fields.Date.context_today(env['account.move'])

    def _factura(self):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': self.hoy - timedelta(days=40),
            'invoice_line_ids': [Command.create({'product_id': self.producto.id, 'price_unit': 200.0,
                                                 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        return factura

    def _pagar(self, factura, monto, hace_dias):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create({
                'amount': monto, 'journal_id': self.diario.id,
                'payment_date': self.hoy - timedelta(days=hace_dias)}).action_create_payments()

    def test_el_vencimiento_se_guarda_y_se_ordena(self):
        pronto = self._factura()
        self._pagar(pronto, 100.0, hace_dias=27)        # vence en 3 días
        lejos = self._factura()
        self._pagar(lejos, 100.0, hace_dias=0)          # vence en 30 días
        vencida = self._factura()
        self._pagar(vencida, 100.0, hace_dias=35)       # venció hace 5 días
        pagada = self._factura()
        self._pagar(pagada, 200.0, hace_dias=1)
        self.assertEqual(pronto.dcasa_abono_vence, self.hoy + timedelta(days=3))
        self.assertEqual(pronto.dcasa_abono_dias, 3)
        self.assertTrue(pronto.dcasa_abono_pronto)
        self.assertEqual(lejos.dcasa_abono_vence, self.hoy + timedelta(days=30))
        self.assertFalse(lejos.dcasa_abono_pronto)
        self.assertEqual(vencida.dcasa_abono_dias, -5)
        self.assertFalse(pagada.dcasa_abono_vence)
        encontradas = self.env['account.move'].search([('dcasa_abono_pronto', '=', True)])
        self.assertIn(pronto, encontradas)
        self.assertIn(vencida, encontradas)
        self.assertNotIn(lejos, encontradas)
        self.assertNotIn(pagada, encontradas)
        # Se termina de pagar: sale de la lista.
        self._pagar(pronto, 100.0, hace_dias=0)
        self.assertFalse(pronto.dcasa_abono_vence)

    def test_si_cambia_el_plazo_se_recalcula_cada_noche(self):
        factura = self._factura()
        self._pagar(factura, 100.0, hace_dias=10)
        self.assertEqual(factura.dcasa_abono_vence, self.hoy + timedelta(days=20))
        self.env['ir.config_parameter'].sudo().set_param('dcasa_invoice.abono_dias', '45')
        self.env['account.move']._dcasa_cron_abonos()
        self.assertEqual(factura.dcasa_abono_vence, self.hoy + timedelta(days=35))

    def test_whatsapp_con_el_mensaje_listo(self):
        factura = self._factura()
        self._pagar(factura, 100.0, hace_dias=27)
        accion = factura.with_user(self.caja).action_dcasa_abono_whatsapp()
        self.assertEqual(accion['type'], 'ir.actions.act_url')
        self.assertTrue(accion['url'].startswith('https://wa.me/50760000061?text='))
        texto = unquote(accion['url'].split('text=', 1)[1])
        self.assertIn('Hola Cliente', texto)
        self.assertIn(factura.name, texto)
        self.assertIn('$100.00', texto)
        self.assertIn((self.hoy + timedelta(days=3)).strftime('%d/%m/%Y'), texto)

    def test_numeros_para_whatsapp(self):
        self.assertEqual(whatsapp_de('6026-1919'), '50760261919')
        self.assertEqual(whatsapp_de('+507 6026-1919'), '50760261919')
        self.assertEqual(whatsapp_de('+1 305 555 1234'), '13055551234')
        self.assertEqual(whatsapp_de('00507 6026 1919'), '50760261919')
        self.assertEqual(whatsapp_de('123'), '')
        self.assertEqual(whatsapp_de(False), '')

    def test_la_lista_se_abre_para_caja(self):
        accion = self.env.ref('dcasa_abonos.action_dcasa_abonos_por_vencer')
        vistas = self.env['account.move'].with_user(self.caja).get_views(
            [(self.env.ref('dcasa_abonos.view_move_list_abonos_por_vencer').id, 'list')],
            {'action_id': accion.id, 'load_filters': True})
        arbol = etree.fromstring(vistas['views']['list']['arch'])
        self.assertIn('dcasa_abono_vence', {n.get('name') for n in arbol.iter('field')})
        self.env['account.move'].with_user(self.caja).web_search_read(
            [('move_type', '=', 'out_invoice'), ('dcasa_abono_vence', '!=', False), ('dcasa_abono_pronto', '=', True)],
            {'dcasa_abono_vence': {}, 'dcasa_abono_dias': {}, 'partner_id': {}, 'amount_residual_signed': {}})
