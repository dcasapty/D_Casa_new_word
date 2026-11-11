"""El panel en el celular al entrar: nunca en blanco, y un menú de una sola lista (reporte de la dueña, 2026-11-11).

Lo que pasaba: tras entrar desde el iPhone la pantalla quedaba vacía (solo la barra de arriba) hasta que el servidor
entregaba las cifras del Inicio; y al tocar las tres rayas, el menú de Odoo mostraba «las secciones de la app abierta»,
que en el Inicio no existen: una hoja en blanco con la palabra «Inicio» y nada que tocar.

* El Inicio se pinta de inmediato (el saludo y bloques en gris) y las cifras llegan después. Si no llegan, lo dice y
  ofrece «Reintentar».
* El área de trabajo vacía dice «Cargando…» (vale para cualquier pantalla que tarde en llegar).
* El menú del celular es una sola lista: todas las aplicaciones y, debajo de la abierta, sus secciones.
"""
import os

from odoo.tests import HttpCase, tagged

from .test_inicio_por_rol import ESPERAR_JS

# Retiene o hace fallar la consulta de las cifras del Inicio, para ver la pantalla mientras «el servidor tarda».
SERVIDOR_LENTO_JS = """
    const consulta = { retener: false, fallar: false, retenidas: [] };
    const abrirOriginal = XMLHttpRequest.prototype.open;
    const enviarOriginal = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (metodo, url, ...resto) {
        this.dcasaUrl = String(url);
        return abrirOriginal.call(this, metodo, url, ...resto);
    };
    XMLHttpRequest.prototype.send = function (...args) {
        if ((this.dcasaUrl || '').includes('dcasa.tablero/obtener_datos')) {
            if (consulta.fallar) {
                setTimeout(() => this.dispatchEvent(new Event('error')), 50);
                return;
            }
            if (consulta.retener) {
                consulta.retenidas.push(() => enviarOriginal.apply(this, args));
                return;
            }
        }
        return enviarOriginal.apply(this, args);
    };
    const soltar = () => {
        consulta.retener = false;
        consulta.fallar = false;
        for (const enviar of consulta.retenidas.splice(0)) { enviar(); }
    };
    const abrirElMenu = async () => {
        document.querySelector('.o_main_navbar .o_menu_toggle').click();
        return await esperar(() => document.querySelector('.o_app_menu_sidebar .o_dcasa_cajon_app'),
                             'el menú del celular');
    };
    const appDelMenu = (xmlid) => document.querySelector(
        `.o_app_menu_sidebar .o_dcasa_cajon_app[data-menu-xmlid="${xmlid}"]`);
    const menuCerrado = () => !document.querySelector('.o_app_menu_sidebar')
        && !document.querySelector('.modal-backdrop');
"""


