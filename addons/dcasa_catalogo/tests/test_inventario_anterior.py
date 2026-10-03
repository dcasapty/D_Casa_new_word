import json
from pathlib import Path

from odoo.addons.dcasa_catalogo.inventario_anterior import (
    cargar_inventario_anterior,
    fotos_del_modulo,
    leer_inventario_anterior,
    xmlid_inventario,
)
from odoo.addons.dcasa_catalogo.reglas import (
    categoria_de_inventario,
    clase_de_fila_inventario,
    filas_inventario,
    foto_por_codigo,
    planificar_inventario,
)
from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_open

FIXTURE = Path(__file__).with_name('inventario_fixture.csv')
FOTOS_PRUEBA = {'INV-PRUEBA-FOTO': '77090.jpg'}
TOTALES_LEEME = [565, 490, 627, 125, 806, 832, 664]


@tagged('post_install', '-at_install')
class TestReglasInventario(TransactionCase):
    """Reglas puras (sin Odoo) del inventario anterior."""

    def test_clases_de_fila(self):
        self.assertEqual(clase_de_fila_inventario('Descuento'), 'omitir')
        self.assertEqual(clase_de_fila_inventario('Propinas'), 'omitir')
        self.assertEqual(clase_de_fila_inventario('X COLCHON IMPERIAL TWIN 2/3 PARA COMBO'), 'omitir')
        self.assertEqual(clase_de_fila_inventario('COMBO CAMA BUTTERFLY UP TWIN + COLCHO IMPERIAL'), 'combo')
        self.assertEqual(clase_de_fila_inventario('COMBO CAMA QUEEN IVORY 8017-1002-Q + COLCHÓN DULCES SUEÑOS'),
                         'combo')
        self.assertEqual(clase_de_fila_inventario('COMBO CAMAROTE TRIPLE 3 TWIN W160969418 + 3 COLCHONES IMPERIAL'),
                         'combo')
        self.assertEqual(clase_de_fila_inventario('COLCHON FLEX FULL RELAX'), 'producto')
        self.assertEqual(clase_de_fila_inventario('COMODA BLACK + WARM WHITE 6 GAVETAS'), 'producto',
                         'El «+» solo no es combo')

    def test_filas_y_categorias(self):
        filas = filas_inventario(FIXTURE.read_text(encoding='utf-8'))
        self.assertEqual(len(filas), 9)
        combo = filas[3]
        self.assertEqual(combo['llave'], combo['nombre'], 'Sin código, la llave es el nombre exacto')
        self.assertIsNone(combo['a_la_mano'])
        self.assertEqual(combo['costo'], 0.0)
        self.assertEqual(categoria_de_inventario(combo), 'recamaras', 'El combo se clasifica por la cama')
        self.assertEqual(categoria_de_inventario(filas[2]), 'organizacion', 'Biblioteca → organización')
        self.assertEqual(filas[2]['a_la_mano'], -3.0)
        self.assertEqual(filas[0]['precio'], 70.99)

    def test_foto_por_codigo(self):
        fotos = foto_por_codigo({'ALJ021439', 'CZX100308', 'NADA'},
                                ['ALJ021439_2.png', 'ALJ021439_1.png', 'CZX100308.jpg', 'CZX1003081.jpg', 'x.txt'])
        self.assertEqual(fotos, {'ALJ021439': 'ALJ021439_1.png', 'CZX100308': 'CZX100308.jpg'})

    def test_plan(self):
        filas = filas_inventario(FIXTURE.read_text(encoding='utf-8'))
        plan = planificar_inventario(filas, {'YPN272102'}, FOTOS_PRUEBA)
        self.assertEqual([f['llave'] for f in plan['actualizar']], ['YPN272102'])
        self.assertEqual([f['llave'] for f in plan['crear']],
                         ['INV-PRUEBA-FOTO', 'INV-PRUEBA-SINFOTO', 'COMBO CAMA DE PRUEBA KING + COLCHÓN IMPERIAL',
                          'MESA DE PRUEBA SIN CODIGO 120X60'])
        self.assertEqual(len(plan['omitidos']), 3)
        self.assertEqual([f['fila'] for f in plan['repetidos']], [9])
        self.assertEqual([f['llave'] for f in plan['negativos']], ['INV-PRUEBA-SINFOTO'])
        self.assertEqual([f['llave'] for f in plan['con_foto']], ['INV-PRUEBA-FOTO'])
        self.assertEqual([f['llave'] for f in plan['sin_foto']],
                         ['INV-PRUEBA-SINFOTO', 'MESA DE PRUEBA SIN CODIGO 120X60'])
        self.assertEqual(len(plan['combos']), 1)
        self.assertEqual(len(plan['dudas']), 1)


