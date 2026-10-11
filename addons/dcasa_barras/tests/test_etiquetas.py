"""Etiquetas numeradas del rollo: asignar a un producto, pasarla, reemplazarla, quitarla y que quede historial."""
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from ..models.etiqueta import DcasaBarrasEtiquetas, codigo_de_etiqueta
from .comun import BarrasCommon


@tagged('post_install', '-at_install')
class TestCodigoDeEtiqueta(BarrasCommon):
    """Qué se lee como una etiqueta (sin base de datos: es una función)."""

    def test_se_guarda_en_mayusculas_y_sin_saltos_de_linea(self):
        for escrito in ('DC0001', 'dc0001', ' dc0001 ', '\r\ndc0001\n'):
            self.assertEqual(codigo_de_etiqueta(escrito), 'DC0001', repr(escrito))

    def test_lo_que_no_es_una_etiqueta(self):
        for malo in (None, '', '   ', 'DC 0001', 'ñandú', 'x' * 64, 'x' * 300, 12, True, ['DC0001'], 'DC\u200b01'):
            self.assertIsNone(codigo_de_etiqueta(malo), repr(malo))

    def test_cualquier_simbolo_del_teclado_vale(self):
        self.assertEqual(codigo_de_etiqueta('a-b_c.1/2'), 'A-B_C.1/2')


