"""Camila en el navegador, como la usa el equipo de marketing (pedidos de la dueña, 2026-11-06, etapas 1 y 2).

* **EL SCROLL** (el bug de siempre: Odoo corta las pantallas propias con ``overflow: hidden``): la pantalla tiene
  ``overflow-y: auto`` y baja de verdad con una campaña larga (8 productos). Los diálogos nuevos (Previsualizar, cambiar
  o agregar un producto, Nueva campaña) también bajan con su propio scroll.
* El constructor a todo el ancho (la vista previa ya no roba la mitad de la pantalla): «Previsualizar» abre el correo
  grande, con su asunto y Celular / Computadora.
* «Cambiar» abre el diálogo con buscador, filtros y tarjetas: al elegir, el producto queda en su lugar.
* «Escribir con IA» por producto; si la IA falla, lo dice y ofrece «Reintentar» (nunca en silencio).
* Los chips del público dicen el número en vivo; los botones del correo (al menos uno).
* El tablero de Marketing: «Crear campaña con estos» abre Camila con el borrador nuevo.
* Sin la clave de campañas, la pantalla lo dice en palabras sencillas y no deja enviar. En el celular: sin scroll de
  lado. Y la casilla del permiso en la ficha del cliente."""
import json

from odoo import Command
from odoo.addons.dcasa_brian.models import proveedores as P
from odoo.addons.dcasa_contactos.tests.test_fijo_y_copiar_navegador import COMUN
from odoo.tests import HttpCase, tagged

from .comun import CamilaComun

PANTALLA = """
    const pantalla = await esperar(() => document.querySelector('.o_action.o_camila'), 'la pantalla de Camila');
    await esperar(() => document.querySelectorAll('li.o_camila_producto').length === 8, 'los 8 productos');
    sinErrores();
    // El constructor a todo el ancho: la vista previa no está en la pantalla (se abre con «Previsualizar»).
    if (document.querySelector('.o_camila iframe.o_camila_previa_correo')) {
        throw new Error('La vista previa sigue ocupando la pantalla');
    }
    const cuerpo = document.querySelector('.o_camila_cuerpo').getBoundingClientRect();
    const constructor = document.querySelector('.o_camila_constructor').getBoundingClientRect();
    if (constructor.width < cuerpo.width * 0.9) {
        throw new Error('El constructor no ocupa todo el ancho: ' + constructor.width + ' de ' + cuerpo.width);
    }
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
    const ultimo = document.querySelector('.o_camila_pie_ajuste');
    if (ultimo.getBoundingClientRect().bottom > window.innerHeight + 2) {
        throw new Error('Abajo del todo, lo último sigue cortado');
    }
    pantalla.scrollTop = 0;
    if (document.documentElement.scrollWidth > window.innerWidth + 1) {
        throw new Error('Hay scroll de lado: ' + document.documentElement.scrollWidth + ' > ' + window.innerWidth);
    }
"""

# Un diálogo de Camila baja con su propio scroll (la misma regla que las pantallas).
DIALOGO_CON_SCROLL = """
    const dialogoBaja = async (selector, que) => {
        const contenido = await esperar(() => document.querySelector(selector), que);
        const cuerpoDialogo = contenido.querySelector('.modal-body');
        const estilo = getComputedStyle(cuerpoDialogo).overflowY;
        if (!['auto', 'scroll'].includes(estilo)) {
            throw new Error(que + ': el diálogo no baja con scroll (overflow-y: ' + estilo + ')');
        }
        if (contenido.getBoundingClientRect().bottom > window.innerHeight + 2) {
            throw new Error(que + ': el diálogo se sale de la pantalla');
        }
        if (cuerpoDialogo.scrollHeight > cuerpoDialogo.clientHeight + 20) {
            cuerpoDialogo.scrollTop = 100000;
            await new Promise((ok) => setTimeout(ok, 150));
            if (cuerpoDialogo.scrollTop < 10) { throw new Error(que + ': el diálogo no baja con scroll'); }
        }
        return contenido;
    };
    const cerrarDialogo = async () => {
        // En la computadora es la X; en el celular el diálogo va a pantalla completa y cierra con la flecha.
        document.querySelector('.modal .modal-header .btn-close, .modal .modal-header .oi-arrow-left').click();
        await esperar(() => !document.querySelector('.o_camila_dialogo'), 'que se cierre el diálogo');
    };
"""

