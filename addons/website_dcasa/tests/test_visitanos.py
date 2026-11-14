"""Lote 2 de la web: el horario en Visítanos (y en el pie) y el mapa de Google solo con permiso.

* El horario sale de un solo lugar: `website._dcasa_horario_tienda()`. Aquí devuelve [] (sin fuente no se inventa);
  dcasa_conversaciones lo llena con el horario de Ajustes de Juan (sus pruebas en test_horario_sitio.py).
* El mapa: la página trae un recuadro con «Ver el mapa». El <iframe> de Google se pone en el navegador si quien visita
  ya aceptó las cookies opcionales, si las acepta luego o si toca el botón. Sin eso, el navegador no le pide nada a
  Google (se mira con `fetch_proxy`, por donde pasa toda petición externa del Chrome de las pruebas).
"""
from lxml import html as lxml_html

from odoo import Command
from odoo.addons.website_dcasa.models.horario_tienda import filas_horario, hora_amable
from odoo.tests import HttpCase, TransactionCase, tagged

TODOS = frozenset(range(7))

FILAS = [
    {'dias': 'Lunes a sábado', 'horas': '9:00 a. m. a 6:00 p. m.', 'corto': 'Lun. a sáb. 9:00 a. m. a 6:00 p. m.'},
    {'dias': 'Domingo', 'horas': '9:00 a. m. a 5:00 p. m.', 'corto': 'Dom. 9:00 a. m. a 5:00 p. m.'},
]


@tagged('post_install', '-at_install')
class TestFilasHorario(TransactionCase):

    def test_hora_amable(self):
        self.assertEqual(hora_amable(9.0), '9:00 a. m.')
        self.assertEqual(hora_amable(18.0), '6:00 p. m.')
        self.assertEqual(hora_amable(12.0), '12:00 p. m.')
        self.assertEqual(hora_amable(0.0), '12:00 a. m.')
        self.assertEqual(hora_amable(8.5), '8:30 a. m.')
        self.assertEqual(hora_amable(17.75), '5:45 p. m.')

    def test_horario_de_la_tienda(self):
        """El horario que dio la dueña: lunes a sábado 9 a 6 y domingo 9 a 5."""
        self.assertEqual(filas_horario(9.0, 18.0, TODOS, fin_domingo=17.0), FILAS)

    def test_domingo_sin_cierre_propio_junta_la_semana(self):
        self.assertEqual(filas_horario(9.0, 18.0, TODOS), [
            {'dias': 'Lunes a domingo', 'horas': '9:00 a. m. a 6:00 p. m.',
             'corto': 'Lun. a dom. 9:00 a. m. a 6:00 p. m.'},
        ])

    def test_dias_cerrados(self):
        filas = filas_horario(8.0, 17.0, frozenset({1, 2, 3, 4, 5}))
        self.assertEqual(filas[0]['dias'], 'Lunes a viernes')
        self.assertEqual(filas[1], {'dias': 'Sábado y domingo', 'horas': 'Cerrado',
                                    'corto': 'Sáb. y dom. cerrado'})

    def test_sin_dias_o_sin_horas_no_hay_tabla(self):
        self.assertEqual(filas_horario(9.0, 18.0, frozenset()), [])
        self.assertEqual(filas_horario(18.0, 9.0, TODOS), [], 'Un horario al revés no se publica')

    def test_sin_fuente_no_se_inventa(self):
        """website_dcasa solo no sabe el horario: el gancho devuelve [] hasta que otro módulo lo llene."""
        Website = self.env.registry['website']
        base = next(c for c in Website.__mro__ if c.__module__ == 'odoo.addons.website_dcasa.models.horario_tienda')
        self.assertEqual(base._dcasa_horario_tienda(self.env['website'].get_current_website()), [])


@tagged('post_install', '-at_install')
class TestVisitanosHorario(HttpCase):

    def _con_horario(self, filas):
        self.patch(self.env.registry['website'], '_dcasa_horario_tienda', lambda website: filas)

    def test_tabla_en_visitanos_y_linea_en_el_pie(self):
        self._con_horario(FILAS)
        html = self.url_open('/visitanos').text
        self.assertIn('class="o_dcasa_horario"', html)
        self.assertRegex(html, r'<th scope="row">Lunes a sábado</th>\s*<td>9:00 a\. m\. a 6:00 p\. m\.</td>')
        self.assertRegex(html, r'<th scope="row">Domingo</th>\s*<td>9:00 a\. m\. a 5:00 p\. m\.</td>')
        fila = r'<span class="o_dcasa_pie_horario_fila">%s</span>'
        self.assertRegex(html, fila % r'Lun\. a sáb\. 9:00 a\. m\. a 6:00 p\. m\.' + r'\s*'
                         + fila % r'Dom\. 9:00 a\. m\. a 5:00 p\. m\.', 'Pie')
        self.assertNotIn('feriado', html.lower(), 'No se inventan feriados')
        # el pie es el mismo en todo el sitio
        self.assertIn('Lun. a sáb. 9:00 a. m. a 6:00 p. m.', self.url_open('/').text)

    def test_sin_horario_no_hay_tabla_ni_linea(self):
        self._con_horario([])
        html = self.url_open('/visitanos').text
        self.assertNotIn('o_dcasa_horario', html)
        self.assertNotIn('o_dcasa_pie_horario', html)
        self.assertIn('el horario', html, '«Antes de venir» sigue invitando a preguntar el horario')

    def test_editor_del_sitio_abre_visitanos_con_horario(self):
        """Con la marca del editor (data-oe-*) la página sigue armándose: lección del lote 1."""
        self._con_horario(FILAS)
        self.authenticate('admin', 'admin')
        respuesta = self.url_open('/visitanos')
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('Lunes a sábado', respuesta.text)


