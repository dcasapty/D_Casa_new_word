"""Socios en la web (ronda 7): catálogo de premios, puntos en el carrito y cuenta unificada.

Las reglas de DCasa-Referidos siguen mandando: ninguna cifra fuera de puntos.json, el saldo es la
suma del libro, el libro no se edita (se reversa con motivo), nunca saldo negativo.
"""
import os
import re
from pathlib import Path
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.service.model import call_kw
from odoo.sql_db import Cursor
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import SQL

from ..models import reglas as R
from ..models.sale_order import PARAM_PUNTOS_EN_CARRITO
from .common import SociosCommon

PIN = '482915'
CLAVE = 'socia-web-2026'


class CarritoCommon(SociosCommon):
    """Una socia con cuenta de la tienda (usuario portal): la misma ficha es cliente y socia."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref('website.default_website')
        cls.producto.product_tmpl_id.write({'is_published': True, 'website_id': False})
        cls.usuaria = new_test_user(cls.env, login='web_socia', password=CLAVE, groups='base.group_portal',
                                    name='Socia Web')
        cls.socia = cls.usuaria.partner_id
        cls.socia.write({'phone': '6000-0003', 'email': 'socia@example.com'})
        cls.socia._dcasa_asegurar_ficha()

    def setUp(self):
        super().setUp()
        self.socia._dcasa_guardar_pin(PIN)
        self.env['dcasa.movimiento']._asentar(self.socia, 'ajuste', 1500, 'test', motivo='Saldo de prueba')
        self.diez = self.env.ref('dcasa_socios.premio_desc_10')  # 1,000 puntos = $10

    def modo(self, valor):
        self.env['ir.config_parameter'].sudo().set_param(PARAM_PUNTOS_EN_CARRITO, valor)

    def carrito(self, cantidad=2, partner=None):
        """Un carrito de la tienda web: `cantidad` camas de $100 + ITBMS."""
        return self.env['sale.order'].sudo().create({
            'partner_id': (partner or self.socia).id,
            'website_id': self.website.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': cantidad})],
        })

    def reversos(self, canje):
        return self.env['dcasa.movimiento'].search([('canje_id', '=', canje.id), ('tipo', '=', 'reverso')])


@tagged('post_install', '-at_install')
class TestPuntosEnCarrito(CarritoCommon):

    def test_modo_por_defecto_es_premios(self):
        self.assertEqual(self.env['sale.order']._dcasa_modo_puntos_en_carrito(), 'premios')
        self.modo('cualquier-cosa')
        self.assertEqual(self.env['sale.order']._dcasa_modo_puntos_en_carrito(), 'premios')

    def test_el_catalogo_no_ensena_el_premio_tecnico(self):
        libre = self.env.ref('dcasa_socios.premio_libre_web')
        self.assertTrue(libre.libre)
        self.assertNotIn(libre, self.env['dcasa.premio']._catalogo())
        self.assertIn(self.diez, self.env['dcasa.premio']._catalogo('descuento'))

    def test_usar_un_premio_del_catalogo(self):
        orden = self.carrito()
        self.assertAlmostEqual(orden.amount_total, 214.0)
        canje = orden._dcasa_usar_puntos_web(premio=self.diez)
        self.assertEqual(canje.origen, 'web')
        self.assertEqual(canje.estado, 'solicitado')
        self.assertEqual(self.socia.dcasa_saldo, 500, 'Los puntos salen al pedir, como reserva')
        self.assertAlmostEqual((canje.expira_en - canje.solicitado_en).total_seconds(),
                               R.cargar_reglas()['canje']['vigenciaDelCodigoHoras'] * 3600)
        linea = orden.order_line.filtered('dcasa_canje_id')
        self.assertEqual(len(linea), 1)
        self.assertLess(linea.price_unit, 0)
        self.assertAlmostEqual(orden.amount_total, 214.0 - 10.0, msg='El premio vale lo que dice, ITBMS incluido')
        self.assertEqual(orden.cart_quantity, 2, 'El premio no cuenta en el globo del carrito')
        self.assertFalse(linea._is_sellable(), 'Sin enlace ni cantidad en el carrito')
        valores = orden._dcasa_valores_puntos_web()
        self.assertEqual(valores['dcasa_premio_aplicado'], canje)

    def test_solo_premios_que_caben_y_al_alcance(self):
        valores = self.carrito()._dcasa_valores_puntos_web()
        nombres = valores['dcasa_premios'].mapped('name')
        self.assertIn('$10 de descuento', nombres)
        self.assertIn('$100 de descuento', nombres,
                      'Cabe en el carrito aunque no alcance el saldo: se enseña «te faltan»')
        self.assertNotIn('Puntos en la tienda web', nombres)
        chico = self.carrito(cantidad=1)
        chico.order_line.price_unit = 20.0  # $21.40 con ITBMS
        self.assertEqual(chico._dcasa_valores_puntos_web()['dcasa_premios'].mapped('name'),
                         ['$5 de descuento', '$10 de descuento'])

    def test_el_premio_no_puede_ser_mayor_que_el_carrito(self):
        orden = self.carrito(cantidad=1)
        orden.order_line.price_unit = 5.0  # $5.35 con ITBMS
        with self.assertRaisesRegex(UserError, 'mayor que tu carrito'):
            orden._dcasa_usar_puntos_web(premio=self.diez)
        self.assertEqual(self.socia.dcasa_saldo, 1500)
        self.assertFalse(orden.order_line.filtered('dcasa_canje_id'))

    def test_nunca_saldo_negativo(self):
        orden = self.carrito(cantidad=3)
        with self.assertRaisesRegex(UserError, 'Te faltan'):
            orden._dcasa_usar_puntos_web(premio=self.env.ref('dcasa_socios.premio_desc_25'))
        self.assertEqual(self.socia.dcasa_saldo, 1500)

    def test_pedir_escribe_la_ficha_para_serializar_el_saldo(self):
        """App y carrito a la vez: un SELECT ... FOR UPDATE deja a la segunda transacción con su foto
        vieja del saldo (REPEATABLE READ). Hay que ESCRIBIR la fila de la ficha antes de leer el saldo,
        para que PostgreSQL rechace la segunda y Odoo la reintente con el saldo ya descontado."""
        orden = self.carrito()
        consultas = []
        ejecutar = Cursor.execute

        def espia(cr, query, params=None, log_exceptions=True):
            consultas.append(query.code if isinstance(query, SQL) else query)
            return ejecutar(cr, query, params, log_exceptions)

        self.env.invalidate_all()
        with patch('odoo.sql_db.Cursor.execute', espia):
            orden._dcasa_usar_puntos_web(premio=self.diez)
        escritura = [i for i, q in enumerate(consultas)
                     if re.match(r'\s*UPDATE\s+"?res_partner"?\s+SET', str(q), re.I) and 'WHERE id' in str(q)]
        self.assertTrue(escritura, 'pedir un premio escribe la fila de la ficha')
        lecturas_del_libro = [i for i, q in enumerate(consultas)
                              if 'dcasa_movimiento' in str(q) and re.match(r'\s*SELECT', str(q), re.I)]
        self.assertTrue(lecturas_del_libro, 'el saldo se lee del libro dentro de la transacción')
        self.assertLess(escritura[0], min(lecturas_del_libro), 'la escritura va antes de leer el saldo')
        self.assertEqual(self.socia.dcasa_saldo, 500)

    def test_respeta_el_minimo_para_canjear(self):
        orden = self.carrito()
        with self.reglas_con(canje__saldoMinimoParaCanjear=2000):
            ofrecidos = orden._dcasa_valores_puntos_web()['dcasa_premios']
            self.assertNotIn(self.diez, ofrecidos, 'Por debajo del mínimo el premio no se ofrece')
            self.assertIn(self.env.ref('dcasa_socios.premio_desc_25'), ofrecidos)
            with self.assertRaisesRegex(UserError, 'canje mínimo'):
                orden._dcasa_usar_puntos_web(premio=self.diez)
        self.assertEqual(self.socia.dcasa_saldo, 1500)

    def test_un_premio_por_carrito(self):
        orden = self.carrito()
        orden._dcasa_usar_puntos_web(premio=self.diez)
        with self.assertRaisesRegex(UserError, 'Ya tienes un premio'):
            orden._dcasa_usar_puntos_web(premio=self.env.ref('dcasa_socios.premio_desc_5'))

    def test_solo_el_socio_con_sesion_de_la_tienda(self):
        publico = self.website.user_id.partner_id
        with self.assertRaisesRegex(UserError, 'entra a tu cuenta'):
            self.carrito(partner=publico)._dcasa_usar_puntos_web(premio=self.diez)
        # Un cliente con puntos pero sin PIN todavía no es socio: no canjea.
        self.cliente._dcasa_asegurar_ficha()
        self.env['dcasa.movimiento']._asentar(self.cliente, 'ajuste', 1500, 'test', motivo='Saldo')
        with self.assertRaisesRegex(UserError, 'entra a tu cuenta'):
            self.carrito(partner=self.cliente)._dcasa_usar_puntos_web(premio=self.diez)

    def test_quitar_el_premio_reversa_con_motivo(self):
        orden = self.carrito()
        canje = orden._dcasa_usar_puntos_web(premio=self.diez)
        orden._dcasa_quitar_puntos_web()
        self.assertEqual(canje.estado, 'cancelado')
        self.assertEqual(self.socia.dcasa_saldo, 1500)
        reverso = self.reversos(canje)
        self.assertEqual(reverso.puntos, 1000)
        self.assertIn('Quitaste el premio', reverso.motivo)
        self.assertFalse(orden.order_line.filtered('dcasa_canje_id'))
        self.assertAlmostEqual(orden.amount_total, 214.0)

    def test_quitar_la_linea_desde_la_tienda_devuelve_los_puntos(self):
        orden = self.carrito()
        canje = orden._dcasa_usar_puntos_web(premio=self.diez)
        linea = orden.order_line.filtered('dcasa_canje_id')
        resultado = orden._cart_update_line_quantity(linea.id, 0)
        self.assertFalse(resultado.get('warning'))
        self.assertEqual(canje.estado, 'cancelado')
        self.assertEqual(self.socia.dcasa_saldo, 1500)

    def test_la_cantidad_del_premio_no_se_cambia(self):
        orden = self.carrito()
        orden._dcasa_usar_puntos_web(premio=self.diez)
        linea = orden.order_line.filtered('dcasa_canje_id')
        resultado = orden._cart_update_line_quantity(linea.id, 3)
        self.assertIn('una sola vez', resultado['warning'])
        self.assertEqual(linea.product_uom_qty, 1)
        self.assertAlmostEqual(orden.amount_total, 204.0)

    def test_si_el_carrito_se_achica_el_premio_sale_solo(self):
        cojin = self.env['product.product'].create({
            'name': 'COJÍN', 'type': 'consu', 'list_price': 4.0, 'is_published': True,
            'taxes_id': [Command.set(self.itbms.ids)],
        })
        orden = self.env['sale.order'].sudo().create({
            'partner_id': self.socia.id, 'website_id': self.website.id,
            'order_line': [Command.create({'product_id': cojin.id, 'product_uom_qty': 3})],  # $12.84
        })
        canje = orden._dcasa_usar_puntos_web(premio=self.diez)
        linea = orden.order_line.filtered(lambda line: not line.dcasa_canje_id)
        orden._cart_update_line_quantity(linea.id, 2)  # $8.56: ya no cabe un premio de $10
        self.assertEqual(canje.estado, 'cancelado')
        self.assertEqual(self.socia.dcasa_saldo, 1500)
        self.assertIn('por debajo', orden.shop_warning)
        self.assertFalse(orden.order_line.filtered('dcasa_canje_id'))

    def test_un_codigo_vencido_sale_del_carrito(self):
        orden = self.carrito()
        canje = orden._dcasa_usar_puntos_web(premio=self.diez)
        canje._cerrar('vencido', 'Venció', 'sistema')
        aviso = orden._dcasa_limpiar_premios_web()
        self.assertIn('venció', aviso)
        self.assertFalse(orden.order_line.filtered('dcasa_canje_id'))
        self.assertEqual(self.socia.dcasa_saldo, 1500, 'Los puntos volvieron una sola vez')

    def test_cancelar_el_pedido_reversa_el_canje(self):
        orden = self.carrito()
        canje = orden._dcasa_usar_puntos_web(premio=self.diez)
        orden.action_confirm()
        self.assertEqual(canje.estado, 'entregado')
        self.assertEqual(canje.sale_order_id, orden)
        orden._action_cancel()
        self.assertEqual(canje.estado, 'cancelado')
        self.assertEqual(self.socia.dcasa_saldo, 1500)
        reverso = self.reversos(canje)
        self.assertEqual(len(reverso), 1, 'Un reverso, una sola vez')
        self.assertIn(f'Se canceló el pedido {orden.name}', reverso.motivo)
        self.assertIn(f'Se canceló el pedido {orden.name}', canje.cerrado_motivo)

    def test_cancelar_un_carrito_en_borrador_tambien_reversa(self):
        orden = self.carrito()
        canje = orden._dcasa_usar_puntos_web(premio=self.diez)
        orden._action_cancel()
        self.assertEqual(canje.estado, 'cancelado')
        self.assertEqual(self.socia.dcasa_saldo, 1500)

    def test_el_libro_nunca_se_edita(self):
        orden = self.carrito()
        canje = orden._dcasa_usar_puntos_web(premio=self.diez)
        asiento = self.env['dcasa.movimiento'].search([('canje_id', '=', canje.id), ('tipo', '=', 'canje')])
        orden._dcasa_quitar_puntos_web()
        self.assertTrue(asiento.exists(), 'El asiento del canje sigue ahí: se reversó, no se borró')
        self.assertEqual(asiento.puntos, -1000)
        libro = self.env['dcasa.movimiento'].search([('partner_id', '=', self.socia.id)])
        self.assertEqual(sum(libro.mapped('puntos')), self.socia.dcasa_saldo)

    # --- Modo 'todo': puntos sueltos contra cualquier producto -------------------------------

    def test_modo_premios_no_acepta_puntos_sueltos(self):
        with self.assertRaisesRegex(UserError, 'premios del catálogo'):
            self.carrito()._dcasa_usar_puntos_web(puntos=700)
        self.assertEqual(self.carrito()._dcasa_valores_puntos_web()['dcasa_puntos_libres_max'], 0)

    def test_modo_todo_usa_los_puntos_que_el_socio_elige(self):
        self.modo('todo')
        orden = self.carrito()
        valores = orden._dcasa_valores_puntos_web()
        self.assertEqual(valores['dcasa_modo_puntos'], 'todo')
        self.assertEqual(valores['dcasa_puntos_libres_max'], 1500, 'Todo el saldo cabe en un carrito de $214')
        canje = orden._dcasa_usar_puntos_web(puntos=733)
        self.assertEqual(canje.puntos, 733)
        self.assertAlmostEqual(canje.valor, 7.33, msg='100 puntos = $1, redondeado hacia abajo al centavo')
        self.assertEqual(canje.premio_id, self.env.ref('dcasa_socios.premio_libre_web'))
        self.assertIn('733 puntos', canje.premio_nombre)
        self.assertEqual(self.socia.dcasa_saldo, 1500 - 733)
        self.assertAlmostEqual(orden.amount_total, 214.0 - 7.33)
        orden._dcasa_quitar_puntos_web()
        self.assertEqual(self.socia.dcasa_saldo, 1500)

    def test_modo_todo_respeta_minimo_saldo_y_carrito(self):
        self.modo('todo')
        orden = self.carrito()
        with self.assertRaisesRegex(UserError, 'canje mínimo'):
            orden._dcasa_usar_puntos_web(puntos=499)
        with self.assertRaisesRegex(UserError, 'Te faltan'):
            orden._dcasa_usar_puntos_web(puntos=1501)
        with self.assertRaisesRegex(UserError, 'cuántos puntos'):
            orden._dcasa_usar_puntos_web(puntos=0)
        chico = self.carrito(cantidad=1)
        chico.order_line.price_unit = 6.0  # $6.42: caben 642 puntos
        self.assertEqual(chico._dcasa_valores_puntos_web()['dcasa_puntos_libres_max'], 642)
        with self.assertRaisesRegex(UserError, 'mayor que tu carrito'):
            chico._dcasa_usar_puntos_web(puntos=700)
        self.assertEqual(self.socia.dcasa_saldo, 1500)
        chico.order_line.price_unit = 4.0  # $4.28: caben 428, menos que el mínimo de 500
        self.assertEqual(chico._dcasa_valores_puntos_web()['dcasa_puntos_libres_max'], 0)

    def test_modo_todo_se_apaga_sin_la_cifra_en_puntos_json(self):
        self.modo('todo')
        orden = self.carrito()
        with self.reglas_con(canje__puntosPorDolar=None):
            self.assertEqual(orden._dcasa_valores_puntos_web()['dcasa_puntos_libres_max'], 0)
            with self.assertRaisesRegex(UserError, 'no está configurado'):
                orden._dcasa_usar_puntos_web(puntos=700)
            # Los premios del catálogo siguen funcionando.
            self.assertIn(self.diez, orden._dcasa_valores_puntos_web()['dcasa_premios'])

    def test_modo_todo_tambien_acepta_premios_del_catalogo(self):
        self.modo('todo')
        canje = self.carrito()._dcasa_usar_puntos_web(premio=self.diez)
        self.assertEqual(canje.premio_id, self.diez)

    # --- Puntos de la compra web: solo al pagarse la factura --------------------------------

    def test_la_compra_web_suma_puntos_solo_al_pagar(self):
        orden = self.carrito()
        orden._dcasa_usar_puntos_web(premio=self.diez)
        orden.action_confirm()
        Compra = self.env['dcasa.compra']
        self.assertFalse(Compra.search([('partner_id', '=', self.socia.id)]), 'Confirmar no da puntos')
        factura = orden._create_invoices()
        factura.action_post()
        self.assertFalse(Compra.search([('partner_id', '=', self.socia.id)]), 'Facturar sin pagar tampoco')
        self.pagar(factura)
        compra = Compra.search([('partner_id', '=', self.socia.id)])
        self.assertEqual(compra.puntos, 204, 'Puntos sobre lo que de verdad pagó: $204.00, ya con el premio')
        self.assertEqual(self.socia.dcasa_saldo, 500 + 204)

    # --- Cuenta unificada --------------------------------------------------------------------

    def test_resumen_para_el_portal(self):
        resumen = self.usuaria.partner_id._dcasa_resumen_portal()
        self.assertTrue(resumen['es_socio'])
        self.assertEqual(resumen['saldo'], 1500)
        self.assertEqual(resumen['codigo'], self.socia.dcasa_socio_codigo)
        self.assertEqual(resumen['premios_pendientes'], 0)
        self.carrito()._dcasa_usar_puntos_web(premio=self.diez)
        self.assertEqual(self.usuaria.partner_id._dcasa_resumen_portal()['premios_pendientes'], 1)
        self.assertIsNone(self.website.user_id.partner_id._dcasa_resumen_portal(),
                          'El visitante público no tiene ficha')

    # --- Superficie RPC ----------------------------------------------------------------------

    def test_rpc_los_caminos_del_carrito_son_privados(self):
        orden = self.carrito()
        portal = self.env(user=self.usuaria)
        for modelo, metodo, ids, args in (
            ('sale.order', '_dcasa_usar_puntos_web', orden.ids, ()),
            ('sale.order', '_dcasa_quitar_puntos_web', orden.ids, ()),
            ('dcasa.canje', '_pedir', [], (self.socia.id, self.diez.id)),
            ('dcasa.canje', '_cerrar', [], ('cancelado', 'x', 'yo')),
            ('dcasa.movimiento', '_asentar', [], (self.socia.id, 'ajuste', 5000, 'yo')),
        ):
            with self.subTest(metodo=metodo), self.assertRaises(AccessError):
                call_kw(portal[modelo], metodo, [ids, *args], {})
        with self.assertRaises(AccessError):
            call_kw(portal['dcasa.cobrar.premio.wizard'], 'create', [{'order_id': orden.id, 'codigo': 'X'}], {})
        with self.assertRaises(AccessError):
            call_kw(portal['dcasa.premio'], 'write', [self.diez.ids, {'puntos': 1}], {})
        self.assertEqual(self.socia.dcasa_saldo, 1500)

    def test_ninguna_cifra_de_puntos_en_el_codigo(self):
        """Las cifras del programa viven en puntos.json: ni las plantillas ni el código las repiten."""
        raiz = Path(__file__).resolve().parent.parent
        patron = re.compile(r'\b(?:500|250|1\.?000|5\.?000|50\.?000|100)\s+puntos\s*=|\b100\s+puntos\b')
        for archivo in list((raiz / 'views').glob('*.xml')) + list((raiz / 'controllers').glob('*.py')) \
                + list((raiz / 'models').glob('*.py')):
            with self.subTest(archivo=archivo.name):
                self.assertIsNone(patron.search(archivo.read_text(encoding='utf-8')), archivo)


@tagged('post_install', '-at_install')
class TestSociosWebHttp(HttpCase):
    """De punta a punta, como el navegador: catálogo, carrito y la cuenta unificada."""

    def setUp(self):
        super().setUp()
        patcher = patch.dict(os.environ, {'DCASA_PIN_PEPPER': 'pimienta-de-prueba'})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.env = self.env(context=dict(self.env.context, tracking_disable=True))
        self.website = self.env.ref('website.default_website')
        self.itbms = self.env.ref('base.main_company').account_sale_tax_id
        self.producto = self.env['product.product'].create({
            'name': 'CAMA QUEEN WEB', 'type': 'consu', 'invoice_policy': 'order', 'list_price': 100.0,
            'taxes_id': [Command.set(self.itbms.ids)], 'is_published': True,
        })
        self.usuaria = new_test_user(self.env, login='web_socia_http', password=CLAVE, groups='base.group_portal',
                                     name='Socia Web')
        self.socia = self.usuaria.partner_id
        self.socia.write({'phone': '6000-0004'})
        self.socia._dcasa_asegurar_ficha()
        self.socia._dcasa_guardar_pin(PIN)
        self.env['dcasa.movimiento']._asentar(self.socia, 'ajuste', 1500, 'test', motivo='Saldo de prueba')
        self.diez = self.env.ref('dcasa_socios.premio_desc_10')
        self.authenticate(None, None)

    # --- Como el navegador ----------------------------------------------------------------

    def csrf(self):
        return re.search(r'csrf_token: "([^"]+)"', self.url_open('/socios/terminos').text).group(1)

    def post(self, url, **datos):
        datos['csrf_token'] = self.csrf()
        return self.url_open(url, data=datos)

    def entrar_con_pin(self, celular='6000-0004'):
        return self.post('/socios/entrar', celular=celular, pin=PIN)

    def agregar_al_carrito(self, cantidad=2):
        self.make_jsonrpc_request('/shop/cart/add', {
            'product_template_id': self.producto.product_tmpl_id.id, 'product_id': self.producto.id,
            'quantity': cantidad,
        })
        orden = self.env['sale.order'].search([('website_id', '=', self.website.id)], order='id desc', limit=1)
        self.assertTrue(orden)
        return orden

    def refrescar(self):
        self.env.invalidate_all()

    # --- Catálogo ---------------------------------------------------------------------------

    def test_catalogo_publico_de_premios(self):
        pagina = self.url_open('/socios/premios').text
        self.assertIn('$10 de descuento', pagina)
        self.assertIn('1,000', pagina)
        self.assertIn('Entra para pedirlo', pagina)
        self.assertNotIn('Puntos en la tienda web', pagina, 'El premio técnico no sale en el catálogo')
        self.assertIn('/socios/premios', self.url_open('/socios').text, 'La app enlaza al catálogo')

    def test_pedir_desde_el_catalogo_y_recoger_en_tienda(self):
        self.entrar_con_pin()
        catalogo = self.url_open('/socios/premios').text
        self.assertIn('Pedir', catalogo)
        self.assertIn('1,500', catalogo)
        cojin = self.env['dcasa.premio'].create({'name': 'Cojín D’CASA', 'puntos': 600, 'tipo': 'producto',
                                                 'stock_limitado': True, 'stock': 2})
        respuesta = self.post('/socios/canjear', premio_id=cojin.id, volver='premios')
        self.refrescar()
        canje = self.env['dcasa.canje'].search([('partner_id', '=', self.socia.id)])
        self.assertEqual(canje.estado, 'solicitado')
        self.assertEqual(canje.origen, 'app')
        self.assertIn(canje.codigo, respuesta.text)
        self.assertIn('Recógelo en la tienda', respuesta.text)
        self.assertIn('/socios/premios', respuesta.url)
        self.assertEqual(self.socia.dcasa_saldo, 900)
        self.assertEqual(cojin.stock, 1)
        cancelado = self.post(f'/socios/canjes/{canje.codigo}/cancelar', volver='premios')
        self.refrescar()
        self.assertEqual(canje.estado, 'cancelado')
        self.assertEqual(self.socia.dcasa_saldo, 1500)
        self.assertIn('Cancelado', cancelado.text, 'El historial enseña el estado')

    def test_el_premio_tecnico_no_se_pide_desde_la_app(self):
        self.entrar_con_pin()
        respuesta = self.post('/socios/canjear', premio_id=self.env.ref('dcasa_socios.premio_libre_web').id)
        self.assertIn('no se puede pedir', respuesta.text)
        self.refrescar()
        self.assertEqual(self.socia.dcasa_saldo, 1500)

    # --- Carrito ----------------------------------------------------------------------------

    def test_visitante_ve_la_invitacion_en_el_carrito(self):
        self.agregar_al_carrito()
        pagina = self.url_open('/shop/cart').text
        self.assertIn('Entra con tu cuenta de la tienda', pagina)
        self.assertNotIn('Usar mis puntos', pagina)

    def test_socia_con_pin_pero_sin_cuenta_de_la_tienda(self):
        self.entrar_con_pin()
        self.agregar_al_carrito()
        pagina = self.url_open('/shop/cart').text
        self.assertIn('1,500', pagina)
        self.assertIn('pide un premio', pagina)
        self.assertNotIn('Usar mis puntos', pagina)

    def test_usar_y_quitar_puntos_en_el_carrito(self):
        self.authenticate('web_socia_http', CLAVE)
        orden = self.agregar_al_carrito()
        pagina = self.url_open('/shop/cart').text
        self.assertIn('Usar mis puntos', pagina)
        self.assertIn('1,500', pagina)
        self.assertIn('$10 de descuento', pagina)
        respuesta = self.post('/socios/carrito/usar', premio_id=self.diez.id)
        self.assertIn('Tu premio está aplicado', respuesta.text)
        self.assertIn('$10.00 de descuento', respuesta.text)
        self.refrescar()
        canje = self.env['dcasa.canje'].search([('partner_id', '=', self.socia.id)])
        self.assertEqual(canje.origen, 'web')
        self.assertEqual(orden.order_line.filtered('dcasa_canje_id').dcasa_canje_id, canje)
        self.assertAlmostEqual(orden.amount_total, 214.0 - 10.0)
        self.assertEqual(self.socia.dcasa_saldo, 500)
        # La línea del premio no se multiplica por RPC.
        linea = orden.order_line.filtered('dcasa_canje_id')
        resultado = self.make_jsonrpc_request('/shop/cart/update', {'line_id': linea.id, 'quantity': 3})
        self.assertIn('una sola vez', resultado['warning'])
        self.refrescar()
        self.assertEqual(linea.product_uom_qty, 1)
        # Desde la app, ese premio no se cancela: se quita desde el carrito.
        rechazo = self.post(f'/socios/canjes/{canje.codigo}/cancelar')
        self.assertIn('quítalo desde el carrito', rechazo.text)
        quitado = self.post('/socios/carrito/quitar')
        self.assertIn('tus puntos volvieron', quitado.text)
        self.refrescar()
        self.assertEqual(canje.estado, 'cancelado')
        self.assertEqual(self.socia.dcasa_saldo, 1500)
        self.assertFalse(orden.order_line.filtered('dcasa_canje_id'))

    def test_modo_todo_en_el_carrito(self):
        self.env['ir.config_parameter'].sudo().set_param(PARAM_PUNTOS_EN_CARRITO, 'todo')
        self.authenticate('web_socia_http', CLAVE)
        orden = self.agregar_al_carrito()
        pagina = self.url_open('/shop/cart').text
        self.assertIn('usa los puntos que quieras', pagina)
        self.assertIn('name="puntos"', pagina)
        respuesta = self.post('/socios/carrito/usar', puntos='700')
        self.assertIn('$7.00 de descuento', respuesta.text)
        self.refrescar()
        self.assertAlmostEqual(orden.amount_total, 214.0 - 7.0)
        self.assertEqual(self.socia.dcasa_saldo, 800)
        # En modo 'premios' el mismo formulario no existe y la petición se rechaza.
        self.post('/socios/carrito/quitar')
        self.env['ir.config_parameter'].sudo().set_param(PARAM_PUNTOS_EN_CARRITO, 'premios')
        self.assertNotIn('name="puntos"', self.url_open('/shop/cart').text)
        rechazo = self.post('/socios/carrito/usar', puntos='700')
        self.assertIn('premios del catálogo', rechazo.text)
        self.refrescar()
        self.assertEqual(self.socia.dcasa_saldo, 1500)

    # --- Cuenta unificada -------------------------------------------------------------------

    def test_socios_reconoce_la_sesion_de_la_tienda(self):
        self.authenticate('web_socia_http', CLAVE)
        cuenta = self.url_open('/socios')
        self.assertIn('/socios/cuenta', cuenta.url)
        self.assertIn(self.socia.dcasa_socio_codigo, cuenta.text)
        self.assertIn('1,500', cuenta.text)
        self.assertIn('Mi cuenta de la tienda', cuenta.text)
        self.assertEqual(self.env['res.partner'].search_count([('dcasa_celular', '=', '60000004')]), 1,
                         'Una sola ficha: la del usuario de la tienda')

    def test_usuario_de_la_tienda_activa_el_programa_con_pin(self):
        usuario = new_test_user(self.env, login='web_cliente', password=CLAVE, groups='base.group_portal',
                                name='Cliente Web')
        ficha = usuario.partner_id
        ficha.phone = '6000-0005'
        # Ya compró: tiene ficha y puntos esperando, pero no PIN.
        ficha._dcasa_asegurar_ficha()
        self.env['dcasa.movimiento']._asentar(ficha, 'ajuste', 353, 'test', motivo='Compra')
        self.authenticate('web_cliente', CLAVE)
        inicio = self.url_open('/socios').text
        self.assertIn('Activa tus puntos', inicio)
        self.assertIn('6000-0005', inicio)
        facil = self.post('/socios/activar', pin='123456', pin2='123456', acepta='on')
        self.assertIn('fácil de adivinar', facil.text)
        cuenta = self.post('/socios/activar', pin=PIN, pin2=PIN, acepta='on', cumple_dia='14', cumple_mes='2')
        self.assertIn('/socios/cuenta', cuenta.url)
        self.assertIn('353', cuenta.text, 'Sus puntos ya estaban en su misma ficha: no hace falta el código')
        self.refrescar()
        self.assertTrue(ficha.dcasa_reclamada)
        self.assertEqual(ficha.dcasa_celular, '60000005')
        self.assertEqual(ficha.dcasa_cumple, '02-14')
        self.assertEqual(ficha.dcasa_terminos_version, R.VERSION_TERMINOS)
        self.assertEqual(self.env['res.partner'].search_count([('dcasa_celular', '=', '60000005')]), 1)
        # /my enseña el programa.
        my = self.url_open('/my').text
        self.assertIn('Socios D', my)
        self.assertIn('353', my)
        self.assertIn('/socios/cuenta', my)

    def test_usuario_de_la_tienda_sin_celular_valido(self):
        usuario = new_test_user(self.env, login='web_sin_cel', password=CLAVE, groups='base.group_portal',
                                name='Sin Celular')
        self.authenticate('web_sin_cel', CLAVE)
        inicio = self.url_open('/socios').text
        self.assertIn('no tiene un celular', inicio)
        self.assertNotIn('Activa tus puntos', inicio)
        # El celular de otra socia tampoco sirve: un celular, una ficha.
        usuario.partner_id.phone = '6000-0004'
        self.assertIn('no tiene un celular', self.url_open('/socios').text)
        self.assertEqual(self.url_open('/socios/activar', data={'csrf_token': self.csrf(), 'pin': PIN, 'pin2': PIN,
                                                               'acepta': 'on'}).url.split('?')[0].rstrip('/'),
                         self.base_url() + '/socios')
        self.refrescar()
        self.assertFalse(usuario.partner_id.dcasa_reclamada)

    def test_my_invita_a_activar_cuando_no_es_socio(self):
        new_test_user(self.env, login='web_nuevo', password=CLAVE, groups='base.group_portal', name='Nuevo Web')
        self.authenticate('web_nuevo', CLAVE)
        my = self.url_open('/my').text
        self.assertIn('Activar mis puntos', my)
        self.assertIn('href="/socios"', my)

    def test_salir_desde_la_tienda_cierra_la_sesion_de_la_tienda(self):
        self.authenticate('web_socia_http', CLAVE)
        self.assertIn(self.socia.dcasa_socio_codigo, self.url_open('/socios/cuenta').text)
        self.post('/socios/salir')
        self.assertNotIn(self.socia.dcasa_socio_codigo, self.url_open('/socios/cuenta').text)

    # --- Ninguna cifra fuera de puntos.json -----------------------------------------------

    def test_la_equivalencia_del_canje_sale_de_las_reglas(self):
        reglas = R.cargar_reglas()
        reglas['canje']['puntosPorDolar'] = 250
        with patch('odoo.addons.dcasa_socios.models.reglas.cargar_reglas', return_value=reglas):
            self.assertIn('250 puntos = $1', self.url_open('/socios').text)
        self.assertIn('100 puntos = $1', self.url_open('/socios').text)
