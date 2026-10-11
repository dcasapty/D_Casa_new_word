"""Encontrar el producto que se escaneó: por código de barras, referencia o empaque; sin costos y con permisos."""
from odoo.addons.dcasa_barras.models.barras import clave_tolerante, etiqueta_existencias, limpiar_codigo, precio_texto
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .comun import BarrasCommon


@tagged('post_install', '-at_install')
class TestBusqueda(BarrasCommon):

    def test_ayudantes(self):
        self.assertEqual(limpiar_codigo('\r\n ZZT-CAMA-1 \t\n'), 'ZZT-CAMA-1')
        self.assertEqual(limpiar_codigo('A\x00B\x1fC'), 'ABC')
        self.assertEqual(limpiar_codigo('x' * 500), 'x' * 64)
        self.assertEqual((limpiar_codigo(None), limpiar_codigo(123), limpiar_codigo(['a'])), ('', '', ''))
        self.assertEqual(clave_tolerante('zzt_cama/1'), clave_tolerante('ZZT-CAMA-1'))
        self.assertEqual(precio_texto(349.99), '$349.99 + ITBMS')
        self.assertEqual(precio_texto(1234.5), '$1,234.50 + ITBMS')

    def test_las_tres_etiquetas_de_existencias(self):
        self.assertEqual(etiqueta_existencias(0), 'agotado')
        self.assertEqual(etiqueta_existencias(-3), 'agotado', 'un negativo no es stock')
        self.assertEqual(etiqueta_existencias(1), 'pocas')
        self.assertEqual(etiqueta_existencias(5), 'pocas')
        self.assertEqual(etiqueta_existencias(5.5), 'disponible')
        self.assertEqual(etiqueta_existencias(0, controla_inventario=False), 'disponible')

    def test_por_codigo_de_barras(self):
        r = self.Barras.buscar('7501234567890')
        self.assertEqual((r['resultado'], r['forma']), ('ok', 'codigo_de_barras'))
        self.assertEqual(r['productos'][0]['id'], self.zapatera.id)

    def test_por_referencia_aunque_aun_no_tenga_codigo(self):
        """Hoy ningún producto tiene código de barras: la referencia ya sirve para empezar a escanear."""
        r = self.Barras.buscar('ZZT-CAMA-1')
        self.assertEqual((r['resultado'], r['forma']), ('ok', 'referencia'))
        self.assertEqual(r['productos'][0]['id'], self.cama.id)
        self.assertEqual(self.Barras.buscar('zzt-cama-1')['productos'][0]['id'], self.cama.id, 'sin mirar mayúsculas')

    def test_lo_que_escribe_el_lector_llega_con_saltos_de_linea(self):
        self.assertEqual(self.Barras.buscar('\r\nZZT-CAMA-1\n')['productos'][0]['id'], self.cama.id)

    def test_tolera_los_simbolos_que_cambia_el_teclado_del_lector(self):
        for escrito in ('ZZT_CAMA_1', 'zzt/cama/1', 'ZZT-CAMA1', 'zzt cama 1'):
            r = self.Barras.buscar(escrito)
            self.assertEqual((r['resultado'], r['forma']), ('ok', 'parecido'), escrito)
            self.assertEqual(r['productos'][0]['id'], self.cama.id, escrito)

    def test_un_codigo_demasiado_corto_no_se_parece_a_nada(self):
        self.producto('Corto', 'AB-C')
        self.assertEqual(self.Barras.buscar('a_b_c')['resultado'], 'no_encontrado')

    def test_comodines_de_busqueda_no_encuentran_todo(self):
        for escrito in ('%', '_', 'ZZT%', '%CAMA%', 'ZZT-CAMA-_'):
            self.assertEqual(self.Barras.buscar(escrito)['resultado'], 'no_encontrado', escrito)

    def test_por_el_codigo_del_empaque(self):
        # En Odoo 19 el código del empaque vive en product.uom (una unidad de medida con su propio código).
        self.env['product.uom'].create({
            'uom_id': self.env.ref('uom.product_uom_unit').id, 'product_id': self.cama.id, 'barcode': 'EMP-0001'})
        r = self.Barras.buscar('EMP-0001')
        self.assertEqual((r['resultado'], r['forma']), ('ok', 'empaque'))
        self.assertEqual(r['productos'][0]['id'], self.cama.id)

    def test_dos_productos_con_la_misma_referencia_se_ofrecen_los_dos(self):
        a = self.producto('Repetido A', 'REP-100')
        b = self.producto('Repetido B', 'rep-100')
        r = self.Barras.buscar('REP-100')
        self.assertEqual(r['resultado'], 'varios')
        self.assertEqual({p['id'] for p in r['productos']}, {a.id, b.id})

    def test_no_encontrado_vacio_y_archivado(self):
        self.assertEqual(self.Barras.buscar('NO-EXISTE-999')['resultado'], 'no_encontrado')
        for vacio in ('', '   ', '\r\n', None, 5, ['x']):
            self.assertEqual(self.Barras.buscar(vacio)['resultado'], 'vacio', repr(vacio))
        archivado = self.producto('Archivado', 'OLD-1000')
        archivado.action_archive()
        self.assertEqual(self.Barras.buscar('OLD-1000')['resultado'], 'no_encontrado')

    def test_la_tarjeta_trae_precio_existencias_y_ubicacion_pero_nunca_el_costo(self):
        ficha = self.Barras.buscar('ZZT-CAMA-1')['productos'][0]
        self.assertEqual(ficha['nombre'], self.cama.display_name)
        self.assertEqual(ficha['referencia'], 'ZZT-CAMA-1')
        self.assertEqual(ficha['precio_texto'], '$349.99 + ITBMS')
        self.assertEqual(ficha['unidades'], 12)
        self.assertEqual(ficha['etiqueta'], 'disponible')
        self.assertEqual([(u['nombre'], u['cantidad']) for u in ficha['ubicaciones']],
                         [(self.bodega.complete_name, 12)])
        self.assertEqual(ficha['ubicacion_habitual'], self.bodega.id)
        self.assertEqual((ficha['admite_decimales'], bool(ficha['unidad'])), (False, True))
        self.assertNotIn('77.77', str(ficha), 'el costo no sale en el lector')
        self.assertFalse([k for k in ficha if 'costo' in k or 'cost' in k])

    def test_sin_existencias_dice_agotado_y_propone_la_bodega(self):
        ficha = self.Barras.buscar('7501234567890')['productos'][0]
        self.assertEqual((ficha['unidades'], ficha['etiqueta']), (0, 'agotado'))
        self.assertEqual(ficha['ubicacion_habitual'], self.bodega.id)

    def test_lo_que_no_controla_inventario_no_tiene_cifra(self):
        servicio = self.env['product.product'].create({
            'name': 'Flete de prueba', 'default_code': 'FLETE-1', 'type': 'service', 'list_price': 5})
        ficha = self.Barras.buscar('FLETE-1')['productos'][0]
        self.assertFalse(ficha['controla_inventario'])
        self.assertIsNone(ficha['unidades'])
        self.assertEqual(ficha['etiqueta'], 'disponible')
        self.assertFalse(ficha['puede_contar'])
        self.assertTrue(servicio)

    def test_buscar_por_nombre_y_ficha(self):
        encontrados = self.Barras.buscar_por_nombre('zzcama prueba')
        self.assertIn(self.cama.id, [p['id'] for p in encontrados])
        self.assertEqual(self.Barras.buscar_por_nombre('x'), [], 'una sola letra no busca')
        self.assertEqual(self.Barras.ficha(self.cama.id)['referencia'], 'ZZT-CAMA-1')

    def test_ficha_con_un_dato_que_no_es_un_producto(self):
        for malo in (True, 'abc', None, -1, 99999999):
            with self.assertUserError():
                self.Barras.ficha(malo)

    def test_solo_quien_trabaja_con_inventario_puede_consultar(self):
        portal = new_test_user(self.env, login='barras_portal', groups='base.group_portal')
        for usuario in (self.sin_inventario, portal):
            for llamada in (lambda b: b.buscar('ZZT-CAMA-1'), lambda b: b.buscar_por_nombre('cama'),
                            lambda b: b.ficha(self.cama.id)):
                with self.assertRaises(AccessError, msg=usuario.login):
                    llamada(self.como(usuario))
        self.assertEqual(self.como(self.vendedora).buscar('ZZT-CAMA-1')['resultado'], 'ok')
