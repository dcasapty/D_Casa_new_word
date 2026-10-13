"""La lectura de las facturas y los pagos del año, sin base de datos."""
from odoo.addons.dcasa_migracion import reglas_historial as H
from odoo.addons.dcasa_migracion.reglas import ErrorDeArchivo
from odoo.tests import BaseCase, tagged

from . import ejemplos


@tagged('post_install', '-at_install')
class TestLecturaDeFacturas(BaseCase):

    def test_facturas_de_clientes_de_los_cinco_ejemplos(self):
        facturas, errores = H.filas_facturas(ejemplos.FACTURAS_CLIENTES, ejemplos.FACTURAS_CLIENTES_LINEAS, 'cliente')
        self.assertEqual(errores, [])
        self.assertEqual([f['numero'] for f in facturas], [
            'INV/2026/90001', 'INV/2026/90002', 'INV/2026/90003', 'RINV/2026/90001', 'INV/2026/90004'])
        dos = facturas[1]
        self.assertEqual((dos['fecha'], dos['vencimiento'], dos['id_contacto'], dos['base'], dos['impuesto'],
                          dos['total'], dos['saldo'], dos['referencia'], dos['origen']),
                         ('2026-08-15', '2026-09-14', 90002, 250.0, 17.5, 267.5, 167.5, 'FE-0000000001', 'S90002'))
        self.assertFalse(dos['nota'])
        nota = facturas[3]
        self.assertTrue(nota['nota'])
        self.assertEqual((nota['original'], nota['total']), ('INV/2026/90001', 21.4), 'Los montos de la nota van en +')

    def test_las_lineas_traen_el_impuesto_el_descuento_y_la_cuenta(self):
        facturas, _ = H.filas_facturas(ejemplos.FACTURAS_CLIENTES, ejemplos.FACTURAS_CLIENTES_LINEAS, 'cliente')
        (servicio,) = facturas[2]['lineas']
        self.assertEqual((servicio['codigo'], servicio['nombre'], servicio['cantidad'], servicio['precio'],
                          servicio['descuento'], servicio['impuesto'], servicio['subtotal'], servicio['cuenta']),
                         ('', 'Servicio Ejemplo de entrega', 1.0, 50.0, 10.0, 'ITBMS 7% Ventas', 45.0, '000002'))

    def test_facturas_de_proveedores_de_los_cinco_ejemplos(self):
        facturas, errores = H.filas_facturas(
            ejemplos.FACTURAS_PROVEEDORES, ejemplos.FACTURAS_PROVEEDORES_LINEAS, 'proveedor')
        self.assertEqual(errores, [])
        self.assertEqual([(f['numero'], f['id_contacto'], f['referencia']) for f in facturas], [
            ('BILL/2026/90001', 70001, 'FAC-EJ-1001'), ('BILL/2026/90002', 70002, 'FAC-EJ-1002'),
            ('BILL/2026/90003', 70001, ''), ('RBILL/2026/90001', 70001, 'NC-EJ-0001'),
            ('BILL/2026/90004', 70005, 'PI-EJ-0004')])
        self.assertEqual(facturas[1]['lineas'][0]['impuesto'], '', 'Una línea sin impuesto es una línea exenta')
        self.assertEqual(facturas[3]['original'], 'BILL/2026/90001')

    def test_el_id_externo_no_lleva_barras(self):
        self.assertEqual(H.xmlid_factura('INV/2026/00123'), 'dcasa_factura_INV_2026_00123')

    def test_facturas_con_problemas(self):
        facturas, errores = H.filas_facturas(
            'numero,id_cliente_viejo,total,tipo,fecha\n'
            'A1,5,10,,2026-01-01\n,6,10,,2026-01-01\nA3,abc,10,,2026-01-01\nA1,5,10,,2026-01-01\n'
            'A5,5,10,devolucion,2026-01-01\nA6,5,10,,2026-13-45\nA7,5,10,,\nA8,5,10,,2026-01-01\n',
            'numero,cantidad,precio_unitario\nA1,1,10\nA9,1,10\nA3,1,10\n', 'cliente')
        self.assertEqual([f['numero'] for f in facturas], ['A1'])
        motivos = ' | '.join(f'{numero}: {motivo}' for numero, motivo in errores)
        for texto in ('fila 3', 'A3: el número del cliente', 'A1: la factura aparece dos veces', 'A5: el tipo',
                      'A6: una fecha', 'A7: le falta la fecha', 'A8: la factura no tiene líneas', 'A9: una línea'):
            self.assertIn(texto, motivos)
        self.assertNotIn('A3: una línea', motivos, 'Las líneas de una factura ya rechazada no se reportan otra vez')

    def test_faltan_columnas(self):
        with self.assertRaisesRegex(ErrorDeArchivo, 'facturas_proveedores_lineas.csv'):
            H.filas_facturas('numero,id_proveedor_viejo,total\nB1,7,10\n', 'numero,cantidad\nB1,1\n', 'proveedor')
        with self.assertRaisesRegex(ErrorDeArchivo, 'id_proveedor_viejo'):
            H.filas_facturas('numero,id_cliente_viejo,total\nB1,7,10\n', 'numero,cantidad,precio_unitario\n',
                             'proveedor')

    def test_un_numero_mal_escrito_dice_en_que_fila(self):
        with self.assertRaisesRegex(ErrorDeArchivo, 'Fila 3: «caro»'):
            H.filas_facturas('numero,id_cliente_viejo,total,fecha\nA1,5,10,2026-01-01\nA2,5,caro,2026-01-01\n',
                             'numero,cantidad,precio_unitario\nA1,1,10\n', 'cliente')