INICIO = """
    (async () => {
        const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
        const falla = (motivo) => console.error(motivo);
        const EMBED = 'https://www.google.com/maps/embed?';
        for (let i = 0; i < 200 && document.body.getAttribute('is-ready') !== 'true'; i++) { await esperar(50); }
        const caja = document.querySelector('[data-dcasa-mapa]');
"""
FIN = """
        console.log('test successful');
    })();
"""

MAPA_SIN_TOCAR = INICIO + """
        await esperar(800);
        if (!caja || !caja.querySelector('.o_dcasa_mapa_ver')) { return falla('Falta el recuadro «Ver el mapa»'); }
        if (document.querySelector('iframe[src*="google.com/maps"]')) { return falla('El mapa cargó sin permiso'); }
""" + FIN

MAPA_AL_TOCAR = INICIO + """
        await esperar(300);
        if (caja.querySelector('iframe')) { return falla('El mapa cargó antes de tocar'); }
        caja.querySelector('.o_dcasa_mapa_ver').click();
        await esperar(300);
        const mapa = caja.querySelector('iframe');
        if (!mapa || !mapa.src.startsWith(EMBED)) { return falla('No cargó el mapa'); }
        if (!mapa.title.includes('CASA en La Chorrera')) { return falla('El mapa no tiene título'); }
        if (!caja.classList.contains('o_dcasa_mapa_cargado')) { return falla('El recuadro sigue a la vista'); }
        caja.querySelector('.o_dcasa_mapa_ver').click();
        if (caja.querySelectorAll('iframe').length !== 1) { return falla('Dos mapas'); }
""" + FIN

MAPA_SOLO = INICIO + """
        let mapa = null;
        for (let i = 0; i < 100 && !(mapa = caja.querySelector('iframe')); i++) { await esperar(50); }
        if (!mapa || !mapa.src.startsWith(EMBED)) { return falla('No cargó solo con las cookies aceptadas'); }
""" + FIN

MAPA_ACEPTA_DESPUES = INICIO + """
        await esperar(300);
        if (caja.querySelector('iframe')) { return falla('Cargó sin permiso'); }
        document.dispatchEvent(new Event('optionalCookiesAccepted'));  // lo que hace el aviso de Odoo al aceptar
        await esperar(300);
        if (!caja.querySelector('iframe')) { return falla('No cargó al aceptar en el aviso'); }
""" + FIN

ACEPTA_TODO = '{"required": true, "optional": true, "ts": 1790000000000}'
SOLO_NECESARIAS = '{"required": true, "optional": false, "ts": 1790000000000}'


@tagged('post_install', '-at_install')
class TestVisitanosMapa(HttpCase):

    def setUp(self):
        super().setUp()
        self.externas = []

    def fetch_proxy(self, url):
        self.externas.append(url)
        return super().fetch_proxy(url)

    def _pidio_a_google_maps(self):
        return any(url.startswith('https://www.google.com/maps') for url in self.externas)

    def test_sin_permiso_no_carga_el_mapa(self):
        self.browser_js('/visitanos', MAPA_SIN_TOCAR, timeout=90)
        self.assertFalse(self._pidio_a_google_maps(), self.externas)

    def test_solo_necesarias_no_carga_el_mapa(self):
        self.browser_js('/visitanos', MAPA_SIN_TOCAR, timeout=90, cookies={'website_cookies_bar': SOLO_NECESARIAS})
        self.assertFalse(self._pidio_a_google_maps(), self.externas)

    def test_ver_el_mapa_lo_carga(self):
        self.browser_js('/visitanos', MAPA_AL_TOCAR, timeout=90)

    def test_con_cookies_aceptadas_carga_solo(self):
        self.browser_js('/visitanos', MAPA_SOLO, timeout=90, cookies={'website_cookies_bar': ACEPTA_TODO})

    def test_al_aceptar_en_el_aviso_carga(self):
        self.browser_js('/visitanos', MAPA_ACEPTA_DESPUES, timeout=90)

    def test_portada_no_trae_mapa(self):
        html = self.url_open('/').text
        self.assertNotIn('data-dcasa-mapa=', html)
        self.assertNotIn('google.com/maps/embed', html)


OTRO_HORARIO = [{'dias': 'Lunes a viernes', 'horas': '10:00 a. m. a 7:00 p. m.',
                 'corto': 'Lun. a vie. 10:00 a. m. a 7:00 p. m.'}]