CARGADA = """
    await esperar(() => document.querySelector('.o_action.o_camila'), 'la pantalla de Camila');
    await esperar(() => document.querySelectorAll('li.o_camila_producto').length === 8, 'los 8 productos');
"""

PREVIA = """
    document.querySelector('.o_camila_previsualizar').click();
    const previa = await esperar(() => document.querySelector('.o_camila_dialogo_previa'),
                                 'el diálogo de la vista previa');
    const marco = await esperar(() => previa.querySelector('iframe.o_camila_previa_correo'), 'el correo en el diálogo');
    await esperar(() => marco.contentDocument
                        && marco.contentDocument.querySelectorAll('table.o_camila_producto').length === 8,
                  'los 8 productos en la vista previa');
    await esperar(() => marco.getBoundingClientRect().height > 1500, 'que la vista previa muestre el correo entero');
    if (!previa.querySelector('.o_camila_asunto_previa').textContent.includes('Asunto')) {
        throw new Error('La vista previa no dice el asunto');
    }
    await dialogoBaja('.o_camila_dialogo_previa', 'Previsualizar');
    previa.querySelector('.o_camila_ver_computadora').click();
    await esperar(() => previa.querySelector('.o_camila_marco_computadora'), 'la vista de computadora');
    await cerrarDialogo();
"""

EDITAR = """
    // Sin la clave de campañas: lo dice en palabras sencillas y no deja enviar.
    const bloqueos = document.querySelector('.o_camila_bloqueos');
    if (!bloqueos || !bloqueos.textContent.includes('Todavía no está la clave de campañas de Resend')) {
        throw new Error('No dice que falta la clave');
    }
    if (!document.querySelector('.o_camila_enviar').disabled) { throw new Error('Sin clave dejó enviar'); }
    if (!document.querySelector('.o_camila_cifra_permiso').textContent.includes('2')) {
        throw new Error('No dice cuántos clientes dijeron que sí');
    }
    // Editar el asunto: se guarda y la vista previa lo trae.
    const asunto = document.querySelector('input.o_camila_asunto');
    asunto.value = 'Lo nuevo para tu casa';
    asunto.dispatchEvent(new Event('input', { bubbles: true }));
    await esperar(() => !document.querySelector('.o_camila_guardar').disabled, 'que se pueda guardar');
    document.querySelector('.o_camila_guardar').click();
    // Guardado de verdad: sin cambios pendientes y la pantalla ya no está ocupada (Previsualizar se puede tocar).
    await esperar(() => document.querySelector('.o_camila_guardar').disabled
                        && !document.querySelector('.o_camila_previsualizar').disabled, 'que se guarde');
    document.querySelector('.o_camila_previsualizar').click();
    const previaNueva = await esperar(() => document.querySelector('.o_camila_dialogo_previa'), 'la vista previa');
    await esperar(() => previaNueva.querySelector('.o_camila_asunto_previa').textContent
                        .includes('Lo nuevo para tu casa'),
                  'el asunto nuevo en la vista previa');
    await esperar(() => {
        const doc = previaNueva.querySelector('iframe.o_camila_previa_correo').contentDocument;
        return doc && doc.querySelector('h1') && doc.querySelector('h1').textContent.includes('Lo nuevo para tu casa');
    }, 'el asunto nuevo dentro del correo');
    await cerrarDialogo();
    // Quitar un producto.
    document.querySelector('li.o_camila_producto .o_camila_quitar').click();
    await esperar(() => document.querySelectorAll('li.o_camila_producto').length === 7, 'que salga el producto');
    sinErrores();
"""

