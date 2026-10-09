"""«Foto del catálogo» y «Cotización en PDF» de la caja de respuesta (mismas reglas de vista pública que Juan)."""
import base64
import io
import json
import shutil
from unittest import skipUnless
from unittest.mock import patch

from PIL import Image

try:
    import PyPDF2
except ImportError:   # con pypdf (Python 3.13+) no hay PyPDF2 que revisar
    PyPDF2 = None

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.service.model import call_kw
from odoo.tests import BaseCase, HttpCase, tagged

from ..models.conversacion_panel_catalogo import nombre_de_foto, pie_de_foto
from .test_panel import PanelCase


def foto(color=(19, 64, 177), tamano=(1600, 1200), formato='PNG', modo='RGB'):
    salida = io.BytesIO()
    Image.new(modo, tamano, color).save(salida, formato)
    return base64.b64encode(salida.getvalue())


@tagged('post_install', '-at_install')
class TestPieDeFoto(BaseCase):

    def test_pie_completo(self):
        self.assertEqual(
            pie_de_foto('Cama Roble Queen', '$349.99 + ITBMS', 'Ancho × Largo: 160 × 200 cm',
                        'https://dcasapty.com/shop/cama-1'),
            'Cama Roble Queen\n$349.99 + ITBMS\nMedidas: Ancho × Largo: 160 × 200 cm\nhttps://dcasapty.com/shop/cama-1')

    def test_no_se_rellena_lo_que_no_hay(self):
        self.assertEqual(pie_de_foto('Sofá Gris', '$800.00 + ITBMS', '', None), 'Sofá Gris\n$800.00 + ITBMS')
        self.assertEqual(pie_de_foto('Sofá Gris', '$800.00 + ITBMS', '  ', '  '), 'Sofá Gris\n$800.00 + ITBMS')

    def test_nombre_de_archivo(self):
        self.assertEqual(nombre_de_foto('Colchón First Class (Queen)', 2), 'colchon-first-class-queen-2.jpg')
        self.assertEqual(nombre_de_foto('', 1), 'producto-1.jpg')
        self.assertTrue(nombre_de_foto('x' * 200).startswith('x' * 40 + '-'))