def _es_guardable(el):
    """Lo que el editor del sitio guarda al salir (html_builder, save_plugin.js: «savable_selectors»): una zona
    .oe_structure de una vista o un elemento con las marcas del editor (``data-oe-field``: lo estático de una vista)."""
    clases = (el.get('class') or '').split()
    return bool(('oe_structure' in clases and el.get('data-oe-id') and el.get('data-oe-xpath'))
                or el.get('data-oe-field'))


def _guardable(el):
    """La zona que el editor guardaría con ``el`` dentro (el mismo, un ancestro o un descendiente), o None."""
    for candidato in (*el.iterancestors(), el, *el.iterdescendants()):
        if isinstance(candidato.tag, str) and _es_guardable(candidato):
            return candidato
    return None


@tagged('post_install', '-at_install')
class TestHorarioYElEditor(HttpCase):
    """El pie lo puede editar quien tiene el constructor del sitio. Al guardar, el editor manda el HTML ya dibujado de
    la zona editable y Odoo lo escribe tal cual en la vista (``ir.ui.view.save``): lo que se dibuja dentro (un
    ``t-out``) queda como texto fijo. El horario no puede quedar en una zona así: si no, un cambio en los Ajustes de
    Juan ya no se vería."""

    def setUp(self):
        super().setUp()
        self.website = self.env.ref('website.default_website')
        self.horario = FILAS
        self.patch(self.env.registry['website'], '_dcasa_horario_tienda', lambda website: self.horario)
        # Alguien con el constructor del sitio. En D'CASA nadie lo tiene (dcasa_interfaz se lo quita a todos y frena
        # el guardado de las vistas propias), salvo con el escape documentado: aquí se simula ese caso.
        self.env.ref('base.user_admin').group_ids = [Command.link(self.env.ref('website.group_website_designer').id)]
        self.env['ir.config_parameter'].sudo().set_param('dcasa_interfaz.sitio_editable', '1')

    def _como_editor(self, ruta):
        self.authenticate('admin', 'admin')
        html = self.url_open(ruta).text
        self.authenticate(None, None)
        return lxml_html.fromstring(html)

    def test_el_horario_no_queda_en_una_zona_que_el_editor_guarda(self):
        raiz = self._como_editor('/')
        (pie,) = raiz.xpath('//div[@id="footer"]')
        self.assertIsNotNone(_guardable(pie), 'El pie sí es una zona que el editor guarda')
        lineas = raiz.xpath('//*[contains(concat(" ", @class, " "), " o_dcasa_pie_horario ")]')
        self.assertTrue(lineas, 'El horario sale en el pie')
        for linea in lineas:
            self.assertIsNone(_guardable(linea), 'El horario quedaría congelado al guardar con el editor')
        visita = self._como_editor('/visitanos')
        for selector in ('o_dcasa_visita_horario', 'o_dcasa_mapa', 'o_dcasa_pie_horario'):
            (el,) = visita.xpath(f'//*[contains(concat(" ", @class, " "), " {selector} ")]')
            self.assertIsNone(_guardable(el), f'{selector} de Visítanos no está en una zona que el editor guarda')

    def test_guardar_el_pie_con_el_editor_no_congela_el_horario(self):
        """Como el editor: abre la página, cambia un texto del pie y guarda (``save`` con el HTML dibujado de la zona y
        su xpath, en el contexto del sitio). Luego cambia el horario: el pie enseña el nuevo."""
        raiz = self._como_editor('/')
        (pie,) = raiz.xpath('//div[@id="footer"]')
        (parrafo,) = pie.xpath('.//p[contains(., "Tu casa, bien amueblada")]')
        parrafo.text = parrafo.text.replace('Tu casa, bien amueblada.', 'Tu casa, bien amueblada (editado).')
        vista = self.env['ir.ui.view'].browse(int(pie.get('data-oe-id')))
        vista.with_user(self.env.ref('base.user_admin')).with_context(website_id=self.website.id).save(
            lxml_html.tostring(pie, encoding='unicode'), pie.get('data-oe-xpath'))

        html = self.url_open('/').text
        self.assertIn('Tu casa, bien amueblada (editado).', html, 'El cambio del editor quedó guardado')
        self.assertIn('Lun. a sáb. 9:00 a. m. a 6:00 p. m.', html)
        self.horario = OTRO_HORARIO   # como cambiar el horario en los Ajustes de Juan
        html = self.url_open('/').text
        self.assertIn('Lun. a vie. 10:00 a. m. a 7:00 p. m.', html, 'El pie enseña el horario nuevo')
        self.assertNotIn('Lun. a sáb. 9:00 a. m. a 6:00 p. m.', html, 'Y ya no el viejo, congelado en el pie')
        copia = self.env['ir.ui.view'].search([('key', '=', vista.key), ('website_id', '=', self.website.id)])
        self.assertTrue(copia, 'El editor guardó su copia del pie para el sitio')
        self.assertNotIn('a. m.', copia.arch, 'En la vista guardada no quedó ningún horario escrito')
