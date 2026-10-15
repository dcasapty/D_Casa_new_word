"""Lo que la pantalla de Conversaciones necesita además de la API base: subir archivos, el equipo, la oportunidad y
«Sugerir» (el borrador que redacta el Worker)."""
import base64
import io
import json
import os
import zipfile
from datetime import timedelta
from unittest.mock import patch

import requests
from PIL import Image

from odoo.exceptions import AccessError, UserError
from odoo.service.model import call_kw
from odoo.tests import tagged

from ..models.conversacion_panel_extra import tipo_de_archivo
from .common import respuesta_http
from .test_panel import PanelCase


def png():
    salida = io.BytesIO()
    Image.new('RGB', (4, 4), (19, 64, 177)).save(salida, 'PNG')
    return salida.getvalue()


def jpeg():
    salida = io.BytesIO()
    Image.new('RGB', (4, 4), (19, 64, 177)).save(salida, 'JPEG')
    return salida.getvalue()


def zip_con(archivos):
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, 'w') as z:
        for nombre, contenido in archivos.items():
            z.writestr(nombre, contenido)
    return salida.getvalue()


DOCX = zip_con({'[Content_Types].xml': '<Types/>', 'word/document.xml': '<x/>'})
XLSX = zip_con({'[Content_Types].xml': '<Types/>', 'xl/workbook.xml': '<x/>'})
PDF = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF'
OLE = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'\0' * 200


def b64(contenido):
    return base64.b64encode(contenido).decode()


