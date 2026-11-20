"""Cuarta revisión adversarial, importante 1: lo que recalcula el SERVIDOR (los precios al cambiar la lista de precios o
la posición fiscal; «Actualizar precios») no marca el carrito de un visitante como «del equipo»; lo que una persona
del equipo TECLEA sigue marcado, y cambiar la lista de precios a mano también (si no, «cambiar la lista y actualizar»
sería un camino sin huella).

Cifras y personas de PRUEBA."""
# ruff: noqa: E501
from unittest.mock import patch

from odoo import Command
from odoo.addons.dcasa_base.models.venta_online import CLAVE_PRECIO
from odoo.addons.dcasa_comision_web.tests.test_vendedoras import VendedoraCommon
from odoo.sql_db import Cursor
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestRecalcularPreciosNoMarcaAlVisitante(VendedoraCommon):

    def setUp(self):
        super().setUp()
        self.publico = self.env.ref('base.public_user')
        self.lista = self.env['product.pricelist'].create({'name': 'Lista de prueba 10 %', 'item_ids': [Command.create({
            'applied_on': '3_global', 'compute_price': 'percentage', 'percent_price': 10})]})

    def carrito(self, producto=None):
        return self.orden(creado_por=self.publico, confirmar=False, lineas=[(producto or self.mueble, 1000.0, 1, {})])

    @staticmethod
    def neto(linea):
        """Lo que paga el cliente por la unidad: con descuentos visibles la lista de precios baja ``discount`` y no el precio."""
        return round(linea.price_unit * (1 - linea.discount / 100.0), 2)

    def cambiar_la_lista_como_la_tienda(self, orden):
        """Lo que hace la tienda cuando el visitante cambia de lista de precios: ella escribe la lista y recalcula."""
        orden.with_user(self.publico).sudo().write({'pricelist_id': self.lista.id})
        orden.with_user(self.publico).sudo()._recompute_prices()

    def test_el_servidor_que_recalcula_los_precios_de_un_visitante_no_lo_marca_como_del_equipo(self):
        for nombre, extra in (('con ITBMS', {}), ('sin ITBMS', {'taxes_id': [Command.set([])]}),
                              ('se factura al pedir', {'invoice_policy': 'order'})):
            with self.subTest(producto=nombre):
                producto = self.env['product.product'].create({
                    'name': 'MUEBLE DE PRUEBA RECALCULO ' + nombre, 'type': 'consu', 'list_price': 1000.0,
                    'taxes_id': [Command.set(self.itbms.ids)], **extra})
                orden = self.carrito(producto)
                self.assertFalse(orden.dcasa_tocada_por_id)
                self.cambiar_la_lista_como_la_tienda(orden)
                self.assertEqual(self.neto(orden.order_line), 900.0, 'el servidor sí recalculó el precio')
                self.assertFalse(orden.dcasa_tocada_por_id, 'recalcular lo hizo el servidor, no una persona del equipo')

    def test_el_descuento_que_pone_la_lista_de_precios_tampoco_cuenta(self):
        """Con descuentos visibles, ``_recompute_prices`` escribe ``discount``: también es del servidor."""
        self.env.user.group_ids += self.env.ref('sale.group_discount_per_so_line')
        orden = self.carrito()
        self.cambiar_la_lista_como_la_tienda(orden)
        self.assertEqual((orden.order_line.price_unit, orden.order_line.discount), (1000.0, 10.0),
                         'el servidor sí escribió el descuento')
        self.assertFalse(orden.dcasa_tocada_por_id)

    def test_un_usuario_interno_que_toca_actualizar_precios_no_marca_el_carrito_si_nadie_cambio_la_lista(self):
        orden = self.carrito()
        # la lista la cambió el visitante (la tienda); el equipo solo toca «Actualizar precios»
        orden.with_user(self.publico).sudo().write({'pricelist_id': self.lista.id})
        for usuario in (self.u_vendedora, self.u_gerencia):
            with self.subTest(usuario=usuario.login):
                orden.with_user(usuario).action_update_prices()
                self.assertEqual(self.neto(orden.order_line), 900.0)
                self.assertFalse(orden.dcasa_tocada_por_id, 'el recálculo es del servidor aunque lo dispare una persona')

    def test_la_venta_de_un_carrito_que_cambio_de_lista_no_sale_como_del_equipo(self):
        self.version(10.0)
        orden = self.orden(creado_por=self.publico, confirmar=False)
        self.cambiar_la_lista_como_la_tienda(orden)
        orden.action_confirm()
        factura = self.facturar(orden)
        self.pagar(factura)
        venta = self.venta(factura)
        self.assertTrue(venta)
        self.assertFalse(venta.creado_por_personal, 'solo un visitante y el servidor: no es alguien del equipo')
        self.assertFalse(venta.tocada_por_id)

    # ------------------------------------------------------------------ lo que una persona TECLEA sigue marcado

    def test_lo_que_una_persona_del_equipo_teclea_a_mano_sigue_marcado(self):
        casos = {
            'precio': {'price_unit': 1.0},
            'descuento': {'discount': 5.0},
            'precio y descuento juntos': {'price_unit': 1.0, 'technical_price_unit': 1.0, 'discount': 5.0},
            'solo el descuento con la llave del servidor en el contexto, mandada por RPC (True)': (
                {'discount': 5.0}, {CLAVE_PRECIO: True}),
            'el precio con la llave en el contexto como texto': ({'price_unit': 1.0}, {CLAVE_PRECIO: 'dcasa_base_precio_del_sistema'}),
        }
        for nombre, caso in casos.items():
            valores, contexto = caso if isinstance(caso, tuple) else (caso, {})
            with self.subTest(caso=nombre):
                orden = self.carrito()
                orden.order_line.with_user(self.u_gerencia).with_context(**contexto).write(valores)
                self.assertEqual(orden.dcasa_tocada_por_id, self.u_gerencia)

    def test_cambiar_la_lista_de_precios_o_la_posicion_fiscal_a_mano_tambien_queda_anotado(self):
        posicion = self.env['account.fiscal.position'].create({'name': 'Posición de prueba'})
        for nombre, valores in (('lista de precios', {'pricelist_id': self.lista.id}),
                                ('posición fiscal', {'fiscal_position_id': posicion.id})):
            with self.subTest(cambio=nombre):
                orden = self.carrito()
                orden.with_user(self.u_gerencia).write(valores)
                self.assertEqual(orden.dcasa_tocada_por_id, self.u_gerencia)

    def test_la_lista_de_precios_que_cambia_un_visitante_o_un_pedido_de_mostrador_no_deja_huella(self):
        orden = self.carrito()
        orden.with_user(self.publico).sudo().write({'pricelist_id': self.lista.id})
        self.assertFalse(orden.dcasa_tocada_por_id)
        tienda = self.orden(web=False, confirmar=False)
        tienda.with_user(self.u_gerencia).write({'pricelist_id': self.lista.id})
        self.assertFalse(tienda.dcasa_tocada_por_id)

    def test_actualizar_precios_despues_de_que_el_equipo_cambio_la_lista_deja_la_huella_del_cambio(self):
        """Quien cambia la lista a mano y luego actualiza: la huella es la del cambio de lista, no la borra el recálculo."""
        orden = self.carrito()
        orden.with_user(self.u_gerencia).write({'pricelist_id': self.lista.id})
        orden.with_user(self.u_gerencia).action_update_prices()
        self.assertEqual(self.neto(orden.order_line), 900.0)
        self.assertEqual(orden.dcasa_tocada_por_id, self.u_gerencia)


