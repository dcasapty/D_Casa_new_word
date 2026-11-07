"""El remitente propio de las campañas y el aviso cuando Resend no cuenta aperturas ni clics (2026-11-07).

La tabla de campañas decía 0 «Abrieron» y 0 «Tocaron»: Resend trae el conteo APAGADO por dominio y Camila salía del
remitente de las facturas (``ventas@dcasapty.com``). Encenderlo ahí pondría el píxel y cambiaría los enlaces de las
facturas; Resend recomienda contar solo en el dominio de las campañas. Por eso:

* **«Remitente de las campañas»** (``dcasa_camila.remitente``, lo cambian Gerencia y los administradores): vacío, todo
  sigue como antes; con un correo, el *broadcast* y la prueba salen de ahí, con el mismo nombre y la misma dirección
  de respuesta de siempre. Las facturas no cambian.
* **El aviso**: con la clave de campañas y en producción se leen los dominios de Resend (cada 6 horas con el cron de
  cada hora, al cambiar el remitente y con «Revisar ahora»; la pantalla solo lee lo guardado y nunca falla por
  Resend). Si el dominio no está o no está verificado, lo dice y no deja enviar; si el conteo está apagado, lo dice con
  los pasos para encenderlo.

Resend es el falso en memoria de ``comun.py`` (nunca la API de verdad); datos inventados (example.com)."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import BaseCase, HttpCase, tagged

from .comun import CLAVE_CAMPANAS, CLAVE_CORREO, CamilaComun

REMITENTE = 'novedades@novedades.example.com'
DOMINIO = 'novedades.example.com'
P_REMITENTE = 'dcasa_camila.remitente'
P_REVISION = 'dcasa_camila.remitente_revision'
NO_VERIFICADO = 'El remitente de las campañas todavía no está verificado en Resend: las campañas no saldrán desde ahí'


def llamadas_a_dominios(resend):
    return [ruta for metodo, ruta, _c, _p in resend.llamadas if ruta.startswith('/domains')]


class ComunRemitente(CamilaComun):

    def setUp(self):
        super().setUp()
        self.ICP = self.env['ir.config_parameter'].sudo()

    def con_remitente(self, correo=REMITENTE):
        self.ICP.set_param(P_REMITENTE, correo)

    def panel(self, usuario=None):
        return self.Camila.with_user(usuario or self.marketing).panel()

    def enviar(self, campana, usuario=None):
        return self.Camila.with_user(usuario or self.marketing).enviar(campana['id'], campana['huella'])

    def revisar(self, usuario=None):
        return self.Camila.with_user(usuario or self.marketing).revisar_remitente()

    def textos(self, datos):
        """Todo lo que la pantalla muestra del remitente y sus avisos (para buscar la clave o un correo)."""
        return repr(datos['remitente']) + repr(datos['bloqueos'])


@tagged('post_install', '-at_install')
class TestRemitenteDeLasCampanas(ComunRemitente):

    def preparar(self):
        self.con_clave()
        self.permiso(self.ana, self.beto)
        return self.armar()['campana']

    def test_sin_remitente_propio_todo_sigue_igual(self):
        campana = self.preparar()
        remitente = self.panel()['remitente']
        self.assertEqual((remitente['correo'], remitente['propio']), ('ventas@dcasapty.com', ''))
        self.assertTrue(self.enviar(campana)['ok'])
        (broadcast,) = self.resend.broadcasts.values()
        self.assertEqual(broadcast['from'], '"D\'CASA Panamá" <ventas@dcasapty.com>')
        self.assertEqual(broadcast['reply_to'], 'info@dcasapty.com')

    def test_el_broadcast_sale_del_remitente_de_las_campanas(self):
        campana = self.preparar()
        self.con_remitente()
        resultado = self.enviar(campana)
        self.assertTrue(resultado['ok'], resultado)
        (broadcast,) = self.resend.broadcasts.values()
        self.assertEqual(broadcast['from'], f'"D\'CASA Panamá" <{REMITENTE}>',
                         'El nombre es el de siempre; el correo, el de las campañas')
        self.assertEqual(broadcast['reply_to'], 'info@dcasapty.com', 'Las respuestas llegan a donde siempre')
        self.assertEqual(self.env['dcasa.correo']._config()['remitente'], 'ventas@dcasapty.com',
                         'El remitente de las facturas no cambia')

    def test_la_prueba_sale_del_remitente_de_las_campanas_y_las_facturas_no(self):
        campana = self.armar()['campana']
        self.con_remitente()
        with self.correo_transaccional() as post:
            self.Camila.with_user(self.marketing).enviar_prueba(campana['id'])
        datos = post.call_args.kwargs['json']
        self.assertEqual(datos['from'], f'"D\'CASA Panamá" <{REMITENTE}>')
        self.assertEqual(datos['reply_to'], ['info@dcasapty.com'])
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], f'Bearer {CLAVE_CORREO}',
                         'La prueba sigue saliendo por los correos de siempre')
        # Cualquier otro correo (una factura, la bienvenida…) sigue saliendo del remitente de siempre.
        otro = self.env['mail.mail'].sudo().create({
            'subject': 'Factura ZZCM', 'body_html': '<p>Factura</p>', 'email_to': 'marketing.zzcm@example.com',
            'headers': repr({'X-Dcasa-Correo': 'prueba'})})
        with self.correo_transaccional() as post:
            otro.send(raise_exception=True)
        self.assertEqual(post.call_args.kwargs['json']['from'], '"D\'CASA Panamá" <ventas@dcasapty.com>')

    def test_la_marca_de_la_prueba_no_viaja_por_rpc(self):
        """El cambio de remitente de la prueba va con un objeto de Python en el contexto: un texto mandado por RPC
        (con el mismo nombre de clave) no cambia el remitente de nada."""
        from ..models import remitente as REM

        self.con_remitente()
        otro = self.env['mail.mail'].sudo().with_context(**{REM.MARCA_PRUEBA: REMITENTE}).create({
            'subject': 'Factura ZZCM', 'body_html': '<p>Factura</p>', 'email_to': 'marketing.zzcm@example.com',
            'headers': repr({'X-Dcasa-Correo': 'prueba'})})
        with self.correo_transaccional() as post:
            otro.send(raise_exception=True)
        self.assertEqual(post.call_args.kwargs['json']['from'], '"D\'CASA Panamá" <ventas@dcasapty.com>')

    def test_lo_cambian_gerencia_y_administradores_y_se_valida(self):
        with self.assertRaises(AccessError):
            self.Camila.with_user(self.marketing).ajustar_remitente(REMITENTE)
        with self.assertRaises(AccessError):
            self.Camila.with_user(self.vendedora).ajustar_remitente(REMITENTE)
        for malo in ('no es un correo', 'Novedades <novedades@novedades.example.com>', 'a@example.com, b@example.com',
                     'a@@example.com', 'x' * 250 + '@example.com', 7, None, ['a@example.com']):
            with self.subTest(malo=malo), self.assertRaises(UserError):
                self.Camila.with_user(self.gerencia).ajustar_remitente(malo)
        self.assertFalse(self.ICP.get_param(P_REMITENTE), 'Nada inválido quedó guardado')
        datos = self.Camila.with_user(self.gerencia).ajustar_remitente('  Novedades@Novedades.Example.COM ')
        self.assertEqual(self.ICP.get_param(P_REMITENTE), REMITENTE, 'Queda normalizado')
        self.assertEqual((datos['remitente']['correo'], datos['remitente']['propio']), (REMITENTE, REMITENTE))
        self.assertTrue(datos['remitente']['puede_cambiar'])
        self.assertFalse(self.panel()['remitente']['puede_cambiar'], 'El rol Marketing lo ve, no lo cambia')
        datos = self.Camila.with_user(self.gerencia).ajustar_remitente('')
        self.assertEqual((datos['remitente']['correo'], datos['remitente']['propio']), ('ventas@dcasapty.com', ''),
                         'Vacío: vuelve al de las facturas')


@tagged('post_install', '-at_install')
class TestRevisarElRemitenteEnResend(ComunRemitente):

    def setUp(self):
        super().setUp()
        self.con_clave()
        self.con_remitente()
        self.permiso(self.ana, self.beto)

    def test_sin_conteo_avisa_con_los_tres_pasos(self):
        self.resend.dominio(DOMINIO, aperturas=False, clics=False)
        datos = self.revisar()
        aviso = datos['remitente']['aviso']
        self.assertEqual(aviso['tipo'], 'sin_seguimiento')
        self.assertIn('Resend no está contando aperturas ni clics de este remitente', aviso['titulo'])
        self.assertIn('Abrieron y Tocaron saldrán en 0', aviso['titulo'])
        self.assertEqual(len(aviso['pasos']), 3)
        pasos = ' '.join(aviso['pasos'])
        for texto in ('Domains', DOMINIO, 'Configuration', 'Enable tracking metrics', 'links', 'DNS only',
                      'Revisar ahora'):
            self.assertIn(texto, pasos)
        self.assertFalse(datos['bloqueos'], 'Sin conteo igual se puede enviar (solo no se cuentan)')
        detalle = f"/domains/{self.resend.dominios[DOMINIO]['id']}"
        self.assertEqual(llamadas_a_dominios(self.resend), ['/domains', detalle],
                         'La lista no trae el subdominio de seguimiento: se pide el detalle')
        self.assertNotIn(CLAVE_CAMPANAS, self.textos(datos))

    def test_solo_clics_apagados_lo_dice_asi(self):
        self.resend.dominio(DOMINIO, aperturas=True, clics=False, subdominio='links')
        aviso = self.revisar()['remitente']['aviso']
        self.assertIn('Resend no está contando clics de este remitente: Tocaron saldrá en 0', aviso['titulo'])
        self.assertNotIn('aperturas', aviso['titulo'])

    def test_solo_aperturas_apagadas_lo_dice_asi(self):
        self.resend.dominio(DOMINIO, aperturas=False, clics=True, subdominio='links')
        aviso = self.revisar()['remitente']['aviso']
        self.assertIn('Resend no está contando aperturas de este remitente: Abrieron saldrá en 0', aviso['titulo'])

    def test_con_conteo_encendido_no_hay_aviso(self):
        self.resend.dominio(DOMINIO, aperturas=True, clics=True, subdominio='links')
        datos = self.revisar()
        self.assertIsNone(datos['remitente']['aviso'])
        self.assertIn('Revisado en Resend', datos['remitente']['revision'])
        self.assertFalse(datos['bloqueos'])

    def test_conteo_encendido_pero_el_cname_sin_verificar(self):
        """Resend solo cuenta cuando el subdominio de seguimiento («links») está verificado."""
        self.resend.dominio(DOMINIO, aperturas=True, clics=True, subdominio='links', seguimiento='pending')
        aviso = self.revisar()['remitente']['aviso']
        self.assertEqual(aviso['tipo'], 'sin_seguimiento')
        self.assertIn(f'links.{DOMINIO}', aviso['detalle'])

    def test_dominio_sin_verificar_avisa_y_no_deja_enviar(self):
        self.resend.dominio(DOMINIO, status='pending', aperturas=True, clics=True, subdominio='links')
        campana = self.armar()['campana']
        datos = self.revisar()
        aviso = datos['remitente']['aviso']
        self.assertEqual(aviso['tipo'], 'no_verificado')
        self.assertIn(NO_VERIFICADO, aviso['titulo'])
        self.assertTrue(any('todavía no está verificado en Resend' in b for b in datos['bloqueos']),
                        'La pantalla apaga «Enviar» y dice por qué')
        resultado = self.enviar(campana)
        self.assertFalse(resultado['ok'])
        self.assertIn('todavía no está verificado en Resend', resultado['mensaje'])
        self.assertFalse(self.resend.broadcasts, 'Un broadcast de un dominio sin verificar falla en Resend: no sale')
        self.assertEqual(self.env['dcasa.camila.campana'].browse(campana['id']).estado, 'borrador')
        # La dueña lo verifica en Resend: al tocar «Enviar» se vuelve a mirar (no se queda con lo guardado) y sale.
        self.resend.dominios[DOMINIO]['status'] = 'verified'
        resultado = self.enviar(resultado['panel']['campana'])
        self.assertTrue(resultado['ok'], resultado)
        (broadcast,) = self.resend.broadcasts.values()
        self.assertEqual(broadcast['from'], f'"D\'CASA Panamá" <{REMITENTE}>')

    def test_dominio_que_no_esta_en_resend(self):
        self.resend.dominio('dcasapty.com')   # solo el de las facturas
        datos = self.revisar()
        aviso = datos['remitente']['aviso']
        self.assertEqual(aviso['tipo'], 'no_verificado')
        self.assertIn('no está en Resend', aviso['detalle'])
        self.assertTrue(datos['bloqueos'])
        campana = self.armar()['campana']
        with patch.object(type(self.Camila), '_bloqueos', autospec=True, return_value=[]):
            # Aunque la pantalla no lo dijera (por RPC), el servidor no lo deja salir.
            self.assertFalse(self.enviar(campana)['ok'])
        self.assertFalse(self.resend.broadcasts)

    def test_si_resend_falla_la_pantalla_sigue_y_no_bloquea(self):
        self.resend.dominio(DOMINIO)
        self.resend.fallar.append(('GET', r'^/domains', 500, f'falló con {CLAVE_CAMPANAS}'))
        datos = self.revisar()
        self.assertIsNone(datos['remitente']['aviso'], 'Si Resend falla, no se inventa un aviso')
        self.assertIn('No se pudo revisar', datos['remitente']['nota'])
        self.assertFalse(datos['bloqueos'], 'Lo que no se sabe no bloquea')
        self.assertNotIn(CLAVE_CAMPANAS, self.textos(datos))
        self.assertTrue(self.enviar(self.armar()['campana'])['ok'])

    def test_la_pantalla_nunca_llama_a_resend(self):
        self.resend.dominio(DOMINIO)
        datos = self.panel()
        self.assertFalse(llamadas_a_dominios(self.resend), 'La pantalla solo lee lo guardado')
        self.assertIsNone(datos['remitente']['aviso'])
        self.assertIn('Todavía no se ha revisado', datos['remitente']['revision'])
        self.assertTrue(datos['remitente']['puede_revisar'])
        with patch('odoo.addons.dcasa_camila.models.remitente.DcasaCamila._aviso_remitente',
                   side_effect=RuntimeError('algo raro')):
            self.assertIsNone(self.panel()['remitente']['aviso'], 'Un error del aviso nunca tumba la pantalla')
        self.ICP.set_param(P_REVISION, f'{{"dominio": "{DOMINIO}", "en": "basura", "resultado": "ok"}}')
        self.assertIn('Revisado en Resend', self.panel()['remitente']['revision'], 'Un dato raro tampoco')
        self.ICP.set_param(P_REVISION, 'esto no es json')
        self.assertIn('Todavía no se ha revisado', self.panel()['remitente']['revision'])

    def test_el_cron_revisa_cada_6_horas(self):
        self.resend.dominio(DOMINIO)
        self.assertTrue(self.Camila._cron_sincronizar())
        self.assertEqual(len([r for r in llamadas_a_dominios(self.resend) if r == '/domains']), 1)
        self.Camila._cron_sincronizar()
        self.assertEqual(len([r for r in llamadas_a_dominios(self.resend) if r == '/domains']), 1,
                         'Revisado hace un momento: no se pregunta otra vez')
        self.assertEqual(self.panel()['remitente']['aviso']['tipo'], 'sin_seguimiento',
                         'Lo que guardó el cron es lo que la pantalla muestra')
        self.mover_revision(horas=7)
        self.Camila._cron_sincronizar()
        self.assertEqual(len([r for r in llamadas_a_dominios(self.resend) if r == '/domains']), 2)

    def test_un_error_se_reintenta_con_el_cron_siguiente(self):
        self.resend.dominio(DOMINIO)
        self.resend.fallar.append(('GET', r'^/domains', 503, 'Unavailable'))
        self.Camila._cron_sincronizar()
        self.resend.fallar.clear()
        self.mover_revision(horas=1, minutos=5)
        self.Camila._cron_sincronizar()
        self.assertEqual(self.panel()['remitente']['aviso']['tipo'], 'sin_seguimiento')

    def test_un_error_del_aviso_nunca_frena_el_cron(self):
        with patch('odoo.addons.dcasa_camila.models.remitente.DcasaCamila._revisar_remitente',
                   side_effect=RuntimeError('algo raro')), \
                self.assertLogs('odoo.addons.dcasa_camila.models.envio', level='WARNING'):
            self.assertTrue(self.Camila._cron_sincronizar())

    def test_cambiar_el_remitente_revisa_el_dominio_nuevo(self):
        self.resend.dominio(DOMINIO, aperturas=True, clics=True, subdominio='links')
        self.resend.dominio('otro.example.com', status='not_started')
        datos = self.Camila.with_user(self.gerencia).ajustar_remitente(REMITENTE)
        self.assertIsNone(datos['remitente']['aviso'])
        datos = self.Camila.with_user(self.gerencia).ajustar_remitente('campanas@otro.example.com')
        self.assertEqual(datos['remitente']['aviso']['tipo'], 'no_verificado',
                         'Lo revisado de otro dominio no vale para el nuevo')

    def test_revisar_ahora_no_martilla_a_resend(self):
        self.resend.dominio(DOMINIO)
        self.revisar()
        self.revisar()
        self.assertEqual(len([r for r in llamadas_a_dominios(self.resend) if r == '/domains']), 1)
        with self.assertRaises(AccessError):
            self.Camila.with_user(self.vendedora).revisar_remitente()

    def test_en_staging_ni_revisa_ni_avisa(self):
        self.resend.dominio(DOMINIO)
        with patch.dict('os.environ', {'DCASA_ENTORNO': 'staging'}):
            with self.assertRaisesRegex(UserError, 'producción'):
                self.revisar()
            self.Camila._cron_sincronizar()
            remitente = self.panel()['remitente']
        self.assertFalse(llamadas_a_dominios(self.resend))
        self.assertIsNone(remitente['aviso'])
        self.assertFalse(remitente['puede_revisar'])

    def test_sin_remitente_propio_revisa_el_de_las_facturas_y_no_lo_enciende_ahi(self):
        self.ICP.set_param(P_REMITENTE, '')
        self.resend.dominio('dcasapty.com')
        aviso = self.revisar()['remitente']['aviso']
        self.assertEqual(aviso['tipo'], 'sin_seguimiento')
        self.assertIn('las facturas', aviso['detalle'], 'Avisa que encenderlo ahí cambia las facturas')
        pasos = ' '.join(aviso['pasos'])
        self.assertIn('Remitente de las campañas', pasos)
        self.assertIn('subdominio', pasos)

    def test_un_dominio_con_falla_temporal_avisa_sin_bloquear(self):
        self.resend.dominio(DOMINIO, status='temporary_failure', aperturas=True, clics=True, subdominio='links')
        datos = self.revisar()
        self.assertEqual(datos['remitente']['aviso']['tipo'], 'otro')
        self.assertFalse(datos['bloqueos'], 'Solo bloquea lo que se sabe que no está verificado')

    def test_brian_dice_el_remitente_y_el_aviso(self):
        self.resend.dominio(DOMINIO)
        self.revisar()
        respuesta = self.env['brian.herramientas'].with_user(self.marketing).ejecutar('estado_campanas', {})
        self.assertTrue(respuesta['ok'], respuesta)
        self.assertEqual(respuesta['datos']['remitente_de_las_campanas'], REMITENTE)
        self.assertIn('Abrieron y Tocaron saldrán en 0', respuesta['datos']['aviso_de_resend'])

    def mover_revision(self, horas=0, minutos=0):
        import json

        revision = json.loads(self.ICP.get_param(P_REVISION))
        revision['en'] = fields.Datetime.to_string(fields.Datetime.now() - timedelta(hours=horas, minutes=minutos))
        self.ICP.set_param(P_REVISION, json.dumps(revision))


@tagged('post_install', '-at_install')
class TestGuiaAbrieronEnCero(BaseCase):
    """La Guía (``dcasa_guia/data/guia.json``) explica en palabras sencillas por qué «Abrieron» sale en 0 y cómo
    encender el conteo solo para las campañas (sin fechas ni montos inventados)."""

    def test_la_guia_tiene_los_pasos(self):
        import json

        from odoo.tools import file_open

        try:
            with file_open('dcasa_guia/data/guia.json') as archivo:
                guia = json.load(archivo)
        except FileNotFoundError:
            self.skipTest('dcasa_guia no está en el camino de módulos')
        tarea = next(t for t in guia['tareas'] if t['id'] == 'camila-abrieron-en-cero')
        self.assertEqual(tarea['titulo'], '¿Por qué Abrieron sale en 0?')
        self.assertEqual(tarea['destino'], {'menu': 'dcasa_camila.menu_camila'})
        pasos = ' '.join(p['texto'] for p in tarea['pasos'])
        for texto in ('Resend › Domains', 'novedades.dcasapty.com', 'Configuration', 'Enable tracking metrics',
                      '«links»', 'Cloudflare', 'CNAME', 'nube gris', 'DNS only', 'Remitente de las campañas'):
            self.assertIn(texto, pasos)
        self.assertIn('facturas', tarea['nota'], 'Dice por qué no se enciende en el dominio de las facturas')


@tagged('post_install', '-at_install')
class TestClasificarDominio(BaseCase):
    """Lo que dice Resend de un dominio, en lo que le importa a Camila (sin base de datos)."""

    def clasificar(self, **datos):
        from ..models import remitente as REM

        return REM.clasificar_dominio(datos)

    def test_estados_de_resend(self):
        for estado, resultado in (('verified', 'ok'), ('partially_verified', 'ok'), ('not_started', 'no_verificado'),
                                  ('pending', 'no_verificado'), ('failed', 'no_verificado'),
                                  ('temporary_failure', 'otro'), ('partially_failed', 'otro'), ('', 'otro'),
                                  ('algo_nuevo', 'otro')):
            with self.subTest(estado):
                self.assertEqual(self.clasificar(status=estado)['resultado'], resultado)
        self.assertEqual(self.clasificar(status='verified', capabilities={'sending': 'disabled'})['resultado'],
                         'no_verificado', 'Con el envío apagado en Resend tampoco sale')

    def test_el_conteo(self):
        datos = self.clasificar(status='verified', open_tracking=True, click_tracking=False,
                                tracking_subdomain='links', records=[
                                    {'record': 'Tracking', 'name': 'links.example.com', 'status': 'verified'}])
        self.assertEqual((datos['aperturas'], datos['clics'], datos['subdominio'], datos['seguimiento_verificado']),
                         (True, False, 'links', True))
        sin_datos = self.clasificar(status='verified')
        self.assertEqual((sin_datos['aperturas'], sin_datos['clics'], sin_datos['seguimiento_verificado']),
                         (None, None, None), 'Lo que Resend no dijo no se adivina')
        viejo_y_nuevo = self.clasificar(status='verified', open_tracking=True, click_tracking=True,
                                        tracking_subdomain='clics', records=[
                                            {'record': 'Tracking', 'name': 'links.example.com', 'status': 'verified'},
                                            {'record': 'Tracking', 'name': 'clics.example.com', 'status': 'pending'}])
        self.assertFalse(viejo_y_nuevo['seguimiento_verificado'], 'Cuenta el registro del subdominio de ahora')


# ----------------------------------------------------------------------
# En el navegador: el aviso se ve, la pantalla sigue bajando (el bug de siempre) y Gerencia cambia el remitente
# ----------------------------------------------------------------------

AVISO_Y_SCROLL = """
    const pantalla = await esperar(() => document.querySelector('.o_action.o_camila'), 'la pantalla de Camila');
    await esperar(() => document.querySelectorAll('li.o_camila_producto').length === 8, 'los 8 productos');
    const aviso = await esperar(() => document.querySelector('.o_camila_aviso_remitente'),
                                'el aviso de que Resend no cuenta aperturas ni clics');
    if (!aviso.textContent.includes('Abrieron y Tocaron saldrán en 0')) {
        throw new Error('El aviso no dice que saldrán en 0: ' + aviso.textContent.trim().slice(0, 200));
    }
    if (aviso.querySelectorAll('ol li').length !== 3) { throw new Error('El aviso no trae los 3 pasos'); }
    const caja = aviso.getBoundingClientRect();
    if (caja.height < 40 || caja.top > window.innerHeight || caja.right > window.innerWidth + 1) {
        throw new Error('El aviso no se ve entero arriba: ' + JSON.stringify(caja));
    }
    if (!aviso.querySelector('.o_camila_aviso_revisar')) { throw new Error('Falta «Revisar ahora» en el aviso'); }
    const nota = document.querySelector('.o_camila_nota_seguimiento');
    if (!nota || !nota.textContent.includes('siempre dirán 0')) {
        throw new Error('Falta la nota de las campañas que salieron sin el conteo');
    }
    // EL SCROLL (el bug de siempre): con el aviso arriba, la pantalla sigue bajando hasta el final.
    const desborde = getComputedStyle(pantalla).overflowY;
    if (!['auto', 'scroll'].includes(desborde)) {
        throw new Error('Camila no baja con scroll: overflow-y: ' + desborde);
    }
    if (pantalla.scrollHeight <= pantalla.clientHeight + 50) {
        throw new Error('La pantalla no es más alta que la ventana: no se puede probar el scroll');
    }
    pantalla.scrollTop = 100000;
    await new Promise((ok) => setTimeout(ok, 150));
    if (pantalla.scrollTop < 50) { throw new Error('Camila no baja con scroll'); }
    for (const selector of ['.o_camila_remitente', '.o_camila_pie_ajuste']) {
        const seccion = document.querySelector(selector);
        if (!seccion) { throw new Error('Falta ' + selector); }
        if (seccion.getBoundingClientRect().bottom > window.innerHeight + 2) {
            throw new Error('Abajo del todo, ' + selector + ' sigue cortado');
        }
    }
    sinScrollDeLado();
    pantalla.scrollTop = 0;
