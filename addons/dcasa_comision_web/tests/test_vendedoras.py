"""Las vendedoras NUNCA reciben nada por una venta online (decisión de Gerencia, 2026-11-19): ni el bono por meta, ni el
avance de su Inicio, ni la comisión del programa de vendedores. Solo hacia adelante: desde el día de la primera versión
de las reglas de la comisión web. Lo de la tienda, y lo de Juan que atiende una vendedora, sigue contando como hoy."""
import os
from datetime import date
from unittest.mock import patch

from odoo.addons.dcasa_socios.tests.common import SociosCommon
from odoo.tests import tagged

from .test_comision import ComisionReloj

MARZO = date(2030, 3, 1)


class VendedoraCommon(ComisionReloj):
    """Una vendedora del departamento de Ventas, con su meta (1,000 y 1 %: cifras de PRUEBA)."""

    def setUp(self):
        super().setUp()
        self.env['dcasa.nomina.meta.regla'].create({
            'company_id': self.company.id, 'fecha_desde': '2030-01-01', 'meta_mensual': 1000, 'porcentaje': 1,
            'meta_diaria': 100})
        ventas = self.env['hr.department'].create({'name': 'Ventas prueba comisión', 'dcasa_meta_ventas': True,
                                                   'company_id': self.company.id})
        self.vera = self._empleado('Vera Comisión', 1200, '2029-01-01', department_id=ventas.id,
                                   user_id=self.u_vendedora.id)
        self.Bono = self.env['dcasa.nomina.meta.bono']

    def bono(self):
        return self.Bono._calcular(self.vera, MARZO, self.company)

    def vender(self, web, pago='2030-03-05', precio=1000.0, **extra):
        """Un pedido de la vendedora, facturado y pagado el día ``pago``."""
        factura = self.facturar(self.orden(web=web, vendedora=self.u_vendedora,
                                           lineas=[(self.mueble, precio, 1, {})], **extra), pago)
        self.pagar(factura, pago)
        return factura


