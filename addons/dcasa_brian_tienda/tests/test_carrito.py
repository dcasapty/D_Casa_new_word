"""El carrito del chat (contrato §3): la sesión del visitante, solo lo publicado y agregable, las cantidades, que otro
visitante no vea el carrito ajeno, el PDF sin datos de nadie y las estrellas (número y fecha)."""
from unittest.mock import patch

from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from ..controllers import main as C
from .common import RAIZ, TiendaCase


@tagged('post_install', '-at_install')
class TestCarrito(TiendaCase):

    def agregar(self, plantilla_o_id, cantidad=1, **kw):
        producto_id = plantilla_o_id.product_variant_id.id if hasattr(plantilla_o_id, 'product_variant_id') \
            else plantilla_o_id
        return self.post('carrito/agregar', {'producto_id': producto_id, 'cantidad': cantidad}, **kw)

    def carrito(self):
        respuesta = self.url_open(f'{RAIZ}/carrito')
        self.assertEqual(respuesta.headers['Cache-Control'], 'no-store')
        return respuesta.json()['carrito']

    def test_agrega_lo_publicado_y_los_numeros_salen_de_odoo(self):
        self.assertEqual(self.carrito()['lineas'], [], 'sin carrito todavía')
        datos = self.agregar(self.colchon, 2).json()
        self.assertTrue(datos['ok'], datos)
        (linea,) = datos['carrito']['lineas']
        self.assertEqual(linea['producto_id'], self.colchon.product_variant_id.id)
        nombre = self.colchon.product_variant_id._dcasa_nombre_cliente()
        self.assertEqual((linea['nombre'], linea['cantidad']), (nombre, 2))
        self.assertNotEqual(nombre, self.colchon.name, 'como lo lee el cliente, no en MAYÚSCULAS')
        self.assertEqual(linea['subtotal_texto'], '$556.00 + ITBMS')
        self.assertEqual(linea['imagen'], f'/web/image/product.product/{self.colchon.product_variant_id.id}/image_128')
        self.assertEqual(datos['carrito']['cantidad_total'], 2)
        self.assertEqual(datos['carrito']['total_texto'], '$556.00 + ITBMS')
        self.assertEqual(datos['carrito']['itbms_texto'], '$38.92')
        self.assertEqual(datos['carrito']['total_con_itbms_texto'], '$594.92')
        # Es el carrito de verdad de la tienda (/shop/cart lo muestra).
        self.assertIn('COLCHÓN QUEEN', self.url_open('/shop/cart').text.upper())
        self.assertEqual(self.carrito()['cantidad_total'], 2)

    def test_sumar_cambiar_y_quitar(self):
        self.agregar(self.colchon, 1)
        self.assertEqual(self.agregar(self.colchon, 3).json()['carrito']['cantidad_total'], 4, 'suma a la línea')
        self.assertEqual(self.agregar(self.colchon, 20).json()['carrito']['cantidad_total'], 20, 'una línea: hasta 20')
        self.agregar(self.base_cama, 1)
        datos = self.post('carrito/cantidad', {'producto_id': self.colchon.product_variant_id.id, 'cantidad': 2}).json()
        self.assertEqual({x['producto_id']: x['cantidad'] for x in datos['carrito']['lineas']},
                         {self.colchon.product_variant_id.id: 2, self.base_cama.product_variant_id.id: 1})
        datos = self.post('carrito/cantidad', {'producto_id': self.colchon.product_variant_id.id, 'cantidad': 0}).json()
        self.assertEqual([x['producto_id'] for x in datos['carrito']['lineas']],
                         [self.base_cama.product_variant_id.id], '0 = quitar')

    def test_solo_lo_publicado_agregable_y_con_precio(self):
        self.assertEqual(self.agregar(self.secreto).json(), {'ok': False, 'motivo': 'no_disponible'})
        self.assertEqual(self.agregar(99999999).json(), {'ok': False, 'motivo': 'no_disponible'})
        variante = self.con_medidas.product_variant_ids[0]
        elegir = self.agregar(variante.id).json()
        self.assertEqual((elegir['ok'], elegir['motivo'], elegir['url']),
                         (False, 'elegir', self.con_medidas.website_url))
        self.assertEqual(self.agregar(self.gratis).json()['motivo'], 'elegir', 'sin precio, a la ficha')
        self.assertEqual(self.carrito()['lineas'], [], 'nada de eso entró al carrito')
        king = self.de_medida.product_variant_ids[1]
        self.assertTrue(self.agregar(king.id).json()['ok'], 'una medida concreta, cuando solo se elige la medida')
        self.assertEqual([x['producto_id'] for x in self.carrito()['lineas']], [king.id])

    def test_cantidades_y_cuerpos_malos(self):
        for cantidad in (0, 21, -1, 1.5, True, '2', None):
            with self.subTest(cantidad=cantidad):
                self.assertEqual(self.agregar(self.colchon, cantidad).status_code, 400)
        for producto_id in ('1', None, True, 2 ** 31):
            with self.subTest(producto_id=producto_id):
                self.assertEqual(self.agregar(producto_id).status_code, 400)
        self.assertEqual(self.agregar(self.colchon, csrf=False).status_code, 403)
        self.assertEqual(self.carrito()['lineas'], [])

    def test_otro_visitante_no_ve_tu_carrito(self):
        self.agregar(self.colchon, 2)
        self.otra_sesion()
        self.assertEqual(self.carrito()['lineas'], [])
        self.assertEqual(self.post('carrito/cantidad', {'producto_id': self.colchon.product_variant_id.id,
                                                        'cantidad': 0}).json()['carrito']['lineas'], [])

    def test_apagado(self):
        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian_tienda.activo', 'False')
        self.assertEqual(self.agregar(self.colchon).json(), {'ok': False, 'motivo': 'apagado'})
        self.assertEqual(self.url_open(f'{RAIZ}/carrito').json(), {'ok': False, 'motivo': 'apagado'})