@tagged('post_install', '-at_install')
class TestCargaInventario(TransactionCase):
    """La carga del fixture pequeño aplica las reglas de la dueña y se puede repetir."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')
        cls.ubicacion = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1).lot_stock_id
        cls.filas = filas_inventario(FIXTURE.read_text(encoding='utf-8'))
        cls.existente = cls.env['product.product'].search([('default_code', '=', 'YPN272102')], limit=1)
        cls.nombre_antes = cls.existente.name
        cls.foto_antes = cls.existente.product_tmpl_id.image_1920
        cls.movimientos = cls.env['stock.move'].search_count([])

    def variante(self, codigo):
        variante = self.env['product.product'].with_context(active_test=False).search([('default_code', '=', codigo)])
        self.assertEqual(len(variante), 1, codigo)
        return variante

    def existencias(self, variante):
        return variante.with_context(location=self.ubicacion.id).qty_available

    def test_carga_y_segunda_corrida(self):
        resumen = cargar_inventario_anterior(self.env, self.filas, fotos=FOTOS_PRUEBA)
        self.assertEqual(resumen['actualizados'], ['YPN272102'])
        self.assertEqual(resumen['creados'], ['INV-PRUEBA-FOTO', 'INV-PRUEBA-SINFOTO',
                                              'COMBO CAMA DE PRUEBA KING + COLCHÓN IMPERIAL',
                                              'MESA DE PRUEBA SIN CODIGO 120X60'])
        self.assertEqual(resumen['omitidos'], ['Descuento', 'Propinas', 'X COLCHON IMPERIAL TWIN 2/3 PARA COMBO'])
        self.assertEqual(resumen['repetidos'], ['INV-PRUEBA-FOTO'])
        self.assertEqual(resumen['negativos'], ['INV-PRUEBA-SINFOTO'])
        self.assertEqual(resumen['combos'], ['COMBO CAMA DE PRUEBA KING + COLCHÓN IMPERIAL'])
        self.assertEqual(resumen['con_foto'], ['INV-PRUEBA-FOTO'])
        self.assertEqual(resumen['sin_foto'], ['INV-PRUEBA-SINFOTO', 'MESA DE PRUEBA SIN CODIGO 120X60'])

        # Mismo código = mismo producto: existencias, precio y costo; nombre y foto intactos.
        existente = self.existente
        self.assertEqual(existente.name, self.nombre_antes)
        self.assertEqual(existente.product_tmpl_id.image_1920, self.foto_antes)
        self.assertAlmostEqual(existente.lst_price, 70.99, places=2)
        self.assertAlmostEqual(existente.standard_price, 40.00, places=2)
        self.assertEqual(self.existencias(existente), 5)

        # Código nuevo con foto: producto publicado, con el ITBMS que se suma y su categoría.
        con_foto = self.variante('INV-PRUEBA-FOTO')
        plantilla = con_foto.product_tmpl_id
        self.assertTrue(plantilla.is_published)
        self.assertTrue(plantilla.image_1920)
        self.assertEqual(plantilla.taxes_id, self.company.account_sale_tax_id)
        self.assertFalse(plantilla.taxes_id.price_include, 'Precio sin ITBMS, como el resto del catálogo')
        self.assertAlmostEqual(plantilla.list_price, 199.99, places=2)
        self.assertAlmostEqual(con_foto.standard_price, 100.50, places=2)
        self.assertEqual(plantilla.categ_id, self.env.ref('dcasa_base.product_category_recamaras'))
        self.assertTrue(plantilla.is_storable)
        self.assertEqual(self.existencias(con_foto), 7, 'La fila repetida (99) no se aplica')
        self.assertTrue(self.env.ref(f'dcasa_catalogo.{xmlid_inventario("INV-PRUEBA-FOTO")}'))

        # Sin foto: en inventario sin publicar; negativo → 0.
        sin_foto = self.variante('INV-PRUEBA-SINFOTO')
        self.assertFalse(sin_foto.product_tmpl_id.is_published)
        self.assertFalse(sin_foto.product_tmpl_id.image_1920)
        self.assertEqual(sin_foto.product_tmpl_id.categ_id,
                         self.env.ref('dcasa_catalogo.product_category_organizacion'))
        self.assertEqual(self.existencias(sin_foto), 0)

        # Combo: producto sin publicar, sin existencias.
        combo = self.env.ref(f'dcasa_catalogo.{xmlid_inventario("COMBO CAMA DE PRUEBA KING + COLCHÓN IMPERIAL")}')
        self.assertFalse(combo.is_published)
        self.assertAlmostEqual(combo.list_price, 319.99, places=2)
        self.assertEqual(self.existencias(combo.product_variant_id), 0)
        self.assertFalse(self.env['stock.move'].search_count([('product_id', '=', combo.product_variant_id.id)]))

        # Sin código: la llave es el nombre exacto.
        mesa = self.env['product.template'].search([('name', '=', 'MESA DE PRUEBA SIN CODIGO 120X60')])
        self.assertEqual(len(mesa), 1)
        self.assertFalse(mesa.default_code)
        self.assertEqual(self.existencias(mesa.product_variant_id), 4)

        # No se importan.
        for nombre in ('Descuento', 'Propinas', 'X COLCHON IMPERIAL TWIN 2/3 PARA COMBO'):
            self.assertFalse(self.env['product.template'].search_count([('name', '=', nombre)]), nombre)
        self.assertFalse(self.env['product.product'].search_count([('default_code', '=', 'TIPS')]))

    def test_segunda_corrida_no_cambia_nada(self):
        cargar_inventario_anterior(self.env, self.filas, fotos=FOTOS_PRUEBA)
        mesa = self.env['product.template'].search([('name', '=', 'MESA DE PRUEBA SIN CODIGO 120X60')])
        movimientos = self.env['stock.move'].search_count([])
        self.assertGreater(movimientos, self.movimientos)
        mesa.name = 'Mesa que la dueña renombró'  # se sigue encontrando por su xmlid, no se duplica
        otra_vez = cargar_inventario_anterior(self.env, self.filas, fotos=FOTOS_PRUEBA)
        self.assertEqual(otra_vez['creados'], [])
        self.assertEqual(otra_vez['actualizados'], [])
        self.assertEqual(len(otra_vez['sin_cambios']), 5)
        self.assertEqual(self.env['stock.move'].search_count([]), movimientos)
        self.assertEqual(self.env['product.template'].search_count([('name', 'ilike', 'MESA DE PRUEBA SIN CODIGO')]), 0)
        self.assertEqual(self.existencias(mesa.product_variant_id), 4)

    def test_el_csv_manda_sobre_un_precio_cambiado_en_odoo(self):
        """El inventario anterior es la fuente de esta carga: al repetirla, el precio vuelve al del CSV."""
        cargar_inventario_anterior(self.env, self.filas, fotos=FOTOS_PRUEBA)
        existente = self.existente
        existente.product_tmpl_id.list_price = 123.45  # la dueña cambió el precio en Odoo
        resumen = cargar_inventario_anterior(self.env, self.filas, fotos=FOTOS_PRUEBA)
        self.assertIn('YPN272102', resumen['actualizados'], 'El CSV manda: vuelve al precio del inventario anterior')
        self.assertAlmostEqual(existente.lst_price, 70.99, places=2)


@tagged('post_install', '-at_install')
class TestInventarioCompleto(TransactionCase):
    """El CSV real quedó cargado al instalar y cuadra con el plan sin Odoo del informe."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.filas = leer_inventario_anterior()
        cls.company = cls.env.ref('base.main_company')
        cls.ubicacion = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1).lot_stock_id

    def test_transcripcion_cuadra_con_el_leeme(self):
        self.assertEqual(len(self.filas), 535)
        for pagina, total in enumerate(TOTALES_LEEME, start=1):
            suma = sum(f['a_la_mano'] or 0 for f in self.filas if f['pagina'] == pagina)
            self.assertEqual(suma, total, f'página {pagina}')
        copia = Path(__file__).parents[4] / 'up media' / 'inventario-anterior' / 'inventario_anterior.csv'
        if copia.exists():
            with file_open('dcasa_catalogo/data/inventario_anterior.csv', 'r', encoding='utf-8') as archivo:
                self.assertEqual(archivo.read(), copia.read_text(encoding='utf-8'),
                                 'data/inventario_anterior.csv es copia de la transcripción de «up media»')

    def test_cargado_al_instalar_segun_el_plan(self):
        with file_open('dcasa_catalogo/data/catalogo.json', 'r', encoding='utf-8') as archivo:
            catalogo = json.load(archivo)
        Variante = self.env['product.product'].with_context(active_test=False)
        existentes = set(Variante.search([('default_code', '!=', False)]).mapped('default_code'))
        codigos_catalogo = {item['codigo'] for item in catalogo}
        fotos = foto_por_codigo({f['codigo'] for f in self.filas if f['codigo']}, fotos_del_modulo())
        plan = planificar_inventario(self.filas, existentes, fotos)
        # Todo lo que el plan dice «actualizar» ya estaba en el catálogo del Excel (no lo creó esta carga).
        for fila in plan['actualizar']:
            xmlid = f'dcasa_catalogo.{xmlid_inventario(fila["llave"])}'
            self.assertFalse(self.env.ref(xmlid, raise_if_not_found=False), fila['llave'])
        creados = self.env['ir.model.data'].search_count([
            ('module', '=', 'dcasa_catalogo'), ('name', '=like', 'inventario_anterior_%')])
        self.assertEqual(creados, len(plan['crear']))
        self.assertGreater(len(plan['actualizar']), 100, 'Buena parte del inventario ya estaba en el catálogo')
        self.assertEqual(len(plan['omitidos']), 4)
        self.assertEqual(len(plan['negativos']), 7)
        self.assertEqual(len(plan['combos']), 49)
        self.assertEqual([f['codigo'] for f in plan['repetidos']], ['XXI070507'])
        for fila in plan['crear'] + plan['actualizar']:
            if fila['codigo']:
                variante = Variante.search([('default_code', '=', fila['codigo'])], limit=1)
            else:
                variante = self.env.ref(f'dcasa_catalogo.{xmlid_inventario(fila["llave"])}').product_variant_ids[:1]
            self.assertTrue(variante, fila['llave'])
            self.assertAlmostEqual(variante.lst_price, fila['precio'], places=2, msg=fila['llave'])
            self.assertAlmostEqual(variante.standard_price, fila['costo'], places=2, msg=fila['llave'])
            if fila['a_la_mano'] is not None:
                self.assertEqual(variante.with_context(location=self.ubicacion.id).qty_available,
                                 max(fila['a_la_mano'], 0), fila['llave'])
            if fila in plan['crear']:
                plantilla = variante.product_tmpl_id
                self.assertEqual(plantilla.is_published, bool(plantilla.image_1920) and fila['clase'] != 'combo',
                                 fila['llave'])
                self.assertNotIn(fila['codigo'], codigos_catalogo)
        for fila in plan['combos']:
            self.assertFalse(self.env.ref(f'dcasa_catalogo.{xmlid_inventario(fila["llave"])}').is_published)
