"""El link del vendedor, su panel y los términos, como los ve el navegador."""
import copy
import os
import re
from datetime import timedelta
from unittest.mock import patch

from odoo import Command
from odoo.tests import HttpCase, tagged

from ..models import reglas as R
from .common import VENDEDORES_DE_PRUEBA

PIN = '482915'


@tagged('post_install', '-at_install')
class TestVendedoresWeb(HttpCase):

    def setUp(self):
        super().setUp()
        patcher = patch.dict(os.environ, {'DCASA_PIN_PEPPER': 'pimienta-de-prueba'})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.env = self.env(context=dict(self.env.context, tracking_disable=True))
        reglas = R.cargar_reglas()
        reglas['vendedores'] = copy.deepcopy(VENDEDORES_DE_PRUEBA)
        self.reglas = reglas
        parche = patch('odoo.addons.dcasa_socios.models.reglas.cargar_reglas', return_value=reglas)
        parche.start()
        self.addCleanup(parche.stop)
        self.website = self.env.ref('website.default_website')
        itbms = self.env.ref('base.main_company').account_sale_tax_id
        self.producto = self.env['product.product'].create({
            'name': 'CAMA QUEEN VENDEDOR', 'type': 'consu', 'invoice_policy': 'order', 'list_price': 100.0,
            'taxes_id': [Command.set(itbms.ids)], 'is_published': True,
        })
        self.ana = self.env['res.partner'].create({'name': 'Ana Vendedora', 'vat': '8-111-111', 'phone': '6100-0001'})
        self.ana._dcasa_afiliar_vendedor('externo', autor='prueba', acepto_terminos=True)
        self.ana._dcasa_guardar_pin(PIN)
        self.authenticate(None, None)

    def texto(self, url):
        """Lo que se lee en la página: sin etiquetas y con los espacios colapsados."""
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', self.url_open(url).text))

    def csrf(self):
        return re.search(r'csrf_token: "([^"]+)"', self.url_open('/vendedores/terminos').text).group(1)

    def post(self, url, **datos):
        datos['csrf_token'] = self.csrf()
        return self.url_open(url, data=datos)

    def entrar(self):
        return self.post('/socios/entrar', celular='6100-0001', pin=PIN)

    def agregar_al_carrito(self):
        self.make_jsonrpc_request('/shop/cart/add', {
            'product_template_id': self.producto.product_tmpl_id.id, 'product_id': self.producto.id, 'quantity': 1})
        orden = self.env['sale.order'].search([('website_id', '=', self.website.id)], order='id desc', limit=1)
        self.assertTrue(orden)
        return orden

    # --- El link -------------------------------------------------------------------------------

    def test_el_link_del_vendedor_deja_el_codigo_en_el_carrito(self):
        respuesta = self.url_open(f'/v/{self.ana.dcasa_vendedor_codigo}')
        self.assertIn('/shop', respuesta.url)
        orden = self.agregar_al_carrito()
        self.assertEqual(orden.dcasa_vendedor_id, self.ana)

    def test_tambien_vale_el_parametro_v_en_cualquier_pagina(self):
        self.url_open(f'/shop?v={self.ana.dcasa_vendedor_codigo.lower()}')
        self.assertEqual(self.agregar_al_carrito().dcasa_vendedor_id, self.ana)

    def test_un_codigo_que_no_existe_o_un_vendedor_suspendido_no_hace_nada(self):
        self.url_open('/v/VENZZZZZZ')
        self.ana.action_dcasa_suspender_vendedor()
        self.url_open(f'/v/{self.ana.dcasa_vendedor_codigo}')
        self.assertFalse(self.agregar_al_carrito().dcasa_vendedor_id)

    # --- El panel --------------------------------------------------------------------------------

    def test_el_panel_pide_sesion_y_ensena_el_codigo_el_link_y_los_puntos(self):
        sin_sesion = self.url_open('/socios/vendedor')
        self.assertTrue(sin_sesion.url.rstrip('/').endswith('/socios'), 'Sin sesión se va a entrar')
        self.entrar()
        self.env['dcasa.vend.movimiento']._asentar(
            self.ana, 'ajuste', 2000, 'prueba', motivo='Saldo de prueba',
            disponible_desde=self.env.cr.now())
        pagina = self.url_open('/socios/vendedor').text
        self.assertIn('Panel de vendedor', pagina)
        self.assertIn(self.ana.dcasa_vendedor_codigo, pagina)
        self.assertIn(f'/v/{self.ana.dcasa_vendedor_codigo}', pagina)
        self.assertIn('2,000', pagina)

    def test_quien_no_es_vendedor_vuelve_a_su_cuenta_de_socio(self):
        persona = self.env['res.partner'].create({'name': 'Solo Socia', 'phone': '6100-0099'})
        persona._dcasa_asegurar_ficha()
        persona._dcasa_guardar_pin(PIN)
        self.post('/socios/entrar', celular='6100-0099', pin=PIN)
        respuesta = self.url_open('/socios/vendedor')
        # /socios/cuenta, o /mi-cuenta/puntos si dcasa_mi_cuenta está instalado (la cuenta del socio vive ahí).
        self.assertTrue(respuesta.url.rstrip('/').endswith(('/socios/cuenta', '/mi-cuenta/puntos')), respuesta.url)

    def test_mi_cuenta_de_socio_enlaza_al_panel_de_vendedor(self):
        self.entrar()
        self.assertIn('/socios/vendedor', self.url_open('/socios/cuenta').text)

    def test_pedir_y_cancelar_un_premio_desde_el_panel(self):
        premio = self.env['dcasa.premio'].create({
            'name': 'Cama box Twin', 'tipo': 'producto', 'puntos': 1500, 'costo': 14.0, 'para_vendedores': True})
        self.env['dcasa.vend.movimiento']._asentar(
            self.ana, 'ajuste', 2000, 'prueba', motivo='Saldo de prueba', disponible_desde=self.env.cr.now())
        self.entrar()
        pagina = self.url_open('/socios/vendedor').text
        self.assertIn('Cama box Twin', pagina)
        respuesta = self.post('/socios/vendedor/canjear', premio_id=premio.id)
        self.env.invalidate_all()
        canje = self.env['dcasa.vend.canje'].search([('partner_id', '=', self.ana.id)])
        self.assertEqual((canje.estado, self.ana.dcasa_vend_saldo), ('solicitado', 500))
        self.assertIn(canje.codigo, respuesta.text)
        respuesta = self.post(f'/socios/vendedor/canjes/{canje.codigo}/cancelar')
        self.env.invalidate_all()
        self.assertEqual((canje.estado, self.ana.dcasa_vend_saldo), ('cancelado', 2000))
        self.assertIn('cancelaste el premio', respuesta.text)

    def test_los_puntos_por_liberar_no_se_pueden_pedir_desde_el_panel(self):
        premio = self.env['dcasa.premio'].create({
            'name': 'Cama box Twin', 'tipo': 'producto', 'puntos': 1500, 'costo': 14.0, 'para_vendedores': True})
        self.env['dcasa.vend.movimiento']._asentar(
            self.ana, 'ajuste', 2000, 'prueba', motivo='Aún por liberar',
            disponible_desde=self.env.cr.now() + timedelta(days=10))
        self.entrar()
        respuesta = self.post('/socios/vendedor/canjear', premio_id=premio.id)
        self.assertIn('Te faltan', respuesta.text)
        self.env.invalidate_all()
        self.assertEqual(self.ana.dcasa_vend_saldo, 2000)

    # --- Los términos ------------------------------------------------------------------------------

    def test_los_terminos_leen_las_reglas_reales(self):
        self.reglas['vendedores']['comision']['puntosPorDolarNeto'] = 4
        self.reglas['vendedores']['retencion']['dias'] = 30
        self.reglas['vendedores']['patrocinio']['topeDeDirectos'] = 3
        pagina = re.sub(r'\s+', ' ', self.url_open('/vendedores/terminos').text)
        self.assertIn('Ganas 4 puntos', pagina)
        self.assertIn('a los 30 días', pagina)
        self.assertIn('(hasta 3)', pagina)
        self.assertIn('un solo nivel', pagina.lower())
        self.assertIn('Ley 81 de 2019', pagina)
        self.assertNotIn('todavía no está encendido', pagina)

    def test_los_terminos_ensenan_la_escalera_si_la_hay(self):
        self.reglas['vendedores']['comision']['escalones'] = [
            {'desdeVentasNetasCentavos': 300000, 'puntosPorDolarNeto': 5, 'topeAlMesPuntos': 30000},
            {'desdeVentasNetasCentavos': 1800000, 'puntosPorDolarNeto': 8, 'topeAlMesPuntos': 90000}]
        pagina = self.texto('/vendedores/terminos')
        self.assertIn('subes de escalón', pagina)
        self.assertIn('Desde $3,000.00 vendidos: 5 puntos por cada dólar, y puedes ganar hasta 30,000 puntos al mes',
                      pagina)
        self.assertIn('Desde $18,000.00 vendidos: 8 puntos', pagina)
        self.assertIn('si dejas de vender, vuelves a bajar', pagina)
        self.reglas['vendedores']['comision']['escalones'] = []
        self.assertNotIn('subes de escalón', self.texto('/vendedores/terminos'))

    def test_el_panel_ensena_el_nivel_y_cuanto_falta_para_el_siguiente(self):
        self.reglas['vendedores']['comision']['escalones'] = [
            {'desdeVentasNetasCentavos': 300000, 'puntosPorDolarNeto': 5, 'topeAlMesPuntos': 30000}]
        self.entrar()
        pagina = self.texto('/socios/vendedor')
        self.assertIn('Tu nivel', pagina)
        self.assertIn('Te faltan $3,000.00 en ventas para ganar 5 puntos por cada $1', pagina)
        self.reglas['vendedores']['comision']['escalones'] = []
        self.assertNotIn('Tu nivel', self.url_open('/socios/vendedor').text)

    def test_los_terminos_avisan_si_el_programa_esta_apagado(self):
        self.reglas['vendedores']['programaActivo'] = False
        self.assertIn('todavía no', self.url_open('/vendedores/terminos').text)