@tagged('post_install', '-at_install')
class TestTipoDeArchivo(PanelCase):
    """Se mira el contenido, no solo el nombre."""

    def test_lo_que_si_se_puede_mandar(self):
        casos = [('foto.jpg', jpeg(), 'image/jpeg'), ('foto.JPEG', jpeg(), 'image/jpeg'),
                 ('foto.png', png(), 'image/png'), ('cotizacion.pdf', PDF, 'application/pdf'),
                 ('carta.docx', DOCX, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
                 ('lista.xlsx', XLSX, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                 ('viejo.doc', OLE, 'application/msword'), ('viejo.xls', OLE, 'application/vnd.ms-excel'),
                 ('notas.txt', b'Hola, texto', 'text/plain'), ('datos.csv', b'a,b\n1,2', 'text/csv')]
        for nombre, contenido, esperado in casos:
            with self.subTest(nombre=nombre):
                self.assertEqual(tipo_de_archivo(nombre, contenido), esperado)

    def test_lo_que_nunca_se_manda(self):
        casos = [('pagina.html', b'<html><body>hola</body></html>'), ('foto.jpg', b'<html><script>1</script></html>'),
                 ('dibujo.svg', b'<svg xmlns="http://www.w3.org/2000/svg"/>'),
                 ('virus.exe', b'MZ\x90\0' + b'0' * 100), ('foto.pdf', png()), ('foto.png', PDF),
                 ('sin_extension', PDF), ('comprimido.zip', zip_con({'a': 'b'})),
                 ('hoja.docx', zip_con({'a': 'b'})), ('script.js', b'alert(1)'), ('foto.jpg', b'')]
        for nombre, contenido in casos:
            with self.subTest(nombre=nombre):
                self.assertIsNone(tipo_de_archivo(nombre, contenido))


@tagged('post_install', '-at_install')
class TestSubirAdjunto(PanelCase):

    def setUp(self):
        super().setUp()
        self.conv = self.cliente(1)

    def test_sube_una_foto_a_nombre_de_quien_la_sube(self):
        resultado = self.panel.subir_adjunto(self.conv.id, 'mi foto.png', b64(png()))
        adjunto = resultado['adjunto']
        self.assertEqual((adjunto['nombre'], adjunto['mime'], adjunto['tipo']), ('mi foto.png', 'image/png', 'imagen'))
        self.assertEqual(adjunto['miniatura'], f"/web/image/{adjunto['id']}?width=360&height=360")
        registro = self.env['ir.attachment'].browse(adjunto['id'])
        self.assertEqual((registro.res_model, registro.res_id, registro.create_uid, registro.public),
                         ('dcasa.conversacion', self.conv.id, self.vendedora, False))

    def test_el_adjunto_subido_se_puede_enviar_y_pasa_a_ser_del_mensaje(self):
        self.configurar_worker()
        adjunto = self.panel.subir_adjunto(self.conv.id, 'lista.pdf', b64(PDF))['adjunto']
        respuesta = self.panel.enviar_respuesta(self.conv.id, 'Te la paso', [adjunto['id']])
        self.assertEqual([a['nombre'] for a in respuesta['mensaje']['adjuntos']], ['lista.pdf'])
        self.assertEqual(self.env['ir.attachment'].browse(adjunto['id']).res_model, 'dcasa.mensaje')

    def test_acepta_el_prefijo_data_url(self):
        resultado = self.panel.subir_adjunto(self.conv.id, 'x.jpg', 'data:image/jpeg;base64,' + b64(jpeg()))
        self.assertEqual(resultado['adjunto']['mime'], 'image/jpeg')

    def test_rechaza_lo_que_no_es_un_archivo_valido(self):
        casos = {
            'html': ('pagina.html', b64(b'<html></html>')),
            'ejecutable': ('virus.exe', b64(b'MZ\x90\0' + b'0' * 100)),
            'foto falsa': ('foto.png', b64(PDF)),
            'vacío': ('x.png', b64(b'')),
            'no es base64': ('x.png', '¡no soy base64!'),
        }
        for nombre, (archivo, datos) in casos.items():
            with self.subTest(nombre), self.assertRaises(UserError):
                self.panel.subir_adjunto(self.conv.id, archivo, datos)
        for malo in (None, 5, ''):
            with self.subTest(datos=malo), self.assertRaises(UserError):
                self.panel.subir_adjunto(self.conv.id, 'x.png', malo)
        with self.assertRaises(UserError):
            self.panel.subir_adjunto(self.conv.id, None, b64(png()))
        self.assertFalse(self.env['ir.attachment'].search([('res_model', '=', 'dcasa.conversacion'),
                                                           ('res_id', '=', self.conv.id)]))

    def test_rechaza_lo_que_pesa_mas_de_10_mb(self):
        enorme = png() + b'\0' * (10 * 1024 * 1024)
        with self.assertRaises(UserError) as error:
            self.panel.subir_adjunto(self.conv.id, 'grande.png', b64(enorme))
        self.assertIn('10 MB', str(error.exception))

    def test_no_se_acumulan_archivos_sin_enviar(self):
        for n in range(10):
            self.panel.subir_adjunto(self.conv.id, f'foto{n}.png', b64(png()))
        with self.assertRaises(UserError):
            self.panel.subir_adjunto(self.conv.id, 'otra.png', b64(png()))

    def test_el_nombre_se_limpia(self):
        resultado = self.panel.subir_adjunto(self.conv.id, '../../etc/pass:wd?.png', b64(png()))
        self.assertNotIn('/', resultado['adjunto']['nombre'])
        self.assertTrue(resultado['adjunto']['nombre'].endswith('.png'))

    def test_solo_el_equipo_de_ventas_sube_archivos_tambien_por_rpc(self):
        for usuario in (self.interno, self.portal):
            for metodo, args in (('subir_adjunto', [self.conv.id, 'x.png', b64(png())]),
                                 ('descartar_adjunto', [1]), ('equipo', []), ('iniciar_panel', []),
                                 ('fijar_disponible', [True]), ('presencia', [self.conv.id, False]),
                                 ('resumir_conversacion', [self.conv.id]),
                                 ('refrescar', []),
                                 ('nueva_oportunidad', [self.conv.id]),
                                 ('sugerir_respuesta', [self.conv.id]), ('reintentar_envios_panel', [self.conv.id])):
                with self.subTest(usuario=usuario.login, metodo=metodo), self.assertRaises(AccessError):
                    call_kw(self.env(user=usuario)['dcasa.conversacion'], metodo, list(args), {})

    def test_quitar_un_archivo_que_no_se_envio(self):
        adjunto = self.panel.subir_adjunto(self.conv.id, 'x.png', b64(png()))['adjunto']
        self.assertEqual(self.panel.descartar_adjunto(adjunto['id']), {'quitado': adjunto['id']})
        self.assertFalse(self.env['ir.attachment'].browse(adjunto['id']).exists())

    def test_no_se_quita_el_archivo_de_otra_persona_ni_uno_ya_enviado(self):
        self.configurar_worker()
        ajeno = self.env['ir.attachment'].with_user(self.gerente).create({
            'name': 'x.png', 'raw': png(), 'res_model': 'dcasa.conversacion', 'res_id': self.conv.id})
        with self.assertRaises(UserError):
            self.panel.descartar_adjunto(ajeno.id)
        propio = self.panel.subir_adjunto(self.conv.id, 'y.png', b64(png()))['adjunto']
        self.panel.enviar_respuesta(self.conv.id, 'Mira', [propio['id']])
        with self.assertRaises(UserError):
            self.panel.descartar_adjunto(propio['id'])
        for malo in (0, -1, 'x', None, True, 999999999):
            with self.subTest(malo=malo), self.assertRaises(UserError):
                self.panel.descartar_adjunto(malo)

    def test_el_cron_borra_lo_subido_y_nunca_enviado_pero_no_lo_reciente_ni_lo_enviado(self):
        self.configurar_worker()
        viejo = self.panel.subir_adjunto(self.conv.id, 'viejo.png', b64(png()))['adjunto']['id']
        reciente = self.panel.subir_adjunto(self.conv.id, 'reciente.png', b64(png()))['adjunto']['id']
        enviado = self.panel.subir_adjunto(self.conv.id, 'enviado.png', b64(png()))['adjunto']['id']
        self.panel.enviar_respuesta(self.conv.id, 'Mira', [enviado])
        self.env.cr.execute('UPDATE ir_attachment SET create_date = %s WHERE id IN %s',
                            [self.ahora - timedelta(days=3), (viejo, enviado)])
        self.env['ir.attachment'].invalidate_model()
        self.assertEqual(self.Conversacion._cron_limpiar_subidas(), 1)
        Adjunto = self.env['ir.attachment']
        self.assertEqual((bool(Adjunto.browse(viejo).exists()), bool(Adjunto.browse(reciente).exists()),
                          bool(Adjunto.browse(enviado).exists())), (False, True, True))

    def test_el_cron_no_borra_el_archivo_que_una_vendedora_adjunto_en_el_chatter_de_la_conversacion(self):
        adjunto = self.env['ir.attachment'].create({
            'name': 'contrato.txt', 'raw': b'datos', 'res_model': 'dcasa.conversacion', 'res_id': self.conv.id})
        self.conv.message_post(body='Contrato firmado', attachment_ids=[adjunto.id])
        sobra = self.panel.subir_adjunto(self.conv.id, 'sobra.png', b64(png()))['adjunto']['id']
        self.env.cr.execute('UPDATE ir_attachment SET create_date = %s WHERE id IN %s',
                            [self.ahora - timedelta(days=3), (adjunto.id, sobra)])
        self.env['ir.attachment'].invalidate_model()
        self.assertEqual(self.Conversacion._cron_limpiar_subidas(), 1)
        self.assertTrue(adjunto.exists(), 'es de una nota del chatter, no una subida sin usar')
        self.assertFalse(self.env['ir.attachment'].browse(sobra).exists())


@tagged('post_install', '-at_install')
class TestIniciarPanel(PanelCase):

    def test_trae_en_una_sola_llamada_todo_lo_que_la_pantalla_necesita_al_abrir(self):
        etiqueta = self.env['dcasa.conversacion.etiqueta'].create({'name': 'Zzinicio', 'color': 4})
        datos = self.panel.iniciar_panel()
        self.assertEqual(datos['usuario'],
                         {'id': self.vendedora.id, 'nombre': 'Vendedora Prueba', 'es_gerencia': False,
                          'disponible': True, 'recibe_reparto': True, 'fuera_del_reparto': False})
        self.assertEqual(datos['limites'], {
            'adjuntos': 5, 'bytes': 10 * 1024 * 1024, 'respuesta': 4000, 'nota': 1000, 'nota_para_el_bot': 500,
            'pausa_minutos': 120, 'espera_aviso_minutos': 10})
        self.assertEqual((datos['reparto'], datos['resumen_ia']), ('manual', True))
        self.assertIn(etiqueta.id, [e['id'] for e in datos['etiquetas']])
        self.assertIn('/horario', [r['atajo'] for r in datos['rapidas']])
        self.assertIn('Gerente Prueba', [u['nombre'] for u in datos['equipo']])
        self.assertEqual([c['id'] for c in datos['canales']],
                         ['whatsapp_qr', 'whatsapp_cloud', 'telegram', 'messenger', 'instagram'])

    def test_la_gerencia_se_reconoce(self):
        self.assertTrue(self.Conversacion.with_user(self.gerente).iniciar_panel()['usuario']['es_gerencia'])

    def test_dice_si_el_bot_esta_conectado_y_encendido(self):
        self.assertEqual(self.panel.iniciar_panel()['bot'], {'conectado': False, 'encendido': True})
        self.configurar_worker()
        self.ajustes.bot_activo_global = False
        self.assertEqual(self.panel.iniciar_panel()['bot'], {'conectado': True, 'encendido': False})

    def test_no_trae_ningun_secreto(self):
        self.configurar_worker()
        self.assertNotIn('w' * 40, json.dumps(self.panel.iniciar_panel()))


@tagged('post_install', '-at_install')
class TestEquipoYOportunidad(PanelCase):

    def test_el_equipo_son_las_personas_de_ventas(self):
        nombres = {p['nombre'] for p in self.panel.equipo()}
        self.assertIn('Vendedora Prueba', nombres)
        self.assertIn('Gerente Prueba', nombres)
        self.assertNotIn('Interno sin ventas', nombres)
        self.assertNotIn('Portal', nombres)
        self.assertEqual([p['nombre'].lower() for p in self.panel.equipo()],
                         sorted(p['nombre'].lower() for p in self.panel.equipo()))

    def test_crear_la_oportunidad_desde_la_pantalla_y_no_duplicarla(self):
        conv = self.cliente(1)
        primera = self.panel.nueva_oportunidad(conv.id)
        self.assertTrue(primera['nueva'])
        self.assertEqual(conv.oportunidad_id.id, primera['oportunidad']['id'])
        self.assertEqual(primera['conversacion']['oportunidad_id'], conv.oportunidad_id.id)
        segunda = self.panel.nueva_oportunidad(conv.id)
        self.assertFalse(segunda['nueva'])
        self.assertEqual(segunda['oportunidad']['id'], primera['oportunidad']['id'])
        self.assertEqual(self.env['crm.lead'].sudo().search_count([('partner_id', '=', conv.partner_id.id)]), 1)

    def test_reintentar_lo_que_no_salio(self):
        worker = self.configurar_worker()
        conv = self.cliente(1)
        worker.side_effect = requests.ConnectionError('sin red')
        respuesta = self.panel.enviar_respuesta(conv.id, 'Hola')
        self.assertFalse(respuesta['enviado'])
        worker.side_effect = None
        worker.return_value = respuesta_http({'ok': True, 'id_mensaje': 'wamid.worker.7'})
        resultado = self.panel.reintentar_envios_panel(conv.id)
        self.assertEqual((resultado['reintentados'], resultado['salieron']), (1, 1))
        self.assertEqual(resultado['conversacion']['por_enviar'], 0)


@tagged('post_install', '-at_install')
class TestSugerir(PanelCase):

    def setUp(self):
        super().setUp()
        self.conv = self.cliente(1, '¿Tienen camas queen?')
        self.registrar('Sí, tenemos varias.', id_externo=self.conv.id_externo, autor='bot')
        self.registrar('¿Cuánto cuesta la gris?', id_externo=self.conv.id_externo)
        self.worker = self.configurar_worker()

    def test_pide_el_borrador_al_worker_con_el_contexto_y_no_envia_nada(self):
        self.worker.return_value = respuesta_http({'ok': True, 'texto': 'Claro, Zzcliente, te cuento.',
                                                   'avisos': ['Quité un precio sin respaldo.']})
        resultado = self.panel.sugerir_respuesta(self.conv.id)
        self.assertEqual(resultado, {'texto': 'Claro, Zzcliente, te cuento.',
                                     'avisos': ['Quité un precio sin respaldo.']})
        (llamada,) = [c for c in self.worker.call_args_list if c.args[1].endswith('/odoo/sugerir')]
        self.assertEqual(llamada.args[0], 'POST')
        cuerpo = llamada.kwargs['json']
        self.assertEqual((cuerpo['conversacion_id'], cuerpo['canal'], cuerpo['id_externo']),
                         (self.conv.id, 'whatsapp_qr', self.conv.id_externo))
        self.assertEqual([(m['autor'], m['texto']) for m in cuerpo['mensajes']], [
            ('cliente', '¿Tienen camas queen?'), ('asistente', 'Sí, tenemos varias.'),
            ('cliente', '¿Cuánto cuesta la gris?')])
        self.assertFalse([c for c in self.worker.call_args_list if c.args[1].endswith('/odoo/enviar')],
                         'Sugerir no manda nada al cliente')
        self.assertFalse(self.conv.mensaje_ids.filtered(lambda m: m.autor == 'vendedora'))
        self.assertEqual(self.conv.estado, 'bot', 'Sugerir no toma la conversación')

    def test_el_token_va_en_la_cabecera_y_nunca_en_el_cuerpo(self):
        self.worker.return_value = respuesta_http({'ok': True, 'texto': 'Hola'})
        self.panel.sugerir_respuesta(self.conv.id)
        (llamada,) = [c for c in self.worker.call_args_list if c.args[1].endswith('/odoo/sugerir')]
        self.assertTrue(llamada.kwargs['headers']['Authorization'].startswith('Bearer '))
        self.assertNotIn('w' * 40, json.dumps(llamada.kwargs['json']))

    def test_las_notas_internas_y_los_avisos_no_viajan(self):
        self.panel.agregar_nota(self.conv.id, 'Este cliente es difícil, no le des descuento')
        self.panel.tomar(self.conv.id)
        self.worker.return_value = respuesta_http({'ok': True, 'texto': 'Hola'})
        self.panel.sugerir_respuesta(self.conv.id)
        (llamada,) = [c for c in self.worker.call_args_list if c.args[1].endswith('/odoo/sugerir')]
        enviado = json.dumps(llamada.kwargs['json'], ensure_ascii=False)
        self.assertNotIn('difícil', enviado)
        self.assertNotIn('tomó la conversación', enviado)

    def test_un_comprobante_viaja_sin_su_texto(self):
        mensaje = self.registrar('Mi cédula es 8-123-456', id_externo=self.conv.id_externo)[1]
        mensaje.with_context(dcasa_mensaje_sistema=True).sudo().tiene_sensible = True
        self.worker.return_value = respuesta_http({'ok': True, 'texto': 'Hola'})
        self.panel.sugerir_respuesta(self.conv.id)
        (llamada,) = [c for c in self.worker.call_args_list if c.args[1].endswith('/odoo/sugerir')]
        enviado = json.dumps(llamada.kwargs['json'], ensure_ascii=False)
        self.assertNotIn('8-123-456', enviado)
        self.assertIn('archivo sensible', enviado)

    def test_solo_los_ultimos_mensajes(self):
        for n in range(30):
            self.registrar(f'Otro {n}', id_externo=self.conv.id_externo)
        self.worker.return_value = respuesta_http({'ok': True, 'texto': 'Hola'})
        self.panel.sugerir_respuesta(self.conv.id)
        (llamada,) = [c for c in self.worker.call_args_list if c.args[1].endswith('/odoo/sugerir')]
        self.assertEqual(len(llamada.kwargs['json']['mensajes']), 14)
        self.assertEqual(llamada.kwargs['json']['mensajes'][-1]['texto'], 'Otro 29')

    def test_sin_el_worker_configurado_dice_falta_conectar_el_bot(self):
        with patch.dict(os.environ, {'JUAN_URL': '', 'JUAN_WORKER_TOKEN': ''}), self.assertRaises(UserError) as error:
            self.panel.sugerir_respuesta(self.conv.id)
        self.assertIn('Falta conectar el bot', str(error.exception))

    def test_si_el_worker_falla_el_error_es_claro_y_no_se_cae(self):
        self.worker.return_value = respuesta_http({'ok': False, 'error': 'la IA no pudo redactar'}, 502)
        with self.assertRaises(UserError) as error:
            self.panel.sugerir_respuesta(self.conv.id)
        self.assertIn('la IA no pudo redactar', str(error.exception))
        self.worker.side_effect = requests.ConnectionError('sin red')
        with self.assertRaises(UserError):
            self.panel.sugerir_respuesta(self.conv.id)

    def test_un_borrador_vacio_es_un_error(self):
        self.worker.return_value = respuesta_http({'ok': True, 'texto': '   '})
        with self.assertRaises(UserError):
            self.panel.sugerir_respuesta(self.conv.id)

    def test_sin_nada_del_cliente_no_hay_a_que_responder(self):
        vacia = self.Conversacion.sudo().create({'canal': 'telegram', 'id_externo': '777'})
        with self.assertRaises(UserError):
            self.panel.sugerir_respuesta(vacia.id)
