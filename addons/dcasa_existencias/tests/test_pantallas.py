"""Las pantallas de bodega en un navegador de verdad, en computadora y en celular: abren, dicen lo que tienen que
decir y no se salen de lado (sin scroll horizontal en el celular)."""
from odoo.tests import HttpCase, tagged

from .comun import crear_usuario

JS = """
(async () => {
    const esperar = async (fn, que, ms = 20000) => {
        const inicio = Date.now();
        while (Date.now() - inicio < ms) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error("Bodega: no apareció " + que);
    };
    const textos = %(textos)s;
    for (const texto of textos) {
        const buscado = texto.toLowerCase();
        await esperar(() => document.body.innerText.toLowerCase().includes(buscado), "«" + texto + "»");
    }
    await new Promise((ok) => setTimeout(ok, 300));
    const ancho = document.documentElement.scrollWidth;
    if (ancho > window.innerWidth + 2) {
        throw new Error("Bodega: la pantalla se sale de lado: " + ancho + " > " + window.innerWidth);
    }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""


@tagged('post_install', '-at_install')
class TestPantallasBodega(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gerencia = crear_usuario(cls.env, 'pantalla_bodega_gerencia', 'dcasa_base.group_gerencia')
        cls.gerencia.write({'password': 'pantalla_bodega_gerencia'})
        producto = cls.env['product.product'].create({
            'name': 'ROPERO DE PRUEBA PANTALLA', 'is_storable': True, 'standard_price': 120.0})
        almacen = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.env['stock.quant']._update_available_quantity(producto, almacen.lot_stock_id, 4)
        scrap = cls.env['stock.scrap'].create({'product_id': producto.id, 'scrap_qty': 1, 'dcasa_motivo': 'dano',
                                               'location_id': almacen.lot_stock_id.id,
                                               'dcasa_nota': 'Llegó rayado'})
        scrap.action_validate()

    def _ver(self, ruta, textos, tamano):
        self.browser_size = tamano
        self.browser_js(ruta, JS % {'textos': repr(list(textos)).replace("'", '"')}, ready='odoo.isReady',
                        login='pantalla_bodega_gerencia', timeout=90)

    def test_mermas_en_computadora_y_celular(self):
        for tamano in ('1366x768', '390x844'):
            with self.subTest(tamano=tamano):
                self._ver('/odoo/action-dcasa_existencias.accion_mermas',
                          ['ROPERO DE PRUEBA PANTALLA', 'Daño'], tamano)

    def test_mermas_del_mes_dice_si_faltan_las_cuentas_y_el_tope(self):
        for tamano in ('1366x768', '390x844'):
            with self.subTest(tamano=tamano):
                self._ver('/odoo/action-dcasa_existencias.accion_resumen',
                          ['Mermas de', 'Falta elegir', 'Pasan del tope', 'El año, mes a mes'], tamano)

    def test_bitacora_y_ajustes_de_bodega(self):
        for tamano in ('1366x768', '390x844'):
            with self.subTest(tamano=tamano):
                self._ver('/odoo/action-dcasa_existencias.accion_bitacora', ['ROPERO DE PRUEBA PANTALLA'], tamano)
                self._ver('/odoo/action-dcasa_existencias.accion_config',
                          ['Faltan las cuentas contables', 'Vienen apagadas'], tamano)