"""

CAMBIAR_REMITENTE = """
    const campo = await esperar(() => document.querySelector('input.o_camila_remitente_correo'),
                                'el campo del remitente de las campañas');
    campo.value = 'novedades@novedades.example.com';
    campo.dispatchEvent(new Event('input', { bubbles: true }));
    document.querySelector('.o_camila_remitente_guardar').click();
    await esperar(() => document.querySelector('.o_camila_remitente_actual')
                        && document.querySelector('.o_camila_remitente_actual').textContent
                            .includes('novedades@novedades.example.com'), 'el remitente nuevo en la pantalla');
    // El subdominio de las campañas ya cuenta aperturas y clics: el aviso se va.
    await esperar(() => !document.querySelector('.o_camila_aviso_remitente'), 'que se vaya el aviso');
    sinErrores();
"""

SOLO_VER = """
    const seccion = await esperar(() => document.querySelector('.o_camila_remitente'), 'la sección del remitente');
    if (seccion.querySelector('input.o_camila_remitente_correo')) {
        throw new Error('El rol Marketing no cambia el remitente');
    }
    if (!seccion.textContent.includes('Lo cambian Gerencia o un administrador')) {
        throw new Error('No dice quién lo cambia');
    }
    const revisar = () => document.querySelector('.o_camila_aviso_revisar');
    revisar().click();
    for (let i = 0; i < 40 && revisar() && !revisar().disabled; i++) {   // que empiece (puede ser muy rápido)
        await new Promise((ok) => setTimeout(ok, 50));
    }
    await esperar(() => revisar() && !revisar().disabled, 'que termine de revisar');
    await esperar(() => document.querySelector('.o_camila_aviso_remitente'), 'el aviso sigue (no cambió nada)');
    sinErrores();
