"""La foto de perfil del cliente: la manda el Worker, Odoo la valida, la reduce y la guarda en la conversación."""
import base64
import io

from PIL import Image

from odoo.tests import tagged

from ..models import adjuntos as A
from .common import JuanCase
from .test_api import ApiCase


def imagen(formato='JPEG', tamano=(640, 480), color=(19, 64, 177)):
    salida = io.BytesIO()
    Image.new('RGB', tamano, color).save(salida, formato)
    return salida.getvalue()


def b64(datos):
    return base64.b64encode(datos).decode()


@tagged('post_install', '-at_install')
class TestImagenDePerfil(JuanCase):
    """Qué es una foto de perfil aceptable (sin base de datos de por medio)."""

    def test_jpeg_png_y_webp_se_aceptan_y_salen_reducidos(self):
        for formato in ('JPEG', 'PNG', 'WEBP'):
            with self.subTest(formato=formato):
                foto = A.imagen_de_perfil(imagen(formato))
                self.assertEqual(A.tipo_de_imagen(foto), 'jpeg')   # siempre JPEG, venga como venga
                self.assertLessEqual(max(Image.open(io.BytesIO(foto)).size), A.LADO_FOTO_DE_PERFIL)

    def test_una_imagen_con_transparencia_se_aplana_sobre_blanco(self):
        salida = io.BytesIO()
        Image.new('RGBA', (100, 100), (0, 0, 0, 0)).save(salida, 'PNG')   # totalmente transparente
        foto = Image.open(io.BytesIO(A.imagen_de_perfil(salida.getvalue())))
        self.assertEqual(foto.getpixel((50, 50)), (255, 255, 255))

    def test_una_imagen_con_demasiados_pixeles_se_rechaza_aunque_pese_poco(self):
        salida = io.BytesIO()
        Image.new('L', (6000, 6000), 0).save(salida, 'PNG')               # 36 millones de píxeles, pocos KB
        self.assertLess(len(salida.getvalue()), A.MAX_FOTO_DE_PERFIL)
        self.assertIsNone(A.imagen_de_perfil(salida.getvalue()))

    def test_el_tipo_se_conoce_por_los_bytes_no_por_lo_que_diga_el_nombre(self):
        self.assertEqual(A.tipo_de_imagen(imagen('PNG')), 'png')
        self.assertIsNone(A.tipo_de_imagen(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'))
        self.assertIsNone(A.tipo_de_imagen(b'GIF89a......'))
        self.assertIsNone(A.tipo_de_imagen(b'%PDF-1.4'))
        self.assertIsNone(A.tipo_de_imagen(b'PK\x03\x04'))

    def test_lo_que_no_sirve_se_descarta_sin_lanzar(self):
        enorme = imagen('PNG', (1500, 1500))   # un PNG liso pesa poco: se prueba el tope con relleno aparte
        casos = {
            'svg': b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            'gif': imagen('GIF'),
            'pdf': b'%PDF-1.4 ...',
            'basura': b'\xff\xd8\xff' + b'no es una imagen' * 10,   # empieza como JPEG pero está rota
            'vacía': b'',
            'texto': 'no son bytes',
            'más grande que el tope': imagen('JPEG') + b'\0' * A.MAX_FOTO_DE_PERFIL,
        }
        for nombre, datos in casos.items():
            with self.subTest(nombre):
                self.assertIsNone(A.imagen_de_perfil(datos))
        self.assertTrue(enorme)


@tagged('post_install', '-at_install')
class TestFotoDePerfilPorApi(ApiCase):

    def setUp(self):
        super().setUp()
        self.post('mensaje', self.mensaje())
        self.conv = self.conversacion()
        self.foto = imagen('JPEG')

    def dominio_del_archivo(self):
        return [('res_model', '=', 'dcasa.conversacion'), ('res_id', '=', self.conv.id),
                ('res_field', '=', 'foto_perfil')]

    def mandar(self, datos=None, **extra):
        cuerpo = {'canal': 'whatsapp_qr', 'id_externo': '50761230000', 'mime': 'image/jpeg',
                  'base64': b64(self.foto if datos is None else datos), **extra}
        return self.post('foto-perfil', {k: v for k, v in cuerpo.items() if v is not None})

    def test_guarda_la_foto_reducida_en_la_conversacion(self):
        respuesta = self.mandar()
        self.assertEqual((respuesta.status_code, respuesta.json()), (200, {'ok': True, 'guardada': True}))
        self.assertTrue(self.conv.foto_perfil_en)
        lado = max(Image.open(io.BytesIO(base64.b64decode(self.conv.foto_perfil))).size)
        self.assertLessEqual(lado, 256)
        self.assertFalse(self.conv.partner_id.image_1920, 'No se toca la foto del contacto')

    def test_la_pantalla_recibe_su_direccion_con_la_fecha_y_sin_foto_es_none(self):
        self.assertIsNone(self.conv._resumen_panel()['foto_perfil'])
        self.mandar()
        url = self.conv._resumen_panel()['foto_perfil']
        self.assertRegex(url, rf'^/web/image/dcasa\.conversacion/{self.conv.id}/foto_perfil/128x128\?unique=\d+$')

    def test_apagado_en_ajustes_no_guarda_nada(self):
        self.env['dcasa.juan.ajustes'].obtener().guardar_foto_perfil = False
        respuesta = self.mandar()
        self.assertEqual(respuesta.json(), {'ok': True, 'guardada': False, 'motivo': 'apagado'})
        self.assertFalse(self.conv.foto_perfil_en)

    def test_el_worker_se_entera_del_ajuste(self):
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        self.assertIs(ajustes.como_json()['guardar_foto_perfil'], True)
        ajustes.guardar_foto_perfil = False
        self.assertIs(ajustes.como_json()['guardar_foto_perfil'], False)

    def test_lo_que_no_es_una_foto_valida_no_se_guarda(self):
        casos = {
            'svg': b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
            'gif': imagen('GIF'),
            'rota': b'\xff\xd8\xff' + b'x' * 40,
            'muy grande': self.foto + b'\0' * A.MAX_FOTO_DE_PERFIL,
        }
        for nombre, datos in casos.items():
            with self.subTest(nombre):
                respuesta = self.mandar(datos)
                self.assertEqual((respuesta.status_code, respuesta.json()['guardada']), (200, False))
        self.assertEqual(self.mandar(b'%%%no-es-base64%%%').json()['guardada'], False)
        self.assertFalse(self.conv.foto_perfil_en)

    def test_validaciones_del_cuerpo(self):
        for extra, estado in (({'base64': None}, 400), ({'canal': 'fax'}, 400), ({'id_externo': ''}, 400),
                              ({'id_externo': '50769999999'}, 404)):
            with self.subTest(extra=extra):
                cuerpo = {'canal': 'whatsapp_qr', 'id_externo': '50761230000', 'base64': b64(self.foto), **extra}
                cuerpo = {k: v for k, v in cuerpo.items() if v is not None}
                self.assertEqual(self.post('foto-perfil', cuerpo).status_code, estado)
        self.assertEqual(self.post('foto-perfil', {'canal': 'whatsapp_qr', 'id_externo': '50761230000',
                                                   'base64': 5}).status_code, 400)

    def test_la_misma_foto_no_guarda_otro_archivo_y_una_distinta_la_reemplaza(self):
        Adjunto = self.env['ir.attachment'].sudo()
        dominio = self.dominio_del_archivo()
        self.mandar()
        (primero,) = Adjunto.search(dominio)
        self.mandar()
        self.assertEqual(Adjunto.search(dominio), primero, 'La misma foto no crea otro archivo')
        antes = primero.checksum
        self.mandar(imagen('JPEG', (300, 300), (200, 30, 30)))
        self.env.invalidate_all()
        (segundo,) = Adjunto.search(dominio)
        self.assertNotEqual(segundo.checksum, antes)

    def test_se_borra_con_la_conversacion(self):
        self.mandar()
        Adjunto = self.env['ir.attachment'].sudo()
        dominio = self.dominio_del_archivo()
        self.assertTrue(Adjunto.search(dominio))
        self.conv.sudo().unlink()
        self.assertFalse(Adjunto.search(dominio))

    def test_sin_el_token_no_se_guarda_nada(self):
        self.assertEqual(self.post('foto-perfil', {'canal': 'whatsapp_qr', 'id_externo': '50761230000',
                                                   'base64': b64(self.foto)}, token=None).status_code, 401)
        self.assertFalse(self.conv.foto_perfil_en)


@tagged('post_install', '-at_install')
class TestQuienVeLaFoto(ApiCase):
    """La foto la ve quien atiende conversaciones; un cliente del portal o un usuario sin ventas, no."""

    def setUp(self):
        super().setUp()
        from odoo.tests import new_test_user
        self.post('mensaje', self.mensaje())
        self.conv = self.conversacion()
        self.conv._guardar_foto_de_perfil(imagen('JPEG'))
        self.vendedora = new_test_user(self.env, login='foto_vendedora', password='foto_vendedora',
                                       groups='base.group_user,sales_team.group_sale_salesman')
        self.portal = new_test_user(self.env, login='foto_portal', password='foto_portal', groups='base.group_portal')
        self.url = self.conv._resumen_panel()['foto_perfil']

    def descargar(self, usuario):
        self.authenticate(usuario, usuario) if usuario else self.authenticate(None, None)
        respuesta = self.url_open(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.headers['Content-Type'].startswith('image/'))
        return respuesta.content

    def test_una_vendedora_la_descarga(self):
        foto = self.descargar('foto_vendedora')
        self.assertGreater(len(foto), 100)

    def test_un_cliente_del_portal_y_alguien_sin_sesion_reciben_solo_la_imagen_vacia_de_siempre(self):
        # Odoo contesta con su imagen genérica cuando no se puede leer el campo: lo que importa es que NO sea la foto.
        foto = self.descargar('foto_vendedora')
        del_portal = self.descargar('foto_portal')
        sin_sesion = self.descargar(None)
        self.assertNotEqual(del_portal, foto)
        self.assertEqual(del_portal, sin_sesion)
