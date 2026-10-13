"""Ventas y compras abiertas del sistema anterior: facturas en borrador, órdenes de compra por recibir y la lista de
entregas pendientes. Todo con los ejemplos inventados de la receta."""
from unittest import mock

from odoo.addons.dcasa_base import itbms_de_venta
from odoo.addons.dcasa_migracion import contactos as C
from odoo.addons.dcasa_migracion import documentos as D
from odoo.addons.dcasa_migracion import reglas
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from . import ejemplos


@tagged('post_install', '-at_install')
class TestDocumentosAbiertos(TransactionCase):

    def setUp(self):
        super().setUp()
        C.cargar_clientes(self.env, reglas.filas_clientes(ejemplos.CLIENTES)[0])
        C.cargar_proveedores(self.env, reglas.filas_proveedores(ejemplos.PROVEEDORES)[0])
        self.impuesto_venta = itbms_de_venta(self.env, self.env.company)
        self.impuesto_compra = self.env.company.account_purchase_tax_id
        self.assertTrue(self.impuesto_venta and self.impuesto_compra, 'Se necesitan los impuestos de Panamá')
        Producto = self.env['product.template']
        # PRUEBA-003 no existe a propósito: así se prueba la línea sin producto enlazado.
        for codigo, numero in (('PRUEBA-001', 1), ('PRUEBA-002', 2), ('PRUEBA-004', 4), ('PRUEBA-005', 5)):
            Producto.create({
                'name': f'Producto de Prueba {numero}', 'default_code': codigo, 'type': 'consu',
                'taxes_id': [(6, 0, self.impuesto_venta.ids)],
                'supplier_taxes_id': [(6, 0, self.impuesto_compra.ids)]})
        self.ventas = reglas.filas_ventas_pendientes(ejemplos.VENTAS, ejemplos.VENTAS_LINEAS)[0]
        self.compras = reglas.filas_compras_pendientes(ejemplos.COMPRAS, ejemplos.COMPRAS_LINEAS)[0]

    def _cliente(self, id_viejo):
        return self.env.ref(f'__import__.{C.xmlid_contacto(id_viejo)}')

    def _documento(self, prefijo, numero):
        return self.env.ref(f'__import__.{D._xmlid(prefijo, numero)}')

    # --- ventas por facturar ------------------------------------------------------------------------------------

    def test_ventas_por_facturar_quedan_como_borrador(self):
        resumen = D.cargar_ventas_por_facturar(self.env, self.ventas)
        self.assertEqual(resumen['creados'], ['S99901', 'S99902'])
        self.assertEqual(resumen['sin_pendiente'], ['S99903', 'S99904', 'S99905'])
        self.assertEqual(resumen['con_error'], [])
        factura = self._documento('dcasa_venta', 'S99901')
        self.assertEqual((factura.move_type, factura.state, factura.partner_id, factura.invoice_origin),
                         ('out_invoice', 'draft', self._cliente(90001), 'S99901'))
        self.assertFalse(factura.posted_before, 'En borrador: sin número, sin DGI y sin puntos de Socios')
        self.assertFalse(factura.invoice_date)
        producto, envio = factura.invoice_line_ids
        self.assertEqual((producto.product_id.default_code, producto.quantity, producto.price_unit),
                         ('PRUEBA-001', 2.0, 199.99))
        self.assertEqual((envio.product_id.id, envio.name, envio.quantity, envio.price_unit, envio.tax_ids),
                         (False, 'Servicio de Prueba (entrega)', 1.0, 25.0, self.impuesto_venta))
        self.assertAlmostEqual(factura.amount_total, (2 * 199.99 + 25) * (1 + self.impuesto_venta.amount / 100), 2)

    def test_solo_lo_que_faltaba_por_facturar(self):
        D.cargar_ventas_por_facturar(self.env, self.ventas)
        factura = self._documento('dcasa_venta', 'S99902')
        self.assertEqual([(linea.product_id.default_code, linea.quantity) for linea in factura.invoice_line_ids],
                         [('PRUEBA-002', 1.0)], 'La línea del combo no tenía nada por facturar')

    def test_avisos_de_ventas(self):
        resumen = D.cargar_ventas_por_facturar(self.env, self.ventas)
        self.assertEqual(resumen['sin_producto'], [('S99901', 'ENVIO-PRUEBA')])
        # S99901 se factura completa: su total debe parecerse al de la orden vieja (450). S99902 es parcial: no se
        # compara.
        self.assertEqual([(n, t) for n, t, _ in resumen['total_distinto']], [('S99901', 450.0)])

    def test_volver_a_cargar_no_repite_nada(self):
        D.cargar_ventas_por_facturar(self.env, self.ventas)
        antes = self.env['account.move'].search_count([('invoice_origin', 'in', ['S99901', 'S99902'])])
        resumen = D.cargar_ventas_por_facturar(self.env, self.ventas)
        self.assertEqual((resumen['creados'], resumen['ya_estaban']), ([], ['S99901', 'S99902']))
        self.assertEqual(self.env['account.move'].search_count([('invoice_origin', 'in', ['S99901', 'S99902'])]), antes)

    def test_lo_que_se_borro_se_puede_cargar_de_nuevo(self):
        D.cargar_ventas_por_facturar(self.env, self.ventas)
        self._documento('dcasa_venta', 'S99901').unlink()
        resumen = D.cargar_ventas_por_facturar(self.env, self.ventas)
        self.assertEqual((resumen['creados'], resumen['ya_estaban']), (['S99901'], ['S99902']))

    def test_un_cliente_que_no_esta_cargado_es_un_error_y_no_frena_a_los_demas(self):
        self._cliente(90001).unlink()
        resumen = D.cargar_ventas_por_facturar(self.env, self.ventas)
        self.assertEqual(resumen['creados'], ['S99902'])
        self.assertEqual(len(resumen['con_error']), 1)
        self.assertEqual(resumen['con_error'][0][0], 'S99901')
        self.assertIn('clientes.csv', resumen['con_error'][0][1])

    def test_una_orden_que_falla_no_deja_nada_a_medias(self):
        original = D._linea

        def falla_en_la_primera(env, fila, *args, **kwargs):
            if fila['codigo'] == 'PRUEBA-001':
                raise UserError('línea rechazada')
            return original(env, fila, *args, **kwargs)

        with mock.patch.object(D, '_linea', side_effect=falla_en_la_primera):
            resumen = D.cargar_ventas_por_facturar(self.env, self.ventas)
        self.assertEqual(resumen['creados'], ['S99902'])
        self.assertEqual(resumen['con_error'], [('S99901', 'línea rechazada')])
        self.assertEqual(resumen['sin_producto'], [], 'Los avisos de la orden que falló no cuentan')
        self.assertFalse(self.env['account.move'].search([('invoice_origin', '=', 'S99901')]))
        self.assertFalse(self.env['ir.model.data'].search([('module', '=', '__import__'),
                                                           ('name', '=', 'dcasa_venta_S99901')]))

    # --- ventas por entregar --------------------------------------------------------------------------------------

    def test_las_entregas_pendientes_solo_se_listan(self):
        self.assertEqual(D.entregas_pendientes(self.env, self.ventas), [
            ('S99902', 'Cliente de Prueba 2', [('PRUEBA-002', 1.0)]),
            ('S99903', 'Empresa de Prueba 3 S.A.', [('PRUEBA-003', 1.0)]),
        ])

    # --- compras por recibir --------------------------------------------------------------------------------------

    def test_compras_por_recibir_quedan_confirmadas(self):
        resumen = D.cargar_compras_por_recibir(self.env, self.compras)
        self.assertEqual(resumen['creados'], ['P99904', 'P99905'])
        self.assertEqual(resumen['sin_pendiente'], ['P99901', 'P99902'])
        self.assertEqual([numero for numero, _motivo in resumen['con_error']], ['P99903'])
        orden = self._documento('dcasa_compra', 'P99904')
        self.assertEqual((orden.state, orden.partner_id, orden.origin, str(orden.date_order.date())),
                         ('purchase', self._cliente(70004), 'P99904', '2026-10-02'))
        linea = orden.order_line
        self.assertEqual((linea.product_id.default_code, linea.product_qty, linea.price_unit, linea.tax_ids),
                         ('PRUEBA-004', 25.0, 92.0, self.impuesto_compra))
        self.assertTrue(orden.picking_ids, 'Al confirmar queda la recepción esperando la mercancía')

    def test_una_orden_con_un_producto_que_no_existe_no_se_confirma_y_dice_cual(self):
        resumen = D.cargar_compras_por_recibir(self.env, self.compras)
        (numero, motivo), = resumen['con_error']
        self.assertEqual(numero, 'P99903')
        self.assertIn('PRUEBA-003', motivo)
        self.assertFalse(self.env['purchase.order'].search([('origin', '=', 'P99903')]))

    def test_compra_con_referencia_del_proveedor_y_solo_lo_pendiente(self):
        # P99903 con un producto que sí existe: de las 10 pedidas, 8 ya se recibieron y solo faltan 2.
        orden = dict(self.compras[2], lineas=[dict(self.compras[2]['lineas'][0], codigo='PRUEBA-002')])
        D.cargar_compras_por_recibir(self.env, [orden])
        compra = self._documento('dcasa_compra', 'P99903')
        self.assertEqual(compra.partner_ref, 'FAC-PRUEBA-003')
        (linea,) = compra.order_line
        self.assertEqual((linea.product_id.default_code, linea.product_qty, linea.price_unit),
                         ('PRUEBA-002', 2.0, 98.0))

    def test_compra_ya_facturada_lo_avisa_en_la_nota(self):
        resumen = D.cargar_compras_por_recibir(self.env, self.compras)
        self.assertEqual(resumen['ya_facturadas'], ['P99905'])
        self.assertIn('NO la factures', self._documento('dcasa_compra', 'P99905').note)
        self.assertNotIn('NO la factures', self._documento('dcasa_compra', 'P99904').note)

    def test_compras_por_recibir_no_se_repiten(self):
        D.cargar_compras_por_recibir(self.env, self.compras)
        resumen = D.cargar_compras_por_recibir(self.env, self.compras)
        self.assertEqual((resumen['creados'], resumen['ya_estaban']), ([], ['P99904', 'P99905']))
        self.assertEqual(self.env['purchase.order'].search_count([('origin', 'in', ['P99904', 'P99905'])]), 2)

    # --- compras por facturar -------------------------------------------------------------------------------------

    def test_compras_por_facturar_quedan_como_factura_de_proveedor_en_borrador(self):
        resumen = D.cargar_compras_por_facturar(self.env, self.compras)
        self.assertEqual(resumen['creados'], ['P99901', 'P99903'])
        self.assertEqual(resumen['sin_pendiente'], ['P99902', 'P99904', 'P99905'])
        factura = self._documento('dcasa_factura_compra', 'P99901')
        self.assertEqual((factura.move_type, factura.state, factura.partner_id, factura.ref, factura.invoice_origin),
                         ('in_invoice', 'draft', self._cliente(70001), 'FAC-PRUEBA-001', 'P99901'))
        self.assertEqual([(linea.product_id.default_code, linea.quantity, linea.price_unit)
                          for linea in factura.invoice_line_ids],
                         [('PRUEBA-001', 20.0, 85.5), ('PRUEBA-002', 50.0, 22.0)])
        self.assertFalse(factura.invoice_date, 'La fecha de la factura del proveedor la pone quien la registra')

    def test_avisos_de_compras_por_facturar(self):
        resumen = D.cargar_compras_por_facturar(self.env, self.compras)
        self.assertEqual(resumen['sin_producto'], [('P99903', 'PRUEBA-003')])
        self.assertEqual([(n, t) for n, t, _ in resumen['total_distinto']], [('P99901', 5400.0)])
        sin_numero = D.cargar_compras_por_facturar(self.env, [dict(self.compras[1], lineas=[
            dict(self.compras[0]['lineas'][0], pend_facturar=1.0)])])
        self.assertEqual(sin_numero['sin_referencia'], ['P99902'], 'Hay que ponerle el número del proveedor a mano')

    def test_compras_por_facturar_no_se_repiten(self):
        D.cargar_compras_por_facturar(self.env, self.compras)
        resumen = D.cargar_compras_por_facturar(self.env, self.compras)
        self.assertEqual((resumen['creados'], resumen['ya_estaban']), ([], ['P99901', 'P99903']))

    def test_una_orden_de_compra_y_su_factura_conviven(self):
        """P99903: faltan 2 por recibir y 8 por facturar: una orden y una factura, cada una con su parte."""
        orden = dict(self.compras[2], lineas=[dict(self.compras[2]['lineas'][0], codigo='PRUEBA-002')])
        D.cargar_compras_por_recibir(self.env, [orden])
        D.cargar_compras_por_facturar(self.env, [orden])
        compra = self._documento('dcasa_compra', 'P99903')
        factura = self._documento('dcasa_factura_compra', 'P99903')
        self.assertEqual((compra.order_line.product_qty, factura.invoice_line_ids.quantity), (2.0, 8.0))