@tagged('post_install', '-at_install')
class TestCostoDeVigilarLasLineas(VendedoraCommon):
    """Cuarta revisión, menor 5: cambiar la cantidad de muchas líneas de un pedido de la página «costaba» una consulta por
    línea. No es trabajo de más: el gancho lee el precio de cada línea y Odoo lo recalcula en ese momento en vez de al
    final (con el vaciado final el costo es el mismo con o sin gancho: 77 consultas sin él y 71 con él en 60 líneas). Lo
    que esta prueba cuida es que el gancho no agregue trabajo por línea: el mismo cambio en un pedido de la página y en
    uno de mostrador cuesta lo mismo."""

    LINEAS = 40

    def consultas(self, funcion):
        total = {'n': 0}
        original = Cursor.execute

        def contado(cursor, *args, **kwargs):
            total['n'] += 1
            return original(cursor, *args, **kwargs)
        with patch.object(Cursor, 'execute', contado):
            funcion()
            self.env.flush_all()
        return total['n']

    def pedido(self, web):
        lineas = [(self.mueble, 100.0, 1, {}) for _ in range(self.LINEAS)]
        return self.orden(web=web, confirmar=False, lineas=lineas, creado_por=self.env.ref('base.public_user'))

    def test_cambiar_la_cantidad_de_muchas_lineas_cuesta_lo_mismo_en_un_pedido_de_la_pagina_que_en_uno_de_mostrador(self):
        online, mostrador = self.pedido(True), self.pedido(False)
        con_gancho = self.consultas(lambda: online.order_line.with_user(self.u_gerencia).write({'product_uom_qty': 3}))
        sin_gancho = self.consultas(lambda: mostrador.order_line.with_user(self.u_gerencia).write({'product_uom_qty': 3}))
        self.assertEqual(online.dcasa_tocada_por_id, self.u_gerencia)
        self.assertLessEqual(con_gancho - sin_gancho, 15, f'{con_gancho} consultas en la página y {sin_gancho} en mostrador')