@tagged('post_install', '-at_install')
class TestCotizacionPdf(TiendaCase):

    def test_la_cotizacion_del_carrito_sin_datos_de_nadie(self):
        otra = self.env['res.partner'].create({'name': 'ZZBT Persona Ajena', 'phone': '+507 6000-0000'})
        self.post('carrito/agregar', {'producto_id': self.colchon.product_variant_id.id, 'cantidad': 2})
        adjuntos = self.env['ir.attachment'].sudo().search_count([])
        respuesta = self.url_open(f'{RAIZ}/carrito/cotizacion.pdf')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers['Cache-Control'], 'no-store')
        # En las pruebas Odoo no llama a wkhtmltopdf y devuelve el HTML del informe (el mismo contenido).
        texto = respuesta.text
        self.assertIn('Cliente: <strong>(por confirmar)</strong>', texto)
        self.assertIn(self.colchon.product_variant_id._dcasa_nombre_cliente(), texto)
        for cifra in ('556.00', '38.92', '594.92'):
            self.assertIn(cifra, texto)
        publico = self.env.ref('base.public_partner').name
        for ajeno in ('ZZBT Persona Ajena', '6000-0000', 'Public user', 'Usuario público', publico):
            self.assertNotIn(ajeno, texto)
        self.assertEqual(self.env['ir.attachment'].sudo().search_count([]), adjuntos, 'el PDF no se guarda')
        self.assertTrue(otra.exists())

    def test_con_cuenta_dice_su_nombre_y_sin_carrito_lleva_al_carrito(self):
        self.assertTrue(self.url_open(f'{RAIZ}/carrito/cotizacion.pdf', allow_redirects=False).headers['Location']
                        .endswith('/shop/cart'))
        cliente = new_test_user(self.env, login='zzbt_portal', password='zzbt_portal', name='ZZBT Cliente Con Cuenta',
                                groups='base.group_portal')
        self.authenticate('zzbt_portal', 'zzbt_portal')
        self.post('carrito/agregar', {'producto_id': self.colchon.product_variant_id.id, 'cantidad': 1})
        texto = self.url_open(f'{RAIZ}/carrito/cotizacion.pdf').text
        self.assertIn(f'Cliente: <strong>{cliente.name}</strong>', texto)

    def test_tope_de_cotizaciones_por_sesion(self):
        self.post('carrito/agregar', {'producto_id': self.colchon.product_variant_id.id, 'cantidad': 1})
        for _ in range(10):
            self.assertEqual(self.url_open(f'{RAIZ}/carrito/cotizacion.pdf').status_code, 200)
        respuesta = self.url_open(f'{RAIZ}/carrito/cotizacion.pdf')
        self.assertEqual((respuesta.status_code, respuesta.headers['Retry-After']), (429, '600'))
        self.assertIn('WhatsApp', respuesta.text)

    def test_a_lo_sumo_dos_cotizaciones_a_la_vez(self):
        """Con dos armándose (el semáforo lleno), la tercera se va al instante con 503 y Retry-After, sin contar."""
        self.post('carrito/agregar', {'producto_id': self.colchon.product_variant_id.id, 'cantidad': 1})
        self.assertEqual(C.MAX_PDF_A_LA_VEZ, 2)
        tomados = [C._SEMAFORO_PDF.acquire(blocking=False) for _ in range(C.MAX_PDF_A_LA_VEZ)]
        try:
            self.assertEqual(tomados, [True, True])
            respuesta = self.url_open(f'{RAIZ}/carrito/cotizacion.pdf')
            self.assertEqual((respuesta.status_code, respuesta.headers['Retry-After']), (503, '20'))
            self.assertIn('otras cotizaciones', respuesta.text)
        finally:
            for _ in tomados:
                C._SEMAFORO_PDF.release()
        self.assertEqual(self.env['dcasa.brian.tienda.cupo'].sudo().search_count([('llave', 'like', 'pdf:%')]), 0)
        self.assertEqual(self.url_open(f'{RAIZ}/carrito/cotizacion.pdf').status_code, 200, 'y al soltarse, vuelve')

    def test_si_el_pdf_falla_el_semaforo_se_suelta(self):
        self.post('carrito/agregar', {'producto_id': self.colchon.product_variant_id.id, 'cantidad': 1})
        Reporte = type(self.env['ir.actions.report'])
        with patch.object(Reporte, '_render_qweb_pdf', side_effect=RuntimeError('wkhtmltopdf se cayó')), \
                mute_logger('odoo.http'):
            for _ in range(3):
                self.assertEqual(self.url_open(f'{RAIZ}/carrito/cotizacion.pdf').status_code, 500)
        self.assertEqual(self.url_open(f'{RAIZ}/carrito/cotizacion.pdf').status_code, 200)


