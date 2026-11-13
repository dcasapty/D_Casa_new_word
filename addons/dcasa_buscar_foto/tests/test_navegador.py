"""«Busca con una foto» en el navegador (static/src/js/buscar_foto.js): la foto se achica antes de subirla (lado mayor
de 1024 px, JPEG), se ve «Buscando muebles parecidos…», va con un token CSRF y el input no se queda con la foto."""
from odoo.tests import HttpCase, tagged

# Una «foto» de 3000 × 2000 en PNG (como una captura grande); se intercepta el envío para mirar lo que saldría.
ELEGIR_UNA_FOTO = """
(async () => {
    const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
    for (let i = 0; i < 100 && document.body.getAttribute('is-ready') !== 'true'; i++) { await esperar(50); }
    const input = document.querySelector('%(selector)s');
    if (!input) { throw new Error('No está el botón de la cámara'); }
    if (input.type !== 'file' || input.accept !== 'image/*' || input.name) {
        throw new Error('El input no es el esperado');
    }
    const lienzo = document.createElement('canvas');
    lienzo.width = 3000;
    lienzo.height = 2000;
    const ctx = lienzo.getContext('2d');
    ctx.fillStyle = '#1340B1';
    ctx.fillRect(0, 0, 3000, 2000);
    ctx.fillStyle = '#FED00F';
    ctx.fillRect(600, 400, 1800, 1200);
    const blob = await new Promise((ok) => lienzo.toBlob(ok, 'image/png'));
    const lista = new DataTransfer();
    lista.items.add(new File([blob], 'captura.png', { type: 'image/png' }));
    let enviado = null;
    HTMLFormElement.prototype.submit = function () { enviado = this; };
    input.files = lista.files;
    input.dispatchEvent(new Event('change', { bubbles: true }));
    for (let i = 0; i < 200 && !enviado; i++) { await esperar(50); }
    if (!enviado) { throw new Error('La foto no se envió'); }
    const capa = document.querySelector('.o_dcasa_foto_cargando');
    if (!capa || !capa.textContent.includes('Buscando muebles parecidos…')) {
        throw new Error('No se ve «Buscando…»');
    }
    if (capa.getAttribute('role') !== 'status') { throw new Error('El lector de pantalla no lo anuncia'); }
    if (enviado.getAttribute('action') !== '/shop/foto' || enviado.method !== 'post') {
        throw new Error('Va a otro lado');
    }
    const datos = new FormData(enviado);
    if (!datos.get('csrf_token')) { throw new Error('Sin token CSRF'); }
    if ([...datos.keys()].sort().join(',') !== 'csrf_token,foto') {
        throw new Error('Campos de más: ' + [...datos.keys()]);
    }
    const base64 = datos.get('foto');
    if (!base64.startsWith('/9j/')) { throw new Error('No salió en JPEG'); }
    const img = new Image();
    img.src = 'data:image/jpeg;base64,' + base64;
    await img.decode();
    if (img.naturalWidth !== 1024 || img.naturalHeight !== 683) {
        throw new Error('Medidas: ' + img.naturalWidth + 'x' + img.naturalHeight);
    }
    if (base64.length > 400000) { throw new Error('Pesa demasiado: ' + base64.length); }
    if (input.value) { throw new Error('El input se quedó con la foto'); }
    console.log('test successful');
})().catch((e) => console.error(e && e.message ? e.message : String(e)));
"""


@tagged('post_install', '-at_install')
class TestBuscarFotoNavegador(HttpCase):

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param('dcasa_buscar_foto.activo', 'True')

    def test_en_la_pagina_la_foto_se_achica_y_se_ve_buscando(self):
        self.browser_js('/shop/foto', ELEGIR_UNA_FOTO % {'selector': '.o_dcasa_foto_pagina .o_dcasa_foto_archivo'},
                        timeout=120)

    def test_desde_la_barra_de_la_tienda(self):
        selector = '.o_wsale_products_searchbar_form .o_dcasa_foto_archivo'
        self.browser_js('/shop', ELEGIR_UNA_FOTO % {'selector': selector}, timeout=120)
