"""La lectura de los CSV de la receta, sin base de datos."""
from odoo.addons.dcasa_migracion import reglas as R
from odoo.tests import BaseCase, tagged

from . import ejemplos


@tagged('post_install', '-at_install')
class TestLecturaDeArchivos(BaseCase):

    def test_utf8_con_o_sin_bom(self):
        self.assertEqual(R.texto_de_bytes('ñandú'.encode()), 'ñandú')
        self.assertEqual(R.texto_de_bytes(ejemplos.como_bytes(ejemplos.CLIENTES)), ejemplos.CLIENTES.lstrip('﻿'))

    def test_un_archivo_que_no_es_utf8_se_rechaza_con_un_texto_claro(self):
        with self.assertRaisesRegex(R.ErrorDeArchivo, 'UTF-8'):
            R.texto_de_bytes('ñandú'.encode('latin-1'))

    def test_falta_una_columna(self):
        with self.assertRaisesRegex(R.ErrorDeArchivo, 'columna «id_viejo»'):
            R.filas_clientes('nombre,celular\nAna,6000-0001\n')

    def test_archivo_vacio(self):
        with self.assertRaisesRegex(R.ErrorDeArchivo, 'vacío'):
            R.filas_clientes('   \n')

    def test_acepta_punto_y_coma(self):
        filas, errores = R.filas_clientes('id_viejo;nombre;celular\n1;Ana de Prueba;6000-0001\n')
        self.assertEqual((len(filas), errores), (1, []))
        self.assertEqual(filas[0]['telefono'], '6000-0001')

    def test_un_numero_mal_escrito_dice_en_que_fila(self):
        with self.assertRaisesRegex(R.ErrorDeArchivo, 'Fila 3: «doce»'):
            R.existencias_por_codigo('codigo_producto,cantidad\nA,1\nB,doce\n')


@tagged('post_install', '-at_install')
class TestTelefonos(BaseCase):

    def test_un_solo_numero_se_deja_tal_cual(self):
        for texto in ('6000-0001', '+507 6000-0002', '60000003'):
            with self.subTest(texto=texto):
                self.assertEqual(R.separar_telefonos(texto), (texto, []))

    def test_dos_numeros_el_primero_es_el_principal_y_el_resto_no_se_pierde(self):
        self.assertEqual(R.separar_telefonos('60000005/2000005'), ('60000005', ['2000005']))
        self.assertEqual(R.separar_telefonos('6000-0001 y 2000002'), ('6000-0001', ['2000002']))
        self.assertEqual(R.separar_telefonos('2000002, 6000-0001'), ('2000002', ['6000-0001']))

    def test_vacio_o_sin_cifras(self):
        self.assertEqual(R.separar_telefonos(''), ('', []))
        self.assertEqual(R.separar_telefonos(None), ('', []))
        self.assertEqual(R.separar_telefonos('sin telefono'), ('sin telefono', []))


