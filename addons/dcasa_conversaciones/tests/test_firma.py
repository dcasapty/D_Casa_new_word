"""URLs firmadas de vida corta para que el puente baje un adjunto: la firma y la ruta pública que lo sirve."""
import re

from odoo import fields
from odoo.addons.dcasa_conversaciones.models import firma as F
from odoo.tests import BaseCase, HttpCase, tagged

SECRETO = 'secreto-de-prueba-del-servidor'
AHORA = 1_800_000_000


@tagged('post_install', '-at_install')
class TestFirma(BaseCase):

    def ruta(self, **kw):
        base = {'secreto': SECRETO, 'adjunto_id': 7, 'checksum': 'abc123', 'nombre': 'foto.jpg', 'ahora': AHORA}
        return F.ruta_firmada(**{**base, **kw})

    def partes(self, ruta):
        coincide = re.fullmatch(r'/dcasa/adjunto/(\d+)/(\d+)/([0-9a-f]{64})/(.+)', ruta)
        self.assertTrue(coincide, ruta)
        return int(coincide[1]), int(coincide[2]), coincide[3], coincide[4]

    def test_la_ruta_lleva_id_vencimiento_firma_y_nombre(self):
        adjunto_id, vence, firma, nombre = self.partes(self.ruta())
        self.assertEqual((adjunto_id, vence, nombre), (7, AHORA + 15 * 60, 'foto.jpg'))
        self.assertTrue(F.es_valida(SECRETO, 7, vence, firma, 'abc123', ahora=AHORA))

    def test_la_ruta_no_empieza_por_la_zona_que_el_borde_bloquea(self):
        self.assertFalse(self.ruta().startswith('/dcasa/juan'))

    def test_vence(self):
        _, vence, firma, _ = self.partes(self.ruta(vida=60))
        self.assertTrue(F.es_valida(SECRETO, 7, vence, firma, 'abc123', ahora=AHORA + 59))
        self.assertFalse(F.es_valida(SECRETO, 7, vence, firma, 'abc123', ahora=AHORA + 61))

    def test_ni_con_un_ajuste_raro_dura_mas_de_un_dia(self):
        _, vence, firma, _ = self.partes(self.ruta(vida=10 ** 9))
        self.assertEqual(vence, AHORA + F.VIDA_MAXIMA)
        self.assertEqual(self.partes(self.ruta(vida=-5))[1], AHORA + 1, 'Y mínimo un segundo')

    def test_no_se_puede_alargar_el_vencimiento(self):
        _, vence, firma, _ = self.partes(self.ruta(vida=60))
        self.assertFalse(F.es_valida(SECRETO, 7, vence + 3600, firma, 'abc123', ahora=AHORA))
        self.assertFalse(F.es_valida(SECRETO, 7, AHORA + 10 ** 7, F.firma(SECRETO, 7, AHORA + 10 ** 7, 'abc123'),
                                     'abc123', ahora=AHORA), 'Una firma con vencimiento lejano no vale')

    def test_es_de_ese_adjunto_y_de_ese_contenido(self):
        _, vence, firma, _ = self.partes(self.ruta())
        self.assertFalse(F.es_valida(SECRETO, 8, vence, firma, 'abc123', ahora=AHORA), 'Otro adjunto')
        self.assertFalse(F.es_valida(SECRETO, 7, vence, firma, 'otro-contenido', ahora=AHORA), 'El archivo cambió')
        self.assertFalse(F.es_valida('otra-clave', 7, vence, firma, 'abc123', ahora=AHORA), 'Otra clave')

    def test_firmas_malformadas(self):
        _, vence, firma, _ = self.partes(self.ruta())
        for mala in (None, '', 'abc', firma.upper(), firma[:-1], firma + '0', 7, 'g' * 64):
            with self.subTest(mala=mala):
                self.assertFalse(F.es_valida(SECRETO, 7, vence, mala, 'abc123', ahora=AHORA))

    def test_el_nombre_no_rompe_la_ruta(self):
        for nombre, esperado in (('foto con espacios.jpg', 'foto%20con%20espacios.jpg'), ('a/b\\c.jpg', 'a_b%5Cc.jpg'),
                                 ('ñandú.png', '%C3%B1and%C3%BA.png'), ('', 'adjunto'), (None, 'adjunto')):
            with self.subTest(nombre=nombre):
                self.assertEqual(self.partes(self.ruta(nombre=nombre))[3], esperado)

    def test_la_firma_no_depende_del_nombre(self):
        # El nombre es solo para que el archivo se llame bien al bajarlo; no puede cambiar a qué archivo apunta.
        a, b = self.partes(self.ruta(nombre='uno.jpg')), self.partes(self.ruta(nombre='dos.jpg'))
        self.assertEqual(a[:3], b[:3])