@tagged('post_install', '-at_install')
class TestBonoPorMeta(VendedoraCommon):

    def test_sin_reglas_de_la_comision_todo_cuenta_como_siempre(self):
        self.vender(web=True)
        self.vender(web=False)
        self.assertFalse(self.env['dcasa.web.reglas'].search([]))
        self.assertEqual(self.bono().cobrado, 2000.0, 'sin la primera versión nada cambia')

    def test_una_venta_online_cobrada_desde_la_primera_version_no_cuenta_y_la_de_la_tienda_si(self):
        self.version(10.0)
        self.vender(web=True)
        tienda = self.vender(web=False)
        bono = self.bono()
        self.assertEqual(bono.cobrado, 1000.0)
        self.assertEqual(bono.factura_ids, tienda)
        self.assertTrue(bono.cumplio)

    def test_lo_ya_cobrado_antes_de_la_primera_version_cuenta_como_siempre_y_sus_devoluciones_restan(self):
        antes = self.vender(web=True, pago='2030-03-03')       # online, pero cobrada antes de la regla
        self.version(10.0)                                      # la regla rige desde el 4
        despues = self.vender(web=True, pago='2030-03-05')
        self.nota(antes, 300.0, fecha='2030-03-06')
        self.nota(despues, 500.0, fecha='2030-03-06')
        bono = self.bono()
        self.assertEqual(bono.factura_ids, antes, 'solo la de antes de la regla')
        self.assertEqual(bono.cobrado, 700.0, '1,000 de antes menos 300 de su nota; la nota de la otra no resta')
        self.assertEqual(len(bono.nota_ids), 1)

    def test_una_factura_que_junta_lo_online_con_la_tienda_cuenta_solo_lo_de_la_tienda(self):
        self.version(10.0)
        web = self.orden(web=True, vendedora=self.u_vendedora, lineas=[(self.mueble, 1000.0, 1, {})])
        tienda = self.orden(web=False, vendedora=self.u_vendedora, lineas=[(self.mueble, 500.0, 1, {})])
        factura = (web | tienda)._create_invoices()
        factura.invoice_date = '2030-03-05'
        factura.action_post()
        self.pagar(factura, '2030-03-05')
        self.assertEqual(self.bono().cobrado, 500.0)

    def test_juan_y_una_vendedora_que_lo_atiende_si_cuenta_para_ella(self):
        self.version(10.0)
        self.hablar(self.cliente, 'vendedora', hace_dias=1)
        orden = self.orden(web=True, vendedora=self.u_vendedora)
        self.assertFalse(orden.dcasa_venta_online)
        factura = self.facturar(orden, '2030-03-05')
        self.pagar(factura, '2030-03-05')
        self.assertEqual(self.bono().cobrado, 1000.0, 'la llevó ella: sigue siendo de la vendedora')
        self.assertFalse(self.venta(factura), 'y no es venta online del sitio')

    def test_andres_que_pasa_al_cliente_a_la_vendedora_que_escribe_y_cierra_es_de_ella(self):
        """Decisión del 2026-11-20: si la vendedora atiende (le escribió por el chat de Juan) y cierra, lo recibe ella
        como hoy en su bono; ya no manda Andrés."""
        self.version(10.0)
        self.hablar(self.cliente, 'vendedora', hace_dias=1)
        orden = self.orden(web=True, vendedora=self.u_vendedora, confirmar=False)
        orden._dcasa_escribir_marca(dcasa_via_andres=True)
        orden.action_confirm()
        factura = self.facturar(orden, '2030-03-05')
        self.pagar(factura, '2030-03-05')
        self.assertEqual(self.bono().cobrado, 1000.0)

    def test_el_carrito_de_andres_que_ella_solo_confirma_sin_escribir_por_juan_no_le_suma(self):
        """El caso gris (documentado): sin mensaje suyo por el chat de Juan, confirmar no basta para que sea de ella."""
        self.version(10.0)
        orden = self.orden(web=True, vendedora=self.u_vendedora, confirmar=False)
        orden._dcasa_escribir_marca(dcasa_via_andres=True)
        orden.action_confirm()
        factura = self.facturar(orden, '2030-03-05')
        self.pagar(factura, '2030-03-05')
        self.assertEqual(self.bono().cobrado, 0.0)

    def test_el_pedido_de_la_pagina_que_ella_confirma_no_le_suma_a_su_meta(self):
        """La vendedora que confirma un pedido de la página se lo queda (user_id), pero no cuenta."""
        self.version(10.0)
        factura = self.vender(web=True)
        self.assertEqual(factura.invoice_user_id, self.u_vendedora)
        self.assertEqual(self.bono().cobrado, 0.0)