@tagged('post_install', '-at_install')
class TestFilasDeClientes(BaseCase):

    def test_los_cinco_ejemplos(self):
        filas, errores = R.filas_clientes(ejemplos.CLIENTES)
        self.assertEqual(errores, [])
        self.assertEqual([f['id_viejo'] for f in filas], [90001, 90002, 90003, 90004, 90005])
        persona, con_correo, empresa, vacio, dos_telefonos = filas
        self.assertFalse(persona['es_empresa'])
        self.assertEqual((persona['vat'], persona['dv'], persona['telefono'], persona['correo']),
                         ('0-000-0001', '', '6000-0001', ''))
        self.assertEqual((con_correo['correo'], con_correo['direccion'], con_correo['ciudad']),
                         ('prueba2@ejemplo.com', 'Calle Ficticia 2', 'Ciudad de Prueba'))
        self.assertTrue(empresa['es_empresa'])
        self.assertEqual((empresa['dv'], empresa['direccion']), ('99', 'Edificio Prueba, Local 3'))
        self.assertEqual((vacio['vat'], vacio['telefono'], vacio['correo']), ('', '', ''))
        self.assertEqual(dos_telefonos['telefono'], '60000005')
        self.assertEqual(dos_telefonos['notas'], ['Otros teléfonos en el sistema anterior: 2000005'])

    def test_filas_que_no_se_cargan(self):
        texto = ('id_viejo,nombre\n'
                 'abc,Sin Numero\n'
                 '10,\n'
                 '11,Ana de Prueba\n'
                 '11,Ana de Prueba Otra Vez\n')
        filas, errores = R.filas_clientes(texto)
        self.assertEqual([f['id_viejo'] for f in filas], [11])
        self.assertEqual(len(errores), 3)
        motivos = ' | '.join(e[2] for e in errores)
        self.assertIn('no es un entero', motivos)
        self.assertIn('no tiene nombre', motivos)
        self.assertIn('dos veces', motivos)

    def test_correo_o_dv_mal_escritos_no_se_pierden_van_a_las_notas(self):
        filas, _ = R.filas_clientes('id_viejo,nombre,correo,dv\n1,Ana de Prueba,no-es-correo,9X\n')
        self.assertEqual((filas[0]['correo'], filas[0]['dv']), ('', ''))
        self.assertEqual(filas[0]['notas'], ['Correo mal escrito en el sistema anterior: no-es-correo',
                                             'DV mal escrito en el sistema anterior: 9X'])

    def test_espacios_de_mas_en_el_nombre(self):
        filas, _ = R.filas_clientes('id_viejo,nombre\n1,  Ana   de   Prueba \n')
        self.assertEqual(filas[0]['nombre'], 'Ana de Prueba')


@tagged('post_install', '-at_install')
class TestFilasDeCatalogo(BaseCase):

    def test_existencias_por_codigo_suma_y_separa_las_que_no_tienen_codigo(self):
        por_codigo, sin_codigo = R.existencias_por_codigo(
            "codigo_producto,cantidad,bodega\nA,2,x\nA,3.5,y\n,7,x\nB,-1,x\nC,,x\n")
        self.assertEqual(por_codigo, {'A': 5.5, 'B': -1.0})
        self.assertEqual(sin_codigo, [7.0])

    def test_los_cinco_ejemplos_de_productos_con_inventario(self):
        filas, avisos = R.filas_catalogo(ejemplos.PRODUCTOS, ejemplos.INVENTARIO)
        self.assertEqual([f['llave'] for f in filas],
                         ['PRUEBA-001', 'PRUEBA-002', 'Producto de Prueba 3', 'PRUEBA-005'])
        uno, dos, sin_codigo, combo = filas
        self.assertEqual((uno['precio'], uno['costo'], uno['a_la_mano']), (199.99, 120.0, 12.0))
        self.assertEqual((dos['precio'], dos['costo'], dos['a_la_mano']), (45.5, 28.75, 3.0))
        # costo 0 = «no se registró»: no se usa; sin código no se toca la existencia
        self.assertEqual((sin_codigo['precio'], sin_codigo['costo'], sin_codigo['a_la_mano']), (89.0, None, None))
        self.assertEqual((combo['precio'], combo['costo'], combo['a_la_mano']), (350.0, None, 1.5))
        self.assertEqual(avisos['archivados'], 1)
        self.assertEqual(avisos['sin_codigo'], ['Producto de Prueba 3'])
        self.assertEqual(avisos['existencias_sin_codigo'], [7.0])
        self.assertEqual(avisos['huerfanos'], [('PRUEBA-004', -2.0)], 'Un producto archivado con existencias')

    def test_sin_inventario_no_se_toca_ninguna_existencia(self):
        filas, avisos = R.filas_catalogo(ejemplos.PRODUCTOS)
        self.assertTrue(filas)
        self.assertTrue(all(f['a_la_mano'] is None for f in filas))
        self.assertEqual(avisos['huerfanos'], [])

    def test_un_producto_con_codigo_que_no_esta_en_el_inventario_queda_en_cero(self):
        productos = 'codigo,nombre,activo\nX1,Mesa de Prueba,si\n'
        filas, _ = R.filas_catalogo(productos, 'codigo_producto,cantidad\nOTRO,5\n')
        self.assertEqual(filas[0]['a_la_mano'], 0.0)


