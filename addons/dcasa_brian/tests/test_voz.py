"""Notas de voz de Brian del panel (``models/voz.py`` y ``controllers/voz.py``).

Lo que se prueba: solo usuarios internos (el portal y el público no), solo vuelve el texto, el audio no queda en
ningún lado (ni adjunto, ni mensaje, ni auditoría, ni registro), las reglas de la nota (tipo, firma, tamaño, un minuto)
y, en el navegador, el micrófono con el tiempo a la vista, cancelar con Esc y el texto en la caja para revisarlo.
"""
import base64
import json
import logging
from contextlib import contextmanager
from unittest.mock import patch

from odoo.addons.dcasa_brian.controllers.voz import MAX_CUERPO
from odoo.addons.dcasa_brian.models.voz import MAX_BYTES, TEXTOS
from odoo.exceptions import AccessError
from odoo.service.model import call_kw
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tests.common import TransactionCase

from .test_interfaz_brian import ESPERAR

# Lo que graba Chrome empieza así (EBML); Firefox, «OggS»; Safari, una caja «ftyp» en el byte 4.
WEBM = b'\x1a\x45\xdf\xa3' + b'\x9f\x42\x86\x81\x01' + b'\x00' * 400
OGG = b'OggS' + b'\x00' * 400
MP4 = b'\x00\x00\x00\x18ftypM4A ' + b'\x00' * 400
DICHO = 'Brian, dime cuántas cotizaciones quedaron abiertas esta semana'


def b64(datos):
    return base64.b64encode(datos).decode()