@tagged('post_install', '-at_install')
class TestElPanelEnElCelularAlEntrar(HttpCase):
    browser_size = '390x844'
    touch_enabled = True

    def setUp(self):
        super().setUp()
        if os.environ.get('DCASA_SIN_NAVEGADOR'):
            self.skipTest('sin navegador')

    def test_el_inicio_se_pinta_antes_de_que_lleguen_las_cifras(self):
        codigo = '(async () => {' + ESPERAR_JS + SERVIDOR_LENTO_JS + """
            await esperar(() => document.querySelector('.o_action_manager .o_action'), 'la primera pantalla');
            // El servidor «tarda»: se entra al Inicio por el menú.
            consulta.retener = true;
            await abrirElMenu();
            appDelMenu('dcasa_interfaz.menu_dcasa_inicio').click();
            const armazon = await esperar(() => document.querySelector('.o_action_manager .o_dcasa_arranque'),
                                          'el armazón del Inicio mientras llegan las cifras');
            if (document.querySelector('.o_dcasa_inicio')) {
                throw new Error('el Inicio no puede estar: faltan sus cifras');
            }
            if (!consulta.retenidas.length) { throw new Error('la consulta de las cifras no salió'); }
            const saludo = armazon.querySelector('h1').textContent.trim();
            if (!/^Hola, \\S+/.test(saludo)) { throw new Error('el armazón saluda por el nombre y dice: ' + saludo); }
            if (!/^(domingo|lunes|martes|miércoles|jueves|viernes|sábado) \\d{1,2} de [a-z]+$/.test(
                    armazon.querySelector('.o_dcasa_inicio_fecha').textContent.trim())) {
                throw new Error('la fecha del armazón: ' + armazon.querySelector('.o_dcasa_inicio_fecha').textContent);
            }
            if (armazon.getAttribute('aria-busy') !== 'true') { throw new Error('el armazón avisa que está cargando'); }
            if (!armazon.querySelector('[role="status"]')) {
                throw new Error('falta el aviso «Preparando tu resumen…»');
            }
            if (armazon.querySelectorAll('.o_dcasa_arranque_bloque').length < 6) {
                throw new Error('faltan los bloques');
            }
            if (armazon.getBoundingClientRect().height < 300) { throw new Error('el armazón ocupa la pantalla'); }
            await esperar(menuCerrado, 'que el menú se cierre al elegir');
            // Llegan las cifras: el armazón se cambia por el Inicio, con el mismo saludo.
            soltar();
            await esperar(() => document.querySelector('.o_dcasa_inicio .o_dcasa_inicio_hero h1'), 'el Inicio');
            if (document.querySelector('.o_dcasa_arranque')) { throw new Error('el armazón debió irse'); }
            igual(document.querySelector('.o_dcasa_inicio .o_dcasa_inicio_hero h1').textContent.trim(), saludo,
                  'saludo');

            // El servidor no contesta: lo dice y deja reintentar.
            consulta.fallar = true;
            await abrirElMenu();
            appDelMenu('dcasa_interfaz.menu_dcasa_inicio').click();
            const boton = await esperar(() => document.querySelector('.o_dcasa_arranque .o_dcasa_arranque_reintentar'),
                                        'el botón «Reintentar»');
            if (document.querySelector('.o_dcasa_arranque').getAttribute('aria-busy') !== 'false') {
                throw new Error('con el error a la vista ya no está «cargando»');
            }
            if (!document.querySelector('.o_dcasa_arranque [role="alert"]')) {
                throw new Error('falta decir que no llegó');
            }
            if (boton.getBoundingClientRect().height < 44) { throw new Error('«Reintentar» mide menos de 44 px'); }
            soltar();
            boton.click();
            await esperar(() => document.querySelector('.o_dcasa_inicio .o_dcasa_inicio_hero h1'),
                          'el Inicio al reintentar');

            // Cualquier pantalla que tarde: el área de trabajo vacía dice «Cargando…» (no queda en blanco).
            const vacia = document.createElement('div');
            vacia.className = 'o_action_manager';
            document.body.appendChild(vacia);
            const aviso = getComputedStyle(vacia, '::before').content;
            vacia.remove();
            if (!aviso.includes('Cargando')) { throw new Error('el área de trabajo vacía no avisa: ' + aviso); }
            console.log('test successful');
        })();"""
        self.browser_js('/odoo/action-sale.action_quotations_with_onboarding', codigo, login='admin')

    def test_el_menu_es_una_sola_lista_sin_hojas_vacias(self):
        codigo = '(async () => {' + ESPERAR_JS + SERVIDOR_LENTO_JS + """
            await esperar(() => document.querySelector('.o_dcasa_inicio .o_dcasa_inicio_hero'), 'el Inicio');
            const ruta = location.pathname;
            await abrirElMenu();
            const cajon = document.querySelector('.o_app_menu_sidebar');
            // Ya no hay dos caras: ni el botón «Todas las aplicaciones» ni la hoja con solo el nombre de la app.
            if (cajon.querySelector('.o_sidebar_topbar a.btn')) {
                throw new Error('sobra el botón «Todas las aplicaciones»');
            }
            const apps = [...cajon.querySelectorAll('.o_dcasa_cajon_app')];
            if (apps.length < 3) { throw new Error('el menú debe listar las aplicaciones y trae ' + apps.length); }
            const inicio = appDelMenu('dcasa_interfaz.menu_dcasa_inicio');
            if (apps[0] !== inicio) { throw new Error('el Inicio va primero'); }
            if (inicio.getAttribute('aria-current') !== 'true') { throw new Error('el Inicio es donde se está'); }
            const chicos = [...cajon.querySelectorAll('a, button')]
                .map((e) => [e, e.getBoundingClientRect()])
                .filter(([e, r]) => r.width > 0 && (r.width < 43.5 || r.height < 43.5))
                .map(([e, r]) => e.className + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
            if (chicos.length) { throw new Error('en el menú, menos de 44 px: ' + chicos.join(' | ')); }
            if (document.documentElement.scrollWidth > window.innerWidth + 1) { throw new Error('se sale de lado'); }

            // La flecha despliega las secciones de una aplicación SIN salir de donde se está.
            const ventas = appDelMenu('sale.sale_menu_root');
            const flecha = ventas.parentElement.querySelector('.o_dcasa_cajon_flecha');
            if (cajon.querySelector('.o_dcasa_cajon_secciones')) { throw new Error('el Inicio no tiene secciones'); }
            flecha.click();
            const secciones = await esperar(
                () => ventas.closest('.o_dcasa_cajon_item').querySelector('.o_dcasa_cajon_secciones'),
                'las secciones de Ventas');
            igual(flecha.getAttribute('aria-expanded'), 'true', 'la flecha desplegada');
            if (location.pathname !== ruta || !document.querySelector('.o_dcasa_inicio')) {
                throw new Error('desplegar no debe cambiar de pantalla');
            }
            // Una pantalla de adentro (se despliega su grupo si hace falta): se abre y el menú se cierra.
            let hoja = secciones.querySelector('a.o_dcasa_cajon_seccion');
            if (!hoja) {
                secciones.querySelector('.o_dcasa_cajon_grupo_btn').click();
                hoja = await esperar(() => secciones.querySelector('a.o_dcasa_cajon_seccion'),
                                     'una pantalla de Ventas');
            }
            hoja.click();
            await esperar(() => !document.querySelector('.o_dcasa_inicio') && location.pathname !== ruta
                                && document.querySelector('.o_action_manager .o_action'), 'la pantalla elegida');
            await esperar(menuCerrado, 'que el menú se cierre al elegir una pantalla');

            // De vuelta en el menú: Ventas es donde se está y sus secciones ya vienen a la vista.
            await abrirElMenu();
            const ahora = appDelMenu('sale.sale_menu_root');
            igual(ahora.getAttribute('aria-current'), 'true', 'Ventas es la app abierta');
            if (!ahora.closest('.o_dcasa_cajon_item').querySelector('.o_dcasa_cajon_secciones a.o_dcasa_cajon_seccion, '
                    + '.o_dcasa_cajon_secciones .o_dcasa_cajon_grupo_btn')) {
                throw new Error('las secciones de la app abierta vienen desplegadas');
            }
            // Y el Inicio queda a un toque: se abre y el menú se cierra (sin pasos intermedios).
            appDelMenu('dcasa_interfaz.menu_dcasa_inicio').click();
            await esperar(() => document.querySelector('.o_dcasa_inicio .o_dcasa_inicio_hero'), 'el Inicio');
            await esperar(menuCerrado, 'que el menú se cierre al ir al Inicio');
            console.log('test successful');
        })();"""
        self.browser_js('/odoo', codigo, login='admin')
