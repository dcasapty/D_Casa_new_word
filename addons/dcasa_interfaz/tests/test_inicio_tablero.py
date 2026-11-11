"""El Inicio mejorado (propuesta 2, aprobada por la dueña el 2026-11-11): mismo orden y contenido, mejor presentado.

* En el celular, los accesos directos tienen tres tamaños («Compactos», «Detalle», «Grandes») que cada quien elige con
  un selector chico justo encima; se recuerdan en ese aparato y, si no se puede guardar, la pantalla funciona igual.
* Tres contadores («En tienda», «Chatbot y web», «Entregas») llevan a cada panel cuando los paneles quedan uno debajo
  del otro (celular y tableta parada).
* Los botones del saludo van enteros dentro de la pantalla en el celular, de a dos por fila.
* Nada se sale de costado en ningún ancho y el Inicio sigue bajando con scroll.
* Las cifras principales «suben» hasta su valor, pero el texto de la etiqueta es el valor final desde el primer momento.
"""
import os
import re
from pathlib import Path

from odoo.tests import HttpCase, TransactionCase, tagged

from .test_inicio_por_rol import ESPERAR_JS, VentasMixin

FUENTES = Path(__file__).resolve().parents[1] / 'static' / 'src'

COMUN_JS = ESPERAR_JS + r"""
    const CLAVE = 'dcasa.inicio.atajos';
    const raiz = () => document.querySelector('.o_dcasa_tablero:not([data-vieja])');
    const en = (selector) => raiz().querySelector(selector);
    const todos = (selector) => [...raiz().querySelectorAll(selector)];
    const pausa = (ms) => new Promise((ok) => setTimeout(ok, ms));
    // Espera a que el Inicio esté pintado y quieto: las cifras ya subieron y los bloques y las barras ya entraron (el
    // movimiento es corto y de una sola vez). Mientras se mueven, las medidas de pantalla no son las finales.
    const quieto = async (selector) => {
        await esperar(() => raiz() && en(selector), 'el Inicio: ' + selector);
        await esperar(() => !en('[data-sube]'), 'las cifras quietas');
        const enMarcha = () => document.getAnimations().filter((a) => a.effect && a.effect.target
            && raiz().contains(a.effect.target) && a.playState === 'running'
            && a.effect.getComputedTiming().endTime < 5000);
        await esperar(() => !enMarcha().length, 'el movimiento del Inicio terminado');
    };
    // Sale del Inicio y lo abre otra vez: una pantalla nueva, como al volver a entrar.
    const reabrir = async () => {
        raiz().dataset.vieja = '1';
        await odoo.__WOWL_DEBUG__.root.env.services.action.doAction(
            'dcasa_interfaz.action_dcasa_inicio', { clearBreadcrumbs: true });
        await quieto('.o_dcasa_cifra');
    };
    // El nombre de un acceso cabe entero: puede bajar de renglón entre palabras, nunca partirse por la mitad.
    const nombreEntero = (acceso) => {
        const nombre = acceso.querySelector('strong');
        const renglon = parseFloat(getComputedStyle(nombre).lineHeight);
        const renglones = Math.round(nombre.getBoundingClientRect().height / renglon);
        if (renglones > nombre.textContent.trim().split(/\s+/).length) {
            throw new Error('el nombre «' + nombre.textContent + '» se parte por la mitad');
        }
    };
    const sinScrollDeCostado = (que) => {
        if (raiz().scrollWidth > raiz().clientWidth + 1
                || document.documentElement.scrollWidth > window.innerWidth + 1) {
            throw new Error(`scroll de costado (${que}): ${raiz().scrollWidth} > ${raiz().clientWidth}`);
        }
        for (const el of todos('button, section, nav, header, h1, h2, li, p, table')) {
            const caja = el.getBoundingClientRect();
            if (caja.width > 1 && (caja.left < -1 || caja.right > window.innerWidth + 1)) {
                throw new Error(`se sale de la pantalla (${que}): «${el.textContent.trim().slice(0, 40)}» `
                                + `${Math.round(caja.left)}–${Math.round(caja.right)}`);
            }
        }
    };
    // Cuántos accesos hay en la primera fila y si se ve el renglón de detalle (en «Compactos» queda de 1 px: solo lo
    // lee el lector de pantalla).
    const accesosPorFila = () => {
        const accesos = todos('.o_dcasa_atajo');
        const arriba = accesos[0].getBoundingClientRect().top;
        return accesos.filter((a) => Math.abs(a.getBoundingClientRect().top - arriba) < 2).length;
    };
    const seVeElDetalle = () => en('.o_dcasa_atajo .o_dcasa_atajo_texto span').getBoundingClientRect().width > 2;
    // Los botones del saludo: enteros dentro de la pantalla y sin texto cortado; en el celular, de a dos por fila y de
    // 44 px de alto, con «Ver la tienda» (solo ícono) al final.
    const botonesDelSaludo = (que) => {
        const caja = en('.o_dcasa_inicio_accesos');
        if (caja.scrollWidth > caja.clientWidth + 1) { throw new Error(`${que}: los botones se deslizan de lado`); }
        const botones = todos('.o_dcasa_inicio_accesos .btn');
        const filas = {};
        for (const boton of botones) {
            const c = boton.getBoundingClientRect();
            const nombre = boton.textContent.trim() || boton.getAttribute('aria-label');
            if (c.left < 0 || c.right > window.innerWidth + 1) {
                throw new Error(`${que}: «${nombre}» se sale de la pantalla: `
                                + `${Math.round(c.left)}–${Math.round(c.right)} de ${window.innerWidth}`);
            }
            if (boton.scrollWidth > boton.clientWidth + 1) { throw new Error(`${que}: «${nombre}» sale cortado`); }
            // Todos azules (pedido del jefe, 2026-10-16); «¿Qué necesito hacer?» va con borde azul.
            if (!boton.classList.contains('o_dcasa_inicio_guia')) {
                igual(getComputedStyle(boton).backgroundColor, 'rgb(19, 64, 177)', `${que}: «${nombre}», azul`);
            }
            (filas[Math.round(c.top)] ||= []).push(boton);
            if (window.innerWidth < 576 && Math.round(c.height) < 44) {
                throw new Error(`${que}: «${nombre}» mide ${Math.round(c.height)} px de alto y deben ser 44`);
            }
        }
        if (window.innerWidth >= 576) { return; }
        const porFila = Object.keys(filas).sort((a, b) => a - b).map((arriba) => filas[arriba]);
        for (const fila of porFila) {
            const conTexto = fila.filter((b) => !b.classList.contains('o_dcasa_ver_tienda'));
            if (conTexto.length > 2) {
                throw new Error(`${que}: van de a dos por fila y hay ${conTexto.length}: `
                                + conTexto.map((b) => b.textContent.trim()).join(' | '));
            }
        }
        igual(porFila.length, Math.ceil(botones.filter((b) => !b.classList.contains('o_dcasa_ver_tienda')).length / 2),
              `${que}: las filas de botones`);
        const tienda = en('.o_dcasa_ver_tienda');
        if (tienda) {
            if (botones.at(-1) !== tienda || !porFila.at(-1).includes(tienda)) {
                throw new Error(`${que}: «Ver la tienda» va al final`);
            }
            igual(Math.round(tienda.getBoundingClientRect().width), 44, `${que}: «Ver la tienda», cuadrado de 44 px`);
        }
    };
"""