CAMBIAR = """
    // «Cambiar» abre el diálogo (como «Armar combo»): buscador, filtros y tarjetas; al elegir, queda en su lugar.
    const segundo = document.querySelectorAll('li.o_camila_producto')[1];
    segundo.querySelector('.o_camila_cambiar').click();
    const dialogo = await esperar(() => document.querySelector('.o_camila_dialogo_productos'),
                                  'el diálogo de productos');
    await esperar(() => dialogo.querySelectorAll('.o_camila_tarjeta').length > 0, 'las tarjetas de productos');
    for (const filtro of ['.o_camila_filtro_tienda', '.o_camila_filtro_foto', '.o_camila_filtro_publicado',
                          '.o_camila_filtro_categoria']) {
        if (!dialogo.querySelector(filtro)) { throw new Error('Falta el filtro ' + filtro); }
    }
    const tarjeta = dialogo.querySelector('.o_camila_tarjeta');
    if (!tarjeta.querySelector('img') || !tarjeta.querySelector('.o_camila_tarjeta_precio')
            || !tarjeta.querySelector('.o_camila_tarjeta_existencias')) {
        throw new Error('La tarjeta no trae foto, precio y existencias');
    }
    await dialogoBaja('.o_camila_dialogo_productos', 'Cambiar producto');
    const buscador = dialogo.querySelector('input.o_camila_buscar');
    buscador.value = 'SILLÓN PARA CAMBIAR';
    buscador.dispatchEvent(new Event('input', { bubbles: true }));
    const nuevo = await esperar(() => [...dialogo.querySelectorAll('.o_camila_tarjeta')].find(
        // El nombre sale como lo ve el cliente («Zzcm Sillón Para Cambiar»).
        (t) => t.textContent.toUpperCase().includes('SILLÓN PARA CAMBIAR') && !t.disabled),
        'el sillón en el buscador');
    nuevo.click();
    await esperar(() => !document.querySelector('.o_camila_dialogo_productos'), 'que se cierre el diálogo');
    await esperar(() => document.querySelectorAll('li.o_camila_producto')[1].textContent.toUpperCase()
                        .includes('SILLÓN PARA CAMBIAR'), 'el sillón en el lugar del producto cambiado');
    sinErrores();
"""

IA = """
    // «Escribir con IA» de un producto: la línea nueva queda en su caja.
    const primero = document.querySelector('li.o_camila_producto');
    primero.querySelector('.o_camila_ia_linea').click();
    await esperar(() => document.querySelector('li.o_camila_producto textarea.o_camila_linea').value
                        .includes('Para tu sala, cómoda y firme'), 'la línea que escribió la IA');
    // Si la IA falla: lo dice y ofrece «Reintentar».
    document.querySelector('li.o_camila_producto .o_camila_ia_linea').click();
    // El aviso sale junto al producto (no arriba, fuera de la vista), con «Reintentar».
    const error = await esperar(() => document.querySelector('li.o_camila_producto .o_camila_ia_error'),
                                'el aviso de que la IA falló, junto al producto');
    if (!error.querySelector('.o_camila_ia_reintentar')) { throw new Error('Falta «Reintentar»'); }
    sinErrores();
"""

PUBLICO = """
    // Los chips del público: con su número en vivo; al tocar uno, queda elegido y el total se pone al día.
    const chip = await esperar(() => document.querySelector('.o_camila_chip[data-chip="compraron"]'),
                               'el chip «Compraron»');
    if (chip.querySelector('.o_camila_chip_n').textContent.trim() === '') {
        throw new Error('El chip no dice su número');
    }
    chip.click();
    await esperar(() => document.querySelector('.o_camila_chip[data-chip="compraron"].o_activa'), 'el chip elegido');
    await esperar(() => document.querySelector('.o_camila_publico_n').textContent.trim() === '0',
                  'que el total diga los que compraron (ninguno)');
    // Carla compró pero no dijo que sí: queda fuera y la pantalla dice cuántos y por qué (nunca quién).
    await esperar(() => document.querySelector('.o_camila_fuera')
                        && document.querySelector('.o_camila_fuera').textContent.includes('No han dicho que sí'),
                  'cuántos quedan fuera y por qué');
    if (document.querySelector('.o_camila_fuera').textContent.includes('carla')) {
        throw new Error('La pantalla muestra a quién deja fuera');
    }
    // Los botones del correo: no deja quedarse sin ninguno.
    document.querySelector('.o_camila_boton_whatsapp').click();
    await esperar(() => document.querySelector('.o_camila_error'), 'el aviso de que hace falta un botón');
    await esperar(() => document.querySelector('.o_camila_boton_whatsapp').checked, 'que WhatsApp siga marcado');
    document.querySelector('.o_camila_error').remove();
"""

