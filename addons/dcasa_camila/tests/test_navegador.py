"""Camila en el navegador, como la usa el equipo de marketing (pedido de la dueña, 2026-11-06).

* **EL SCROLL** (el bug de siempre: Odoo corta las pantallas propias con ``overflow: hidden``): la pantalla tiene
  ``overflow-y: auto`` y baja de verdad con un borrador largo (8 productos y la vista previa entera).
* La vista previa del correo tal como se ve en el celular, editar el asunto y quitar un producto.
* Sin la clave de campañas, la pantalla lo dice en palabras sencillas y no deja enviar.
* En el celular: sin scroll de lado. Y la casilla del permiso en la ficha del cliente."""
from odoo.addons.dcasa_contactos.tests.test_fijo_y_copiar_navegador import COMUN
from odoo.tests import HttpCase, tagged

from .comun import CamilaComun

PANTALLA = """
    const pantalla = await esperar(() => document.querySelector('.o_action.o_camila'), 'la pantalla de Camila');
    const marco = await esperar(() => document.querySelector('iframe.o_camila_previa_correo'), 'la vista previa');
    await esperar(() => marco.contentDocument
                        && marco.contentDocument.querySelectorAll('table.o_camila_producto').length === 8,
                  'los 8 productos en la vista previa');
    await esperar(() => marco.getBoundingClientRect().height > 1500, 'que la vista previa muestre el correo entero');
    sinErrores();
    // EL SCROLL: la pantalla baja con la rueda y con el dedo (overflow-y: auto) y de verdad llega abajo.
    const desborde = getComputedStyle(pantalla).overflowY;
    if (!['auto', 'scroll'].includes(desborde)) {
        throw new Error('Camila no baja con scroll: la pantalla tiene overflow-y: ' + desborde);
    }
    if (pantalla.scrollHeight <= pantalla.clientHeight + 50) {
        throw new Error('La pantalla no es más alta que la ventana: no se puede probar el scroll');
    }
    pantalla.scrollTop = 100000;
    await new Promise((ok) => setTimeout(ok, 150));
    if (pantalla.scrollTop < 50) { throw new Error('Camila no baja con scroll'); }
    const historial = document.querySelector('.o_camila_historial');
    if (historial.getBoundingClientRect().bottom > window.innerHeight + 2) {
        throw new Error('Abajo del todo, el historial sigue cortado');
    }
    pantalla.scrollTop = 0;
    if (document.documentElement.scrollWidth > window.innerWidth + 1) {
        throw new Error('Hay scroll de lado: ' + document.documentElement.scrollWidth + ' > ' + window.innerWidth);
    }
"""

EDITAR = """
    // Sin la clave de campañas: lo dice en palabras sencillas y no deja enviar.
    const bloqueos = document.querySelector('.o_camila_bloqueos');
    if (!bloqueos || !bloqueos.textContent.includes('Todavía no está la clave de campañas de Resend')) {
        throw new Error('No dice que falta la clave');
    }
    if (!document.querySelector('.o_camila_enviar').disabled) { throw new Error('Sin clave dejó enviar'); }
    if (!document.querySelector('.o_camila_cifra_permiso').textContent.includes('2')) {
        throw new Error('No dice a cuántos clientes con permiso le llegaría');
    }
    // Editar el asunto: se guarda y la vista previa cambia.
    const asunto = document.querySelector('input.o_camila_asunto');
    asunto.value = 'Lo nuevo para tu casa';
    asunto.dispatchEvent(new Event('input', { bubbles: true }));
    await esperar(() => !document.querySelector('.o_camila_guardar').disabled, 'que se pueda guardar');
    document.querySelector('.o_camila_guardar').click();
    await esperar(() => document.querySelector('.o_camila_asunto_previa').textContent.includes('Lo nuevo para tu casa'),
                  'el asunto nuevo en la vista previa');
    await esperar(() => {
        const doc = document.querySelector('iframe.o_camila_previa_correo').contentDocument;
        return doc && doc.querySelector('h1') && doc.querySelector('h1').textContent.includes('Lo nuevo para tu casa');
    }, 'el asunto nuevo dentro del correo');
    // Quitar un producto.
    document.querySelector('li.o_camila_producto .o_camila_quitar').click();
    await esperar(() => document.querySelectorAll('li.o_camila_producto').length === 7, 'que salga el producto');
    sinErrores();
"""

FICHA = """
    await esperar(() => document.querySelector('.o_dcasa_promos'), 'el permiso en la ficha');
    const caja = document.querySelector('.o_dcasa_promos');
    if (!caja.textContent.includes('Márcalo solo si dice que sí')) { throw new Error('Falta cómo preguntarle'); }
    const casilla = caja.querySelector('input[type="checkbox"]');
    casilla.click();
    await esperar(() => casilla.checked, 'que la casilla quede marcada');
    // Hay un cambio sin guardar: los botones de la nube dejan de estar ocultos.
    await esperar(() => !document.querySelector('.o_form_status_indicator_buttons').classList.contains('invisible'),
                  'que el cambio quede pendiente de guardar');
    document.querySelector('.o_form_button_save').click();
    await esperar(() => document.querySelector('.o_dcasa_promos').textContent.includes('Dijo que sí el'),
                  'que quede con la fecha');
    sinErrores();
"""


@tagged('post_install', '-at_install')
class TestCamilaEnElNavegador(CamilaComun, HttpCase):

    def setUp(self):
        super().setUp()
        self.website.domain = False   # las fotos las sirve este mismo servidor de pruebas
        self.permiso(self.ana, self.beto)
        campana = self.armar()['campana']
        self.Camila.with_user(self.marketing).guardar(
            campana['id'], {'lineas': [{'producto_id': p.id, 'texto': ''} for p in self.productos]})

    def correr(self, cuerpo, url='/odoo/camila', login='zzcm_marketing'):
        codigo = '(async () => {' + COMUN + cuerpo + "sinErrores(); console.log('test successful'); })();"
        self.browser_js(url, codigo, ready='odoo.isReady', login=login, timeout=180)

    def test_la_pantalla_baja_con_scroll_y_se_edita(self):
        self.browser_size = '1366x768'
        self.correr(PANTALLA + EDITAR)

    def test_en_el_celular_tambien_baja_y_sin_scroll_de_lado(self):
        self.browser_size = '390x844'
        self.correr(PANTALLA)

    def test_la_casilla_del_permiso_en_la_ficha(self):
        self.correr(FICHA, url=f'/odoo/contacts/{self.carla.id}', login='zzcm_vendedora')
        self.carla.invalidate_recordset()
        self.assertEqual((self.carla.dcasa_promos_estado, self.carla.dcasa_promos_usuario_id),
                         ('si', self.vendedora))
