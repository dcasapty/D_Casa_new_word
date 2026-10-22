"""F5: nombres de productos en MAYÚSCULAS (lo nuevo solo; lo viejo con vista previa) y productos repetidos que se
unen sin perder historia."""
import base64
import io

from PIL import Image

from odoo import Command
from odoo.addons.dcasa_base.tests.test_roles import crear_usuario
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from ..inventario_anterior import _buscar
from ..models.nombres_productos import nombre_en_mayusculas


def foto(color):
    """Un PNG de 2×2 de un color (dos colores distintos = dos fotos distintas)."""
    salida = io.BytesIO()
    Image.new('RGB', (2, 2), color).save(salida, format='PNG')
    return base64.b64encode(salida.getvalue())


FOTO_A = foto((19, 64, 177))
FOTO_B = foto((254, 208, 15))


@tagged('post_install', '-at_install')
class TestNombresEnMayusculas(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gerencia = crear_usuario(cls.env, 'f5_gerencia', 'dcasa_base.group_gerencia')
        cls.vendedora = crear_usuario(cls.env, 'f5_vendedora', 'dcasa_base.group_vendedora')

    def test_la_regla(self):
        self.assertEqual(nombre_en_mayusculas('Sofá  seccional   milán '), 'SOFÁ SECCIONAL MILÁN')
        self.assertEqual(nombre_en_mayusculas('cama queen 1.5m x 2m'), 'CAMA QUEEN 1.5M X 2M')
        self.assertIsNone(nombre_en_mayusculas(None))

    def test_lo_nuevo_se_guarda_en_mayusculas(self):
        plantilla = self.env['product.template'].with_user(self.gerencia).create({'name': 'Mesa de centro roble'})
        self.assertEqual(plantilla.name, 'MESA DE CENTRO ROBLE')
        variante = self.env['product.product'].create({'name': 'silla ñandú'})
        self.assertEqual(variante.name, 'SILLA ÑANDÚ')
        plantilla.with_user(self.vendedora).write({'name': 'mesa de centro nogal'})
        self.assertEqual(plantilla.name, 'MESA DE CENTRO NOGAL')
        nombre_rapido = self.env['product.template'].name_create('cojín azul')
        self.assertEqual(nombre_rapido[1], 'COJÍN AZUL')

    def _viejo(self, nombre):
        """Un producto «de antes»: con el nombre guardado tal cual (como quedó antes de F5)."""
        plantilla = self.env['product.template'].create({'name': 'x'})
        self.env.cr.execute("UPDATE product_template SET name = jsonb_build_object('en_US', %s, 'es_419', %s) "
                            'WHERE id = %s', [nombre, nombre, plantilla.id])
        plantilla.invalidate_recordset(['name'])
        return plantilla

    def test_lo_viejo_con_vista_previa_y_boton(self):
        viejo = self._viejo('Sofá cama gris')
        otro = self._viejo('Lámpara de pie')
        ya_bien = self.env['product.template'].create({'name': 'YA ESTÁ BIEN'})
        Asistente = self.env['dcasa.producto.mayusculas'].with_user(self.gerencia)
        asistente = Asistente.create(Asistente.default_get(['linea_ids']))
        lineas = {linea.product_tmpl_id: linea for linea in asistente.linea_ids}
        self.assertEqual(lineas[viejo].antes, 'Sofá cama gris')
        self.assertEqual(lineas[viejo].despues, 'SOFÁ CAMA GRIS')
        self.assertNotIn(ya_bien, lineas)
        # Lo que alguien cambió después de la vista previa no se toca.
        self.env.cr.execute("UPDATE product_template SET name = jsonb_build_object('en_US', 'Lampara nueva', "
                            "'es_419', 'Lampara nueva') WHERE id = %s", [otro.id])
        otro.invalidate_recordset(['name'])
        asistente.action_aplicar()
        self.env.flush_all()
        self.env.cr.execute('SELECT name FROM product_template WHERE id = %s', [viejo.id])
        self.assertEqual(self.env.cr.fetchone()[0], {'en_US': 'SOFÁ CAMA GRIS', 'es_419': 'SOFÁ CAMA GRIS'})
        self.assertEqual(otro.name, 'Lampara nueva')

    def test_solo_gerencia(self):
        with self.assertRaises(AccessError):
            self.env['dcasa.producto.mayusculas'].with_user(self.vendedora).default_get(['linea_ids'])

    def test_el_inventario_anterior_encuentra_sin_mayusculas(self):
        plantilla = self.env['product.template'].create({'name': 'Hamaca Doble Tejida'})
        encontrada = _buscar(self.env, {'llave': 'zz-no-existe', 'codigo': '', 'nombre': 'hamaca doble  tejida'})
        self.assertEqual(encontrada, plantilla.product_variant_ids[:1])


@tagged('post_install', '-at_install')
class TestProductosRepetidos(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.gerencia = crear_usuario(env, 'f5r_gerencia', 'dcasa_base.group_gerencia')
        cls.vendedora = crear_usuario(env, 'f5r_vendedora', 'dcasa_base.group_vendedora')
        cls.proveedor = env['res.partner'].create({'name': 'PROVEEDOR DE PRUEBA REPETIDOS'})
        cls.cliente = env['res.partner'].create({
            'name': 'CLIENTE DE PRUEBA REPETIDOS', 'phone': '6000-0071', 'email': 'cliente.repetidos@example.com'})
        Producto = env['product.product']
        cls.queda = Producto.create({
            'name': 'Comedor Roma 6 sillas', 'default_code': 'ROMA-600', 'is_storable': True, 'image_1920': FOTO_A,
            'seller_ids': [Command.create({'partner_id': cls.proveedor.id, 'price': 300.0})]})
        cls.sale = Producto.create({
            'name': 'COMEDOR ROMA 6 SILLAS', 'default_code': 'roma600', 'is_storable': True, 'image_1920': FOTO_B,
            'barcode': 'ZZ7501234567890',
            'seller_ids': [Command.create({'partner_id': cls.proveedor.id, 'price': 290.0})]})
        cls.etiqueta = Producto.create({'name': 'Mesa lateral', 'default_code': 'ZZ7509999000011'})
        cls.con_etiqueta = Producto.create({'name': 'Mesa lateral blanca', 'barcode': 'ZZ-7509999000011'})
        cls.almacen = env['stock.warehouse'].search([('company_id', '=', env.company.id)], limit=1)
        env['stock.quant']._update_available_quantity(cls.queda, cls.almacen.lot_stock_id, 3)
        env['stock.quant']._update_available_quantity(cls.sale, cls.almacen.lot_stock_id, 2)

    def _grupos(self):
        Repetido = self.env['dcasa.producto.repetido'].with_user(self.gerencia)
        Repetido.flush_model()
        return Repetido.search([])

    def _grupo(self, tipo, producto):
        return self._grupos().filtered(
            lambda g: g.tipo == tipo and str(producto.id) in (g.ids_productos or '').split(','))

    def test_lista_de_parecidos(self):
        self.assertTrue(self._grupo('codigo', self.sale), 'ROMA-600 y roma600 son el mismo código')
        self.assertTrue(self._grupo('nombre', self.sale), 'el mismo nombre con otras mayúsculas')
        self.assertTrue(self._grupo('barras', self.con_etiqueta), 'su código de barras es la referencia del otro')
        with self.assertRaises(AccessError):
            self.env['dcasa.producto.repetido'].with_user(self.vendedora).search([])

    def _asistente(self, queda=None, sale=None):
        accion = self._grupo('codigo', self.sale).action_unir()
        asistente = self.env['dcasa.producto.unir'].with_user(self.gerencia).browse(accion['res_id'])
        if queda:
            asistente.write({'queda_id': queda.id, 'sale_id': sale.id})
        return asistente

    def test_unir_pasa_todo_y_archiva_sin_tocar_la_historia(self):
        asistente = self._asistente(self.queda, self.sale)
        self.assertFalse(asistente.bloqueos)
        self.assertIn('Pasan 2 unidades', asistente.resumen)
        asistente.action_unir()
        self.assertEqual(self.queda.qty_available, 5)
        self.assertEqual(self.sale.with_context(active_test=False).qty_available, 0)
        self.assertFalse(self.sale.product_tmpl_id.active)
        self.assertEqual(self.sale.product_tmpl_id.dcasa_unido_a_id, self.queda.product_tmpl_id)
        self.assertIn(self.sale.product_tmpl_id, self.queda.product_tmpl_id.dcasa_unidas_ids)
        self.assertEqual(sorted(self.queda.product_tmpl_id.seller_ids.mapped('price')), [290.0, 300.0])
        self.assertEqual(self.queda.barcode, 'ZZ7501234567890')
        self.assertFalse(self.sale.barcode)
        self.assertEqual(self.queda.image_1920, FOTO_A)
        self.assertIn(FOTO_B, self.queda.product_tmpl_id.product_template_image_ids.mapped('image_1920'))
        movimientos = self.env['stock.move'].search([('reference', 'like', 'Unión de productos%')])
        self.assertEqual(sorted(movimientos.mapped('product_id').ids), sorted((self.queda | self.sale).ids))
        self.assertIn('Se le unió', self.queda.product_tmpl_id.message_ids[0].body)

    def test_no_deja_unir_con_algo_a_medias(self):
        cotizacion = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': self.sale.id, 'product_uom_qty': 1})]})
        asistente = self._asistente(self.queda, self.sale)
        self.assertIn(cotizacion.name, asistente.bloqueos)
        with self.assertRaises(UserError):
            asistente.action_unir()
        self.assertTrue(self.sale.active)

    def test_no_se_archiva_una_ficha_con_varios_tamanos(self):
        talla = self.env['product.attribute'].create({'name': 'Zztalla f5', 'create_variant': 'always', 'value_ids': [
            Command.create({'name': 'Chica'}), Command.create({'name': 'Grande'})]})
        varias = self.env['product.template'].create({
            'name': 'Comedor roma con tallas', 'attribute_line_ids': [Command.create({
                'attribute_id': talla.id, 'value_ids': [Command.set(talla.value_ids.ids)]})]})
        asistente = self._asistente(self.queda, varias.product_variant_ids[0])
        self.assertIn('varios tamaños', asistente.bloqueos)

    def test_solo_gerencia_une(self):
        asistente = self._asistente(self.queda, self.sale)
        with self.assertRaises(AccessError):
            asistente.with_user(self.vendedora).action_unir()
