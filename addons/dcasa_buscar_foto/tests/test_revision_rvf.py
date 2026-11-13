"""Revisión adversarial (rvf) de «Busca con una foto»: cada prueba de aquí FALLABA con el código revisado y describe el
escenario que lo rompía. Se adaptaron a lo que se decidió (B1, I1, I2, I3, M1, M2); las carreras con transacciones de
verdad las comprueba ``scripts/revision_rvf_carrera_foto.py`` (aquí la prueba corre dentro de una sola transacción)."""
import base64
import hashlib
import hmac
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.website_dcasa.tests.chrome_movil import ChromeMovilCase
from odoo.tests import TransactionCase, tagged
from odoo.tests.test_cursor import TestCursor

from ..models import buscar_foto as B

FOTO = base64.b64encode(b'\xff\xd8\xff\xe0' + b'foto de prueba' * 4 + b'\xff\xd9').decode()


@tagged('post_install', '-at_install')
class TestRevisionRvf(TransactionCase):

    def setUp(self):
        super().setUp()
        # La reserva del cupo abre su propia transacción (registry.cursor()): en la prueba, dentro de la de la prueba.
        self.registry_enter_test_mode()
        self.env['dcasa.buscar.foto.uso'].sudo().search([]).unlink()
        param = self.env['ir.config_parameter'].sudo()
        param.set_param(B.PARAM_ACTIVO, 'True')
        param.set_param(B.PARAM_TOPES['visitante'], '100')
        param.set_param(B.PARAM_TOPES['conexion'], '2')
        param.set_param(B.PARAM_TOPES['dia'], '1000')
        # La reserva lee los topes desde su propio cursor: lo de aquí tiene que estar escrito en la base (no solo en
        # la memoria de este entorno), si no lee lo de antes y lo guarda en la caché de get_param.
        self.env.flush_all()
        self.Foto = self.env['dcasa.buscar.foto']
        self.website = self.env.ref('website.default_website')

    # ------------------------------------------------------------------
    # 1. IPv6: cambiar de dirección dentro de la MISMA red /64 (lo que recibe un solo cliente) daba topes nuevos
    # ------------------------------------------------------------------

    def test_ipv6_de_la_misma_red_cuenta_como_una_sola_conexion(self):
        """Con tope por conexión 2: tres búsquedas desde 2001:db8:1:2::1, ::2 y ::3 (misma /64, sesiones nuevas,
        como hace un script) cortan la tercera."""
        with patch.object(type(self.Foto), '_dcasa_leer', lambda self_, datos, mime: None):
            estados = [self.Foto._dcasa_buscar(FOTO, self.website, sesion=f'sesion-{n}',
                                               conexion=f'2001:db8:1:2::{n}')['estado'] for n in (1, 2, 3)]
            # Otra /64 es otra conexión.
            estados.append(self.Foto._dcasa_buscar(FOTO, self.website, sesion='otra', conexion='2001:db8:1:3::1')[
                'estado'])
        self.assertEqual(estados, ['otra', 'otra', 'no_ahora', 'otra'],
                         'Una IPv6 cuenta por su red /64 (como dcasa_envios/controllers/choferes.py, llave_ip)')

    # ------------------------------------------------------------------
    # 2. «Nunca se confía en lo que llega»: una lectura con tipos raros reventaba (y el fallo NO contaba para el tope)
    # ------------------------------------------------------------------

    def test_una_lectura_con_tipos_raros_no_revienta(self):
        for raro in ({'tipo': 'producto', 'codigos': [], 'categoria': ['cama'], 'medida': None,
                      'parece_pago': False, 'parece_identidad': False},
                     {'tipo': 'producto', 'codigos': [], 'categoria': 'cama', 'medida': {'queen': 1},
                      'parece_pago': False, 'parece_identidad': False}):
            with self.subTest(raro=raro):
                try:
                    B.normalizar_lectura(raro)
                except TypeError as error:
                    self.fail(f'normalizar_lectura revienta con {raro!r}: {error}')

    def test_si_la_busqueda_revienta_despues_de_la_ia_igual_cuenta_para_el_tope(self):
        """La fila del cupo se escribe y se CONFIRMA en una transacción corta aparte, antes de llamar al Worker: si algo
        revienta después de la IA, esa búsqueda —que sí gastó IA— queda contada. (Que la fila sobrevive a que se
        deshaga la transacción de la petición lo comprueba el escenario C de scripts/revision_rvf_carrera_foto.py.)"""
        Cliente = type(self.env['dcasa.juan.cliente'])
        respuesta = {'conectado': True, 'error': None, 'cuerpo': {'ok': True, 'lectura': {
            'tipo': 'producto', 'codigos': [], 'categoria': ['cama'], 'medida': None,
            'parece_pago': False, 'parece_identidad': False}}}
        orden = []
        confirmar = TestCursor.commit

        def al_confirmar(cursor):
            orden.append('confirma')
            return confirmar(cursor)

        def al_pedir(self_, *args, **kwargs):
            orden.append('worker')
            return respuesta

        def revienta(self_, website, lectura):
            raise RuntimeError('algo reventó después de la IA')

        # Sin assertRaises: el de Odoo deshace lo hecho dentro (un savepoint) y en la prueba la reserva vive en él.
        revento = False
        with patch.object(Cliente, '_pedir', al_pedir), patch.object(TestCursor, 'commit', al_confirmar), \
                patch.object(type(self.Foto), '_dcasa_parecidos', revienta):
            try:
                self.Foto._dcasa_buscar(FOTO, self.website, sesion='s', conexion='10.9.8.7')
            except RuntimeError:
                revento = True
        self.assertTrue(revento)
        self.assertEqual(orden[:2], ['confirma', 'worker'], 'El cupo se confirma antes de llamar al Worker')
        usos = self.env['dcasa.buscar.foto.uso'].sudo().search([])
        self.assertEqual(len(usos), 1, 'La búsqueda llegó a la IA y quedó contada')
        self.assertEqual(usos.resultado, 'no_ahora')

    # ------------------------------------------------------------------
    # 3. La «huella» de la conexión se revertía con el secreto que está en la misma base
    # ------------------------------------------------------------------

    def test_la_huella_de_la_conexion_no_se_revierte_con_el_secreto_de_la_base(self):
        """Antes: HMAC con database.secret (en la misma base y en cada respaldo) de la IP entera; probando direcciones
        salía la IP. Ahora: la red (/24 en IPv4) con una sal al azar del día que el cron borra a los dos días. Con el
        secreto de la base no sale nada; con la sal del día, a lo sumo la /24 (256 direcciones, la red del operador),
        nunca la IP; y sin la sal (al día siguiente) ya no se puede volver a calcular."""
        with patch.object(type(self.Foto), '_dcasa_leer', lambda self_, datos, mime: None):
            self.Foto._dcasa_buscar(FOTO, self.website, sesion='s', conexion='10.20.30.40')
        huella = self.env['dcasa.buscar.foto.uso'].sudo().search([], limit=1).huella_conexion
        self.assertTrue(huella)
        secreto = self.env['ir.config_parameter'].sudo().get_param('database.secret').encode()
        sal_hoy, _ayer = self.Foto._dcasa_sales()
        con_el_secreto = con_la_sal = None
        for a in range(256):
            for b in range(256):
                ip = f'10.20.{a}.{b}'
                if hmac.new(secreto, f'c:{ip}'.encode(), hashlib.sha256).hexdigest()[:32] == huella:
                    con_el_secreto = ip
                if B.huella(sal_hoy, 'c', ip) == huella:
                    con_la_sal = ip
        self.assertIsNone(con_el_secreto, f'La huella se revirtió con database.secret: era {con_el_secreto}')
        self.assertIsNone(con_la_sal, 'Con la sal del día tampoco sale la IP')
        self.assertEqual(B.huella(sal_hoy, 'c', '10.20.30.0/24'), huella, 'Lo más que dice es la red /24')
        # Pasado mañana la sal ya no está.
        pasado = fields.Datetime.now() + timedelta(days=2)
        with patch.object(fields.Datetime, 'now', lambda *a, **k: pasado):
            self.env['dcasa.buscar.foto.uso']._cron_limpiar()
        self.assertFalse(self.env['dcasa.buscar.foto.sal'].sudo().search([('valor', '=', sal_hoy)]))

    # ------------------------------------------------------------------
    # 4. Lo que cobra Cloudflare (el lector de imágenes) salía como «Por pagar a Meta» en Costos de IA
    # ------------------------------------------------------------------

    def test_lo_del_lector_de_cloudflare_no_queda_como_deuda_con_meta(self):
        """«Por pagar a Meta» (y el botón «Pagar», y «lo que cobró Meta − lo calculado») sale del gasto del mes del
        Worker. El Worker ya deja fuera de ese gasto lo de Workers AI (lo cobra Cloudflare) y lo manda aparte, en
        ``cloudflare``: aquí sale como su propio renglón, sin «respuestas», y no toca el saldo."""
        Cliente = type(self.env['dcasa.juan.cliente'])
        Panel = type(self.env['dcasa.juan.panel'])
        salud = {'conectado': True, 'error': None,
                 'cuerpo': {'ok': True, 'mes': '2026-11', 'gasto_ia_mes_usd': 9.0, 'tope_usd': 30}}
        costos = {'conectado': True, 'error': None, 'cuerpo': {
            'ok': True, 'gasto_usd': 9.0, 'turnos': 100, 'por_modelo': [
                {'modelo': 'muse-spark-de-prueba', 'usd': 9.0, 'turnos': 100, 'estimado': False}],
            'cloudflare': [{'concepto': 'cloudflare:lector-de-fotos', 'usd': 1.0, 'lecturas': 20, 'estimado': False}]}}
        with patch.object(Cliente, 'configurado', lambda s: True), \
                patch.object(Cliente, 'informe_de_salud', lambda s: salud), \
                patch.object(Cliente, 'costos', lambda s: costos), \
                patch.object(Panel, '_tomar_foto_de_costos', lambda s, informe=None: informe):
            datos = self.env['dcasa.juan.panel'].sudo()._datos_de_costos()
        self.assertEqual(datos['pagos']['saldo'], 9.0, '«Por pagar a Meta» no incluye el lector de fotos')
        self.assertEqual(datos['turnos'], 100, 'Las fotos no son respuestas de Juan')
        renglon = next(m for m in datos['por_modelo'] if m.get('aparte'))
        self.assertEqual((renglon['modelo'], renglon['usd'], renglon['lecturas'], renglon['turnos']),
                         ('Cloudflare: lector de fotos', 1.0, 20, 0))
        self.assertEqual(datos['cloudflare_usd'], 1.0)