@tagged('post_install', '-at_install')
class TestDescargaFirmada(HttpCase):

    def setUp(self):
        super().setUp()
        self.secreto = self.env['ir.config_parameter'].sudo().get_param('database.secret')
        self.conv, self.mensaje, _ = self.env['dcasa.conversacion']._registrar_mensaje({
            'canal': 'whatsapp_qr', 'id_externo': '50761230001', 'id_mensaje': 'wamid.firma.1',
            'direccion': 'entrante', 'autor': 'cliente', 'texto': 'Mira', 'ts': fields.Datetime.now(), 'adjuntos': []})
        self.foto = self.adjunto('foto.png', b'\x89PNG\r\n\x1a\nfoto', 'image/png')
        self.cotizacion = self.adjunto('cotizacion.pdf', b'%PDF-1.4 cotizacion', 'application/pdf')
        self.pagina = self.adjunto('truco.html', b'<script>alert(1)</script>', 'text/html')
        self.env.flush_all()

    def adjunto(self, nombre, contenido, mime, res_model='dcasa.mensaje'):
        return self.env['ir.attachment'].create({
            'name': nombre, 'raw': contenido, 'mimetype': mime, 'res_model': res_model,
            'res_id': self.mensaje.id if res_model == 'dcasa.mensaje' else 0})

    def url(self, adjunto, **kw):
        return F.ruta_firmada(**{'secreto': self.secreto, 'adjunto_id': adjunto.id, 'checksum': adjunto.checksum,
                                 'nombre': adjunto.name, **kw})

    def test_con_la_firma_valida_se_baja_sin_sesion(self):
        self.authenticate(None, None)
        respuesta = self.url_open(self.url(self.cotizacion))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.content, b'%PDF-1.4 cotizacion')
        self.assertEqual(respuesta.headers['Content-Type'], 'application/pdf')
        self.assertIn('private', respuesta.headers['Cache-Control'])
        self.assertEqual(respuesta.headers['X-Content-Type-Options'], 'nosniff')
        self.assertIn('cotizacion.pdf', respuesta.headers['Content-Disposition'])

    def test_una_imagen_se_sirve_como_imagen(self):
        respuesta = self.url_open(self.url(self.foto))
        self.assertEqual((respuesta.status_code, respuesta.headers['Content-Type']), (200, 'image/png'))

    def test_un_tipo_que_se_podria_ejecutar_se_baja_como_descarga(self):
        respuesta = self.url_open(self.url(self.pagina))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers['Content-Type'], 'application/octet-stream')

    def test_vencida_no_sirve(self):
        ruta = F.ruta_firmada(self.secreto, self.cotizacion.id, self.cotizacion.checksum, 'x.pdf',
                              vida=1, ahora=1_000_000_000)    # venció en 2001
        self.assertEqual(self.url_open(ruta).status_code, 404)

    def test_firma_falsa_otro_adjunto_o_archivo_cambiado_no_sirven(self):
        ruta = self.url(self.cotizacion)
        falsa = re.sub(r'/[0-9a-f]{64}/', '/' + '0' * 64 + '/', ruta)
        self.assertEqual(self.url_open(falsa).status_code, 404)
        otro_id = ruta.replace(f'/adjunto/{self.cotizacion.id}/', f'/adjunto/{self.foto.id}/')
        self.assertEqual(self.url_open(otro_id).status_code, 404)
        self.cotizacion.raw = b'%PDF-1.4 cambiada'
        self.assertEqual(self.url_open(ruta).status_code, 404, 'Si el archivo cambia, el enlace viejo deja de valer')

    def test_solo_sirve_adjuntos_de_mensajes_de_conversaciones(self):
        ajeno = self.adjunto('secreto.pdf', b'%PDF-1.4 ajeno', 'application/pdf', res_model='res.partner')
        self.assertEqual(self.url_open(self.url(ajeno)).status_code, 404)
        self.assertEqual(self.url_open('/dcasa/adjunto/999999999/9999999999/' + '0' * 64 + '/x.pdf').status_code, 404)

    def test_es_solo_lectura(self):
        self.assertEqual(self.url_open(self.url(self.cotizacion), data=' ').status_code, 405)