MARKETING = """
    const boton = await esperar(() => document.querySelector('.o_camila_desde_marketing[data-tema="stock"]'),
                                'el botón «Crear campaña con estos» en el tablero de Marketing');
    boton.click();
    await esperar(() => document.querySelector('.o_action.o_camila'), 'Camila con la campaña nueva');
    await esperar(() => document.querySelector('.o_camila_constructor .o_camila_detalle')
                        && document.querySelector('.o_camila_constructor .o_camila_detalle').textContent
                            .includes('Lo que más hay en stock'), 'la campaña del stock');
    await esperar(() => document.querySelectorAll('li.o_camila_producto').length > 0, 'sus productos');
    sinErrores();
"""

FICHA = """
    await esperar(() => document.querySelector('.o_dcasa_promos'), 'el permiso en la ficha');
    const caja = document.querySelector('.o_dcasa_promos');
    if (!caja.textContent.includes('Se activa sola cuando le agregas su correo')) { throw new Error('Falta la ayuda'); }
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
        self.sillon = self.producto('ZZCM SILLÓN PARA CAMBIAR', precio=210.0)
        campana = self.armar()['campana']
        self.Camila.with_user(self.marketing).guardar(
            campana['id'], {'lineas': [{'producto_id': p.id, 'texto': ''} for p in self.productos]})

    def correr(self, cuerpo, url='/odoo/camila', login='zzcm_marketing'):
        codigo = ('(async () => {' + COMUN + DIALOGO_CON_SCROLL + cuerpo
                  + "sinErrores(); console.log('test successful'); })();")
        self.browser_js(url, codigo, ready='odoo.isReady', login=login, timeout=180)

    def test_la_pantalla_baja_con_scroll_y_se_edita(self):
        self.browser_size = '1366x768'
        self.correr(PANTALLA + PREVIA + EDITAR)

    def test_en_el_celular_tambien_baja_y_sin_scroll_de_lado(self):
        self.browser_size = '390x844'
        self.correr(PANTALLA + PREVIA)

    def test_cambiar_un_producto_en_el_dialogo(self):
        self.browser_size = '1366x768'
        self.correr(CARGADA + CAMBIAR)
        campana = self.Camila._abierta()
        self.assertEqual(campana.linea_ids[1].producto_id, self.sillon, 'En el lugar del que se cambió')

    def test_la_ia_escribe_y_si_falla_lo_dice(self):
        self.browser_size = '1366x768'
        P.fijar_guion([json.dumps({'linea': 'Para tu sala, cómoda y firme.'})])
        self.correr(CARGADA + IA)

    def test_los_chips_del_publico_y_los_botones(self):
        self.browser_size = '1366x768'
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.carla.id,
            'invoice_line_ids': [Command.create({'product_id': self.productos[0].product_variant_id.id,
                                                 'quantity': 1, 'price_unit': 100.0, 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        self.correr(CARGADA + PUBLICO)
        self.assertEqual(self.Camila._abierta().publico, 'compraron')
        self.assertTrue(self.Camila._abierta().boton_whatsapp)

    def test_crear_campana_desde_el_tablero_de_marketing(self):
        self.browser_size = '1366x768'
        self.env['stock.quant']._update_available_quantity(
            self.productos[0].product_variant_id, self.bodega.lot_stock_id, 100000)
        antes = len(self.Camila._abiertas())
        self.correr(MARKETING, url='/odoo/action-dcasa_marketing.accion_marketing')
        self.assertEqual(len(self.Camila._abiertas()), antes + 1)
        self.assertEqual(self.Camila._abiertas()[:1].tema, 'stock')

    def test_la_casilla_del_permiso_en_la_ficha(self):
        self.correr(FICHA, url=f'/odoo/contacts/{self.carla.id}', login='zzcm_vendedora')
        self.carla.invalidate_recordset()
        self.assertEqual((self.carla.dcasa_promos_estado, self.carla.dcasa_promos_usuario_id),
                         ('si', self.vendedora))