@tagged('post_install', '-at_install')
class TestInicioTableroCodigo(TransactionCase):
    """Sin navegador: las reglas de la casa en la hoja del Inicio y lo que no puede perderse del código."""

    def test_la_hoja_del_inicio_respeta_la_marca(self):
        scss = (FUENTES / 'scss' / 'tablero.scss').read_text(encoding='utf-8')
        sin_comentarios = re.sub(r'//[^\n]*', '', scss)
        self.assertNotRegex(sin_comentarios, r'#[0-9a-fA-F]{3,8}\b', 'colores sueltos: van con las variables --dc-*')
        self.assertNotRegex(sin_comentarios, r'\brgba?\(', 'colores sueltos: van con las variables --dc-*')
        self.assertNotIn('gradient', sin_comentarios, 'sistema plano: sin degradados')
        self.assertNotIn('--dc-amarillo', sin_comentarios,
                         'lo nuevo va sobre blanco: los números en azul (el amarillo nunca toca el blanco)')
        self.assertNotIn('--dc-sombra-2', sin_comentarios, 'sistema plano: sin sombras marcadas')
        for variable in set(re.findall(r'var\((--dc-[a-z0-9-]+)', sin_comentarios)) - {'--dc-turno'}:
            self.assertIn(variable + ':', (FUENTES / 'scss' / 'tokens.scss').read_text(encoding='utf-8'), variable)

    def test_el_movimiento_respeta_a_quien_pidio_menos(self):
        scss = (FUENTES / 'scss' / 'tablero.scss').read_text(encoding='utf-8')
        inicio = scss.index('@media (prefers-reduced-motion: no-preference) {')
        profundidad, fin = 0, None
        for i in range(scss.index('{', inicio), len(scss)):
            profundidad += {'{': 1, '}': -1}.get(scss[i], 0)
            if profundidad == 0:
                fin = i
                break
        fuera = re.sub(r'//[^\n]*', '', scss[:inicio] + scss[fin:])
        self.assertNotRegex(fuera, r'\banimation(-name)?\s*:', 'toda animación va dentro de «no-preference»')
        self.assertGreaterEqual(len(re.findall(r'\banimation:', scss[inicio:fin])), 3)
        # Cortas y una sola vez: ninguna dura más de 0,8 s contando su espera, ni se repite.
        self.assertNotIn('infinite', scss)
        for duracion in re.findall(r'animation:[^;]*?(\d+)ms', scss):
            self.assertLessEqual(int(duracion), 500)
        js = (FUENTES / 'js' / 'inicio.js').read_text(encoding='utf-8')
        self.assertIn('prefers-reduced-motion: reduce', js)
        self.assertIn('behavior: sinMovimiento() ? "auto" : "smooth"', js)

    def test_la_plantilla_conserva_lo_de_siempre_y_suma_lo_nuevo(self):
        xml = (FUENTES / 'xml' / 'inicio.xml').read_text(encoding='utf-8')
        # El orden de siempre: saludo, accesos, paneles, avisos, ventas, cifras, gráficas, aplicaciones.
        orden = ['o_dcasa_inicio_hero', 'class="o_dcasa_atajos"', 'class="o_dcasa_listas"', 'class="o_dcasa_atencion"',
                 'class="o_dcasa_ventas"', 'class="o_dcasa_cifras"', 'class="o_dcasa_inicio_fila"',
                 'class="o_dcasa_apps"']
        posiciones = [xml.index(trozo) for trozo in orden]
        self.assertEqual(posiciones, sorted(posiciones))
        # Los contadores van dentro del bloque de los paneles: salen con las mismas condiciones.
        listas = xml.index('class="o_dcasa_listas"')
        self.assertLess(listas, xml.index('class="o_dcasa_saltos"'))
        self.assertLess(xml.index('class="o_dcasa_saltos"'), xml.index('dcasa_interfaz.InicioCotizaciones'))
        for clave in ('cotizaciones', 'cotizaciones_en_linea', 'entregas'):
            self.assertRegex(
                xml, rf'<button t-if="d\.{clave}" type="button"\s+class="o_dcasa_salto o_dcasa_salto_{clave}"')
        # Lo que hoy se ve en los bloques de abajo no se pierde: fotos, enlaces y textos de vacío.
        for trozo in ('<img t-att-src="p.imagen"', 'this.abrirProducto(p)', 'Aún no hay ventas este mes.',
                      'Todavía no hay cobros registrados hoy.', 'No hay entregas pendientes.', 'o_dcasa_grafico_monto',
                      "dia.dia + ': ' + dinero(dia.monto) + ' sin ITBMS'"):
            self.assertIn(trozo, xml)
        js = (FUENTES / 'js' / 'inicio.js').read_text(encoding='utf-8')
        self.assertIn('export const CLAVE_ATAJOS = "dcasa.inicio.atajos";', js)


