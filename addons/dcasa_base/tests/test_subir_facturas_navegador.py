"""«Subir» en Facturas, solo a quien puede hacer facturas ahí (cabo suelto del 2026-10-22; js/subir_facturas.js).

La vendedora ya no veía «Nuevo» en Facturación › Facturas (el servidor le pone ``create="0"``) y el servidor le
rechaza la factura suelta, pero todavía le salía «Subir». Ahora tampoco, en la lista ni en las tarjetas; Caja lo sigue
viendo."""
from odoo.tests import HttpCase, new_test_user, tagged

CODIGO = """
(async () => {
    const esperar = async (fn, que, intentos = 150) => {
        for (let i = 0; i < intentos; i++) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error('No apareció: ' + que);
    };
    await esperar(() => document.querySelector('.o_VISTA_view .o_control_panel'), 'la vista de facturas');
    await new Promise((ok) => setTimeout(ok, 300));
    const subir = [...document.querySelectorAll('.o_control_panel button')]
        .filter((b) => b.classList.contains('o_button_upload_bill') || b.textContent.trim() === 'Subir'
                       || b.textContent.trim() === 'Upload');
    const nuevo = document.querySelector('.o_control_panel .o_list_button_add, .o_control_panel .o-kanban-button-new');
    if (VE_SUBIR && !subir.length) { throw new Error('Falta «Subir»'); }
    if (!VE_SUBIR && subir.length) { throw new Error('La vendedora todavía ve «Subir»'); }
    if (!VE_SUBIR && nuevo) { throw new Error('La vendedora ve «Nuevo»'); }
    // Soltar un archivo encima de la lista tampoco abre la zona para subir (a Caja, sí).
    const zona = await esperar(() => document.querySelector('.o_VISTA_renderer'), 'la lista o las tarjetas');
    const datos = new DataTransfer();
    datos.items.add(new File(['%PDF-1.4'], 'factura.pdf', { type: 'application/pdf' }));
    zona.dispatchEvent(new DragEvent('dragenter', { bubbles: true, cancelable: true, dataTransfer: datos }));
    await new Promise((ok) => setTimeout(ok, 300));
    const abierta = Boolean(document.querySelector('.o_drop_area'));
    if (abierta !== VE_SUBIR) {
        throw new Error(VE_SUBIR ? 'A Caja no se le abre la zona para soltar archivos'
                                 : 'A la vendedora se le abrió la zona para soltar archivos');
    }
    console.log('test successful');
})();
"""


@tagged('post_install', '-at_install')
class TestSubirFacturasEnElNavegador(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = new_test_user(cls.env, login='vend_subir', name='Vendedora Subir',
                                      groups='base.group_user,dcasa_base.group_vendedora')
        cls.caja = new_test_user(cls.env, login='caja_subir', name='Caja Subir',
                                 groups='base.group_user,dcasa_base.group_caja')

    def _probar(self, login, vista, ve_subir):
        codigo = CODIGO.replace('VISTA', vista).replace('VE_SUBIR', 'true' if ve_subir else 'false')
        self.browser_js(f'/odoo/action-account.action_move_out_invoice_type?view_type={vista}', codigo, login=login,
                        timeout=90)

    def test_la_vendedora_no_ve_subir_en_la_lista(self):
        self._probar('vend_subir', 'list', ve_subir=False)

    def test_la_vendedora_no_ve_subir_en_las_tarjetas(self):
        self._probar('vend_subir', 'kanban', ve_subir=False)

    def test_caja_si_ve_subir(self):
        self._probar('caja_subir', 'list', ve_subir=True)