@tagged('post_install', '-at_install')
class TestCalificar(TiendaCase):

    def test_solo_numero_y_fecha_una_vez_por_chat(self):
        Calificacion = self.env['dcasa.brian.tienda.calificacion'].sudo()
        self.assertEqual(self.post('calificar', {'estrellas': 5}).json(), {'ok': False, 'motivo': 'sin_chat'},
                         'sin haber abierto el chat (sin pase) no se califica')
        self.assertTrue(self.post('pase').json()['ok'])
        for malo in (0, 6, '5', 4.5, True, None):
            with self.subTest(estrellas=malo):
                self.assertEqual(self.post('calificar', {'estrellas': malo}).status_code, 400)
        self.assertEqual(self.post('calificar', {'estrellas': 4}).json(), {'ok': True})
        self.assertEqual(self.post('calificar', {'estrellas': 1}).json(), {'ok': True, 'repetida': True})
        (fila,) = Calificacion.search([])
        self.assertEqual(fila.estrellas, 4)
        self.assertEqual(set(Calificacion._fields), {'id', 'fecha', 'estrellas', 'display_name'},
                         'solo número y fecha: ni sesión, ni red, ni texto, ni quién la creó')
        self.assertEqual(Calificacion._resumen(fila.fecha), {'cantidad': 1, 'promedio': 4.0})
