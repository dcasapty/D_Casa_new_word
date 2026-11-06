"""La calculadora en el navegador, como la usa una vendedora (pedido de la dueña, 2026-11-06).

* Busca, ve el precio con su desglose, copia el texto para el cliente y la pantalla **baja con scroll** (el problema de
  siempre: Odoo corta las pantallas propias con ``overflow: hidden``).
* No encuentra un lugar: «¿Quisiste decir…?» y «Agregar este lugar» (queda su nombre).
* Calcula por kilómetros.
* En el celular: 16 px de margen y sin scroll de lado.
* Sin datos, la pantalla dice cómo cargarlos. Y por RPC la vendedora no cambia la tarifa."""
from odoo.addons.dcasa_contactos.tests.test_fijo_y_copiar_navegador import COMUN
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tests.common import JsonRpcException

from .common import importar

ESCRIBIR = """
    const escribir = async (selector, texto) => {
        const campo = await esperar(() => document.querySelector(selector), 'el campo ' + selector);
        campo.value = texto;
        campo.dispatchEvent(new Event('input', { bubbles: true }));
        return campo;
    };
    const tarjetas = () => [...document.querySelectorAll('.o_dcasa_envios .o_de_tarjeta')];
"""


@tagged('post_install', '-at_install')
class TestCalculadoraEnElNavegador(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = new_test_user(cls.env, login='vend_calc', password='vend_calc', name='Ana Envíos',
                                      groups='base.group_user,dcasa_base.group_vendedora')
        cls.gerencia = new_test_user(cls.env, login='ger_calc', password='ger_calc', name='Gerencia Calc',
                                     groups='base.group_user,dcasa_base.group_gerencia')

    def cargar_fixture(self):
        importar(self.env, self.gerencia)

    def correr(self, cuerpo, login='vend_calc'):
        codigo = '(async () => {' + COMUN + ESCRIBIR + cuerpo + "sinErrores(); console.log('test successful'); })();"
        self.browser_js('/odoo/envios', codigo, login=login, timeout=120)

    def test_busca_copia_el_precio_y_la_pantalla_baja_con_scroll(self):
        self.cargar_fixture()
        self.correr("""
            await escribir('.o_de_q', 'vla prueba');
            await esperar(() => tarjetas().length === 2, 'las dos tarjetas de Villa Prueba');
            const villa = tarjetas()[0];
            const total = villa.querySelector('.o_de_total').textContent;
            if (!villa.textContent.includes('Villa Prueba') || total !== '$15') {
                throw new Error('La primera tarjeta no es Villa Prueba a $15: ' + villa.textContent);
            }
            if (!villa.querySelector('.o_de_desglose').textContent.includes('Tarifa base $15')) {
                throw new Error('Falta el desglose');
            }
            const ruta = villa.querySelector('a[href*="google.com/maps/dir"]').href;
            if (!ruta.includes('origin=8.8765881,-79.7867962')) { throw new Error('La ruta no sale de la tienda'); }
            const aviso = document.querySelector('.o_de_aviso');
            if (!aviso || !aviso.textContent.includes('Tarifa en revisión')) {
                throw new Error('Falta el aviso «Tarifa en revisión»');
            }
            villa.querySelector('.o_de_copiar').click();
            await esperar(() => copiado.length === 1, 'que copie el precio');
            if (copiado[0] !== 'Envío a Villa Prueba (Barrio Prueba, La Chorrera): $15.') {
                throw new Error('Copió otra cosa: ' + copiado[0]);
            }
            await esperar(() => villa.querySelector('.o_de_copiar').textContent.includes('Copiado'), '«Copiado»');
            // Muchos resultados: la pantalla tiene que bajar con la rueda y con el dedo (overflow-y: auto).
            await escribir('.o_de_q', 'prueba');
            await esperar(() => tarjetas().length >= 7, 'muchas tarjetas');
            const pantalla = document.querySelector('.o_action.o_dcasa_envios');
            const desborde = getComputedStyle(pantalla).overflowY;
            if (!['auto', 'scroll'].includes(desborde)) {
                throw new Error('La calculadora no baja con scroll: overflow-y es ' + desborde);
            }
            if (pantalla.scrollHeight <= pantalla.clientHeight + 50) {
                throw new Error('La pantalla no es más alta que la ventana: no se puede probar el scroll');
            }
            pantalla.scrollTop = 100000;
            await new Promise((ok) => setTimeout(ok, 150));
            if (pantalla.scrollTop < 50) { throw new Error('La calculadora no baja con scroll'); }
            const pie = document.querySelector('.o_de_atribucion');
            if (!pie.textContent.includes('OpenStreetMap (ODbL) y GeoNames (CC BY 4.0)')) {
                throw new Error('Falta la atribución de los mapas');
            }
            if (pie.getBoundingClientRect().bottom > window.innerHeight + 2) {
                throw new Error('Abajo del todo, la atribución sigue cortada');
            }
        """)

    def test_no_lo_encuentra_sugiere_y_agrega_el_lugar(self):
        self.cargar_fixture()
        self.correr("""
            await escribir('.o_de_q', 'pruebaxx zzz');
            const vacio = await esperar(() => document.querySelector('.o_de_no_encontrado'), 'el estado vacío');
            if (!vacio.textContent.includes('¿Quisiste decir…?')) { throw new Error('Falta «¿Quisiste decir…?»'); }
            const sugerencias = [...vacio.querySelectorAll('.o_de_sugerencia')].map((b) => b.textContent.trim());
            if (!sugerencias.includes('Villa Prueba')) { throw new Error('No sugiere Villa Prueba: ' + sugerencias); }
            vacio.querySelector('.o_de_agregar_boton').click();
            const nombre = await esperar(() => document.querySelector('.o_de_agregar input[name="nombre"]'),
                                         'el formulario para agregar');
            if (nombre.value !== 'pruebaxx zzz') { throw new Error('No trae lo que se buscó: ' + nombre.value); }
            await escribir('.o_de_agregar input[name="nombre"]', 'Finca del Ensayo');
            await escribir('.o_de_agregar input[name="alias"]', 'La finquita, Finca E');
            await escribir('.o_de_agregar input[name="km"]', '7.04');
            document.querySelector('.o_de_agregar .o_de_guardar').click();
            await esperar(() => tarjetas().some((t) => t.textContent.includes('Finca del Ensayo')
                                                     && t.textContent.includes('agregado a mano')),
                          'el lugar nuevo en la lista, marcado «agregado a mano»');
            const nueva = tarjetas().find((t) => t.textContent.includes('Finca del Ensayo'));
            if (nueva.querySelector('.o_de_total').textContent !== '$20') {
                throw new Error('El lugar nuevo no tiene su precio: ' + nueva.textContent);
            }
        """)
        lugar = self.env['dcasa.envio.lugar'].search([('name', '=', 'Finca del Ensayo')])
        self.assertEqual((lugar.agregado_por, lugar.km, lugar.dist, lugar.alias, lugar.origen),
                         (self.vendedora, 7.0, 'La Chorrera', 'La finquita\nFinca E', 'mano'))

    def test_calcula_por_kilometros_con_peaje(self):
        self.cargar_fixture()
        self.env['dcasa.envio.tarifa'].search([]).cargo_ids.filtered(lambda c: c.codigo == 'peaje').write(
            {'monto': 3, 'activo': True})
        self.correr("""
            await escribir('.o_de_km_entrada', '15');
            await esperar(() => document.querySelector('.o_de_calc_precio').textContent === '$25', '$25 a 15 km');
            const peaje = document.querySelector('.o_de_km_peaje');
            peaje.checked = true;
            peaje.dispatchEvent(new Event('change', { bubbles: true }));
            await esperar(() => document.querySelector('.o_de_calc_precio').textContent === '$28', '$28 con peaje');
            const desglose = document.querySelector('.o_de_calc .o_de_desglose').textContent;
            if (!desglose.includes('+ Peaje $3')) { throw new Error('Falta el peaje en el desglose: ' + desglose); }
            const tramos = document.querySelectorAll('.o_de_tramo');
            if (tramos.length < 5 || !tramos[1].textContent.includes('$15')) {
                throw new Error('Falta la tabla por tramos');
            }
        """)

    def test_en_el_celular_sin_scroll_de_lado(self):
        self.cargar_fixture()
        self.browser_size = '390x844'
        self.touch_enabled = True
        self.correr("""
            await escribir('.o_de_q', 'hola buenas, cuanto me cobran por llevar un sofa a costa inv?');
            await esperar(() => tarjetas().length >= 1, 'el resultado');
            if (!tarjetas()[0].textContent.includes('Costa Inventada')) {
                throw new Error('No encontró Costa Inventada');
            }
            sinScrollDeLado();
            const pantalla = document.querySelector('.o_action.o_dcasa_envios');
            if (pantalla.scrollWidth > pantalla.clientWidth + 1) {
                throw new Error(`Hay scroll de lado: ${pantalla.scrollWidth} > ${pantalla.clientWidth}`);
            }
            const caja = document.querySelector('.o_de_q').getBoundingClientRect();
            if (caja.left < 15 || window.innerWidth - caja.right < 15) {
                throw new Error(`Sin 16 px de margen: ${caja.left} / ${window.innerWidth - caja.right}`);
            }
            const tarjeta = tarjetas()[0].getBoundingClientRect();
            if (tarjeta.left < 15 || tarjeta.right > window.innerWidth - 15) {
                throw new Error('La tarjeta no deja 16 px de margen');
            }
            if (getComputedStyle(pantalla).overflowY !== 'auto') { throw new Error('En el celular tampoco baja'); }
        """)

    def test_sin_datos_dice_como_cargarlos(self):
        self.correr("""
            const caja = await esperar(() => document.querySelector('.o_de_sin_datos'), 'el aviso sin datos');
            if (!caja.textContent.includes('Pídele a Gerencia')) { throw new Error('No dice a quién pedirlo'); }
            if (document.querySelector('.o_de_cargar')) { throw new Error('La vendedora no carga el archivo'); }
        """)
        self.correr("""
            const boton = await esperar(() => document.querySelector('.o_de_cargar'), 'el botón para cargar');
            if (!boton.textContent.includes('Cargar lugares y tarifa desde el archivo')) {
                throw new Error('El botón no dice qué hace');
            }
            boton.click();
            await esperar(() => document.querySelector('.modal .o_field_binary'), 'el asistente para subir el archivo');
        """, login='ger_calc')

    def test_por_rpc_la_vendedora_no_cambia_la_tarifa(self):
        self.cargar_fixture()
        tarifa = self.env['dcasa.envio.tarifa'].search([])
        self.authenticate('vend_calc', 'vend_calc')
        for metodo, args in (('write', [[tarifa.id], {'minimo': 1}]), ('action_aprobar', [[tarifa.id]]),
                             ('write', [[tarifa.id], {'aprobada': True}])):
            with self.subTest(metodo=metodo), self.assertRaises(JsonRpcException):
                self.make_jsonrpc_request(f'/web/dataset/call_kw/dcasa.envio.tarifa/{metodo}', {
                    'model': 'dcasa.envio.tarifa', 'method': metodo, 'args': args, 'kwargs': {}})
        resultado = self.make_jsonrpc_request('/web/dataset/call_kw/dcasa.envio.tarifa/cotizar_km', {
            'model': 'dcasa.envio.tarifa', 'method': 'cotizar_km', 'args': [15], 'kwargs': {}})
        self.assertEqual(resultado['total_txt'], '$25', 'cotizar sí puede')
        tarifa.invalidate_recordset()
        self.assertEqual((tarifa.minimo, tarifa.aprobada), (10, False))
