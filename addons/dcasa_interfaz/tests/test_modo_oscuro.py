"""El modo oscuro del panel: lo enciende cada persona (cookie ``color_scheme``) y el claro no cambia.

Tres cosas se cuidan aquí:

* **El servidor** entrega la hoja oscura solo con la cookie exacta ``dark``; sin cookie o con cualquier otro valor,
  la clara.
* **Las hojas compilan** (un error de SCSS deja todo el panel sin estilos) y **nada oscuro entra en la hoja clara**:
  todo lo oscuro vive en ``static/src/oscuro/`` y solo se nombra en los paquetes ``*_dark`` del manifest.
* **En el navegador**: con la cookie, fondo oscuro y letra clara en el Inicio, una lista y un formulario; sin ella, como
  siempre; y el interruptor del menú de usuario guarda la cookie y recarga.
"""
import glob
import os
import re

from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tools import file_path

from .test_inicio_por_rol import ESPERAR_JS

CARPETA_OSCURA = 'dcasa_interfaz/static/src/oscuro'
HOJA_CLARA = 'web.assets_web'
HOJA_OSCURA = 'web.assets_web_dark'
HOJA_PEREZOSA_CLARA = 'web.assets_backend_lazy'
HOJA_PEREZOSA_OSCURA = 'web.assets_backend_lazy_dark'

# Luz de un color «rgb(…)» tal como la entrega el navegador (0 = negro, 1 = blanco) y un par de ayudas para las pruebas.
COLORES_JS = ESPERAR_JS + r"""
    const luz = (texto) => {
        const p = (texto.match(/rgba?\(([^)]+)\)/) || ['', '0,0,0'])[1].split(/[,\s/]+/).filter(Boolean).map(Number);
        const c = p.slice(0, 3).map((v) => {
            v /= 255;
            return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        });
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
    };
    const fondoDe = (el) => {
        for (let p = el; p; p = p.parentElement) {
            const c = getComputedStyle(p).backgroundColor;
            const alfa = (c.match(/rgba\([^)]*,\s*([\d.]+)\)/) || [])[1];
            if (c && c !== 'transparent' && (alfa === undefined || Number(alfa) > 0.5)) { return c; }
        }
        return 'rgb(255, 255, 255)';
    };
    const contraste = (el) => {
        const a = luz(getComputedStyle(el).color), b = luz(fondoDe(el));
        return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    };
    // «oscuro»: el fondo del elemento es oscuro, su letra es clara y entre los dos hay contraste de sobra.
    const pide = (selector, oscuro, que) => {
        const el = document.querySelector(selector);
        if (!el) { throw new Error('No está: ' + que); }
        const fondo = luz(fondoDe(el)), tinta = luz(getComputedStyle(el).color);
        const bien = oscuro ? (fondo < 0.08 && tinta > 0.5) : (fondo > 0.7 && tinta < 0.2);
        if (!bien || contraste(el) < 4.5) {
            throw new Error(`${que}: se esperaba ${oscuro ? 'oscuro' : 'claro'} y salió fondo ${fondoDe(el)} `
                + `con letra ${getComputedStyle(el).color} (contraste ${contraste(el).toFixed(2)})`);
        }
    };
    const hojas = () => [...document.querySelectorAll('link[rel="stylesheet"]')]
        .map((l) => l.getAttribute('href') || '');
"""


def rutas(env, paquete):
    return [ruta for ruta, *_resto in env['ir.asset']._get_asset_paths(paquete, {})]


# --- Lectura de una hoja ya compilada: pares fondo/letra de una misma regla -------------------------------------------
PROPIO = re.compile(r'\.o_(dcasa|dcj|dc_|brian|sofia|camila|de_|guia)')
COLORES = {'white': '#ffffff', 'black': '#000000'}