@tagged('post_install', '-at_install')
class TestLecturaDePagos(BaseCase):

    def test_los_cinco_pagos_de_ejemplo(self):
        pagos, errores = H.filas_pagos(ejemplos.PAGOS)
        self.assertEqual(errores, [])
        self.assertEqual([(p['rol'], p['id_contacto'], p['monto'], p['diario'], p['conciliado']) for p in pagos], [
            ('cliente', 90001, 107.0, 'Caja Ejemplo', True), ('cliente', 90002, 100.0, 'Banco Ejemplo', False),
            ('proveedor', 70002, 6000.0, 'Banco Ejemplo', True), ('proveedor', 70001, 5350.0, 'Banco Ejemplo', True),
            ('cliente', 90004, 1284.0, 'Banco Ejemplo', False)])
        self.assertEqual(pagos[4]['facturas'], ['INV/2026/90004', 'INV/2026/90005'], 'Un pago puede pagar varias')
        self.assertEqual((pagos[2]['metodo'], pagos[2]['referencia']), ('Transferencia', 'Abono FAC-EJ-1002'))

    def test_la_clave_es_estable_y_distingue_filas_identicas(self):
        fila = '2026-08-03,cobro,90001,107,USD,Caja,Manual,R1,INV/1,conciliado\n'
        cabecera = 'fecha,tipo,id_contacto_viejo,monto,moneda,diario,metodo,referencia,facturas_que_paga,estado\n'
        uno, _ = H.filas_pagos(cabecera + fila + fila)
        otra_vez, _ = H.filas_pagos(cabecera + fila + fila)
        self.assertEqual([p['clave'] for p in uno], [p['clave'] for p in otra_vez])
        self.assertEqual(len({p['clave'] for p in uno}), 2, 'Dos pagos iguales siguen siendo dos pagos')

    def test_pagos_con_problemas(self):
        pagos, errores = H.filas_pagos(
            'fecha,tipo,id_contacto_viejo,monto,estado\n'
            '2026-08-03,regalo,1,5,\n2026-08-03,cobro,abc,5,\n2026-13-45,cobro,1,5,\n2026-08-03,cobro,1,0,\n'
            '2026-08-03,cobro,1,,\n2026-08-03,cobro,1,5,\n2026-08-03,pago,2,7.5,conciliado\n')
        self.assertEqual([(p['rol'], p['monto'], p['conciliado']) for p in pagos],
                         [('cliente', 5.0, False), ('proveedor', 7.5, True)], 'Lo dudoso cuenta como sin conciliar')
        motivos = ' | '.join(f'{fila}: {motivo}' for fila, motivo in errores)
        for texto in ('fila 2: el tipo', 'fila 3: el número del contacto', 'fila 4: la fecha',
                      'fila 5: el monto', 'fila 6: el monto'):
            self.assertIn(texto, motivos)
        self.assertEqual(len(errores), 5)
