"""La revisión adversarial de Camila (2026-11-06): cada hallazgo con su prueba. Datos inventados (ZZCM, @example.com);
Resend siempre es el falso en memoria de ``comun.py``."""
import os
import time
from datetime import timedelta
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

from lxml import html as lxml_html

from odoo import Command, fields
from odoo.addons.dcasa_conversaciones.models.mensaje import CLAVE_SISTEMA
from odoo.exceptions import AccessError, UserError
from odoo.tests import BaseCase, HttpCase, tagged

from ..models import reglas as R
from ..models import resend_campanas as RC
from .comun import CamilaComun

SIN_DUP = {'dcasa_sin_duplicados': True}
LAYOUT = 'dcasa_correo.layout_correo'


def token_de(Camila, ficha, origen='factura', momento=None):
    """Un enlace «Sí, quiero» firmado como lo firma el pie del correo."""
    from odoo.addons.dcasa_correo.models.correo import correo_valido

    momento = momento or int(time.time())
    codigo = {'factura': 'f', 'bienvenida': 'b'}[origen]
    return f'{ficha.id}.{codigo}.{momento}.{Camila._firma(ficha.id, origen, correo_valido(ficha.email), momento)}'


# ----------------------------------------------------------------------
# 1 (alta). La baja se mira por correo, no ficha por ficha
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestBajaPorCorreo(CamilaComun):

    def otra_ficha(self, **valores):
        return self.env['res.partner'].with_context(**SIN_DUP).create(dict(
            {'name': 'Ana Zzcm Repetida', 'email': 'ana.zzcm@example.com', 'phone': '6000-1099'}, **valores))

    def test_la_baja_en_una_ficha_vale_para_todas_las_de_ese_correo(self):
        self.con_clave()
        repetida = self.otra_ficha()
        self.permiso(self.ana, self.beto)
        segmento = self.Camila._segmento(self.Camila._cliente())
        self.resend.contacto('ana.zzcm@example.com', segmentos=[segmento])   # Ana ya está en Resend (otra campaña)
        repetida.with_user(self.vendedora).action_dcasa_promos_baja()
        self.ana.invalidate_recordset()
        self.assertEqual(self.ana.dcasa_promos_estado, 'baja', 'La otra ficha con su correo también la muestra')
        self.assertNotIn('ana.zzcm@example.com', self.env['res.partner']._dcasa_promos_con_permiso())
        campana = self.armar()['campana']
        resultado = self.Camila.with_user(self.marketing).enviar(campana['id'], campana['huella'])
        self.assertTrue(resultado['ok'], resultado)
        (broadcast,) = self.resend.broadcasts.values()
        self.assertEqual(broadcast['enviado_a'], ['beto.zzcm@example.com'])
        self.assertTrue(self.resend.contactos['ana.zzcm@example.com']['unsubscribed'], 'La baja subió a Resend')

    def test_archivadas_contactos_hijos_y_no_contactar_tambien_cuentan(self):
        Partner = self.env['res.partner'].with_context(**SIN_DUP)
        self.permiso(self.ana, self.beto, self.carla)
        archivada = self.otra_ficha(name='Ana Vieja Zzcm', phone='6000-1098')
        archivada.sudo()._dcasa_promos_baja('correo')
        archivada.active = False
        empresa = Partner.create({'name': 'Empresa Zzcm SA', 'is_company': True, 'phone': '6000-1097'})
        Partner.create({'name': 'Beto en la empresa', 'parent_id': empresa.id, 'email': 'beto.zzcm@example.com'})
        empresa.sudo()._dcasa_promos_baja('ficha')
        Partner.create({'name': 'Carla Otra Zzcm', 'email': 'carla.zzcm@example.com', 'phone': '6000-1096',
                        'dcasa_no_contactar': True})
        con_permiso = self.env['res.partner']._dcasa_promos_con_permiso()
        for correo in ('ana.zzcm@example.com', 'beto.zzcm@example.com', 'carla.zzcm@example.com'):
            self.assertNotIn(correo, con_permiso)

    def test_con_baja_en_otra_ficha_no_se_vuelve_a_dar_de_alta(self):
        repetida = self.otra_ficha()
        token = token_de(self.Camila, self.ana)
        repetida.sudo()._dcasa_promos_baja('correo')
        self.assertFalse(self.ana.sudo()._dcasa_promos_registrar('factura'), 'Ni el sistema')
        with self.assertRaises(UserError):
            self.ana.with_user(self.vendedora).write({'dcasa_promos': True})
        self.assertEqual(self.Camila._enlace_leer(token)[0], 'baja', 'Ni el enlace del pie')
        self.assertEqual(self.Camila._enlace_confirmar(token), 'baja')
        self.assertFalse(self.ana.dcasa_promos_fecha)

    def test_la_baja_con_otra_grafia_en_resend_tambien_sube(self):
        self.con_clave()
        self.permiso(self.ana, self.beto)
        segmento = self.Camila._segmento(self.Camila._cliente())
        self.resend.contacto('Beto.Zzcm@Example.com', segmentos=[segmento])
        self.beto.with_user(self.vendedora).action_dcasa_promos_baja()
        self.Camila._sincronizar()
        contacto = self.resend.contactos['Beto.Zzcm@Example.com']
        self.assertTrue(contacto['unsubscribed'], 'Por su id: el 404 por el correo ya no se traga la baja')
        campana = self.armar()['campana']   # al enviar, el segmento queda sin él (también por su id)
        self.assertTrue(self.Camila.with_user(self.marketing).enviar(campana['id'], campana['huella'])['ok'])
        self.assertNotIn(segmento, contacto['segmentos'])