def color(valor, variables, hondo=0):
    """``#hex``, ``rgb()``, ``rgba()`` o ``var(--x, reserva)`` → (r, g, b, alfa); ``None`` si no es un color liso."""
    valor = valor.replace('!important', '').strip()
    if hondo > 8:
        return None
    var = re.match(r'var\(\s*(--[\w-]+)\s*(?:,\s*(.*))?\)$', valor)
    if var:
        nombre, reserva = var.groups()
        if nombre in variables:
            return color(variables[nombre], variables, hondo + 1)
        return color(reserva, variables, hondo + 1) if reserva else None
    valor = COLORES.get(valor.lower(), valor)
    hexa = re.match(r'#([0-9a-fA-F]{3,8})$', valor)
    if hexa:
        h = hexa.group(1)
        if len(h) in (3, 4):
            h = ''.join(c * 2 for c in h)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16) / 255 if len(h) == 8 else 1)
    rgb = re.match(r'rgba?\(([^)]+)\)$', valor)
    if rgb:
        partes = [float(x) for x in re.split(r'[,\s/]+', rgb.group(1).strip()) if x]
        return (partes[0], partes[1], partes[2], partes[3] if len(partes) > 3 else 1)
    return None


def luz(c):
    def canal(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * canal(c[0]) + 0.7152 * canal(c[1]) + 0.0722 * canal(c[2])


def encima(arriba, abajo):
    return tuple(arriba[i] * arriba[3] + abajo[i] * (1 - arriba[3]) for i in range(3)) + (1,)


def pares_que_no_se_leen(css, minimo=3):
    """Reglas propias que ponen fondo Y letra en la misma regla y no llegan a ``minimo``:1 con los colores de la hoja.

    Une las reglas del mismo selector (la última gana, como en la cascada) y resuelve las variables con su última
    definición. No mira herencias: es una red para lo más común (botones, pastillas, insignias)."""
    variables, unidas = {}, {}
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)   # la hoja trae un comentario con el nombre de cada archivo
    for selectores, cuerpo in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
        declaraciones = [tuple(parte.strip() for parte in d.split(':', 1))
                         for d in re.split(r';(?![^(]*\))', cuerpo) if ':' in d]
        for propiedad, valor in declaraciones:
            if propiedad.startswith('--'):
                variables[propiedad] = valor
        for selector in (trozo.strip() for trozo in selectores.split(',')):
            if not PROPIO.search(selector):
                continue
            regla = unidas.setdefault(selector, {})
            for propiedad, valor in declaraciones:
                if propiedad in ('background', 'background-color'):
                    regla['fondo'] = valor
                elif propiedad == 'color':
                    regla['letra'] = valor
    superficie = color(variables.get('--dc-blanco', '#ffffff'), variables)
    malos = []
    for selector, regla in unidas.items():
        fondo = color(regla.get('fondo', ''), variables)
        letra = color(regla.get('letra', ''), variables)
        if not fondo or not letra:
            continue
        fondo = encima(fondo, superficie) if fondo[3] < 1 else fondo
        letra = encima(letra, fondo) if letra[3] < 1 else letra
        a, b = luz(fondo), luz(letra)
        razon = (max(a, b) + 0.05) / (min(a, b) + 0.05)
        if razon < minimo:
            malos.append(f"{selector}: fondo {regla['fondo']} con letra {regla['letra']} ({razon:.2f}:1)")
    return malos