@tagged('post_install', '-at_install')
class TestInicioDeLaVendedora(VendedoraCommon):

    def test_el_avance_del_inicio_no_cuenta_lo_online(self):
        self.version(10.0)
        self.vender(web=True)
        self.vender(web=False, precio=500.0)
        tarjeta = self.Bono._para_inicio(self.u_vendedora, date(2030, 3, 10))
        self.assertEqual(tarjeta['avance_real'], 50, 'solo los 500 de la tienda de una meta de 1,000')

    def test_sin_las_reglas_el_avance_es_el_de_siempre(self):
        self.vender(web=True)
        tarjeta = self.Bono._para_inicio(self.u_vendedora, date(2030, 3, 10))
        self.assertEqual(tarjeta['avance_real'], 100)

    def test_vendido_hoy_de_la_vendedora_no_trae_las_ventas_online(self):
        Orden = self.env['sale.order']
        antes = self.vender(web=True, pago='2030-03-03')
        self.version(10.0)
        online = self.vender(web=True)
        tienda = self.vender(web=False)
        dominio = Orden._dcasa_dominio_vendido(vendedor=self.u_vendedora)
        vendidas = Orden.search(dominio)
        pedido = lambda f: f.line_ids.sale_line_ids.order_id  # noqa: E731
        self.assertEqual(vendidas, pedido(antes) | pedido(tienda))
        self.assertNotIn(pedido(online), vendidas)
        sin_filtro = Orden.search(Orden._dcasa_dominio_vendido())
        self.assertIn(pedido(online), sin_filtro, 'lo de toda la tienda sigue completo')

    def test_el_inicio_de_gerencia_atribuye_lo_online_a_sin_vendedora(self):
        Tablero = self.env['dcasa.tablero']
        self.version(10.0)
        online = self.vender(web=True)
        tienda = self.vender(web=False)
        nota = self.nota(online, 100.0, fecha='2030-03-05')
        duenas = Tablero._duenas(online | tienda | nota)
        self.assertEqual(duenas[online.id], ('sin', False))
        self.assertEqual(duenas[tienda.id], (self.u_vendedora.id, True))
        self.assertEqual(duenas[nota.id], ('sin', False), 'su nota es de la misma dueña')

    def test_gerencia_filtra_por_vendedora_y_por_sin_vendedora(self):
        Orden = self.env['sale.order']
        Tablero = self.env['dcasa.tablero']
        self.version(10.0)
        online = self.vender(web=True)
        tienda = self.vender(web=False)
        pedido = lambda f: f.line_ids.sale_line_ids.order_id  # noqa: E731
        de_ella = Orden.search(Orden._dcasa_dominio_vendido() + Tablero._clausula_vendedor(self.u_vendedora.id))
        self.assertEqual(de_ella, pedido(tienda))
        sin = Orden.search(Orden._dcasa_dominio_vendido() + Tablero._clausula_vendedor('sin'))
        self.assertEqual(sin, pedido(online))
        medida = {'pedidos': Orden.search(Orden._dcasa_dominio_vendido())}
        por_vendedora = Tablero._por_vendedora(medida)
        self.assertEqual(por_vendedora[self.u_vendedora.id][0], 1)
        self.assertEqual(por_vendedora['sin'][0], 1)