class _Captura(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lineas = []

    def emit(self, record):
        try:
            self.lineas.append(record.getMessage())
        except Exception:  # noqa: BLE001 — un registro raro no rompe la prueba
            self.lineas.append(str(record.msg))


@contextmanager
def registros():
    """Todo lo que Odoo escribe en sus registros (en cualquier nivel) mientras dura el bloque."""
    captura = _Captura()
    raiz = logging.getLogger()
    nivel = raiz.level
    raiz.addHandler(captura)
    raiz.setLevel(logging.DEBUG)
    try:
        yield captura.lineas
    finally:
        raiz.removeHandler(captura)
        raiz.setLevel(nivel)


@tagged('post_install', '-at_install')
class TestVozBrian(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.interno = new_test_user(cls.env, login='voz_brian_interno', name='Interno Voz', groups='base.group_user')
        cls.portal = new_test_user(cls.env, login='voz_brian_portal', name='Portal Voz', groups='base.group_portal')
        cls.publico = cls.env.ref('base.public_user')
        cls.Voz = cls.registry['dcasa.brian.voz']

    def contar(self):
        """Cuántos registros hay de todo lo que podría guardar un audio o su texto."""
        modelos = ['ir.attachment', 'brian.conversacion', 'brian.mensaje', 'brian.accion', 'mail.message']
        return {m: self.env[m].sudo().with_context(active_test=False).search_count([]) for m in modelos}

    def test_un_usuario_interno_recibe_solo_el_texto_y_nada_queda_guardado(self):
        antes = self.contar()
        audio = b64(WEBM)
        respuesta = {'ok': True, 'texto': f'  {DICHO}\n', 'recortado': False}
        with patch.object(self.Voz, '_pedir_al_worker', return_value=respuesta) as worker, registros() as lineas:
            r = self.env['dcasa.brian.voz'].with_user(self.interno).transcribir(audio, 'audio/webm;codecs=opus', 4200)
        self.assertEqual(r, {'ok': True, 'texto': DICHO, 'recortado': False})
        worker.assert_called_once_with(audio, 'audio/webm;codecs=opus', 4200)
        self.assertEqual(self.contar(), antes, 'Una nota de voz no debe dejar ningún registro en Odoo')
        todo = '\n'.join(lineas)
        for prohibido in (audio[:40], DICHO, 'cotizaciones'):
            self.assertNotIn(prohibido, todo)

    def test_el_portal_y_el_publico_no_pueden(self):
        with patch.object(self.Voz, '_pedir_al_worker') as worker:
            for usuario in (self.portal, self.publico):
                with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                    self.env['dcasa.brian.voz'].with_user(usuario).transcribir(b64(WEBM), 'audio/webm')
                with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                    self.env['dcasa.brian.voz'].with_user(usuario).disponible()
        worker.assert_not_called()

    def test_no_se_llama_por_rpc_directo(self):
        """La única puerta es el controlador: ``transcribir`` y ``disponible`` son privados (call_kw no los ve)."""
        llamadas = (('transcribir', [b64(WEBM), 'audio/webm']), ('disponible', []),
                    ('_pedir_al_worker', ['x', 'audio/webm', None]))
        for metodo, args in llamadas:
            with self.subTest(metodo=metodo), self.assertRaises(AccessError):
                call_kw(self.env(user=self.interno)['dcasa.brian.voz'], metodo, args, {})

    def test_reglas_de_la_nota_sin_llamar_al_worker(self):
        casos = [
            (b64(WEBM), 'audio/wav', None, 'tipo'),
            (b64(WEBM), 'audio/webm; codecs=opus; x=1', None, 'tipo'),
            (b64(WEBM), 'audio/webm;<script>', None, 'tipo'),
            ('', 'audio/webm', None, 'audio'),
            (None, 'audio/webm', None, 'audio'),
            ('esto no es base64!!', 'audio/webm', None, 'audio'),
            (b64(OGG), 'audio/webm', None, 'audio'),
            (b64(b'<html>hola</html>'), 'audio/mp4', None, 'audio'),
            (b64(WEBM[:4] + b'\x00' * (MAX_BYTES + 10)), 'audio/webm', None, 'muy_pesada'),
            (b64(WEBM), 'audio/webm', 70_000, 'muy_larga'),
            (b64(WEBM), 'audio/webm', -1, 'audio'),
            (b64(WEBM), 'audio/webm', '1000', 'audio'),
        ]
        with patch.object(self.Voz, '_pedir_al_worker') as worker:
            for audio, mime, duracion, causa in casos:
                with self.subTest(mime=mime, causa=causa):
                    r = self.env['dcasa.brian.voz'].with_user(self.interno).transcribir(audio, mime, duracion)
                    self.assertEqual(r, {'ok': False, 'causa': causa, 'error': TEXTOS[causa]})
        worker.assert_not_called()

    def test_ogg_y_mp4_tambien(self):
        with patch.object(self.Voz, '_pedir_al_worker', return_value={'ok': True, 'texto': 'hola', 'recortado': False}):
            for audio, mime in ((OGG, 'audio/ogg;codecs=opus'), (MP4, 'audio/mp4')):
                with self.subTest(mime=mime):
                    voz = self.env['dcasa.brian.voz'].with_user(self.interno)
                    self.assertTrue(voz.transcribir(b64(audio), mime)['ok'])

    def test_lo_que_dice_el_worker_se_traduce_a_palabras_sencillas(self):
        for causa in ('tope_usuario', 'tope_mes', 'no_se_entendio', 'no_disponible', 'tardo'):
            with self.subTest(causa=causa), \
                    patch.object(self.Voz, '_pedir_al_worker', return_value={'ok': False, 'causa': causa}):
                r = self.env['dcasa.brian.voz'].with_user(self.interno).transcribir(b64(WEBM), 'audio/webm')
                self.assertEqual(r, {'ok': False, 'causa': causa, 'error': TEXTOS[causa]})
        # Una causa desconocida, o un «ok» sin texto: el fallo genérico (nunca el texto técnico del Worker).
        raras = ({'ok': False, 'causa': 'algo raro', 'error': 'Traceback…'}, {'ok': True}, {'ok': True, 'texto': '  '},
                 None)
        for respuesta in raras:
            with self.subTest(respuesta=respuesta), patch.object(self.Voz, '_pedir_al_worker', return_value=respuesta):
                r = self.env['dcasa.brian.voz'].with_user(self.interno).transcribir(b64(WEBM), 'audio/webm')
                self.assertFalse(r['ok'])
                self.assertNotIn('Traceback', r['error'])

    def test_el_texto_llega_limpio_y_con_tope(self):
        largo = 'cama ' * 600
        voz = self.env['dcasa.brian.voz'].with_user(self.interno)
        sucio = {'ok': True, 'texto': 'hola\x00 \x1b[31m mundo', 'recortado': False}
        with patch.object(self.Voz, '_pedir_al_worker', return_value=sucio):
            self.assertEqual(voz.transcribir(b64(WEBM), 'audio/webm')['texto'], 'hola [31m mundo')
        with patch.object(self.Voz, '_pedir_al_worker', return_value={'ok': True, 'texto': largo, 'recortado': False}):
            r = self.env['dcasa.brian.voz'].with_user(self.interno).transcribir(b64(WEBM), 'audio/webm')
            self.assertTrue(r['recortado'])
            self.assertLessEqual(len(r['texto']), 2000)

    def test_el_estado_del_panel_dice_si_hay_microfono(self):
        Conversacion = self.env['brian.conversacion'].with_user(self.interno)
        with patch.object(self.Voz, '_disponible', return_value=False):
            self.assertIs(Conversacion.estado_proveedor()['voz'], False)
        with patch.object(self.Voz, '_disponible', return_value=True):
            self.assertIs(Conversacion.estado_proveedor()['voz'], True)


@tagged('post_install', '-at_install')
class TestVozBrianHttp(HttpCase):
    """La puerta de verdad: ``POST /dcasa/brian/v1/voz`` con la sesión de cada quien."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.interno = new_test_user(cls.env, login='voz_http_interno', password='voz_http_interno', name='Interno',
                                    groups='base.group_user')
        cls.portal = new_test_user(cls.env, login='voz_http_portal', password='voz_http_portal', name='Portal',
                                   groups='base.group_portal')
        cls.Voz = cls.registry['dcasa.brian.voz']

    def llamar(self, params, cuerpo=None):
        datos = cuerpo
        if datos is None:
            datos = json.dumps({'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': params})
        return self.url_open('/dcasa/brian/v1/voz', data=datos, headers={'Content-Type': 'application/json'})

    def test_interno_si_portal_y_publico_no(self):
        params = {'audio': b64(WEBM), 'mime': 'audio/webm;codecs=opus', 'duracion_ms': 3000}
        bien = {'ok': True, 'texto': DICHO, 'recortado': False}
        with patch.object(self.Voz, '_pedir_al_worker', return_value=bien) as worker:
            # Sin sesión (público): la sesión venció, sin texto.
            r = self.llamar(params).json()
            self.assertNotIn('result', r)
            self.assertEqual(r['error']['data']['name'], 'odoo.http.SessionExpiredException')
            # Portal: prohibido.
            self.authenticate('voz_http_portal', 'voz_http_portal')
            r = self.llamar(params).json()
            self.assertNotIn('result', r)
            self.assertEqual(r['error']['data']['name'], 'odoo.exceptions.AccessError')
            worker.assert_not_called()
            # Interno: solo el texto.
            self.authenticate('voz_http_interno', 'voz_http_interno')
            r = self.llamar(params).json()
            self.assertEqual(r['result'], {'ok': True, 'texto': DICHO, 'recortado': False})
            worker.assert_called_once()

    def test_un_cuerpo_mas_grande_que_el_tope_no_se_lee(self):
        self.authenticate('voz_http_interno', 'voz_http_interno')
        with patch.object(self.Voz, '_pedir_al_worker') as worker:
            enorme = json.dumps({'jsonrpc': '2.0', 'method': 'call', 'id': 1,
                                 'params': {'audio': 'A' * (MAX_CUERPO + 10), 'mime': 'audio/webm'}})
            respuesta = self.llamar(None, cuerpo=enorme)
            # Si la ruta corta la lectura: 413 o un error de JSON-RPC. Si no, el modelo la rechaza sin llamar al Worker.
            if respuesta.status_code != 413:
                cuerpo = respuesta.json()
                self.assertTrue('error' in cuerpo or cuerpo['result'] == {
                    'ok': False, 'causa': 'muy_pesada', 'error': TEXTOS['muy_pesada']}, cuerpo)
        worker.assert_not_called()

    def test_solo_post(self):
        self.authenticate('voz_http_interno', 'voz_http_interno')
        self.assertIn(self.url_open('/dcasa/brian/v1/voz').status_code, (404, 405))

    def test_si_el_panel_se_cierra_mientras_pide_permiso_el_microfono_no_queda_encendido(self):
        """Revisión adversarial (2026-11-16): si la pantalla se cerraba mientras el navegador pedía el permiso del
        micrófono, el flujo llegaba DESPUÉS de cancelar y se quedaba grabando para siempre, con la lucecita del
        micrófono encendida y sin nadie que la apagara."""
        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian.proveedor', 'prueba')
        codigo = ESPERAR + """
(async () => {
    // El permiso tarda: así da tiempo a cerrar el panel antes de que llegue el micrófono.
    let pistasApagadas = 0;
    let entregado = false;
    navigator.mediaDevices.getUserMedia = async () => {
        await new Promise((ok) => setTimeout(ok, 1200));
        const ctx = new AudioContext();
        const tono = ctx.createOscillator();
        const destino = ctx.createMediaStreamDestination();
        tono.connect(destino);
        tono.start();
        destino.stream.getTracks().forEach((p) => {
            const parar = p.stop.bind(p);
            p.stop = () => { pistasApagadas++; parar(); };
        });
        entregado = true;
        return destino.stream;
    };
    await esperar(() => document.querySelector(".o_brian_lanzador"), "el botón flotante");
    document.querySelector(".o_brian_lanzador").click();
    const panel = await esperar(() => document.querySelector(".o_brian_panel.o_brian_visible"), "el panel");
    const mic = await esperar(() => panel.querySelector(".o_brian_microfono"), "el botón del micrófono");
    mic.click();
    // Se cierra la pantalla ANTES de que el navegador entregue el micrófono.
    if (entregado) { throw new Error("Brian: el permiso llegó demasiado rápido para esta prueba"); }
    panel.querySelector(".o_brian_cerrar").click();
    await esperar(() => !document.querySelector(".o_brian_panel.o_brian_visible"), "el panel cerrado");
    await esperar(() => entregado, "el micrófono entregado por el navegador", 8000);
    await esperar(() => pistasApagadas > 0, "el micrófono apagado al llegar tarde");
    if (document.querySelector(".o_brian_grabando_punto_activo")) {
        throw new Error("Brian: se quedó grabando con el panel cerrado");
    }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""
        with patch.object(self.Voz, '_disponible', return_value=True), \
                patch.object(self.Voz, '_pedir_al_worker') as worker:
            self.browser_js('/odoo', codigo, ready="odoo.isReady", login='admin', timeout=120)
        worker.assert_not_called()

    def test_microfono_en_el_navegador(self):
        """El micrófono (con una voz de mentira: un tono del propio navegador), el tiempo a la vista, Esc cancela sin
        mandar nada, «Listo» pasa la nota a texto y el texto queda en la caja para revisarlo. Nada queda guardado."""
        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian.proveedor', 'prueba')
        # Los paquetes de la interfaz también son adjuntos (se generan al abrir la página): se cuentan solo los de
        # audio y los de Brian.
        de_audio = ['|', ('mimetype', '=like', 'audio/%'), ('res_model', '=like', 'brian.%')]
        antes = self.env['ir.attachment'].sudo().search_count(de_audio)
        mensajes = self.env['brian.mensaje'].sudo().search_count([])
        llamadas = []

        def worker(audio, mime, duracion):
            llamadas.append((len(audio), mime, duracion))
            return {'ok': True, 'texto': DICHO, 'recortado': False}

        codigo = ESPERAR + """
(async () => {
    // Una voz de mentira: un tono del propio navegador en lugar del micrófono (MediaRecorder es el de verdad).
    let pistasApagadas = 0;
    navigator.mediaDevices.getUserMedia = async () => {
        const ctx = new AudioContext();
        const tono = ctx.createOscillator();
        const destino = ctx.createMediaStreamDestination();
        tono.connect(destino);
        tono.start();
        destino.stream.getTracks().forEach((p) => {
            const parar = p.stop.bind(p);
            p.stop = () => { pistasApagadas++; parar(); };
        });
        return destino.stream;
    };
    await esperar(() => document.querySelector(".o_brian_lanzador"), "el botón flotante");
    document.querySelector(".o_brian_lanzador").click();
    const panel = await esperar(() => document.querySelector(".o_brian_panel.o_brian_visible"), "el panel");
    const mic = await esperar(() => panel.querySelector(".o_brian_microfono"), "el botón del micrófono");
    if (!/nota de voz/i.test(mic.getAttribute("aria-label") || "")) {
        throw new Error("Brian: el micrófono sin nombre");
    }

    // 1. Grabar y cancelar con Esc: no se manda nada y el micrófono se apaga.
    mic.click();
    await esperar(() => panel.querySelector(".o_brian_grabando_punto_activo"), "la grabación en curso");
    if (!panel.querySelector(".o_brian_voz_nota")?.textContent.includes("el audio no se guarda")) {
        throw new Error("Brian: falta el aviso de que el audio no se guarda");
    }
    document.activeElement.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await esperar(() => panel.querySelector(".o_brian_texto"), "la caja de texto de vuelta");
    if (!document.querySelector(".o_brian_panel.o_brian_visible")) {
        throw new Error("Brian: Esc cerró el panel en vez de cancelar");
    }
    await esperar(() => pistasApagadas > 0, "el micrófono apagado al cancelar");

    // 2. Grabar, ver el tiempo y «Listo»: el texto queda en la caja, sin enviarse.
    pistasApagadas = 0;
    panel.querySelector(".o_brian_microfono").click();
    await esperar(() => panel.querySelector(".o_brian_grabando_tiempo")?.textContent.startsWith("0:01"),
        "el tiempo corriendo", 8000);
    const listo = panel.querySelector(".o_brian_voz_listo");
    await esperar(() => document.activeElement === listo, "el foco en «Listo» al grabar");
    listo.click();
    const caja = await esperar(() => {
        const t = panel.querySelector(".o_brian_texto");
        return t && t.value.includes("cotizaciones") && t;
    }, "el texto de la nota en la caja");
    if (panel.querySelector(".o_brian_burbuja_usuario")) { throw new Error("Brian: la nota no debe enviarse sola"); }
    await esperar(() => document.activeElement === caja, "el foco de vuelta en la caja para revisar");
    if (!/revisa el texto/i.test(panel.querySelector(".o_brian_voz_anuncio")?.textContent || "")) {
        throw new Error("Brian: el lector de pantalla no oyó que la nota quedó lista");
    }
    if (!pistasApagadas) { throw new Error("Brian: el micrófono siguió encendido"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""
        with patch.object(self.Voz, '_disponible', return_value=True), \
                patch.object(self.Voz, '_pedir_al_worker', side_effect=worker):
            self.browser_js('/odoo', codigo, ready="odoo.isReady", login='admin', timeout=120)
        self.assertEqual(len(llamadas), 1, 'Se canceló una nota y se mandó la otra')
        largo, mime, duracion = llamadas[0]
        self.assertGreater(largo, 0)
        self.assertTrue(mime.startswith('audio/webm'), mime)
        self.assertGreaterEqual(duracion, 1000)
        self.assertEqual(self.env['ir.attachment'].sudo().search_count(de_audio), antes)
        self.assertEqual(self.env['brian.mensaje'].sudo().search_count([]), mensajes)