class CatalogoCase(PanelCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Template = cls.env['product.template']
        impuesto = cls.env['brian.herramientas']._b_itbms_venta()
        cls.categoria = cls.env['product.public.category'].create({'name': 'Zzdormitorio'})
        base = {'type': 'consu', 'is_storable': True, 'sale_ok': True, 'is_published': True,
                'taxes_id': [Command.set(impuesto.ids)], 'public_categ_ids': [Command.set(cls.categoria.ids)]}
        cls.cama = Template.create({
            **base, 'name': 'Zzcama Roble Queen', 'default_code': 'ZZ-CAMA', 'list_price': 349.99,
            'standard_price': 123.45, 'dcasa_medidas': 'Ancho × Largo: 160 × 200 cm', 'image_1920': foto(),
            'product_template_image_ids': [
                Command.create({'name': 'Lado', 'image_1920': foto((200, 30, 30))}),
                Command.create({'name': 'Detalle', 'image_1920': foto((30, 200, 30))})]})
        cls.sofa = Template.create({**base, 'name': 'Zzsofa Gris', 'default_code': 'ZZ-SOFA', 'list_price': 800.0})
        cls.secreto = Template.create({**base, 'name': 'Zzsecreto Borrador', 'default_code': 'ZZ-SECRETO',
                                       'list_price': 10.0, 'is_published': False, 'image_1920': foto()})
        tamano = cls.env['product.attribute'].create({'name': 'Zztamaño', 'create_variant': 'always', 'value_ids': [
            Command.create({'name': 'Zzqueen'}), Command.create({'name': 'Zzking'})]})
        cls.colchon = Template.create({
            **base, 'name': 'Zzcolchón First Class', 'list_price': 400.0, 'default_code': 'ZZ-COL',
            'attribute_line_ids': [Command.create({'attribute_id': tamano.id,
                                                   'value_ids': [Command.set(tamano.value_ids.ids)]})]})
        almacen = cls.env['stock.warehouse'].search([], limit=1)
        cls.env['stock.quant']._update_available_quantity(cls.cama.product_variant_id, almacen.lot_stock_id, 7777)
        cls.env['stock.quant']._update_available_quantity(cls.sofa.product_variant_id, almacen.lot_stock_id, 3)

    def setUp(self):
        super().setUp()
        self.worker = self.configurar_worker()
        self.conv = self.cliente(1)

    def envios(self):
        return [c for c in self.worker.call_args_list if c.args[1].endswith('/odoo/enviar')]


@tagged('post_install', '-at_install')
class TestBuscarCatalogo(CatalogoCase):

    def nombres(self, resultado):
        return [p['nombre'] for p in resultado['productos']]

    def test_busca_por_nombre_y_por_codigo_solo_entre_los_publicados(self):
        self.assertEqual(self.nombres(self.panel.buscar_catalogo('zzcama queen')), ['Zzcama Roble Queen'])
        self.assertEqual(self.nombres(self.panel.buscar_catalogo('ZZ-SOFA')), ['Zzsofa Gris'])
        todo = self.panel.buscar_catalogo('zz')
        self.assertNotIn('Zzsecreto Borrador', self.nombres(todo), 'Un producto sin publicar no existe')
        self.assertEqual(todo['encontrados'], 3)
        self.assertEqual(self.panel.buscar_catalogo('ZZ-SECRETO')['encontrados'], 0)

    def test_consultas_vacias_o_raras_no_devuelven_todo_el_catalogo(self):
        for consulta in ('', '   ', None, 'a', '!!!'):
            with self.subTest(consulta=consulta):
                self.assertEqual(self.panel.buscar_catalogo(consulta), {'productos': [], 'encontrados': 0})

    def test_precio_mas_itbms_y_disponibilidad_como_etiqueta(self):
        (cama,) = self.panel.buscar_catalogo('ZZ-CAMA')['productos']
        self.assertEqual((cama['precio'], cama['precio_texto'], cama['mas_itbms']), (349.99, '$349.99 + ITBMS', True))
        self.assertEqual(cama['disponibilidad'], 'disponible')
        (sofa,) = self.panel.buscar_catalogo('ZZ-SOFA')['productos']
        self.assertEqual(sofa['disponibilidad'], 'pocas')
        self.assertEqual(self.panel.buscar_catalogo('first class')['productos'][0]['disponibilidad'], 'agotado')

    def test_nunca_el_numero_de_existencias_ni_costos(self):
        datos = json.dumps(self.panel.buscar_catalogo('zz'), ensure_ascii=False)
        self.assertNotIn('7777', datos)
        self.assertNotIn('123.45', datos)
        self.assertNotRegex(datos, r'(?i)standard_price|costo|free_qty|qty_available|existencias')

    def test_trae_medidas_enlace_y_fotos(self):
        (cama,) = self.panel.buscar_catalogo('ZZ-CAMA')['productos']
        self.assertEqual(cama['medidas'], 'Ancho × Largo: 160 × 200 cm')
        self.assertEqual(cama['id'], self.cama.id)
        self.assertEqual(cama['fotos_total'], 3)
        self.assertRegex(
            cama['miniatura'], rf'^/dcasa/img/product\.template/{self.cama.id}/image_1920/256\.webp\?v=\w+$')
        self.assertTrue(cama['url'].endswith(self.cama.website_url))
        (sofa,) = self.panel.buscar_catalogo('ZZ-SOFA')['productos']
        self.assertEqual((sofa['fotos_total'], sofa['miniatura']), (0, None), 'Sin foto no se inventa una')

    def test_un_producto_con_variantes_lista_cada_una(self):
        (colchon,) = self.panel.buscar_catalogo('ZZ-COL')['productos']
        self.assertIsNone(colchon['variante_id'])
        self.assertEqual(sorted(v['nombre'] for v in colchon['variantes']),
                         ['Zzcolchón First Class (Zzking)', 'Zzcolchón First Class (Zzqueen)'])
        (cama,) = self.panel.buscar_catalogo('ZZ-CAMA')['productos']
        self.assertEqual((cama['variante_id'], cama['variantes']), (self.cama.product_variant_id.id, []))

    def test_limite(self):
        self.assertEqual(len(self.panel.buscar_catalogo('zz', limite=2)['productos']), 2)
        self.assertEqual(self.panel.buscar_catalogo('zz', limite=2)['encontrados'], 3)
        self.assertLessEqual(len(self.panel.buscar_catalogo('zz', limite=500)['productos']), 8)

    def test_solo_el_equipo_de_ventas_por_rpc(self):
        for usuario in (self.interno, self.portal):
            for metodo, args in (('buscar_catalogo', ['cama']), ('fotos_catalogo', [self.cama.id]),
                                 ('enviar_foto_catalogo', [self.conv.id, self.cama.id]),
                                 ('preparar_foto_catalogo', [self.conv.id, self.cama.id]),
                                 ('cotizaciones_abiertas', [self.conv.id]),
                                 ('crear_cotizacion', [self.conv.id, []]), ('enviar_cotizacion', [self.conv.id])):
                with self.subTest(usuario=usuario.login, metodo=metodo), self.assertRaises(AccessError):
                    call_kw(self.env(user=usuario)['dcasa.conversacion'], metodo, list(args), {})


@tagged('post_install', '-at_install')
class TestFotosYEnvio(CatalogoCase):

    def test_las_fotos_de_un_producto(self):
        resultado = self.panel.fotos_catalogo(self.cama.id)
        self.assertEqual(resultado['producto']['nombre'], 'Zzcama Roble Queen')
        refs = [f['ref'] for f in resultado['fotos']]
        self.assertEqual(refs[0], 'principal')
        self.assertEqual(len(refs), 3)
        for f in resultado['fotos']:
            self.assertRegex(f['miniatura'], r'/256\.webp\?v=')
            self.assertRegex(f['grande'], r'/1024\.webp\?v=')

    def test_un_producto_sin_publicar_no_tiene_fotos_para_nadie(self):
        for metodo, args in (('fotos_catalogo', [self.secreto.id]),
                             ('enviar_foto_catalogo', [self.conv.id, self.secreto.id])):
            with self.subTest(metodo=metodo), self.assertRaises(UserError):
                getattr(self.panel, metodo)(*args)
        self.assertFalse(self.envios())

    def test_manda_la_foto_con_el_pie_armado(self):
        resultado = self.panel.enviar_foto_catalogo(self.conv.id, self.cama.id)
        self.assertTrue(resultado['enviado'])
        (envio,) = self.envios()
        cuerpo = envio.kwargs['json']
        lineas = cuerpo['texto'].split('\n')
        self.assertEqual(lineas[0], 'Zzcama Roble Queen')
        self.assertEqual(lineas[1], '$349.99 + ITBMS')
        self.assertEqual(lineas[2], 'Medidas: Ancho × Largo: 160 × 200 cm')
        self.assertTrue(lineas[3].endswith(self.cama.website_url))
        self.assertEqual(len(lineas), 4)
        (adjunto,) = cuerpo['adjuntos']
        self.assertEqual((adjunto['tipo'], adjunto['mime'], adjunto['nombre']),
                         ('imagen', 'image/jpeg', 'zzcama-roble-queen-1.jpg'))
        self.assertRegex(adjunto['url'], r'/dcasa/adjunto/\d+/\d+/[0-9a-f]{64}/zzcama-roble-queen-1\.jpg$')
        self.assertNotIn('123.45', json.dumps(cuerpo))

    def test_la_foto_sale_en_jpeg_de_hasta_1024_px_y_sin_transparencias(self):
        self.cama.image_1920 = foto((0, 0, 0, 0), (2000, 1000), 'PNG', 'RGBA')
        resultado = self.panel.enviar_foto_catalogo(self.conv.id, self.cama.id)
        (adjunto,) = resultado['mensaje']['adjuntos']
        registro = self.env['ir.attachment'].browse(adjunto['id'])
        imagen = Image.open(io.BytesIO(registro.raw))
        self.assertEqual((imagen.format, imagen.width), ('JPEG', 1024))
        self.assertEqual(imagen.convert('RGB').getpixel((10, 10)), (255, 255, 255), 'Fondo blanco, no negro')
        self.assertEqual((registro.res_model, registro.create_uid), ('dcasa.mensaje', self.vendedora))

    def test_la_galeria_manda_varias_fotos_en_un_mensaje(self):
        galeria = self.panel.fotos_catalogo(self.cama.id)['fotos']
        resultado = self.panel.enviar_foto_catalogo(self.conv.id, self.cama.id, [f['ref'] for f in galeria])
        self.assertEqual([a['nombre'] for a in resultado['mensaje']['adjuntos']],
                         ['zzcama-roble-queen-1.jpg', 'zzcama-roble-queen-2.jpg', 'zzcama-roble-queen-3.jpg'])
        (envio,) = self.envios()
        self.assertEqual(len(envio.kwargs['json']['adjuntos']), 3)
        self.assertEqual(len(self.conv.mensaje_ids.filtered(lambda m: m.autor == 'vendedora')), 1)

    def test_el_pie_se_puede_cambiar(self):
        resultado = self.panel.enviar_foto_catalogo(self.conv.id, self.cama.id, None, 'Esta es la que te dije')
        (envio,) = self.envios()
        self.assertEqual(envio.kwargs['json']['texto'], 'Esta es la que te dije')
        self.assertEqual(resultado['mensaje']['texto'], 'Esta es la que te dije')

    def test_preparar_deja_las_fotos_en_la_caja_sin_enviar_nada(self):
        preparado = self.panel.preparar_foto_catalogo(self.conv.id, self.cama.id)
        self.assertTrue(preparado['texto'].startswith('Zzcama Roble Queen\n$349.99 + ITBMS'))
        (adjunto,) = preparado['adjuntos']
        self.assertEqual(adjunto['tipo'], 'imagen')
        self.assertFalse(self.envios())
        registro = self.env['ir.attachment'].browse(adjunto['id'])
        self.assertEqual((registro.res_model, registro.res_id), ('dcasa.conversacion', self.conv.id))
        # Y desde la caja se envía como cualquier respuesta.
        self.panel.enviar_respuesta(self.conv.id, preparado['texto'] + '\nTe la dejo apartada', [adjunto['id']])
        self.assertEqual(len(self.envios()), 1)

    def test_fotos_invalidas(self):
        demasiadas = ['principal'] + [f'galeria-{n}' for n in range(8)]
        for fotos in (['galeria-999999'], ['inexistente'], [5], 'principal', demasiadas):
            with self.subTest(fotos=fotos), self.assertRaises(UserError):
                self.panel.enviar_foto_catalogo(self.conv.id, self.cama.id, fotos)
        with self.assertRaises(UserError):
            self.panel.enviar_foto_catalogo(self.conv.id, self.sofa.id)   # sin foto: no se inventa una
        with self.assertRaises(UserError):
            self.panel.enviar_foto_catalogo(self.conv.id, self.cama.id, None, 5)
        for malo in (0, -1, 'x', None, True):
            with self.subTest(producto=malo), self.assertRaises(UserError):
                self.panel.enviar_foto_catalogo(self.conv.id, malo)
        self.assertFalse(self.envios())

    def test_la_foto_enviada_toma_la_conversacion_igual_que_cualquier_respuesta(self):
        self.panel.enviar_foto_catalogo(self.conv.id, self.cama.id)
        self.assertEqual((self.conv.estado, self.conv.asignada_a), ('humano', self.vendedora))


@tagged('post_install', '-at_install')
class TestCotizacion(CatalogoCase):

    def setUp(self):
        super().setUp()
        self.partner = self.conv.partner_id

    def orden(self, estado='draft', partner=None, **valores):
        return self.env['sale.order'].with_user(self.vendedora).create({
            'partner_id': (partner or self.partner).id, 'user_id': self.vendedora.id,
            'order_line': [Command.create({'product_id': self.cama.product_variant_id.id, 'product_uom_qty': 1})],
            **valores})

    def test_sin_cotizaciones_abiertas(self):
        self.assertEqual(self.panel.cotizaciones_abiertas(self.conv.id), {'cotizaciones': [], 'cliente': True})

    def test_la_abierta_mas_reciente_va_primero_y_las_confirmadas_no_cuentan(self):
        vieja = self.orden()
        confirmada = self.orden()
        confirmada.action_confirm()
        nueva = self.orden()
        resultado = self.panel.cotizaciones_abiertas(self.conv.id)
        self.assertEqual([c['id'] for c in resultado['cotizaciones']], [nueva.id, vieja.id])
        primera = resultado['cotizaciones'][0]
        self.assertEqual((primera['estado'], primera['estado_nombre']), ('draft', 'Borrador'))
        self.assertEqual(primera['lineas'][0]['producto'], 'Zzcama Roble Queen')
        self.assertEqual(primera['lineas'][0]['cantidad'], 1)
        self.assertAlmostEqual(primera['subtotal'], 349.99)
        self.assertAlmostEqual(primera['total'], 349.99 * 1.07, places=2)

    def test_las_de_otro_cliente_no_se_mezclan(self):
        otro = self.cliente(2).partner_id
        self.orden(partner=otro)
        self.assertEqual(self.panel.cotizaciones_abiertas(self.conv.id)['cotizaciones'], [])

    def test_crear_un_borrador_con_productos_del_catalogo_sin_confirmar(self):
        resultado = self.panel.crear_cotizacion(self.conv.id, [
            {'variante_id': self.cama.product_variant_id.id, 'cantidad': 2},
            {'variante_id': self.sofa.product_variant_id.id, 'cantidad': 1}])
        orden = self.env['sale.order'].browse(resultado['cotizacion']['id'])
        self.assertEqual((orden.state, orden.partner_id, orden.user_id), ('draft', self.partner, self.vendedora))
        self.assertEqual(sorted((linea.product_id.name, linea.product_uom_qty) for linea in orden.order_line),
                         [('Zzcama Roble Queen', 2.0), ('Zzsofa Gris', 1.0)])
        self.assertAlmostEqual(orden.amount_untaxed, 2 * 349.99 + 800.0)
        self.assertEqual(resultado['cotizacion']['estado'], 'draft')
        self.assertIn('Sin confirmar', orden.message_ids[0].body)

    def test_el_precio_lo_pone_odoo_no_la_pantalla(self):
        resultado = self.panel.crear_cotizacion(self.conv.id, [
            {'variante_id': self.cama.product_variant_id.id, 'cantidad': 1, 'precio': 1.0}])
        self.assertAlmostEqual(resultado['cotizacion']['lineas'][0]['precio_unitario'], 349.99)

    def test_cotizacion_invalida(self):
        variante = self.cama.product_variant_id.id
        casos = {
            'sin lineas': [], 'no es lista': 'x', 'demasiadas': [{'variante_id': variante, 'cantidad': 1}] * 21,
            'no publicado': [{'variante_id': self.secreto.product_variant_id.id, 'cantidad': 1}],
            'inexistente': [{'variante_id': 999999999, 'cantidad': 1}],
            'cantidad cero': [{'variante_id': variante, 'cantidad': 0}],
            'cantidad enorme': [{'variante_id': variante, 'cantidad': 10 ** 6}],
            'cantidad texto': [{'variante_id': variante, 'cantidad': '2'}],
            'línea rara': ['x'], 'sin variante': [{'cantidad': 1}],
        }
        for nombre, lineas in casos.items():
            with self.subTest(nombre), self.assertRaises(UserError):
                self.panel.crear_cotizacion(self.conv.id, lineas)
        self.assertFalse(self.env['sale.order'].search([('partner_id', '=', self.partner.id)]))

    def test_sin_cotizacion_abierta_no_hay_que_enviar(self):
        with self.assertRaises(UserError) as error:
            self.panel.enviar_cotizacion(self.conv.id)
        self.assertIn('cotización abierta', str(error.exception))
        confirmada = self.orden()
        confirmada.action_confirm()
        with self.assertRaises(UserError):
            self.panel.enviar_cotizacion(self.conv.id, confirmada.id)
        self.assertFalse(self.envios())

    def test_enviar_una_cotizacion_de_otro_cliente_no_se_puede(self):
        ajena = self.orden(partner=self.cliente(2).partner_id)
        with self.assertRaises(UserError):
            self.panel.enviar_cotizacion(self.conv.id, ajena.id)
        for malo in (0, 'x', True):
            with self.subTest(orden=malo), self.assertRaises(UserError):
                self.panel.enviar_cotizacion(self.conv.id, malo)

    def test_sin_el_pdf_no_se_envia_un_archivo_roto(self):
        self.orden()
        with patch('odoo.addons.base.models.ir_actions_report.IrActionsReport._render_qweb_pdf',
                   return_value=(b'<html>no es pdf</html>', 'html')), self.assertRaises(UserError):
            self.panel.enviar_cotizacion(self.conv.id)
        self.assertFalse(self.envios())


def _pypdf2_compatible():
    """Odoo 19 usa PyPDF2 < 3 (requirements.txt: 2.12.1); con PyPDF2 3.x el PDF de una cotización no sale."""
    return PyPDF2 is None or int(PyPDF2.__version__.split('.')[0]) < 3


@tagged('post_install', '-at_install')
class TestCotizacionEnPdf(HttpCase, CatalogoCase):
    """El PDF de verdad: wkhtmltopdf pide los estilos al propio Odoo (hace falta el servidor de HttpCase)."""

    def setUp(self):
        super().setUp()
        self.partner = self.conv.partner_id

    def orden(self, **valores):
        return self.env['sale.order'].with_user(self.vendedora).create({
            'partner_id': self.partner.id, 'user_id': self.vendedora.id,
            'order_line': [Command.create({'product_id': self.cama.product_variant_id.id, 'product_uom_qty': 1})],
            **valores})

    @skipUnless(shutil.which('wkhtmltopdf') and _pypdf2_compatible(),
                'Falta wkhtmltopdf, o el PyPDF2 instalado no es el que pide Odoo (< 3)')
    def test_envia_la_cotizacion_abierta_en_pdf_como_documento(self):
        orden = self.orden()
        resultado = self.panel.enviar_cotizacion(self.conv.id)
        (adjunto,) = resultado['mensaje']['adjuntos']
        self.assertEqual((adjunto['tipo'], adjunto['mime']), ('documento', 'application/pdf'))
        self.assertEqual(adjunto['nombre'], f'Cotizacion-{orden.name}.pdf')
        registro = self.env['ir.attachment'].browse(adjunto['id'])
        self.assertTrue(registro.raw.startswith(b'%PDF'), 'Es un PDF de verdad, no el HTML del modo de pruebas')
        (envio,) = self.envios()
        self.assertEqual(envio.kwargs['json']['adjuntos'][0]['tipo'], 'documento')
        self.assertIn(orden.name, envio.kwargs['json']['texto'])
        self.assertEqual(orden.state, 'sent', 'Enviada, no confirmada')
        self.assertEqual(resultado['cotizacion']['estado'], 'sent')

    @skipUnless(shutil.which('wkhtmltopdf') and _pypdf2_compatible(),
                'Falta wkhtmltopdf, o el PyPDF2 instalado no es el que pide Odoo (< 3)')
    def test_envia_la_que_se_elige_y_el_texto_se_puede_cambiar(self):
        elegida, _mas_nueva = self.orden(), self.orden()
        resultado = self.panel.enviar_cotizacion(self.conv.id, elegida.id, 'Mira, esta es la buena')
        self.assertEqual(resultado['mensaje']['texto'], 'Mira, esta es la buena')
        self.assertEqual(resultado['cotizacion']['id'], elegida.id)