# ----------------------------------------------------------------------
# 5. En el celular, la cámara le quitaba a la caja de búsqueda de /shop casi la mitad de su ancho
# ----------------------------------------------------------------------

MEDIR_CAJA = """
    (async () => {
        const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
        for (let i = 0; i < 100 && document.body.getAttribute('is-ready') !== 'true'; i++) { await esperar(50); }
        await esperar(300);
        const caja = document.querySelector('.o_wsale_products_searchbar_form input[name="search"]');
        const camara = document.querySelector('.o_wsale_products_searchbar_form .o_dcasa_foto_en_caja');
        if (!caja || !camara) { return {caja: -1}; }
        const c = camara.getBoundingClientRect();
        const medir = document.createElement('span');
        medir.style.cssText = 'position:absolute;visibility:hidden;white-space:pre;font:' + getComputedStyle(caja).font;
        medir.textContent = 'colchon queen';
        document.body.appendChild(medir);
        const texto = medir.getBoundingClientRect().width;
        const estilo = getComputedStyle(caja);
        const util = caja.clientWidth - parseFloat(estilo.paddingLeft) - parseFloat(estilo.paddingRight);
        return {caja: Math.round(util), texto: Math.round(texto), camara: Math.round(c.width),
                alto: Math.round(c.height), desborde: document.documentElement.scrollWidth - window.innerWidth};
    })()
"""