# ----------------------------------------------------------------------
# 2 (media). El «Sí, quiero» solo a la ficha firmada, en la factura y la bienvenida que arma D'CASA
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestEnlaceSoloALaFicha(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        Partner = cls.env['res.partner'].with_context(**SIN_DUP)
        cls.empresa = Partner.create({'name': 'Empresa Zzcm Enlace SA', 'is_company': True, 'phone': '6000-3001',
                                      'email': 'compras.empresa.zzcm@example.com'})
        cls.pepe = Partner.create({'name': 'Pepe Zzcm', 'parent_id': cls.empresa.id, 'type': 'invoice',
                                   'email': 'pepe.zzcm@example.com'})
        cls.otro = Partner.create({'name': 'Otro Zzcm', 'email': 'otro.enlace.zzcm@example.com', 'phone': '6000-3002'})
        cls.mueble = cls.env['product.product'].create({'name': 'ZZCM MESA REVISIÓN', 'type': 'consu',
                                                        'list_price': 50.0, 'taxes_id': [Command.clear()]})
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.gerencia = Users.create({'name': 'Gerencia Zzcm Enlace', 'login': 'zzcm_gerencia_enlace',
                                     'email': 'gerencia.enlace.zzcm@example.com',
                                     'group_ids': [Command.set([cls.env.ref('base.group_user').id,
                                                                cls.env.ref('dcasa_base.group_gerencia').id])]})
        cls.marketing = Users.create({'name': 'Marketing Zzcm Enlace', 'login': 'zzcm_marketing_enlace',
                                      'email': 'marketing.enlace.zzcm@example.com',
                                      'group_ids': [Command.set([cls.env.ref('base.group_user').id,
                                                                 cls.env.ref('dcasa_marketing.group_marketing').id])]})

    def setUp(self):
        super().setUp()
        parche = patch.dict(os.environ, {'DCASA_ENTORNO': 'produccion', 'RESEND_API_KEY': 're_correo_prueba'})
        parche.start()
        self.addCleanup(parche.stop)
        post = patch('requests.post', MagicMock(side_effect=AssertionError('requests.post no debe llamarse')))
        post.start()
        self.addCleanup(post.stop)

    def factura(self, partner):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': partner.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 50.0,
                                                 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        return factura

    def ultimo_correo(self, registro):
        return self.env['mail.mail'].sudo().search(
            [('model', '=', registro._name), ('res_id', '=', registro.id)], order='id desc', limit=1)

    def enlace(self, registro):
        enlaces = lxml_html.fromstring(self.ultimo_correo(registro).body_html).xpath(
            "//a[contains(@class, 'o_camila_si_quiero')]")
        return enlaces[0].get('href') if enlaces else None

    def postear(self, registro, destino, tipo='factura', plantilla='dcasa_correo.plantilla_factura'):
        self.env['dcasa.correo'].sudo()._postear(registro, self.env.ref(plantilla), destino, tipo=tipo)

    def test_la_factura_a_un_contacto_hijo_no_lleva_el_enlace_de_la_empresa(self):
        factura = self.factura(self.pepe)
        destino = self.env['dcasa.correo'].sudo()._destino(factura)
        self.assertEqual(destino, self.pepe)
        self.postear(factura, destino)
        self.assertIsNone(self.enlace(factura), 'Pepe no puede dar el permiso de la empresa')

    def test_la_factura_a_la_ficha_lleva_el_enlace_de_esa_ficha(self):
        factura = self.factura(self.empresa)
        self.postear(factura, self.empresa)
        token = parse_qs(urlsplit(self.enlace(factura)).query)['t'][0]
        self.assertEqual(token.split('.')[0], str(self.empresa.id))
        abono = self.factura(self.empresa)
        self.postear(abono, self.empresa, tipo='abono')
        self.assertTrue(self.enlace(abono), 'La factura con saldo (abono) también es la factura')

    def test_ni_recordatorio_ni_asistente_ni_varios_destinatarios(self):
        factura = self.factura(self.empresa)
        self.postear(factura, self.empresa, tipo='recordatorio', plantilla='dcasa_correo.plantilla_recordatorio_abono')
        self.assertIsNone(self.enlace(factura), 'El recordatorio del abono no lleva la línea (decisión de la dueña)')
        self.postear(factura, self.empresa | self.otro)
        self.assertIsNone(self.enlace(factura), 'Solo con un destinatario: la ficha firmada')
        factura.message_post(body='Tu factura', partner_ids=self.empresa.ids, email_layout_xmlid=LAYOUT,
                             message_type='comment', subtype_xmlid='mail.mt_comment')
        self.assertIsNone(self.enlace(factura), 'Un correo con el layout que no armó D\'CASA (el asistente «Enviar»)')

    def test_el_interruptor_de_gerencia_apaga_la_linea_y_el_enlace(self):
        Camila = self.env['dcasa.camila']
        factura = self.factura(self.empresa)
        self.postear(factura, self.empresa)
        token = parse_qs(urlsplit(self.enlace(factura)).query)['t'][0]
        with self.assertRaises(AccessError):
            Camila.with_user(self.marketing).ajustar_enlace_pie(False)
        panel = Camila.with_user(self.gerencia).ajustar_enlace_pie(False)
        self.assertFalse(panel['enlace_pie']['encendido'])
        otra = self.factura(self.empresa)
        self.postear(otra, self.empresa)
        self.assertIsNone(self.enlace(otra), 'Apagado: la línea no va')
        self.assertEqual(Camila._enlace_leer(token)[0], 'invalido', 'Apagado: los enlaces de antes no anotan')
        Camila.with_user(self.gerencia).ajustar_enlace_pie(True)
        self.assertEqual(Camila._enlace_leer(token)[0], 'confirmar')

    def test_un_token_raro_no_da_error_500(self):
        for token in (f'{self.empresa.id}.f.1234567890.' + 'ñ' * 40, '².f.1.abc', '999999999.f.1234567890.ñ',
                      f'{self.empresa.id}.f.１２３４５６７８９０.' + 'a' * 40):
            with self.subTest(token):
                respuesta = self.url_open(f'/novedades/si?t={token}')
                self.assertEqual(respuesta.status_code, 200)
                self.assertIn('Este enlace ya no sirve', respuesta.text)
                self.assertEqual(self.env['dcasa.camila']._enlace_leer(token)[0], 'invalido')


# ----------------------------------------------------------------------
# 3 (media). Sofía: el mensaje que de verdad salió, con la frase de la plantilla
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestSofiaFraseExacta(CamilaComun):

    PLANTILLA = ('¡Hola Dani! Soy Vendedora de D\'CASA. Para atenderte mejor, ¿me regalas tu correo? Así te avisamos '
                 'de promociones, del programa Socios D\'CASA y de los beneficios de cumpleaños.')

    def setUp(self):
        super().setUp()
        self.ficha = self.env['res.partner'].create({'name': 'Dani Zzcm', 'phone': '6000-1020'})
        self.conv = self.env['dcasa.conversacion'].sudo().create({
            'canal': 'whatsapp_cloud', 'id_externo': '50760001020', 'partner_id': self.ficha.id, 'estado': 'humano'})
        self.hace = fields.Datetime.now() - timedelta(days=1)

    def propuesta(self, accion='chat', resuelta_en=None):
        return self.env['dcasa.sofia.propuesta'].sudo().create({
            'clave': f'pedir_datos:partner:{self.ficha.id}', 'tipo': 'pedir_datos', 'estado': 'aplicada',
            'pide_datos': True, 'partner_id': self.ficha.id, 'conversacion_id': self.conv.id, 'accion': accion,
            'resuelta_por': self.vendedora.id, 'resuelta_en': resuelta_en or self.hace})

    def mensaje(self, autor, texto, minutos, base=None):
        Mensaje = self.env['dcasa.mensaje'].sudo().with_context(**{CLAVE_SISTEMA: True})
        return Mensaje.create({
            'conversacion_id': self.conv.id, 'id_mensaje': f'r-{autor}-{minutos}', 'tipo': 'mensaje',
            'direccion': 'entrante' if autor == 'cliente' else 'saliente', 'autor': autor, 'texto': texto,
            'ts': (base or self.hace) + timedelta(minutes=minutos),
            'estado_envio': 'recibido' if autor == 'cliente' else 'enviado',
            'usuario_id': self.vendedora.id if autor == 'vendedora' else False})

    def correr(self):
        self.ficha.email = 'dani.zzcm@example.com'
        return self.env['res.partner']._dcasa_promos_de_sofia()

    def test_negado_no_cuenta(self):
        self.propuesta()
        self.mensaje('vendedora', 'Tranquila, no es para promociones: ¿me pasas tu correo para mandarte la factura?', 1)
        self.mensaje('cliente', 'ok, es dani.zzcm@example.com', 30)
        self.assertEqual(self.correr(), 0)
        self.assertEqual(R.pide_correo_para_promociones('No te avisamos de promociones, ¿me das tu correo?'), False)

    def test_la_promocion_de_otro_mensaje_no_cuenta(self):
        self.propuesta()
        self.mensaje('vendedora', 'Esta semana hay promoción en comedores, por si te interesa.', 1)
        self.mensaje('vendedora', '¿Me regalas tu correo para mandarte la cotización?', 2)
        self.mensaje('cliente', 'ok, es dani.zzcm@example.com', 30)
        self.assertEqual(self.correr(), 0)

    def test_en_el_chat_cuenta_el_primer_mensaje_con_la_frase_de_la_plantilla(self):
        self.propuesta()
        self.mensaje('vendedora', self.PLANTILLA, 3)
        self.mensaje('cliente', 'Claro: dani.zzcm@example.com', 30)
        self.assertEqual(self.correr(), 1)
        self.assertEqual(self.ficha.dcasa_promos_origen, 'sofia_whatsapp')

    def test_enviar_ya_cuenta_solo_el_mensaje_que_salio_de_la_propuesta(self):
        self.propuesta(accion='enviar')
        # Un mensaje con la frase que NO salió de la propuesta (lo escribió alguien en el chat): no cuenta.
        self.mensaje('vendedora', self.PLANTILLA, 1)
        self.mensaje('cliente', 'dani.zzcm@example.com', 30)
        self.assertEqual(self.correr(), 0)

    def test_enviar_ya_guarda_su_mensaje_y_ese_cuenta(self):
        self.ficha.email = 'dani.zzcm@example.com'
        propuesta = self.env['dcasa.sofia.propuesta'].sudo().create({
            'clave': f'pedir_datos:partner:{self.ficha.id}', 'tipo': 'pedir_datos', 'estado': 'pendiente',
            'pide_datos': True, 'partner_id': self.ficha.id, 'conversacion_id': self.conv.id})
        with patch('odoo.addons.dcasa_sofia.models.panel.SofiaPanel._exigir_que_se_pueda_escribir',
                   return_value=self.conv):
            self.env['dcasa.sofia'].with_user(self.gerencia)._aplicar_enviar(propuesta, self.PLANTILLA)
        mensaje = propuesta.dcasa_camila_mensaje_id
        self.assertTrue(mensaje, 'Se guarda el mensaje que salió de «Enviar ya»')
        self.assertEqual(mensaje.texto, self.PLANTILLA)
        self.assertEqual(self.env['res.partner']._dcasa_promos_de_sofia(), 0, 'Todavía no salió (sin Worker)')
        mensaje.with_context(**{CLAVE_SISTEMA: True}).sudo().write({'estado_envio': 'enviado'})
        self.mensaje('cliente', 'es dani.zzcm@example.com', 5, base=mensaje.ts)
        self.assertEqual(self.env['res.partner']._dcasa_promos_de_sofia(), 1)


# ----------------------------------------------------------------------
# 4 (media). El permiso es del correo al que se dio
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestPermisoDelCorreo(CamilaComun):

    def test_sin_correo_no_se_marca(self):
        sin = self.env['res.partner'].create({'name': 'Sin Correo Zzcm', 'phone': '6000-1098'})
        with self.assertRaisesRegex(UserError, 'correo'):
            sin.with_user(self.vendedora).write({'dcasa_promos': True})
        self.assertFalse(sin.dcasa_promos_fecha)

    def test_si_cambia_el_correo_el_permiso_no_pasa_al_nuevo(self):
        self.ana.sudo()._dcasa_promos_registrar('tienda')
        self.assertEqual(self.ana.dcasa_promos_correo, 'ana.zzcm@example.com')
        self.ana.write({'email': 'otra.persona.zzcm@example.com'})
        self.ana.invalidate_recordset()
        self.assertNotIn('otra.persona.zzcm@example.com', self.env['res.partner']._dcasa_promos_con_permiso())
        self.assertEqual(self.ana.dcasa_promos_estado, 'otro_correo')
        self.assertFalse(self.ana.dcasa_promos)
        # Si el cliente lo vuelve a decir, queda el «sí» para el correo nuevo.
        self.ana.with_user(self.vendedora).write({'dcasa_promos': True})
        self.ana.invalidate_recordset()
        self.assertEqual((self.ana.dcasa_promos_estado, self.ana.dcasa_promos_correo),
                         ('si', 'otra.persona.zzcm@example.com'))
        self.assertIn('otra.persona.zzcm@example.com', self.env['res.partner']._dcasa_promos_con_permiso())


# ----------------------------------------------------------------------
# 5 (media). En el segmento no queda nadie de más
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestSegmentoSinNadieDeMas(CamilaComun):

    def preparar(self):
        self.con_clave()
        self.permiso(self.ana)
        segmento = 'seg-reusado'
        self.resend.segmentos[segmento] = "D'CASA: clientes con permiso (Odoo)"
        self.env['ir.config_parameter'].sudo().set_param('dcasa_camila.segmento_id', segmento)
        return self.armar()['campana'], segmento

    def enviar(self, campana):
        return self.Camila.with_user(self.marketing).enviar(campana['id'], campana['huella'])

    def test_saca_por_su_id_a_los_correos_que_odoo_no_sabe_leer(self):
        campana, segmento = self.preparar()
        self.resend.contacto("o'brien.zzcm@example.com", segmentos=[segmento])
        self.resend.contacto('José.zzcm@example.com', segmentos=[segmento])
        self.resend.contacto('a@b@example.com', segmentos=[segmento])
        resultado = self.enviar(campana)
        self.assertTrue(resultado['ok'], resultado)
        (broadcast,) = self.resend.broadcasts.values()
        self.assertEqual(broadcast['enviado_a'], ['ana.zzcm@example.com'])

    def test_si_alguien_de_mas_sigue_en_el_segmento_no_sale(self):
        campana, segmento = self.preparar()
        self.resend.contacto('ajeno.zzcm@example.com', segmentos=[segmento])
        with patch.object(RC.ClienteCampanas, 'sacar_del_segmento', return_value={}):
            resultado = self.enviar(campana)
        self.assertFalse(resultado['ok'])
        self.assertIn('no van en esta campaña', resultado['mensaje'])
        self.assertFalse(any(b.get('enviado_a') for b in self.resend.broadcasts.values()), 'No salió a nadie')


# ----------------------------------------------------------------------
# 6 (media). Una campaña aprobada nunca se traba para siempre
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestCampanaTrabada(CamilaComun):

    def preparar(self):
        self.con_clave()
        self.permiso(self.ana)
        return self.armar()['campana']

    def enviar(self, campana):
        return self.Camila.with_user(self.marketing).enviar(campana['id'], campana['huella'])

    def test_cancelada_en_resend_la_descarta_gerencia(self):
        campana = self.preparar()
        self.resend.fallar.append(('POST', r'/send$', 503, 'Unavailable'))
        resultado = self.enviar(campana)
        self.resend.fallar.clear()
        (bid,) = self.resend.broadcasts
        self.resend.broadcasts[bid]['status'] = 'canceled'
        self.assertFalse(self.enviar(resultado['panel']['campana'])['ok'])
        with self.assertRaises(UserError):
            self.Camila.with_user(self.marketing).descartar(campana['id'])
        self.Camila.with_user(self.gerencia).descartar(campana['id'])
        self.assertEqual(self.env['dcasa.camila.campana'].browse(campana['id']).estado, 'cancelada')
        self.assertTrue(self.armar()['campana'], 'Ya se puede armar otra')

    def test_en_borrador_en_resend_se_descarta_y_se_borra_alla(self):
        campana = self.preparar()
        self.resend.fallar.append(('POST', r'/send$', 503, 'Unavailable'))
        self.enviar(campana)
        self.resend.fallar.clear()
        self.Camila.with_user(self.gerencia).descartar(campana['id'])
        self.assertFalse(self.resend.broadcasts, 'El borrador de Resend se borró: nadie lo manda después')

    def test_sin_broadcast_pasada_la_ventana_la_descarta_gerencia(self):
        campana = self.preparar()
        registro = self.env['dcasa.camila.campana'].browse(campana['id'])
        registro.sudo().write({'estado': 'aprobada', 'enviando_desde': fields.Datetime.now()})
        with self.assertRaisesRegex(UserError, 'se está enviando'):
            self.Camila.with_user(self.gerencia).descartar(campana['id'])
        registro.sudo().write({'enviando_desde': fields.Datetime.now() - timedelta(minutes=11)})
        self.Camila.with_user(self.gerencia).descartar(campana['id'])
        self.assertEqual(registro.estado, 'cancelada')

    def test_un_error_inesperado_no_la_deja_a_medias(self):
        campana = self.preparar()
        with patch.object(RC.ClienteCampanas, 'crear_broadcast', side_effect=RuntimeError('algo raro')), \
                self.assertLogs('odoo.addons.dcasa_camila.models.envio', level='ERROR'):
            resultado = self.enviar(campana)
        self.assertFalse(resultado['ok'])
        registro = self.env['dcasa.camila.campana'].browse(campana['id'])
        self.assertEqual((registro.estado, registro.enviando_desde), ('borrador', False))
        self.assertTrue(registro.error)


# ----------------------------------------------------------------------
# 7 (media-baja). La casilla: una ficha a la vez; desmarcar no es la baja
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestCasillaUnaALaVez(CamilaComun):

    def test_no_se_marcan_muchas_fichas_de_una_vez(self):
        todas = self.ana | self.beto | self.carla
        for usuario in (self.vendedora, self.marketing):
            with self.subTest(usuario.login), self.assertRaises(UserError):
                todas.with_user(usuario).write({'dcasa_promos': True})
        self.assertEqual(set(todas.mapped('dcasa_promos_estado')), {'sin'})
        with self.assertRaises(UserError):
            self.ana.with_user(self.vendedora).with_context(import_file=True).write({'dcasa_promos': True})
        self.permiso(self.ana, self.beto)
        with self.assertRaises(UserError):
            (self.ana | self.beto).with_user(self.vendedora).action_dcasa_promos_baja()
        self.assertFalse((self.ana | self.beto).filtered('dcasa_promos_baja_fecha'))

    def test_desmarcar_quita_el_permiso_pero_no_es_la_baja(self):
        self.permiso(self.ana)
        self.ana.with_user(self.vendedora).write({'dcasa_promos': False})
        self.ana.invalidate_recordset()
        self.assertEqual(self.ana.dcasa_promos_estado, 'sin')
        self.assertFalse(self.ana.dcasa_promos_baja_fecha, 'La baja final solo sale del botón con confirmación')
        self.ana.with_user(self.vendedora).write({'dcasa_promos': True})
        self.ana.invalidate_recordset()
        self.assertEqual(self.ana.dcasa_promos_estado, 'si')


# ----------------------------------------------------------------------
# 8 (media-baja). La revisión de marca
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestRevisionDeMarcaMasDura(BaseCase):

    def test_numeros_en_letras_beneficios_y_prisas(self):
        for texto in ('Llévate dos por uno esta quincena.', 'Ahora a mitad de precio.', 'Para seis personas.',
                      'Entrega sin costo a toda Panamá.', 'Y te regalamos la instalación.',
                      'Paga en cuotas sin intereses.', 'Con garantía de por vida.', 'Últimos días para tenerlo.',
                      'Aprovecha antes de que se acabe.', 'Precio de fábrica: nadie te lo deja más barato.',
                      'Promoción de locura en salas.', 'Ahorra en tu comedor.'):
            with self.subTest(texto):
                self.assertTrue(R.problemas(texto, 300), texto)

    def test_remate_escondido(self):
        cirilico = 'r\u0435mate de temporada'   # «\u0435» cirílica
        self.assertTrue(R.problemas(cirilico, 300))
        self.assertEqual(R.elegir_texto(cirilico, 'FIJO', 300), ('FIJO', False))
        invisible = 'Gran re\u200bmate de sofás'
        self.assertEqual(R.limpiar(invisible), 'Gran remate de sofás', 'El invisible se quita, no se vuelve espacio')
        self.assertEqual(R.elegir_texto(invisible, 'FIJO', 300), ('FIJO', False))
        self.assertTrue(R.problemas('Gran re\u00admate de sofás', 300), 'Guion suave dentro de la palabra')
        self.assertTrue(R.problemas('Gran \uff52\uff45\uff4d\uff41\uff54\uff45 de sofás', 300), 'Letras anchas')

    def test_lo_de_siempre_sigue_pasando(self):
        for texto in ('Llegaron muebles nuevos para tu sala. Escríbenos por WhatsApp y te contamos.',
                      'Una cama lista para tu recámara, con espacio para guardar.', R.ASUNTO_FIJO, R.ENTRADA_FIJA,
                      *R.LINEAS_FIJAS.values()):
            with self.subTest(texto):
                self.assertEqual(R.problemas(texto, 300), [])


# ----------------------------------------------------------------------
# 10 (baja). La prueba tiene tope
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestTopeDePruebas(CamilaComun):

    def test_una_cada_dos_minutos_y_pocas_al_dia(self):
        campana = self.armar()['campana']
        Camila = self.Camila.with_user(self.marketing)
        with self.correo_transaccional() as post:
            Camila.enviar_prueba(campana['id'])
            with self.assertRaisesRegex(UserError, 'minutos'):
                Camila.enviar_prueba(campana['id'])
            self.assertEqual(post.call_count, 1)
            Prueba = self.env['dcasa.camila.prueba'].sudo()
            hace_tres_minutos = fields.Datetime.now() - timedelta(minutes=3)
            Prueba.search([('usuario_id', '=', self.marketing.id)]).write({'enviada_en': hace_tres_minutos})
            Camila.enviar_prueba(campana['id'])
            self.assertEqual(post.call_count, 2)
            Prueba.search([('usuario_id', '=', self.marketing.id)]).write({'enviada_en': hace_tres_minutos})
            Prueba.create([{'usuario_id': self.marketing.id, 'enviada_en': fields.Datetime.now() - timedelta(hours=5)}
                           for _i in range(8)])
            with self.assertRaisesRegex(UserError, '24 horas'):
                Camila.enviar_prueba(campana['id'])
            self.assertEqual(post.call_count, 2)
            Prueba.search([('enviada_en', '<', fields.Datetime.now() - timedelta(hours=1))]).write(
                {'enviada_en': fields.Datetime.now() - timedelta(hours=25)})
            Camila.enviar_prueba(campana['id'])
            self.assertEqual(post.call_count, 3, 'Las de hace más de 24 horas ya no cuentan')


# ----------------------------------------------------------------------
# 12 (baja). Las bajas de los resultados y la marca en el primer mensaje
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestMitigaciones(CamilaComun):

    def setUp(self):
        super().setUp()
        self.con_clave()
        self.permiso(self.ana, self.beto)
        campana = self.armar()['campana']
        self.Camila.with_user(self.marketing).enviar(campana['id'], campana['huella'])
        self.campana = self.env['dcasa.camila.campana'].browse(campana['id'])

    def llega(self, texto, numero, id_mensaje, minutos):
        return self.env['dcasa.conversacion'].sudo()._registrar_mensaje({
            'canal': 'whatsapp_cloud', 'id_externo': numero, 'id_mensaje': id_mensaje, 'direccion': 'entrante',
            'autor': 'cliente', 'texto': texto, 'nombre': 'Cliente Zzcm Chat',
            'ts': fields.Datetime.now() + timedelta(minutes=minutos)})

    def test_las_bajas_de_los_resultados_quedan_en_odoo(self):
        bid = self.campana.resend_broadcast_id
        self.resend.destinatarios[(bid, 'unsubscribed')] = ['Ana.Zzcm@example.com']
        self.Camila.with_user(self.marketing).actualizar_resultados(self.campana.id)
        self.assertEqual(self.campana.bajas, 1)
        self.assertEqual((self.ana.dcasa_promos_estado, self.ana.dcasa_promos_baja_origen), ('baja', 'correo'))
        self.assertEqual(self.beto.dcasa_promos_estado, 'si')

    def test_la_marca_cuenta_solo_en_el_primer_mensaje_despues_de_la_campana(self):
        marca = R.texto_whatsapp(self.campana.id)
        self.llega('Hola, ¿tienen camas?', '50760004001', 'p1', 1)
        self.llega(f'Por cierto {marca}', '50760004001', 'p2', 2)
        self.assertFalse(self.campana.llegada_ids, 'La marca escrita después no cuenta')
        self.llega(marca, '50760004002', 'p3', 3)
        self.assertEqual(len(self.campana.llegada_ids), 1)
        # Un cliente de antes (con chats viejos) que vuelve por el correo sí cuenta: es su primer mensaje desde la
        # campaña (la conversación de un cliente es una sola, de siempre).
        self.llega('Gracias por la entrega', '50760004003', 'p4', -60 * 24 * 3)
        self.llega(marca, '50760004003', 'p5', 4)
        self.assertEqual(len(self.campana.llegada_ids), 2)