@tagged('post_install', '-at_install')
class TestProveedoresYPrecios(BaseCase):

    def test_proveedores_con_las_columnas_reales_ruc_telefono_y_pais(self):
        filas, errores = R.filas_proveedores(ejemplos.PROVEEDORES)
        self.assertEqual((len(filas), errores), (5, []))
        uno, china, persona, sin_datos, eeuu = filas
        self.assertTrue(uno['es_empresa'])
        self.assertEqual((uno['vat'], uno['dv'], uno['telefono'], uno['pais']),
                         ('0000000-0-000001', '99', '200-0001', 'Panamá'))
        self.assertEqual((china['vat'], china['telefono'], china['pais']),
                         ('PRUEBA-0002', '+86 000 0000 0002', 'China'))
        self.assertFalse(persona['es_empresa'])
        self.assertEqual((sin_datos['telefono'], sin_datos['pais'], sin_datos['correo']), ('', '', ''))
        self.assertEqual((eeuu['vat'], eeuu['pais']), ('', 'Estados Unidos'))

    def test_el_error_de_columna_nombra_el_archivo(self):
        with self.assertRaisesRegex(R.ErrorDeArchivo, 'A proveedores.csv le falta la columna'):
            R.filas_proveedores('nombre\nAna\n')

    def test_precios_con_todas_las_columnas_de_la_receta(self):
        filas, errores = R.filas_precios_proveedor(ejemplos.PRECIOS)
        self.assertEqual(errores, [])
        self.assertEqual([(f['id_proveedor_viejo'], f['codigo'], f['nombre'], f['precio'], f['cantidad_minima'])
                          for f in filas], [
            (70001, 'PRUEBA-001', 'Producto de Prueba 1', 85.5, 1.0),
            (70001, 'PRUEBA-002', 'Producto de Prueba 2', 22.0, 1.0),
            (70002, 'PRUEBA-003', 'Producto de Prueba 3', 140.0, 1.0),
            (70004, '', 'Producto de Prueba 4', 0.0, 1.0),
            (70005, 'PRUEBA-005', 'Producto de Prueba 5', 61.25, 1.0)])
        self.assertEqual((filas[0]['moneda'], filas[0]['descuento'], filas[0]['plazo'], filas[0]['desde']),
                         ('USD', 0.0, 0, None))

    def test_descuento_plazo_y_vigencia(self):
        filas, errores = R.filas_precios_proveedor(
            'id_proveedor_viejo,codigo_producto,precio,cantidad_minima,descuento,plazo_entrega_dias,vigente_desde,'
            'vigente_hasta\n7,A,10,5,12.5,30,2026-10-01,2026-12-31\n')
        self.assertEqual(errores, [])
        self.assertEqual((filas[0]['cantidad_minima'], filas[0]['descuento'], filas[0]['plazo'],
                          filas[0]['desde'], filas[0]['hasta']), (5.0, 12.5, 30, '2026-10-01', '2026-12-31'))

    def test_precios_que_no_se_cargan(self):
        filas, errores = R.filas_precios_proveedor(
            'id_proveedor_viejo,codigo_producto,precio,vigente_desde\n'
            'abc,A,1,\n7,,1,\n7,B,,\n7,C,-3,\n7,D,2,\n7,E,2,2026-13-45\n')
        self.assertEqual([f['codigo'] for f in filas], ['D'])
        self.assertEqual(len(errores), 5)
        motivos = ' | '.join(e[2] for e in errores)
        for texto in ('no es un entero', 'no tiene código ni nombre', 'falta o es negativo', 'AAAA-MM-DD'):
            self.assertIn(texto, motivos)

    def test_un_precio_mal_escrito_dice_en_que_fila(self):
        with self.assertRaisesRegex(R.ErrorDeArchivo, 'Fila 3: «caro»'):
            R.filas_precios_proveedor('id_proveedor_viejo,codigo_producto,precio\n1,A,2\n1,B,caro\n')
