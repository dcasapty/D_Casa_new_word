"""Qué entra al catálogo para Meta y cómo se escribe cada fila (el formato del diseño §4)."""
import re

from lxml import etree

from odoo.addons.dcasa_meta_catalogo.models.product_feed import COLUMNAS
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open

from .common import BASE, MetaComun, foto

ETIQUETA = re.compile(r'^[a-z0-9_]*$')
PRECIO = re.compile(r'^\d+\.\d{2} USD$')


@tagged('post_install', '-at_install')
class TestFeedContenido(MetaComun, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mesa = cls._producto('Mesa de noche prueba Meta', 120.0, description_sale='Mesa de noche con dos gavetas.')
        cls.oculto = cls._producto('Mesa que no se anuncia', 80.0, dcasa_meta_no_anunciar=True)
        cls.archivado = cls._producto('Mesa archivada', 80.0)
        cls.archivado.active = False
        cls.borrador = cls._producto('Mesa sin publicar', 80.0, is_published=False)
        cls.sin_foto = cls._producto('Mesa sin foto', 80.0, image_1920=False)
        cls.gratis = cls._producto('Mesa gratis', 0.0)
        cls.no_se_vende = cls._producto('Mesa que no se vende', 80.0, sale_ok=False)
        cls.otro_sitio = cls._producto('Mesa de otro sitio', 80.0, website_id=cls.env['website'].create({
            'name': 'Otro sitio Meta'}).id)
        cls.cama, cls.queen, cls.king = cls._cama_con_tamanos()

    def test_solo_entran_los_publicados_del_sitio(self):
        filas = self._por_id()
        esperados = {str(v.id) for v in self.mesa.product_variant_ids | self.queen | self.king}
        self.assertEqual(set(filas), esperados)
        for fuera in (self.oculto, self.borrador, self.sin_foto, self.gratis, self.no_se_vende, self.otro_sitio):
            with self.subTest(fuera.name):
                self.assertNotIn(str(fuera.product_variant_id.id), filas)
        self.assertNotIn(str(self.archivado.with_context(active_test=False).product_variant_ids.id), filas)

    def test_cabecera_en_orden_y_utf8_sin_bom(self):
        contenido = self._csv()
        self.assertFalse(contenido.startswith(b'\xef\xbb\xbf'), 'sin BOM')
        cabecera = contenido.decode('utf-8').split('\n', 1)[0]
        self.assertEqual(cabecera, ','.join(COLUMNAS))
        self.assertEqual(cabecera, (
            'id,item_group_id,title,description,availability,condition,price,sale_price,sale_price_effective_date,'
            'link,image_link,additional_image_link,brand,product_type,custom_label_0,custom_label_1,custom_label_2,'
            'custom_label_3,custom_label_4'))

    def test_una_fila_por_variante_y_grupo_solo_con_varias(self):
        filas = self._por_id()
        mesa = filas[str(self.mesa.product_variant_id.id)]
        self.assertEqual(mesa['item_group_id'], '', 'un producto de una sola variante no lleva grupo')
        for variante in self.queen | self.king:
            with self.subTest(variante.display_name):
                fila = filas[str(variante.id)]
                self.assertEqual(fila['id'], str(variante.id), 'el id es el de la variante (contrato 2.1)')
                self.assertEqual(fila['item_group_id'], f'g{self.cama.id}')
        self.assertIn('king', filas[str(self.king.id)]['title'].lower())
        self.assertIn('queen', filas[str(self.queen.id)]['title'].lower())

    def test_campos_de_cada_fila(self):
        fila = self._por_id()[str(self.mesa.product_variant_id.id)]
        variante = self.mesa.product_variant_id
        # El nombre se guarda en MAYÚSCULAS (F5); a Meta le llega en tipo oración (no acepta todo en mayúsculas).
        self.assertEqual(fila['title'], 'Mesa de noche prueba meta')
        self.assertEqual(fila['description'], 'Mesa de noche con dos gavetas.')
        self.assertEqual(fila['condition'], 'new')
        self.assertEqual(fila['brand'], self.env.company.name, 'la marca viene con el nombre de la empresa')
        self.assertEqual(fila['price'], '120.00 USD')
        self.assertEqual(fila['sale_price'], '')
        self.assertEqual(fila['link'], BASE + variante.website_url)
        self.assertEqual(fila['image_link'], BASE + self.website._dcasa_img_url(variante, 1024, 'jpg'))
        self.assertIn('/1024.jpg?v=', fila['image_link'])
        self.assertEqual(fila['product_type'], 'Dormitorio > Habitación de Niños')
        self.assertEqual(fila['custom_label_0'], 'habitacion_de_ninos')
        self.assertEqual(fila['custom_label_1'], '')
        self.assertEqual(fila['custom_label_3'], '100_a_300')
        self.assertRegex(fila['custom_label_4'], r'^DC-[A-Z0-9]{6}$')
        self.assertEqual(fila['custom_label_4'], self.mesa.dcasa_codigo_publico)

    def test_precio_con_dos_decimales_y_extra_de_la_variante(self):
        filas = self._por_id()
        self.assertEqual(filas[str(self.queen.id)]['price'], '300.00 USD')
        self.assertEqual(filas[str(self.king.id)]['price'], '350.00 USD')
        for fila in filas.values():
            self.assertRegex(fila['price'], PRECIO)

    def test_descripcion_de_la_tienda_en_texto_plano_o_el_titulo(self):
        self.mesa.description_sale = False
        self.mesa.description_ecommerce = '<p>MESA DE NOCHE. <a href="https://x.example">VER MÁS</a></p>'
        self.assertEqual(self._por_id()[str(self.mesa.product_variant_id.id)]['description'],
                         'Mesa de noche. Ver más')
        self.mesa.description_ecommerce = False
        self.assertEqual(self._por_id()[str(self.mesa.product_variant_id.id)]['description'],
                         'Mesa de noche prueba meta', 'sin descripción, el título')

    def test_fotos_extra_hasta_diez_separadas_por_coma(self):
        self.env['product.image'].create([
            {'name': f'Extra {i}', 'image_1920': foto('red'), 'product_tmpl_id': self.mesa.id} for i in range(12)])
        fila = self._por_id()[str(self.mesa.product_variant_id.id)]
        extras = fila['additional_image_link'].split(',')
        self.assertEqual(len(extras), 10)
        imagenes = self.mesa.product_template_image_ids[:10]
        self.assertEqual(extras, [BASE + self.website._dcasa_img_url(i, 1024, 'jpg') for i in imagenes])

    def test_disponibilidad_en_los_dos_modos(self):
        self.mesa.is_storable = True  # sin existencias: 0 unidades
        self.cama.is_storable = True
        self._existencias(self.cama, 3)
        filas = self._por_id()
        for fila in filas.values():
            self.assertEqual(fila['availability'], 'in stock', 'como la web: todo lo publicado está disponible')
        mesa = filas[str(self.mesa.product_variant_id.id)]
        self.assertEqual(mesa['custom_label_2'], 'agotado', 'la etiqueta se emite igual')
        self.assertEqual(filas[str(self.king.id)]['custom_label_2'], 'pocas', 'según dcasa_stock (la plantilla)')

        self.feed.dcasa_disponibilidad = 'existencias'
        filas = self._por_id()
        self.assertEqual(filas[str(self.mesa.product_variant_id.id)]['availability'], 'out of stock')
        self.assertEqual(filas[str(self.king.id)]['availability'], 'in stock')
        self._existencias(self.mesa, 40)
        self.assertEqual(self._por_id()[str(self.mesa.product_variant_id.id)]['custom_label_2'], 'disponible')

    def test_sin_control_de_inventario_es_disponible(self):
        self.mesa.is_storable = False
        self.feed.dcasa_disponibilidad = 'existencias'
        fila = self._por_id()[str(self.mesa.product_variant_id.id)]
        self.assertEqual(fila['availability'], 'in stock')
        self.assertEqual(fila['custom_label_2'], 'disponible')

    def test_etiquetas_ascii_y_la_cuatro_con_el_codigo_dc(self):
        campana = self.env['dcasa.meta.campana'].create({'name': 'Navidad Niños 2026'})
        self.cama.dcasa_meta_campana_id = campana
        filas = self._por_id()
        for fila in filas.values():
            for columna in ('custom_label_0', 'custom_label_1', 'custom_label_2', 'custom_label_3'):
                with self.subTest(columna):
                    self.assertRegex(fila[columna], ETIQUETA)
                    self.assertLessEqual(len(fila[columna]), 100)
            self.assertTrue(fila['custom_label_4'].startswith('DC-'))
        self.assertEqual(filas[str(self.king.id)]['custom_label_1'], 'navidad_ninos_2026')
        self.assertEqual(filas[str(self.queen.id)]['custom_label_1'], 'navidad_ninos_2026')
        self.assertEqual(filas[str(self.mesa.product_variant_id.id)]['custom_label_1'], '')
        campana.active = False
        self.assertEqual(self._por_id()[str(self.king.id)]['custom_label_1'], '', 'campaña archivada: sin etiqueta')

    def test_franja_segun_el_precio_de_la_pagina(self):
        barata = self._producto('Lámpara prueba Meta', 99.99)
        cara = self._producto('Sofá prueba Meta', 899.0)
        filas = self._por_id()
        self.assertEqual(filas[str(barata.product_variant_id.id)]['custom_label_3'], 'hasta_100')
        self.assertEqual(filas[str(cara.product_variant_id.id)]['custom_label_3'], 'mas_de_600')
        self.assertEqual(filas[str(self.king.id)]['custom_label_3'], '300_a_600', '300 + 50 de la King')

    def test_categoria_principal_la_primera_por_secuencia(self):
        otra = self.env['product.public.category'].create({
            'name': 'Ofertas', 'sequence': 0, 'parent_id': self.padre.id})
        self.mesa.public_categ_ids = [Command.link(otra.id)]
        fila = self._por_id()[str(self.mesa.product_variant_id.id)]
        self.assertEqual(fila['custom_label_0'], 'ofertas')
        self.assertEqual(fila['product_type'], 'Dormitorio > Ofertas')

    def test_solo_las_categorias_elegidas(self):
        fuera = self.env['product.public.category'].create({'name': 'Cocina'})
        sofa = self._producto('Sofá de otra categoría', 200.0, public_categ_ids=[Command.set(fuera.ids)])
        self.assertNotIn(str(sofa.product_variant_id.id), self._por_id())
        self.feed.product_category_ids = [Command.link(fuera.id)]
        self.assertIn(str(sofa.product_variant_id.id), self._por_id())

    def test_la_marca_y_la_condicion_del_feed(self):
        self.feed.write({'dcasa_marca': "D'CASA", 'dcasa_condicion': 'used'})
        fila = self._por_id()[str(self.mesa.product_variant_id.id)]
        self.assertEqual(fila['brand'], "D'CASA")
        self.assertEqual(fila['condition'], 'used')

    def test_conteos_y_los_que_quedan_fuera(self):
        self.assertEqual(self.feed.dcasa_meta_en_catalogo, 3)
        self.assertEqual(self.feed.dcasa_meta_fuera_sin_foto, 1)
        self.assertEqual(self.feed.dcasa_meta_fuera_sin_precio, 1)
        self.assertEqual(self.feed.dcasa_meta_fuera_marcados, 1)
        accion = self.feed.action_dcasa_meta_ver_fuera()
        plantillas = self.env['product.template'].search(accion['domain'])
        self.assertEqual(plantillas, self.oculto | self.sin_foto | self.gratis)

    def test_nace_apagado(self):
        """El catálogo de fábrica viene apagado (en esta prueba lo encendió setUpClass)."""
        nuevo = self.env['product.feed'].create({'name': 'Otro catálogo Meta', 'target': 'meta',
                                                 'website_id': self.website.id})
        self.assertFalse(nuevo.dcasa_activo)
        with file_open('dcasa_meta_catalogo/data/product_feed_data.xml', 'rb') as archivo:
            [registro] = etree.fromstring(archivo.read()).xpath('//record[@id="feed_meta_principal"]')
        self.assertEqual(registro.xpath('field[@name="dcasa_activo"]/@eval'), ['False'])
