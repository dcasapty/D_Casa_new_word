"""Las fotos de un producto: ver, subir varias, ordenar, principal, quitar, girar, recortar y quién puede cambiarlas."""
import base64
import io

from PIL import Image

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .comun import MarketingCommon, color_al_centro, crear_usuario, foto, tamano

AZUL = (19, 64, 177)
ROJO = (200, 30, 30)
VERDE = (30, 160, 60)
AMARILLO = (254, 208, 15)


def parecido(a, b, tolerancia=12):
    return all(abs(x - y) <= tolerancia for x, y in zip(a, b, strict=True))


@tagged('post_install', '-at_install')
class TestFotosDelProducto(MarketingCommon):

    def setUp(self):
        super().setUp()
        self.sofa = self.producto('ZZMK Sofá de fotos', 'ZZMK-FOTO-1', stock=3)

    def fotos(self, plantilla=None, usuario=None):
        return (plantilla or self.sofa).with_user(usuario or self.gerencia).dcasa_fotos()

    def datos(self, clave, plantilla=None):
        """La foto ``clave`` guardada (base64, la más grande)."""
        plantilla = plantilla or self.sofa
        plantilla.invalidate_recordset()
        if clave == 'principal':
            return plantilla.image_1920
        return self.env['product.image'].browse(int(clave.split('-')[1])).image_1920

    def subir(self, *colores, usuario=None, plantilla=None):
        return (plantilla or self.sofa).with_user(usuario or self.gerencia).dcasa_fotos_subir(
            [{'nombre': f'foto{i}.jpg', 'datos': foto(color=color)} for i, color in enumerate(colores)])

    def colores(self, resultado, plantilla=None):
        return [color_al_centro(self.datos(f['clave'], plantilla)) for f in resultado['fotos']]

    def test_subir_varias_la_primera_es_la_principal_y_el_orden_se_respeta(self):
        resultado = self.subir(AZUL, ROJO, VERDE)
        claves = [f['clave'] for f in resultado['fotos']]
        self.assertEqual(claves[0], 'principal')
        self.assertEqual(len(claves), 3)
        self.assertTrue(all(c.startswith('extra-') for c in claves[1:]))
        for color, esperado in zip(self.colores(resultado), (AZUL, ROJO, VERDE), strict=True):
            self.assertTrue(parecido(color, esperado), (color, esperado))
        self.assertTrue(resultado['fotos'][0]['principal'])
        # Más fotos van al final de las extra.
        resultado = self.subir(AMARILLO)
        self.assertEqual(len(resultado['fotos']), 4)
        self.assertTrue(parecido(self.colores(resultado)[-1], AMARILLO))
        # Cada foto trae su URL grande, mediana, miniatura y la de descarga, con su versión.
        primera = resultado['fotos'][0]
        self.assertIn('/web/image/product.template/', primera['grande'])
        self.assertIn('image_1920?unique=', primera['grande'])
        self.assertIn('download=true', primera['descarga'])
        self.assertTrue(primera['nombre_archivo'].startswith('ZZMK-FOTO-1-1.'))

    def test_reemplazar_la_principal_y_una_extra(self):
        self.subir(AZUL, ROJO)
        antes = self.fotos()
        url_antes = antes['fotos'][0]['grande']
        despues = self.sofa.with_user(self.gerencia).dcasa_fotos_reemplazar('principal', foto(color=VERDE))
        self.assertTrue(parecido(self.colores(despues)[0], VERDE))
        self.assertNotEqual(despues['fotos'][0]['grande'], url_antes, 'la URL cambia de versión: no se ve la vieja')
        extra = despues['fotos'][1]['clave']
        despues = self.sofa.with_user(self.gerencia).dcasa_fotos_reemplazar(extra, foto(color=AMARILLO))
        self.assertEqual([f['clave'] for f in despues['fotos']], ['principal', extra], 'en el mismo lugar')
        self.assertTrue(parecido(self.colores(despues)[1], AMARILLO))

    def test_ordenar_las_extra_y_cambiar_la_principal_arrastrando(self):
        resultado = self.subir(AZUL, ROJO, VERDE, AMARILLO)
        principal, rojo, verde, amarillo = [f['clave'] for f in resultado['fotos']]
        # Solo las extra cambian de lugar: la principal sigue igual.
        resultado = self.sofa.with_user(self.gerencia).dcasa_fotos_ordenar([principal, amarillo, rojo, verde])
        self.assertEqual([f['clave'] for f in resultado['fotos']], [principal, amarillo, rojo, verde])
        # La verde pasa a ser la primera: es la nueva principal y la azul queda donde la pusieron (tercera).
        resultado = self.sofa.with_user(self.gerencia).dcasa_fotos_ordenar([verde, amarillo, principal, rojo])
        colores = self.colores(resultado)
        for color, esperado in zip(colores, (VERDE, AMARILLO, AZUL, ROJO), strict=True):
            self.assertTrue(parecido(color, esperado), (colores, esperado))
        self.assertEqual(len(resultado['fotos']), 4)
        # Un orden que no tiene las mismas fotos (otra pestaña cambió algo) no se aplica.
        with self.assertRaises(UserError):
            self.sofa.with_user(self.gerencia).dcasa_fotos_ordenar([f['clave'] for f in resultado['fotos']][:3])
        with self.assertRaises(UserError):
            self.sofa.with_user(self.gerencia).dcasa_fotos_ordenar(['principal', 'extra-999999', 'x', 'y'])

    def test_poner_como_principal_deja_la_vieja_segunda(self):
        resultado = self.subir(AZUL, ROJO, VERDE)
        verde = resultado['fotos'][2]['clave']
        resultado = self.sofa.with_user(self.gerencia).dcasa_fotos_principal(verde)
        colores = self.colores(resultado)
        for color, esperado in zip(colores, (VERDE, AZUL, ROJO), strict=True):
            self.assertTrue(parecido(color, esperado), (colores, esperado))

    def test_quitar_la_principal_sube_la_siguiente_y_quitar_la_ultima_deja_sin_foto(self):
        resultado = self.subir(AZUL, ROJO)
        resultado = self.sofa.with_user(self.gerencia).dcasa_fotos_quitar('principal')
        self.assertEqual(len(resultado['fotos']), 1)
        self.assertTrue(parecido(self.colores(resultado)[0], ROJO), 'la siguiente pasa a principal')
        self.assertFalse(self.sofa.product_template_image_ids, 'su registro de extra se va')
        resultado = self.sofa.with_user(self.gerencia).dcasa_fotos_quitar('principal')
        self.assertEqual(resultado['fotos'], [])
        self.assertFalse(self.sofa.image_1920)
        # Quitar una extra
        resultado = self.subir(AZUL, ROJO, VERDE)
        resultado = self.sofa.with_user(self.gerencia).dcasa_fotos_quitar(resultado['fotos'][1]['clave'])
        for color, esperado in zip(self.colores(resultado), (AZUL, VERDE), strict=True):
            self.assertTrue(parecido(color, esperado))

    def test_girar_y_recortar_en_el_servidor_sin_perder_tamano(self):
        self.sofa.with_user(self.gerencia).dcasa_fotos_subir([{'nombre': 'a.jpg', 'datos': foto(300, 200)}])
        self.sofa.with_user(self.gerencia).dcasa_fotos_girar('principal', 'derecha')
        self.assertEqual(tamano(self.datos('principal')), (200, 300))
        self.sofa.with_user(self.gerencia).dcasa_fotos_girar('principal', 'izquierda')
        self.assertEqual(tamano(self.datos('principal')), (300, 200))
        # La franja blanca estaba arriba a la izquierda: sigue ahí después de dar la vuelta completa.
        with Image.open(io.BytesIO(base64.b64decode(self.datos('principal')))) as imagen:
            self.assertTrue(parecido(imagen.convert('RGB').getpixel((5, 5)), (255, 255, 255)))
        self.sofa.with_user(self.gerencia).dcasa_fotos_recortar('principal', 100, 50, 150, 120)
        self.assertEqual(tamano(self.datos('principal')), (150, 120))
        # Lo que se sale de la foto se ajusta al borde.
        self.sofa.with_user(self.gerencia).dcasa_fotos_recortar('principal', 50, 20, 9999, 9999)
        self.assertEqual(tamano(self.datos('principal')), (100, 100))
        with self.assertRaises(UserError):
            self.sofa.with_user(self.gerencia).dcasa_fotos_recortar('principal', 0, 0, 5, 5)
        with self.assertRaises(UserError):
            self.sofa.with_user(self.gerencia).dcasa_fotos_recortar('principal', 'a', 0, 50, 50)
        with self.assertRaises(UserError):
            self.sofa.with_user(self.gerencia).dcasa_fotos_girar('principal', 'arriba')
        # Recortar a la foto entera no cambia nada.
        antes = self.datos('principal')
        self.sofa.with_user(self.gerencia).dcasa_fotos_recortar('principal', 0, 0, 100, 100)
        self.assertEqual(self.datos('principal'), antes)

    def test_la_orientacion_de_la_camara_se_aplica_antes_de_girar(self):
        """Una foto del celular «acostada» con la marca EXIF de girarla: se recorta y gira como la ve el navegador."""
        imagen = Image.new('RGB', (300, 200), AZUL)
        exif = imagen.getexif()
        exif[0x0112] = 6  # girar 90° a la derecha para verla derecha
        salida = io.BytesIO()
        imagen.save(salida, format='JPEG', exif=exif.tobytes())
        self.sofa.image_1920 = base64.b64encode(salida.getvalue())
        self.sofa.with_user(self.gerencia).dcasa_fotos_recortar('principal', 0, 0, 200, 150)
        self.assertEqual(tamano(self.datos('principal')), (200, 150), 'el navegador la ve de 200 × 300')

    def test_solo_fotos_de_verdad_y_de_un_tamano_razonable(self):
        for datos in ('', 'no-es-base64!!', base64.b64encode(b'hola, soy un texto').decode(), None):
            with self.subTest(datos=datos), self.assertRaises(UserError):
                self.sofa.with_user(self.gerencia).dcasa_fotos_subir([{'nombre': 'x', 'datos': datos}])
        with self.assertRaises(UserError):
            self.sofa.with_user(self.gerencia).dcasa_fotos_subir([])
        with self.assertRaises(UserError):
            self.sofa.with_user(self.gerencia).dcasa_fotos_subir(
                [{'nombre': str(i), 'datos': foto(20, 20)} for i in range(11)])
        # PNG y WebP también.
        resultado = self.sofa.with_user(self.gerencia).dcasa_fotos_subir([
            {'nombre': 'a.png', 'datos': foto(formato='PNG')}, {'nombre': 'b.webp', 'datos': foto(formato='WEBP')}])
        self.assertEqual(len(resultado['fotos']), 2)
        self.sofa.with_user(self.gerencia).dcasa_fotos_girar(resultado['fotos'][1]['clave'], 'derecha')

    def test_los_videos_de_la_tienda_no_se_tocan_y_quedan_al_final(self):
        video = self.env['product.image'].create({
            'product_tmpl_id': self.sofa.id, 'name': 'Video', 'sequence': 1,
            'video_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'})
        resultado = self.subir(AZUL, ROJO, VERDE)
        self.assertEqual(len(resultado['fotos']), 3, 'el video no sale como foto')
        claves = [f['clave'] for f in resultado['fotos']]
        self.sofa.with_user(self.gerencia).dcasa_fotos_ordenar([claves[0], claves[2], claves[1]])
        fotos = self.sofa.product_template_image_ids.filtered(lambda i: not i.video_url)
        self.assertGreater(video.sequence, max(fotos.mapped('sequence')))
        self.assertTrue(video.exists())

    def test_quien_puede_editar_el_producto_cambia_sus_fotos_y_los_demas_solo_ven(self):
        self.subir(AZUL, ROJO)
        # La vendedora edita el producto (dcasa_base): también sus fotos, las extra incluidas.
        self.assertTrue(self.fotos(usuario=self.vendedora)['puede_editar'])
        resultado = self.subir(VERDE, usuario=self.vendedora)
        self.assertEqual(len(resultado['fotos']), 3)
        self.sofa.with_user(self.vendedora).dcasa_fotos_principal(resultado['fotos'][2]['clave'])
        # Quien solo ve productos (bodega sin Ventas) los ve, pero no los cambia aunque llame a mano.
        vista = self.fotos(usuario=self.bodega)
        self.assertFalse(vista['puede_editar'])
        self.assertEqual(len(vista['fotos']), 3)
        clave = vista['fotos'][1]['clave']
        Sofa = self.sofa.with_user(self.bodega)
        for metodo, args in (('dcasa_fotos_subir', [[{'nombre': 'x', 'datos': foto()}]]),
                             ('dcasa_fotos_reemplazar', [clave, foto()]),
                             ('dcasa_fotos_ordenar', [[f['clave'] for f in vista['fotos']]]),
                             ('dcasa_fotos_principal', [clave]),
                             ('dcasa_fotos_quitar', [clave]),
                             ('dcasa_fotos_girar', [clave, 'derecha']),
                             ('dcasa_fotos_recortar', [clave, 0, 0, 50, 50])):
            with self.subTest(metodo=metodo), self.assertRaises(AccessError):
                getattr(Sofa, metodo)(*args)
        self.assertEqual(len(self.fotos()['fotos']), 3, 'nada cambió')
        # Un portal no ve nada.
        portal = crear_usuario(self.env, 'zzmk_portal_no', [])
        portal.group_ids = [(6, 0, [self.env.ref('base.group_portal').id])]
        with self.assertRaises(AccessError):
            self.sofa.with_user(portal).dcasa_fotos()

    def test_la_clave_de_una_foto_de_otro_producto_no_sirve(self):
        otro = self.producto('ZZMK Mesa ajena', 'ZZMK-FOTO-2')
        resultado = self.subir(AZUL, ROJO, plantilla=otro)
        ajena = resultado['fotos'][1]['clave']
        self.subir(VERDE)
        for metodo, args in (('dcasa_fotos_quitar', [ajena]), ('dcasa_fotos_reemplazar', [ajena, foto()]),
                             ('dcasa_fotos_girar', [ajena, 'derecha']), ('dcasa_fotos_principal', [ajena])):
            with self.subTest(metodo=metodo), self.assertRaises(UserError):
                getattr(self.sofa.with_user(self.gerencia), metodo)(*args)
        self.assertEqual(len(otro.dcasa_fotos()['fotos']), 2, 'la foto del otro producto sigue ahí')