@tagged('post_install', '-at_install')
class TestModoOscuroPaquetes(TransactionCase):
    """Sin navegador: qué archivo entra en qué hoja, y en qué orden."""

    def test_fuera_de_una_peticion_el_esquema_es_claro(self):
        self.assertEqual(self.env['ir.http'].color_scheme(), 'light')

    def test_ningun_archivo_oscuro_entra_en_las_hojas_claras(self):
        """El modo claro no puede cambiar ni un píxel: nada de ``oscuro/`` ni ``*.dark.scss`` en sus hojas."""
        for paquete in (HOJA_CLARA, 'web.assets_backend', HOJA_PEREZOSA_CLARA, 'web.assets_web_print',
                        'web.assets_frontend', 'web.report_assets_common'):
            oscuros = [r for r in rutas(self.env, paquete) if '/oscuro/' in r or r.endswith('.dark.scss')]
            self.assertFalse(oscuros, f'{paquete} no debe llevar archivos del modo oscuro: {oscuros}')

    def test_todo_lo_de_la_carpeta_oscura_entra_en_la_hoja_oscura_y_solo_estilos(self):
        en_disco = sorted(glob.glob(os.path.join(file_path(CARPETA_OSCURA), '*')))
        self.assertTrue(en_disco, 'la carpeta del modo oscuro existe')
        hoja = rutas(self.env, HOJA_OSCURA)
        for ruta in en_disco:
            nombre = os.path.basename(ruta)
            self.assertTrue(nombre.endswith('.dark.scss'),
                            f'{nombre}: en oscuro/ solo van hojas «*.dark.scss» (el manifest no toma otra cosa)')
            self.assertIn(f'/{CARPETA_OSCURA}/{nombre}', hoja, f'{nombre} no está en {HOJA_OSCURA}')

    def test_la_paleta_oscura_va_despues_de_la_de_dcasa_y_antes_de_la_de_odoo(self):
        """Después de la de dcasa_base para pisar su barra blanca; antes de la de Odoo, que es ``!default`` y respeta lo
        ya definido. Y las funciones de Bootstrap, pegadas a las originales. En la hoja de siempre y en la que cargan
        aparte las gráficas y las tablas dinámicas."""
        for paquete in (HOJA_OSCURA, HOJA_PEREZOSA_OSCURA):
            hoja = rutas(self.env, paquete)
            paleta = hoja.index(f'/{CARPETA_OSCURA}/primary_variables.dark.scss')
            self.assertGreater(paleta, hoja.index('/dcasa_base/static/src/scss/primary_variables.scss'), paquete)
            self.assertLess(paleta, hoja.index('/web/static/src/scss/primary_variables.scss'), paquete)
            self.assertEqual(hoja.index(f'/{CARPETA_OSCURA}/bs_functions.dark.scss'),
                             hoja.index('/web/static/lib/bootstrap/scss/_functions.scss') + 1, paquete)
        # Los ajustes por pantalla van al final: después de todo lo claro (para pisarlo con el mismo selector).
        hoja = rutas(self.env, HOJA_OSCURA)
        ultimo_claro = max(i for i, r in enumerate(hoja) if r.endswith('.scss') and '/oscuro/' not in r
                           and not r.endswith('.dark.scss'))
        for nombre in ('tokens', 'interfaz', 'conversaciones', 'odoo'):
            self.assertGreater(hoja.index(f'/{CARPETA_OSCURA}/{nombre}.dark.scss'), ultimo_claro, nombre)

    def test_los_colores_de_noche_cubren_los_de_dia(self):
        """Cada color ``--dc-*`` de tokens.scss tiene su valor de noche (los de forma y movimiento no cambian)."""
        def nombres(ruta):
            with open(file_path(ruta), encoding='utf-8') as archivo:
                return set(re.findall(r'^\s*(--dc-[a-z0-9-]+)\s*:', archivo.read(), flags=re.M))
        de_dia = nombres('dcasa_interfaz/static/src/scss/tokens.scss')
        de_noche = nombres(f'{CARPETA_OSCURA}/tokens.dark.scss')
        iguales = {'--dc-r-sm', '--dc-r-md', '--dc-r-lg', '--dc-barra-w', '--dc-barra-w-colapsada', '--dc-transicion',
                   '--dc-curva', '--dc-amarillo'}
        self.assertFalse(de_dia - de_noche - iguales, 'colores de tokens.scss sin su valor para el modo oscuro')

    def test_la_hoja_perezosa_oscura_compila(self):
        """Gráficas y tablas dinámicas: su hoja se arma al abrirlas; que un error de SCSS salte aquí."""
        paquete = self.env['ir.qweb']._get_asset_bundle(HOJA_PEREZOSA_OSCURA, css=True, js=False)
        paquete.css()
        self.assertFalse(paquete.css_errors, paquete.css_errors)