@tagged('post_install', '-at_install')
class TestProgramaDeVendedores(ComisionReloj):
    """La compra con código VEN da la comisión de vendedor de siempre aunque sea online (decisión del 2026-11-20); una
    venta online SIN código no la da; la de la tienda sí, y lo cobrado antes de la regla, también."""

    activar_vendedores = SociosCommon.activar_vendedores
    vendedor = SociosCommon.vendedor

    def setUp(self):
        super().setUp()
        entorno = patch.dict(os.environ, {'DCASA_PIN_PEPPER': 'pimienta-de-prueba'})
        entorno.start()
        self.addCleanup(entorno.stop)
        self.activar_vendedores()
        self.codigo = self.vendedor('Vendedor Código', '8-901-234', '6100-0901')

    def comision(self, factura):
        return self.env['dcasa.vend.comision'].search([('move_id', '=', factura.id), ('tipo', '=', 'directa')])

    def con_codigo(self, web, pago, cliente=None):
        factura = self.facturar(self.orden(web=web, cliente=cliente, dcasa_vendedor_id=self.codigo.id), pago)
        self.pagar(factura, pago)
        return factura

    def sin_codigo(self, web, pago, cliente=None):
        factura = self.facturar(self.orden(web=web, cliente=cliente), pago)
        self.pagar(factura, pago)
        return factura

    def ligar_al_cliente(self):
        """El cliente queda ligado al vendedor con una compra de la tienda con su código (así sus compras sin código
        también serían de él, si no fueran online)."""
        self.reglas['vendedores']['vinculacion']['meses'] = 12
        antes = self.con_codigo(web=False, pago='2030-03-01')
        self.assertEqual(self.cliente.dcasa_vendedor_ligado_id, self.codigo)
        return antes

    def test_sin_las_reglas_de_la_comision_web_se_paga_como_siempre(self):
        factura = self.con_codigo(web=True, pago='2030-03-04')
        self.assertEqual((self.comision(factura).resultado, bool(self.comision(factura).puntos)), ('pagada', True))

    def test_una_venta_online_con_codigo_ven_paga_igual_que_antes_y_ademas_cuenta_para_el_sitio(self):
        self.version(10.0)
        otro = self.env['res.partner'].create({'name': 'Otro cliente VEN', 'phone': '+507 6555-0398',
                                               'email': 'otro.ven@example.com'})
        tienda = self.comision(self.con_codigo(web=False, pago='2030-03-04', cliente=otro))
        online = self.con_codigo(web=True, pago='2030-03-04')
        comision = self.comision(online)
        self.assertEqual((comision.resultado, comision.puntos), ('pagada', tienda.puntos))
        self.assertGreater(comision.puntos, 0, 'lo mismo que da la tienda')
        self.assertTrue(self.env['dcasa.vend.movimiento'].search([('partner_id', '=', self.codigo.id)]))
        venta = self.env['dcasa.web.venta'].search([('move_id', '=', online.id)])
        self.assertEqual(venta.comision_centavos, 10000, 'y además la comisión del sitio: la empresa paga las dos')

    def test_una_venta_online_sin_codigo_no_paga_a_ninguna_vendedora(self):
        """El cliente está ligado a un vendedor de antes, compra por la página SIN código: no da comisión a nadie."""
        self.ligar_al_cliente()
        self.version(10.0)
        online = self.sin_codigo(web=True, pago='2030-03-04')
        comision = self.comision(online)
        self.assertEqual((comision.resultado, comision.puntos), ('venta-online', 0))
        self.assertIn('venta del sitio web', dict(comision._fields['resultado'].selection)['venta-online'])
        recompra_en_tienda = self.sin_codigo(web=False, pago='2030-03-04')
        self.assertEqual(self.comision(recompra_en_tienda).resultado, 'pagada', 'la de la tienda sigue igual')

    def test_la_venta_de_la_tienda_con_codigo_si_da_comision(self):
        self.version(10.0)
        tienda = self.con_codigo(web=False, pago='2030-03-04')
        self.assertEqual((self.comision(tienda).resultado, bool(self.comision(tienda).puntos)), ('pagada', True))

    def test_lo_cobrado_antes_de_la_primera_version_se_pago_como_siempre(self):
        self.avanzar('2030-03-03 15:00:00')
        antes = self.con_codigo(web=True, pago='2030-03-03')
        self.avanzar('2030-03-04 15:00:00')
        self.version(10.0)
        self.assertEqual(self.comision(antes).resultado, 'pagada', 'ya estaba pagada: nada es retroactivo')
        despues = self.con_codigo(web=True, pago='2030-03-04')
        self.assertEqual(self.comision(despues).resultado, 'pagada', 'con código sigue pagando también online')

    def factura_mixta(self, **extra):
        web = self.orden(web=True, lineas=[(self.mueble, 1000.0, 1, {})], **extra)
        tienda = self.orden(web=False, lineas=[(self.mueble, 500.0, 1, {})], **extra)
        factura = (web | tienda)._create_invoices()
        factura.invoice_date = '2030-03-04'
        factura.action_post()
        self.pagar(factura, '2030-03-04')
        return factura

    def test_una_factura_mixta_con_codigo_comisiona_todo(self):
        self.version(10.0)
        comision = self.comision(self.factura_mixta(dcasa_vendedor_id=self.codigo.id))
        self.assertEqual(comision.resultado, 'pagada')
        self.assertEqual(comision.neto_centavos, 150000, 'con el código, la parte online también cuenta')

    def test_una_factura_mixta_sin_codigo_comisiona_solo_la_parte_de_la_tienda(self):
        self.ligar_al_cliente()
        self.version(10.0)
        comision = self.comision(self.factura_mixta())
        self.assertEqual(comision.resultado, 'pagada')
        self.assertEqual(comision.neto_centavos, 50000, 'solo los 500 de la tienda')
