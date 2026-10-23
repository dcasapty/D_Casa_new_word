"""Adelantos y préstamos en un navegador de verdad, en computadora y en celular: la lista con el saldo y el formulario
con su aviso, sin salirse de lado."""
from datetime import date

from odoo.tests import HttpCase, new_test_user, tagged

JS = """
(async () => {
    const esperar = async (fn, que, ms = 20000) => {
        const inicio = Date.now();
        while (Date.now() - inicio < ms) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error("Nómina: no apareció " + que);
    };
    for (const texto of %(textos)s) {
        const buscado = texto.toLowerCase();
        await esperar(() => document.body.innerText.toLowerCase().includes(buscado), "«" + texto + "»");
    }
    await new Promise((ok) => setTimeout(ok, 300));
    if (document.documentElement.scrollWidth > window.innerWidth + 2) {
        throw new Error("Nómina: la pantalla se sale de lado");
    }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""


@tagged('post_install', '-at_install')
class TestPantallasNomina(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        new_test_user(cls.env, login='pantalla_nomina', password='pantalla_nomina', name='Pantalla Nómina',
                      groups='base.group_user,dcasa_base.group_gerencia')
        empleado = cls.env['hr.employee'].create({'name': 'COLABORADORA DE PRUEBA PANTALLA', 'wage': 800})
        cls.prestamo = cls.env['dcasa.nomina.prestamo'].create({
            'empleado_id': empleado.id, 'monto': 240.0, 'cuotas': 3, 'fecha': date(2030, 2, 1),
            'motivo': 'Útiles escolares'})

    def _ver(self, ruta, textos, tamano):
        self.browser_size = tamano
        self.browser_js(ruta, JS % {'textos': repr(list(textos)).replace("'", '"')}, ready='odoo.isReady',
                        login='pantalla_nomina', timeout=90)

    def test_lista_y_formulario_de_adelantos(self):
        for tamano in ('1366x768', '390x844'):
            with self.subTest(tamano=tamano):
                self._ver('/odoo/action-dcasa_nomina.accion_prestamos', ['COLABORADORA DE PRUEBA PANTALLA'], tamano)
                self._ver(f'/odoo/action-dcasa_nomina.accion_prestamos/{self.prestamo.id}',
                          ['Por autorizar', 'Autorizar', 'Descuento por quincena', '80.00'], tamano)