@tagged('post_install', '-at_install')
class TestInicioTableroEnElNavegador(VentasMixin, HttpCase):

    def setUp(self):
        super().setUp()
        if os.environ.get('DCASA_SIN_NAVEGADOR'):
            self.skipTest('sin navegador')
        # Una venta facturada hoy (para que las cifras no estén en cero), una cotización abierta y una entrega.
        self.facturar(self.pedido(vendedor=self.vendedora))
        self.pedido(vendedor=self.vendedora, confirmar=False)
        self.pedido(vendedor=self.otra)

    def probar(self, login, cuerpo, tamano):
        codigo = '(async () => {' + COMUN_JS + cuerpo + "console.log('test successful'); })();"
        self.browser_size = tamano
        self.browser_js('/odoo/action-dcasa_interfaz.action_dcasa_inicio', codigo, login=login, timeout=120)

    def test_los_tres_tamanos_de_los_accesos_en_el_celular_y_se_recuerdan(self):
        self.probar('gerencia_rol', r"""
            await quieto('.o_dcasa_atajo');
            const modo = () => en('.o_dcasa_atajos').dataset.modo;
            const marcada = () => todos('.o_dcasa_atajos_tamano_opcion[aria-pressed="true"]')
                .map((o) => o.textContent.trim());
            const elegir = async (clave) => {
                en('.o_dcasa_atajos_tamano_' + clave).click();
                await esperar(() => modo() === clave, 'los accesos en ' + clave);
            };
            // La primera vez (nada guardado): «Compactos».
            localStorage.removeItem(CLAVE);
            await reabrir();
            igual(modo(), 'compacto', 'la primera vez');
            igual(marcada(), ['Compactos'], 'la opción marcada');
            igual(todos('.o_dcasa_atajos_tamano_opcion').map((o) => o.textContent.trim()),
                  ['Compactos', 'Detalle', 'Grandes'], 'las tres opciones');
            const selector = en('.o_dcasa_atajos_tamano');
            if (getComputedStyle(selector).display === 'none') { throw new Error('en el celular se ve el selector'); }
            if (selector.nextElementSibling !== en('.o_dcasa_atajos')) {
                throw new Error('el selector va justo encima de los accesos');
            }
            if (selector.getBoundingClientRect().height > 44) { throw new Error('el selector es chico'); }
            igual(accesosPorFila(), 3, 'compactos: tres por fila');
            if (seVeElDetalle()) { throw new Error('compactos: sin el renglón de detalle'); }
            const primero = en('.o_dcasa_atajo');
            igual(getComputedStyle(primero).flexDirection, 'column', 'compactos: el ícono arriba y el nombre abajo');
            // El número va en la esquina, amarillo sobre el azul del acceso (el amarillo nunca toca el blanco).
            const numero = document.createElement('span');
            numero.className = 'o_dcasa_atajo_cuenta';
            numero.textContent = '7';
            primero.appendChild(numero);
            const cajaNumero = numero.getBoundingClientRect();
            const cajaAcceso = primero.getBoundingClientRect();
            igual(getComputedStyle(numero).backgroundColor, 'rgb(254, 208, 15)', 'el número, amarillo');
            igual(getComputedStyle(primero).backgroundColor, 'rgb(19, 64, 177)', 'sobre el azul del acceso');
            if (getComputedStyle(numero).position !== 'absolute' || cajaNumero.right > cajaAcceso.right
                    || cajaNumero.top < cajaAcceso.top || cajaAcceso.right - cajaNumero.right > 12
                    || cajaNumero.top - cajaAcceso.top > 12) {
                throw new Error('compactos: el número va en la esquina de arriba a la derecha, dentro del acceso');
            }
            numero.remove();
            todos('.o_dcasa_atajo').forEach(nombreEntero);
            sinScrollDeCostado('compactos');

            // «Detalle»: dos por fila, con el renglón de detalle. Se guarda y se recuerda al volver a entrar.
            await elegir('detalle');
            igual(accesosPorFila(), 2, 'detalle: dos por fila');
            if (!seVeElDetalle()) { throw new Error('detalle: con el renglón de detalle'); }
            todos('.o_dcasa_atajo').forEach(nombreEntero);
            igual(localStorage.getItem(CLAVE), 'detalle', 'se guarda en el aparato');
            sinScrollDeCostado('detalle');
            await reabrir();
            igual(modo(), 'detalle', 'se recuerda');
            igual(marcada(), ['Detalle'], 'la opción marcada al volver');
            igual(accesosPorFila(), 2, 'detalle al volver');

            // «Grandes»: uno por fila, como siempre.
            await elegir('grande');
            igual(accesosPorFila(), 1, 'grandes: uno por fila');
            if (!seVeElDetalle()) { throw new Error('grandes: con el renglón de detalle'); }
            igual(getComputedStyle(en('.o_dcasa_atajo')).flexDirection, 'row', 'grandes: como siempre');
            igual(localStorage.getItem(CLAVE), 'grande', 'se guarda en el aparato');
            sinScrollDeCostado('grandes');
            await reabrir();
            igual(modo(), 'grande', 'se recuerda');

            // Si el almacenamiento falla al guardar, la pantalla cambia igual (y no revienta).
            const guardar = Storage.prototype.setItem;
            Storage.prototype.setItem = function (clave, valor) {
                if (clave === CLAVE) { throw new Error('sin espacio'); }
                return guardar.call(this, clave, valor);
            };
            await elegir('compacto');
            igual(accesosPorFila(), 3, 'sin poder guardar: cambia igual');
            Storage.prototype.setItem = guardar;
            igual(localStorage.getItem(CLAVE), 'grande', 'no se pudo guardar');
            // Si falla al leer, o lo guardado no es un tamaño, arranca en «Compactos».
            const leer = Storage.prototype.getItem;
            Storage.prototype.getItem = function (clave) {
                if (clave === CLAVE) { throw new Error('bloqueado'); }
                return leer.call(this, clave);
            };
            await reabrir();
            igual(modo(), 'compacto', 'sin poder leer');
            Storage.prototype.getItem = leer;
            localStorage.setItem(CLAVE, 'gigante');
            await reabrir();
            igual(modo(), 'compacto', 'con un valor que no existe');
            localStorage.removeItem(CLAVE);
        """, '390x844')

    def test_los_contadores_solo_con_los_paneles_apilados_y_bajan_a_su_panel(self):
        cuerpo = r"""
            await quieto('.o_dcasa_listas .o_dcasa_lista_entregas');
            const APILADOS = __APILADOS__;
            const paneles = todos('.o_dcasa_listas > .o_dcasa_lista');
            if (paneles.length < 2) { throw new Error('se esperaban los paneles de Gerencia'); }
            const apilados = new Set(paneles.map((p) => Math.round(p.getBoundingClientRect().left))).size === 1;
            igual(apilados, APILADOS, 'los paneles, uno debajo del otro');
            const saltos = en('.o_dcasa_saltos');
            igual(getComputedStyle(saltos).display !== 'none', apilados, 'contadores solo con los paneles apilados');
            // Uno por cada panel que la persona ve, con el mismo número de la cabecera de su panel.
            const claves = paneles.map((p) => [...p.classList]
                .find((c) => /^o_dcasa_lista_(cotizaciones|entregas)/.test(c)).replace('o_dcasa_lista_', ''));
            igual(todos('.o_dcasa_salto').map((s) => [...s.classList].find((c) => c.startsWith('o_dcasa_salto_'))
                .replace('o_dcasa_salto_', '')), claves, 'un contador por panel, en su orden');
            const nombres = { cotizaciones: 'En tienda', cotizaciones_en_linea: 'Chatbot y web', entregas: 'Entregas' };
            for (const clave of claves) {
                const salto = en('.o_dcasa_salto_' + clave);
                igual(salto.querySelector('span').textContent.trim(), nombres[clave], 'el nombre del contador');
                igual(salto.querySelector('strong').textContent.trim(),
                      en(`.o_dcasa_lista_${clave} .o_dcasa_lista_numero`).textContent.trim(), 'el número de ' + clave);
            }
            // Van justo antes de los paneles (entre los accesos y el primer panel).
            if (saltos.nextElementSibling !== paneles[0]) {
                throw new Error('los contadores van antes del primer panel');
            }
            if (!apilados) { return console.log('test successful'); }
            // Números en azul sobre blanco: nada de amarillo, que aquí tocaría el blanco.
            igual(getComputedStyle(en('.o_dcasa_salto strong')).color, 'rgb(19, 64, 177)', 'el número, en azul');
            igual(getComputedStyle(saltos).backgroundColor, 'rgb(255, 255, 255)', 'sobre blanco');
            sinScrollDeCostado('con los contadores');
            // Al tocarlo, la pantalla baja hasta su panel.
            for (const clave of claves) {
                en('.o_dcasa_salto_' + clave).click();
                await esperar(() => {
                    const arriba = en('.o_dcasa_lista_' + clave).getBoundingClientRect().top
                        - raiz().getBoundingClientRect().top;
                    return arriba >= -2 && arriba <= 40;
                }, 'el panel de ' + clave + ' arriba de la pantalla');
                if (raiz().scrollTop <= 0) { throw new Error('la pantalla tenía que bajar'); }
            }
        """
        for tamano, apilados in (('390x844', True), ('768x1024', True), ('1366x768', False)):
            with self.subTest(tamano=tamano):
                self.probar('gerencia_rol', cuerpo.replace('__APILADOS__', 'true' if apilados else 'false'), tamano)

    def test_nada_se_sale_de_costado_y_el_inicio_baja_en_seis_anchos(self):
        cuerpo = r"""
            await quieto('.o_dcasa_inicio_fila .o_dcasa_top');
            const celular = window.innerWidth < 768;
            sinScrollDeCostado('al abrir');
            botonesDelSaludo('saludo');
            // En pantallas táctiles Odoo les cambia el relleno y la letra a todos los botones: tampoco se cortan.
            document.body.classList.add('o_touch_device');
            botonesDelSaludo('saludo en pantalla táctil');
            sinScrollDeCostado('en pantalla táctil');
            document.body.classList.remove('o_touch_device');
            // El selector de tamaño es solo del celular; en la tableta ancha y la computadora los accesos van en fila,
            // con su detalle, elija lo que elija la persona en su teléfono.
            igual(getComputedStyle(en('.o_dcasa_atajos_tamano')).display !== 'none', celular, 'el selector de tamaño');
            if (!celular) {
                igual(getComputedStyle(en('.o_dcasa_atajo')).flexDirection, 'row', 'los accesos, en fila');
                if (!seVeElDetalle()) { throw new Error('en la computadora los accesos llevan su detalle'); }
            }
            // El número amarillo no pisa el nombre del acceso.
            for (const acceso of todos('.o_dcasa_atajo')) {
                const numero = acceso.querySelector('.o_dcasa_atajo_cuenta');
                const nombre = acceso.querySelector('strong');
                const rango = document.createRange();
                rango.selectNodeContents(nombre);
                const t = rango.getBoundingClientRect();
                const a = acceso.getBoundingClientRect();
                if (t.left < a.left || t.right > a.right) {
                    throw new Error('se sale el nombre «' + nombre.textContent + '»');
                }
                nombreEntero(acceso);
                if (numero) {
                    const n = numero.getBoundingClientRect();
                    if (t.right > n.left && t.left < n.right && t.bottom > n.top && t.top < n.bottom) {
                        throw new Error('el número pisa el nombre «' + nombre.textContent + '»');
                    }
                }
            }
            // Las filas de los paneles: el cliente y el monto en el primer renglón; lo demás, en gris, debajo.
            const fila = en('.o_dcasa_lista_cotizaciones .o_dcasa_lista_fila');
            const cliente = fila.querySelector('.o_dcasa_lista_texto strong').getBoundingClientRect();
            const monto = fila.querySelector('.o_dcasa_lista_dato strong').getBoundingClientRect();
            const hace = fila.querySelector('.o_dcasa_lista_dato small');
            if (Math.abs(cliente.top - monto.top) > 6 || monto.left < cliente.right - 1) {
                throw new Error('el cliente y el monto van en el mismo renglón, el monto a la derecha');
            }
            if (!/^con ITBMS · (de hoy|hace \d+ días?)$/.test(hace.textContent.trim().replace(/\s+/g, ' '))) {
                throw new Error('«con ITBMS · hace N días» va en un renglón: ' + hace.textContent);
            }
            if (hace.getBoundingClientRect().top < monto.bottom - 2) {
                throw new Error('lo demás va debajo del monto');
            }
            igual(getComputedStyle(hace).color, 'rgb(107, 118, 144)', 'lo demás, en gris');
            // Entregas: «Lista» en verde oscuro y «Falta mercancía» en ámbar oscuro (se leen sobre blanco).
            const colores = { o_dcasa_estado_lista: 'rgb(15, 107, 60)', o_dcasa_estado_falta: 'rgb(138, 75, 0)' };
            const estados = todos('.o_dcasa_lista_entregas .o_dcasa_estado');
            if (!estados.length) { throw new Error('se esperaba al menos una entrega'); }
            for (const estado of estados) {
                const lista = estado.classList.contains('o_dcasa_estado_lista');
                igual(estado.textContent.trim(), lista ? 'Lista' : 'Falta mercancía', 'el estado');
                igual(getComputedStyle(estado).color, colores[lista ? 'o_dcasa_estado_lista' : 'o_dcasa_estado_falta'],
                      'el color de «' + estado.textContent.trim() + '»');
            }
            // Los bloques de abajo: siete barras (la de hoy, resaltada) y las barras finas de proporción.
            igual(todos('.o_dcasa_semana .o_dcasa_grafico_barra').length, 7, 'las barras de la semana');
            igual(getComputedStyle(en('.o_dcasa_grafico_hoy .o_dcasa_grafico_relleno')).backgroundColor,
                  'rgb(19, 64, 177)', 'la barra de hoy, en el azul de la marca');
            if (parseFloat(getComputedStyle(en('.o_dcasa_grafico_relleno')).borderTopLeftRadius) < 4) {
                throw new Error('las barras van redondeadas');
            }
            const marcas = todos('.o_dcasa_grafico_eje span').map((m) => m.textContent.trim());
            if (marcas.length !== 3 || marcas[0] !== '$0') { throw new Error('la escala de la semana: ' + marcas); }
            const productos = todos('.o_dcasa_top li');
            if (!productos.length) { throw new Error('se esperaba lo más vendido'); }
            for (const producto of productos) {
                if (!producto.querySelector('img') || !producto.querySelector('.o_dcasa_proporcion > span')) {
                    throw new Error('lo más vendido: cada producto con su foto y su barra fina');
                }
            }
            const mayor = en('.o_dcasa_top li .o_dcasa_proporcion');
            const lleno = mayor.firstElementChild.getBoundingClientRect().width;
            if (Math.abs(lleno - mayor.getBoundingClientRect().width) > 1) {
                throw new Error('la barra del más vendido va llena');
            }
            igual(getComputedStyle(mayor).boxShadow, 'none', 'sin sombras');
            for (const tarjeta of todos('.o_dcasa_panel, .o_dcasa_cifra')) {
                igual(getComputedStyle(tarjeta).boxShadow, 'none', 'sistema plano: las tarjetas sin sombra');
            }
            // El Inicio baja con scroll.
            igual(getComputedStyle(raiz()).overflowY, 'auto', 'el Inicio baja con scroll');
            if (raiz().scrollHeight <= raiz().clientHeight) {
                throw new Error('el panel completo no cabe en una pantalla');
            }
            raiz().scrollTop = raiz().scrollHeight;
            await pausa(100);
            if (raiz().scrollTop <= 0) { throw new Error('el Inicio no baja'); }
            sinScrollDeCostado('al fondo');
        """
        for tamano in ('360x740', '390x844', '768x1024', '1024x768', '1366x768', '1920x1080'):
            with self.subTest(tamano=tamano):
                self.probar('gerencia_rol', cuerpo, tamano)

    def test_las_cifras_suben_pero_su_texto_es_el_valor_final_desde_el_primer_momento(self):
        cuerpo = r"""
            await quieto('.o_dcasa_cifra_ventas_hoy .o_dcasa_sube');
            // La hoja: mientras sube, el número se pinta con ::after y el texto real queda en su sitio, sin relleno.
            const muestra = en('.o_dcasa_cifra_valor.o_dcasa_sube');
            const texto = muestra.textContent;
            muestra.dataset.sube = '123';
            const encima = getComputedStyle(muestra, '::after');
            if (!encima.content.startsWith('"123"')) {
                throw new Error('el número que sube se pinta con ::after: ' + encima.content);
            }
            igual(encima.position, 'absolute', 'encima del texto real');
            igual(getComputedStyle(muestra).webkitTextFillColor, 'rgba(0, 0, 0, 0)', 'el texto real, sin relleno');
            igual(encima.webkitTextFillColor, getComputedStyle(muestra).color,
                  'el número que sube, con el color de la cifra');
            igual([muestra.textContent, muestra.innerText], [texto, texto], 'el texto de la etiqueta no cambia');
            delete muestra.dataset.sube;

            // Se abre el Inicio otra vez mirando cada cambio desde antes de que se pinte.
            const mirar = () => {
                const vistos = new Map();
                const anotar = (el) => {
                    if (!el.isConnected || el.closest('[data-vieja]')) { return; }
                    const visto = vistos.get(el) || { textos: new Set(), pintados: [] };
                    visto.textos.add(el.textContent);
                    if (el.dataset.sube !== undefined) { visto.pintados.push(el.dataset.sube); }
                    vistos.set(el, visto);
                };
                const observador = new MutationObserver((cambios) => {
                    for (const cambio of cambios) {
                        if (cambio.type === 'attributes') { anotar(cambio.target); }
                        for (const nodo of cambio.addedNodes || []) {
                            if (nodo.nodeType === 1) {
                                if (nodo.matches('.o_dcasa_sube')) { anotar(nodo); }
                                nodo.querySelectorAll('.o_dcasa_sube').forEach(anotar);
                            }
                        }
                    }
                });
                observador.observe(document.body, { subtree: true, childList: true, characterData: true,
                                                    attributes: true, attributeFilter: ['data-sube'] });
                return { vistos, observador };
            };
            let { vistos, observador } = mirar();
            await reabrir();
            await esperar(() => [...vistos.values()].some((v) => v.pintados.length) && !en('[data-sube]'),
                          'que las cifras suban y terminen');
            observador.disconnect();
            let subieron = 0;
            for (const [el, visto] of vistos) {
                if (visto.textos.size !== 1) {
                    throw new Error('el texto de una cifra cambió mientras subía: ' + [...visto.textos].join(' → '));
                }
                igual(el.textContent, [...visto.textos][0], 'el texto al terminar');
                if (visto.pintados.some((pintado) => pintado !== el.textContent.trim())) { subieron++; }
                // Lo que se pinta a medias tiene la forma del valor final (dinero con dinero, enteros con enteros).
                const forma = (t) => t.trim().replace(/\d/g, '9').replace(/9(,?9)*/g, 'N');
                for (const pintado of visto.pintados) {
                    igual(forma(pintado), forma(el.textContent), 'la forma de lo que se pinta: ' + pintado);
                }
            }
            if (!subieron) { throw new Error('ninguna cifra subió: se esperaban números a medias en data-sube'); }
            const ventas = en('.o_dcasa_cifra_ventas_hoy .o_dcasa_sube');
            if (!vistos.get(ventas) || !vistos.get(ventas).pintados.length) {
                throw new Error('la venta de hoy tenía que subir');
            }
            if (!/^\$[\d,]+\.\d{2}$/.test(ventas.textContent.trim()) || ventas.textContent.trim() === '$0.00') {
                throw new Error('la venta de hoy: ' + ventas.textContent);
            }
            igual(Number(ventas.dataset.valor) > 0, true, 'el valor de la venta de hoy');
            sinScrollDeCostado('después de subir');

            // Quien pidió menos movimiento en su aparato no ve números subiendo.
            const coincide = Object.getOwnPropertyDescriptor(MediaQueryList.prototype, 'matches');
            Object.defineProperty(MediaQueryList.prototype, 'matches', { configurable: true, get() {
                const esDeMovimiento = this.media.includes('prefers-reduced-motion');
                return esDeMovimiento ? this.media.includes('reduce') : coincide.get.call(this);
            } });
            ({ vistos, observador } = mirar());
            await reabrir();
            await pausa(400);
            observador.disconnect();
            Object.defineProperty(MediaQueryList.prototype, 'matches', coincide);
            if (!vistos.size) { throw new Error('no se vieron las cifras al abrir con menos movimiento'); }
            for (const [el, visto] of vistos) {
                if (visto.pintados.length || visto.textos.size !== 1) {
                    throw new Error('con menos movimiento las cifras no suben: ' + el.textContent);
                }
            }
        """
        for tamano in ('390x844', '1366x768'):
            with self.subTest(tamano=tamano):
                self.probar('gerencia_rol', cuerpo, tamano)

    def test_la_vendedora_en_el_celular_y_en_la_computadora(self):
        cuerpo = r"""
            await quieto('.o_dcasa_cifra');
            const celular = window.innerWidth < 768;
            igual(todos('.o_dcasa_cifra .o_dcasa_cifra_titulo').map((t) => t.textContent.trim()),
                  ['Vendido hoy', 'Mis cotizaciones'], 'sus dos cifras');
            // Ni paneles de la tienda ni contadores: su Inicio tiene menos bloques.
            for (const fuera of ['.o_dcasa_listas', '.o_dcasa_saltos', '.o_dcasa_ventas', '.o_dcasa_inicio_fila']) {
                if (en(fuera)) { throw new Error('la vendedora no debe ver ' + fuera); }
            }
            sinScrollDeCostado('la vendedora');
            botonesDelSaludo('la vendedora');
            document.body.classList.add('o_touch_device');
            botonesDelSaludo('la vendedora en pantalla táctil');
            document.body.classList.remove('o_touch_device');
            igual(getComputedStyle(en('.o_dcasa_atajos_tamano')).display !== 'none', celular, 'el selector de tamaño');
            igual(getComputedStyle(raiz()).overflowY, 'auto', 'el Inicio baja con scroll');
            // La cifra de lo que vendió hoy: el texto es el valor final (un monto), no un número a medias.
            const vendido = en('.o_dcasa_cifra_ventas_hoy .o_dcasa_cifra_valor');
            if (!/^\$[\d,]+\.\d{2}$/.test(vendido.textContent.trim()) || vendido.textContent.trim() === '$0.00') {
                throw new Error('lo vendido hoy: ' + vendido.textContent);
            }
            if (!celular) { return console.log('test successful'); }
            // En el celular: tres botones, de a dos; el que queda solo mide media fila, no entera.
            const botones = todos('.o_dcasa_inicio_accesos .btn');
            if (botones.length % 2) {
                const ancho = botones.at(-1).getBoundingClientRect().width;
                if (ancho > en('.o_dcasa_inicio_accesos').getBoundingClientRect().width * 0.6) {
                    throw new Error('el botón que queda solo no ocupa la fila entera: ' + Math.round(ancho));
                }
            }
            // Los tres tamaños también son suyos.
            const porTamano = { compacto: Math.min(3, todos('.o_dcasa_atajo').length), detalle: 2, grande: 1 };
            for (const clave of ['detalle', 'grande', 'compacto']) {
                en('.o_dcasa_atajos_tamano_' + clave).click();
                await esperar(() => en('.o_dcasa_atajos').dataset.modo === clave, 'los accesos en ' + clave);
                igual(accesosPorFila(), porTamano[clave], 'accesos por fila en ' + clave);
                sinScrollDeCostado(clave);
            }
            localStorage.removeItem(CLAVE);
        """
        for tamano in ('390x844', '1366x768'):
            with self.subTest(tamano=tamano):
                self.probar('vendedora_rol', cuerpo, tamano)