@tagged('post_install', '-at_install')
class TestRevisionRvfMovil(ChromeMovilCase):

    def test_la_caja_de_busqueda_de_la_tienda_sigue_usable_en_el_celular(self):
        """Medido en Chrome (teléfono emulado): con la cámara al lado la caja quedaba de 35 px a 360 y 55 px a 390.
        Ahora la cámara va dentro de la caja, que tiene su propia fila: a 360, 390 y 430 px se escribe cómodo (cabe
        «colchon queen»), la cámara mide 44 px de toque y nada se sale de la pantalla."""
        self.env['ir.config_parameter'].sudo().set_param(B.PARAM_ACTIVO, 'True')
        for ancho in (360, 390, 430):
            with self.subTest(ancho=ancho), self._chrome_movil(ancho) as browser:
                browser.navigate_to(self.base_url() + '/shop', wait_stop=True)
                self.assertTrue(browser._wait_ready(), '/shop no terminó de cargar')
                medida = self._evaluar(browser, MEDIR_CAJA)
                self.assertGreaterEqual(medida['caja'], 60, f'A {ancho} px la caja queda casi sin espacio: {medida}')
                self.assertGreaterEqual(medida['caja'], medida['texto'], f'A {ancho} px no cabe «colchon queen»')
                self.assertGreaterEqual(min(medida['camara'], medida['alto']), 44, f'Toque chico: {medida}')
                self.assertLessEqual(medida['desborde'], 0, f'A {ancho} px algo se sale de la pantalla: {medida}')