"""


@tagged('post_install', '-at_install')
class TestAvisoRemitenteEnElNavegador(ComunRemitente, HttpCase):

    def setUp(self):
        super().setUp()
        self.website.domain = False   # las fotos las sirve este mismo servidor de pruebas
        self.con_clave()
        self.permiso(self.ana, self.beto)
        campana = self.armar()['campana']
        self.Camila.with_user(self.marketing).guardar(
            campana['id'], {'lineas': [{'producto_id': p.id, 'texto': ''} for p in self.productos]})
        hace = fields.Datetime.now() - timedelta(days=20)
        self.env['dcasa.camila.campana'].sudo().create({
            'name': 'ZZCM enviada', 'asunto': 'Lo nuevo para tu sala', 'estado': 'enviada', 'enviada_en': hace,
            'destinatarios': 2, 'resend_broadcast_id': 'bc-zzcm', 'resultados_en': hace, 'entregados': 2})
        # Hoy: salen del remitente de las facturas, que (bien) no cuenta; el subdominio de las campañas sí cuenta.
        self.resend.dominio('dcasapty.com')
        self.resend.dominio(DOMINIO, aperturas=True, clics=True, subdominio='links')
        self.Camila.sudo()._revisar_remitente('ahora')

    def correr(self, cuerpo, login):
        from odoo.addons.dcasa_contactos.tests.test_fijo_y_copiar_navegador import COMUN

        codigo = '(async () => {' + COMUN + cuerpo + "sinErrores(); console.log('test successful'); })();"
        self.browser_js('/odoo/camila', codigo, ready='odoo.isReady', login=login, timeout=180)

    def test_el_aviso_se_ve_la_pantalla_baja_y_gerencia_cambia_el_remitente(self):
        self.browser_size = '1366x768'
        self.correr(AVISO_Y_SCROLL + CAMBIAR_REMITENTE, login='zzcm_gerencia')
        self.assertEqual(self.ICP.get_param(P_REMITENTE), REMITENTE)

    def test_en_el_celular_el_aviso_se_ve_y_baja_sin_scroll_de_lado(self):
        self.browser_size = '390x844'
        self.correr(AVISO_Y_SCROLL + SOLO_VER, login='zzcm_marketing')