@tagged('post_install', '-at_install')
class TestModoOscuroServidor(HttpCase):
    """Qué hoja enlaza el panel según la cookie, y que las dos compilan."""

    def hojas(self, cookies=None):
        self.authenticate('admin', 'admin')
        html = self.url_open('/odoo', cookies=cookies).text
        return re.findall(r'href="([^"]*/web/assets/[^"]*\.css)"', html)

    def test_sin_cookie_la_hoja_clara(self):
        enlaces = self.hojas()
        self.assertTrue(any('web.assets_web.min.css' in e for e in enlaces), enlaces)
        self.assertFalse(any('assets_web_dark' in e for e in enlaces), enlaces)

    def test_con_la_cookie_la_hoja_oscura(self):
        enlaces = self.hojas({'color_scheme': 'dark'})
        self.assertTrue(any('web.assets_web_dark.min.css' in e for e in enlaces), enlaces)
        self.assertFalse(any('web.assets_web.min.css' in e for e in enlaces), 'no se cargan las dos hojas a la vez')

    def test_con_un_valor_raro_la_hoja_clara(self):
        for valor in ('light', 'oscuro', 'DARK', 'dark; x', '1', ''):
            enlaces = self.hojas({'color_scheme': valor})
            self.assertTrue(any('web.assets_web.min.css' in e for e in enlaces), (valor, enlaces))
            self.assertFalse(any('assets_web_dark' in e for e in enlaces), (valor, enlaces))

    def test_las_dos_hojas_compilan_y_la_clara_no_trae_nada_oscuro(self):
        """Un error de SCSS deja TODO el panel sin estilos («A css error occured»). Y la hoja clara no lleva ni una
        regla del modo oscuro: lo dicen sus nombres propios (``--dc-relleno`` solo existe de noche)."""
        clara = self.url_open(next(e for e in self.hojas() if 'web.assets_web.min.css' in e)).text
        de_noche = self.hojas({'color_scheme': 'dark'})
        oscura = self.url_open(next(e for e in de_noche if 'assets_web_dark' in e)).text
        for nombre, css in (('clara', clara), ('oscura', oscura)):
            self.assertNotIn('css error', css.lower(), f'la hoja {nombre} no compiló')
            self.assertIn('o_dcasa_inicio', css, f'la hoja {nombre} trae el panel de D\'CASA')
        self.assertNotIn('--dc-relleno', clara)
        self.assertNotIn('color-scheme: dark', clara)
        self.assertIn('--dc-relleno', oscura)
        # La paleta de Odoo quedó invertida: la superficie de las vistas es el gris del prototipo, no blanco.
        self.assertRegex(oscura, r'\.o_form_view \.o_form_sheet\{[^}]*background-color: #2A2E33',
                         'la hoja del formulario')
        self.assertNotRegex(clara, r'#2A2E33')

    def test_los_rellenos_propios_se_leen_de_noche(self):
        """En claro, el azul de la marca es a la vez tinta y relleno; de noche son dos azules, y cada relleno propio
        necesita su regla en ``static/src/oscuro/``. Si alguien agrega un botón o una pastilla azul (o un blanco puesto
        a mano) y no le pone su versión de noche, queda letra clara sobre celeste: esto lo avisa."""
        de_noche = self.hojas({'color_scheme': 'dark'})
        oscura = self.url_open(next(e for e in de_noche if 'assets_web_dark' in e)).text
        self.assertGreater(len(re.findall(r'--dc-relleno\b', oscura)), 20, 'la hoja oscura trae sus rellenos')
        malos = pares_que_no_se_leen(oscura)
        self.assertFalse(malos, 'En modo oscuro estas reglas no se leen (menos de 3:1). Dales su versión de noche en '
                         'dcasa_interfaz/static/src/oscuro/ (relleno: var(--dc-relleno) con var(--dc-en-relleno)):\n'
                         + '\n'.join(malos[:40]))

    def test_la_red_de_los_pares_atrapa_un_relleno_sin_version_de_noche(self):
        """La red de arriba, probada con dos reglas de mentira sobre los colores de noche de verdad."""
        with open(file_path(f'{CARPETA_OSCURA}/tokens.dark.scss'), encoding='utf-8') as archivo:
            noche = re.sub(r'//[^\n]*', '', archivo.read())
        mal = '.o_dcasa_prueba_boton{background: var(--dc-azul-600); color: #FFFFFF;}'
        bien = '.o_dcasa_prueba_bien{background: var(--dc-relleno); color: var(--dc-en-relleno);}'
        ajena = '.o_list_view .o_cosa_de_odoo{background: #FFFFFF; color: #FFFFFF;}'   # lo de Odoo no se revisa aquí
        malos = pares_que_no_se_leen(noche + mal + bien + ajena)
        self.assertEqual(len(malos), 1, malos)
        self.assertIn('.o_dcasa_prueba_boton', malos[0])