@tagged('post_install', '-at_install')
class TestEtiquetas(BarrasCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.a = cls.producto('Zzmesa A de etiqueta', 'ZZT-ETQ-A', precio=50, unidades=3)
        cls.b = cls.producto('Zzmesa B de etiqueta', 'ZZT-ETQ-B', precio=60)
        cls.c = cls.producto('Zzmesa C de etiqueta', 'ZZT-ETQ-C', precio=70)
        cls.Historial = cls.env['dcasa.barras.etiqueta']

    def gerente(self):
        return self.como(self.gerencia)

    def historial(self, codigo):
        return self.Historial.search([('codigo', '=', codigo)], order='id')

    def asignar(self, codigo, producto, confirmar=False):
        return self.gerente().asignar_etiqueta(codigo, producto.id, confirmar)

    # ------------------------------------------------------------------
    def test_una_etiqueta_nueva_no_es_de_nadie(self):
        r = self.gerente().etiqueta('dc9001')
        self.assertEqual((r['codigo'], r['estado'], r['producto'], r['antes']), ('DC9001', 'libre', None, False))

    def test_asignar_deja_el_numero_como_codigo_de_barras(self):
        r = self.asignar('dc9001', self.a)
        self.assertEqual(r['resultado'], 'ok')
        self.assertEqual((r['etiqueta_anterior'], r['dueno_anterior']), ('', ''))
        self.assertEqual(self.a.barcode, 'DC9001')
        self.assertEqual(r['ficha']['codigo_de_barras'], 'DC9001')
        fila = self.historial('DC9001')
        self.assertEqual([(f.accion, f.producto_id, f.usuario_id) for f in fila],
                         [('asignada', self.a, self.gerencia)])
        self.assertEqual(fila.company_id, self.env.company)
        self.assertEqual(fila.producto_nombre, self.a.display_name)

    def test_el_escaner_encuentra_el_producto_por_su_etiqueta_sin_mirar_mayusculas(self):
        self.asignar('DC9001', self.a)
        for escrito in ('DC9001', 'dc9001'):   # un lector con las mayúsculas invertidas escribe «dc9001»
            r = self.como(self.vendedora).buscar(escrito)
            self.assertEqual((r['resultado'], r['forma']), ('ok', 'codigo_de_barras'), escrito)
            self.assertEqual(r['productos'][0]['id'], self.a.id)

    def test_una_etiqueta_asignada_dice_de_quien_es(self):
        self.asignar('DC9001', self.a)
        r = self.gerente().etiqueta('dc9001')
        self.assertEqual((r['estado'], r['producto']['id']), ('asignada', self.a.id))

    def test_asignar_la_misma_etiqueta_al_mismo_producto_no_hace_nada(self):
        self.asignar('DC9001', self.a)
        r = self.asignar('dc9001', self.a)
        self.assertEqual(r['resultado'], 'igual')
        self.assertEqual(len(self.historial('DC9001')), 1)

    # --- pasarla a otro producto ---------------------------------------------------------------------------------
    def test_pasarla_a_otro_producto_pide_confirmar_y_mientras_no_cambia_nada(self):
        self.asignar('DC9001', self.a)
        for no_confirma in (False, None, 1, 'si', 'true', [True]):   # solo un verdadero de verdad confirma
            r = self.asignar('DC9001', self.b, confirmar=no_confirma)
            self.assertEqual((r['resultado'], r['motivo'], r['dueno']['id']), ('confirmar', 'dueno', self.a.id),
                             repr(no_confirma))
        self.assertEqual((self.a.barcode, self.b.barcode), ('DC9001', False))
        self.assertEqual(len(self.historial('DC9001')), 1)

    def test_pasarla_a_otro_producto_confirmado_deja_al_anterior_sin_etiqueta(self):
        self.asignar('DC9001', self.a)
        r = self.asignar('DC9001', self.b, confirmar=True)
        self.assertEqual((r['resultado'], r['dueno_anterior']), ('ok', self.a.display_name))
        self.assertEqual((self.a.barcode, self.b.barcode), (False, 'DC9001'))
        self.assertEqual(
            [(f.accion, f.producto_id, f.motivo) for f in self.historial('DC9001')],
            [('asignada', self.a, ''),
             ('retirada', self.a, f'Pasó a «{self.b.display_name}»'),
             ('asignada', self.b, f'Venía de «{self.a.display_name}»')])

    def test_las_mayusculas_no_hacen_otro_dueno(self):
        self.asignar('DC9001', self.a)
        r = self.asignar('dc9001', self.b)
        self.assertEqual((r['resultado'], r['motivo']), ('confirmar', 'dueno'))

    def test_un_codigo_en_minusculas_que_ya_tenia_un_producto_tambien_cuenta(self):
        self.a.barcode = 'dc9050'   # puesto a mano antes de las etiquetas, en minúsculas
        r = self.gerente().etiqueta('DC9050')
        self.assertEqual((r['estado'], r['producto']['id']), ('asignada', self.a.id))
        self.assertEqual(self.asignar('DC9050', self.b)['resultado'], 'confirmar')
        self.assertEqual(self.a.barcode, 'dc9050')

    def test_si_el_dueno_esta_archivado_la_etiqueta_sigue_siendo_suya(self):
        self.asignar('DC9001', self.a)
        self.a.action_archive()
        self.assertEqual(self.gerente().etiqueta('DC9001')['estado'], 'asignada')
        self.assertEqual(self.asignar('DC9001', self.b)['resultado'], 'confirmar')
        self.assertEqual(self.asignar('DC9001', self.b, confirmar=True)['resultado'], 'ok')
        self.assertEqual((self.a.barcode, self.b.barcode), (False, 'DC9001'))

    # --- reemplazar y quitar -------------------------------------------------------------------------------------
    def test_reemplazar_la_etiqueta_deja_la_vieja_retirada(self):
        self.asignar('DC9001', self.a)
        r = self.asignar('DC9002', self.a)
        self.assertEqual((r['resultado'], r['etiqueta_anterior']), ('ok', 'DC9001'))
        self.assertEqual(self.a.barcode, 'DC9002')
        self.assertEqual([(f.accion, f.motivo) for f in self.historial('DC9001')],
                         [('asignada', ''), ('retirada', 'Reemplazada por DC9002')])
        viejo = self.gerente().etiqueta('DC9001')
        self.assertEqual(viejo['estado'], 'retirada')
        self.assertEqual(viejo['antes']['producto'], self.a.display_name)
        self.assertEqual(viejo['antes']['motivo'], 'Reemplazada por DC9002')

    def test_escanear_una_etiqueta_retirada_avisa_en_vez_de_decir_solo_que_no_existe(self):
        self.asignar('DC9001', self.a)
        self.asignar('DC9002', self.a)
        for usuario in (self.vendedora, self.gerencia):   # la Vendedora también lo ve
            r = self.como(usuario).buscar('dc9001')
            self.assertEqual(r['resultado'], 'no_encontrado')
            self.assertEqual(r['retirada']['producto'], self.a.display_name)
        self.assertFalse(self.como(self.vendedora).buscar('DC9002')['retirada'])
        self.assertFalse(self.como(self.vendedora).buscar('DC0000')['retirada'], 'una etiqueta que nunca existió')

    def test_usar_otra_vez_una_etiqueta_retirada_pide_confirmar(self):
        self.asignar('DC9001', self.a)
        self.asignar('DC9002', self.a)
        r = self.asignar('DC9001', self.c)
        self.assertEqual((r['resultado'], r['motivo']), ('confirmar', 'retirada'))
        self.assertEqual(r['antes']['producto'], self.a.display_name)
        self.assertFalse(self.c.barcode)
        self.assertEqual(self.asignar('DC9001', self.c, confirmar=True)['resultado'], 'ok')
        self.assertEqual(self.c.barcode, 'DC9001')
        self.assertEqual(self.gerente().etiqueta('DC9001')['estado'], 'asignada')

    def test_quitar_la_etiqueta(self):
        self.asignar('DC9001', self.a)
        r = self.gerente().quitar_etiqueta(self.a.id)
        self.assertEqual((r['resultado'], r['etiqueta_anterior']), ('ok', 'DC9001'))
        self.assertFalse(self.a.barcode)
        self.assertEqual([(f.accion, f.motivo) for f in self.historial('DC9001')],
                         [('asignada', ''), ('retirada', 'Quitada a mano')])
        self.assertEqual(self.gerente().etiqueta('DC9001')['estado'], 'retirada')
        with self.assertUserError('no tiene etiqueta'):
            self.gerente().quitar_etiqueta(self.a.id)

    # --- lo que no se puede -------------------------------------------------------------------------------------
    def test_lo_que_no_se_lee_como_etiqueta_se_rechaza(self):
        for malo in ('', '   ', 'DC 9001', 'ñandú', 'x' * 64, None, 12, True):
            with self.assertUserError('etiqueta'):
                self.gerente().etiqueta(malo)
            with self.assertUserError('etiqueta'):
                self.asignar(malo, self.a)
        self.assertFalse(self.a.barcode)

    def test_el_producto_tiene_que_ser_un_producto(self):
        for malo in (True, 'abc', None, -1, 99999999):
            with self.assertUserError():
                self.gerente().asignar_etiqueta('DC9001', malo)
            with self.assertUserError():
                self.gerente().quitar_etiqueta(malo)

    def test_el_codigo_de_un_empaque_no_puede_ser_etiqueta(self):
        self.env['product.uom'].create({
            'uom_id': self.env.ref('uom.product_uom_unit').id, 'product_id': self.b.id, 'barcode': 'DC9100'})
        with self.assertUserError('empaque'):
            self.asignar('dc9100', self.a)
        self.assertFalse(self.a.barcode)

    def test_solo_gerencia_asigna_etiquetas(self):
        self.asignar('DC9001', self.a)
        # El administrador de Inventario sin Productos, la Vendedora y quien no usa Inventario: nada de esto.
        for usuario in (self.solo_inventario, self.vendedora, self.sin_inventario):
            barras = self.como(usuario)
            for llamada in (lambda b: b.etiqueta('DC9001'), lambda b: b.asignar_etiqueta('DC9001', self.b.id, True),
                            lambda b: b.asignar_etiqueta('DC9003', self.b.id), lambda b: b.quitar_etiqueta(self.a.id)):
                with self.assertRaises(AccessError, msg=usuario.login):
                    llamada(barras)
        self.assertEqual((self.a.barcode, self.b.barcode), ('DC9001', False))
        self.assertEqual(len(self.Historial.search([])), 1)

    def test_un_fallo_a_medias_no_deja_nada_a_medias(self):
        self.asignar('DC9001', self.a)
        self.a.barcode = 'DC9001'
        original = DcasaBarrasEtiquetas._anotar_etiqueta

        def falla_al_ultimo(modelo, codigo, accion, producto, motivo):
            if accion == 'asignada':
                raise UserError('falla de prueba')
            return original(modelo, codigo, accion, producto, motivo)

        with patch.object(DcasaBarrasEtiquetas, '_anotar_etiqueta', falla_al_ultimo), \
                self.assertRaisesRegex(UserError, 'falla de prueba'):
            self.asignar('DC9001', self.b, confirmar=True)
        self.a.invalidate_recordset()
        self.b.invalidate_recordset()
        self.assertEqual((self.a.barcode, self.b.barcode), ('DC9001', False), 'el dueño no se queda sin etiqueta')
        self.assertEqual(len(self.historial('DC9001')), 1, 'ni el historial a medias')

    # --- historial ----------------------------------------------------------------------------------------------
    def test_el_historial_no_se_edita_ni_se_borra_ni_se_crea_a_mano(self):
        self.asignar('DC9001', self.a)
        fila = self.historial('DC9001')
        for usuario in (self.gerencia, self.env.ref('base.user_admin')):
            with self.assertRaises(UserError):
                fila.with_user(usuario).write({'motivo': 'otro'})
            with self.assertRaises(UserError):
                fila.with_user(usuario).unlink()
        with self.assertRaises(UserError):
            fila.sudo().write({'codigo': 'DC0000'})
        with self.assertRaises(UserError):
            fila.sudo().unlink()
        for usuario in (self.gerencia, self.vendedora):
            with self.assertRaises(AccessError):
                self.Historial.with_user(usuario).create(
                    {'codigo': 'DC9999', 'accion': 'asignada', 'producto_nombre': 'falso'})

    def test_la_vendedora_lee_el_historial_pero_solo_de_su_empresa(self):
        self.asignar('DC9001', self.a)
        otra = self.env['res.company'].create({'name': 'Otra empresa de prueba'})
        self.Historial.sudo().create({
            'codigo': 'DC7777', 'accion': 'retirada', 'producto_nombre': 'Ajeno', 'company_id': otra.id})
        vistos = self.Historial.with_user(self.vendedora).search([]).mapped('codigo')
        self.assertIn('DC9001', vistos)
        self.assertNotIn('DC7777', vistos)
        self.assertFalse(self.como(self.vendedora).buscar('DC7777')['retirada'], 'tampoco avisa de lo ajeno')

    def test_buscar_por_nombre_trae_la_etiqueta_que_ya_tiene(self):
        self.asignar('DC9001', self.a)
        encontrados = {p['id']: p for p in self.como(self.vendedora).buscar_por_nombre('zzmesa')}
        self.assertEqual(encontrados[self.a.id]['codigo_de_barras'], 'DC9001')
        self.assertEqual(encontrados[self.b.id]['codigo_de_barras'], '')