@tagged('post_install', '-at_install')
class TestModoOscuroEnElNavegador(HttpCase):
    """Lo que se ve: oscuro con la cookie, claro sin ella, y el interruptor."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = new_test_user(cls.env, login='vendedora_noche',
                                      groups='base.group_user,sales_team.group_sale_salesman')
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente de noche'})
        cls.cotizacion = cls.env['sale.order'].create({'partner_id': cls.cliente.id, 'user_id': cls.vendedora.id})

    def probar(self, ruta, cuerpo, oscuro):
        if os.environ.get('DCASA_SIN_NAVEGADOR'):
            self.skipTest('sin navegador')
        codigo = '(async () => {' + COLORES_JS + f'const OSCURO = {"true" if oscuro else "false"};' + cuerpo + r"""
            const oscuras = hojas().filter((h) => h.includes('assets_web_dark')).length;
            const claras = hojas().filter((h) => h.includes('web.assets_web.min')).length;
            if (OSCURO ? (oscuras !== 1 || claras !== 0) : (oscuras !== 0 || claras !== 1)) {
                throw new Error('hojas enlazadas: ' + JSON.stringify(hojas()));
            }
            console.log('test successful');
        })();"""
        self.browser_js(ruta, codigo, login='vendedora_noche', cookies={'color_scheme': 'dark'} if oscuro else None)

    INICIO = """
        await esperar(() => document.querySelector('.o_dcasa_inicio .o_dcasa_atajo'), 'el Inicio');
        pide('body', OSCURO, 'el fondo del panel');
        pide('.o_main_navbar', OSCURO, 'la barra de arriba');
        pide('.o_dcasa_inicio', OSCURO, 'el Inicio');
        pide('.o_dcasa_inicio_hero h1', OSCURO, 'el saludo');
        pide('.o_dcasa_barra', OSCURO, 'la barra lateral');
        const atajo = document.querySelector('.o_dcasa_atajo');
        if (contraste(atajo) < 4.5) { throw new Error('el acceso directo no se lee: ' + contraste(atajo).toFixed(2)); }
        const boton = await esperar(() => document.querySelector('.o_dcasa_inicio_accesos .btn-primary'),
            'el botón principal');
        if (contraste(boton) < 4.5) { throw new Error('el botón principal no se lee: ' + contraste(boton).toFixed(2)); }
    """
    LISTA = """
        await esperar(() => document.querySelector('.o_list_view .o_data_row'), 'la lista de cotizaciones');
        pide('.o_control_panel', OSCURO, 'la cabecera de la lista');
        pide('.o_list_renderer .o_data_row .o_data_cell', OSCURO, 'un renglón de la lista');
        pide('.o_list_renderer thead th', OSCURO, 'los títulos de la lista');
        const nuevo = document.querySelector('.o_control_panel .btn-primary');
        if (nuevo && contraste(nuevo) < 4.5) { throw new Error('«Nuevo» no se lee: ' + contraste(nuevo).toFixed(2)); }
    """
    FORMULARIO = """
        await esperar(() => document.querySelector('.o_form_view .o_form_sheet'), 'el formulario');
        pide('.o_form_view .o_form_sheet', OSCURO, 'la hoja del formulario');
        pide('.o_form_view .o_form_label', OSCURO, 'un rótulo del formulario');
        pide('.o_form_view .o_field_widget[name="partner_id"] input', OSCURO, 'la casilla del cliente');
        pide('.o_notebook .nav-link.active', OSCURO, 'la pestaña elegida');
    """

    def test_con_la_cookie_el_inicio_sale_oscuro(self):
        self.probar('/odoo/action-dcasa_interfaz.action_dcasa_inicio', self.INICIO, oscuro=True)

    def test_sin_cookie_el_inicio_sale_claro_como_siempre(self):
        self.probar('/odoo/action-dcasa_interfaz.action_dcasa_inicio', self.INICIO, oscuro=False)

    def test_con_la_cookie_la_lista_sale_oscura(self):
        self.probar('/odoo/action-sale.action_quotations_with_onboarding', self.LISTA, oscuro=True)

    def test_sin_cookie_la_lista_sale_clara_como_siempre(self):
        self.probar('/odoo/action-sale.action_quotations_with_onboarding', self.LISTA, oscuro=False)

    def test_con_la_cookie_el_formulario_sale_oscuro(self):
        self.probar(f'/odoo/action-sale.action_quotations_with_onboarding/{self.cotizacion.id}', self.FORMULARIO,
                    oscuro=True)

    def test_sin_cookie_el_formulario_sale_claro_como_siempre(self):
        self.probar(f'/odoo/action-sale.action_quotations_with_onboarding/{self.cotizacion.id}', self.FORMULARIO,
                    oscuro=False)

    def test_el_interruptor_guarda_la_cookie_y_recarga(self):
        """Menú de usuario › «Modo oscuro»: apagado al entrar; al tocarlo guarda ``color_scheme=dark`` para todo el
        sitio y recarga; al tocarlo otra vez, ``light``. (La recarga se cambia por una marca para que la prueba no se
        pierda.)"""
        if os.environ.get('DCASA_SIN_NAVEGADOR'):
            self.skipTest('sin navegador')
        codigo = '(async () => {' + ESPERAR_JS + r"""
            const galleta = () => (document.cookie.split('; ').find((c) => c.startsWith('color_scheme=')) || '')
                .split('=')[1] || '';
            const { modoOscuro } = odoo.loader.modules.get('@dcasa_interfaz/js/modo_oscuro');
            const FILA = '.dropdown-item[data-menu="dcasa_modo_oscuro"]';
            let recargas = 0;
            modoOscuro.recargar = () => { recargas += 1; };
            const abrir = async () => {
                (await esperar(() => document.querySelector('.o_user_menu button'), 'el menú de usuario')).click();
                return esperar(() => document.querySelector(FILA), 'el interruptor');
            };
            let fila = await abrir();
            igual(fila.textContent.trim(), 'Modo oscuro', 'el nombre del interruptor');
            const casilla = () => document.querySelector(FILA + ' input[type="checkbox"]');
            if (!casilla() || casilla().checked) { throw new Error('el interruptor debe verse apagado en claro'); }
            igual(galleta(), '', 'sin tocar nada no hay cookie');
            fila.click();
            await esperar(() => recargas >= 1, 'la recarga tras encender');
            igual(galleta(), 'dark', 'la cookie tras encender');
            recargas = 0;
            // Ya «encendido» (la cookie manda): el menú lo muestra prendido y al tocarlo vuelve a claro.
            if (document.querySelector(FILA)) { document.body.click(); }
            await esperar(() => !document.querySelector(FILA), 'que cierre el menú');
            fila = await abrir();
            if (!casilla().checked) { throw new Error('con la cookie en dark debe verse encendido'); }
            fila.click();
            await esperar(() => recargas >= 1, 'la recarga tras apagar');
            igual(galleta(), 'light', 'la cookie tras apagar');
            console.log('test successful');
        })();"""
        self.browser_js('/odoo/action-dcasa_interfaz.action_dcasa_inicio', codigo, login='vendedora_noche')

    def test_el_codigo_del_interruptor(self):
        """Sin navegador: lo que dice el código (un año, para todo el sitio, y en el menú de la persona)."""
        with open(file_path('dcasa_interfaz/static/src/js/modo_oscuro.js'), encoding='utf-8') as archivo:
            js = archivo.read()
        self.assertIn('registry.category("user_menuitems").add("dcasa_modo_oscuro"', js)
        self.assertIn('type: "switch"', js)
        self.assertIn('cookie.set(COOKIE, oscuro ? "dark" : "light")', js)   # cookie.set: path=/ y un año por defecto
        with open(file_path('web/static/src/core/browser/cookie.js'), encoding='utf-8') as archivo:
            galletas = archivo.read()
        self.assertIn('const COOKIE_TTL = 24 * 60 * 60 * 365;', galletas)
        self.assertIn('"path=/"', galletas)
