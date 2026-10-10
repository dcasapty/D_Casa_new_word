"""El atajo «Conversaciones» del Inicio (dcasa_interfaz): a un clic del chat, con cuántas esperan lectura."""
from unittest.mock import patch

from odoo.tests import TransactionCase, new_test_user, tagged

from .test_panel_interfaz import PanelUiCase

CONVERSACION = 'dcasa.conversacion'


@tagged('post_install', '-at_install')
class TestAtajoDeConversaciones(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = new_test_user(cls.env, login='atajo_vendedora',
                                      groups='base.group_user,sales_team.group_sale_salesman')

    def atajos(self, usuario):
        datos = self.env['dcasa.tablero'].with_user(usuario).obtener_datos()
        return {a['clave']: a for a in datos['atajos']}

    def test_la_vendedora_tiene_el_atajo_que_abre_el_panel_del_chat(self):
        atajo = self.atajos(self.vendedora)['conversaciones']
        self.assertEqual(atajo['accion'], 'dcasa_conversaciones.accion_conversaciones')
        self.assertEqual(self.env.ref(atajo['accion']).tag, 'dcasa_conversaciones',
                         'es el panel nuevo, no la lista vieja')
        self.assertEqual((atajo['titulo'], atajo['icono']), ('Conversaciones', 'fa-comments'))

    def test_dice_cuantas_esperan_lectura_o_que_todo_esta_al_dia(self):
        with patch.object(self.env.registry[CONVERSACION], '_ids_con_sin_leer', return_value=[]):
            atajo = self.atajos(self.vendedora)['conversaciones']
        self.assertEqual((atajo['detalle'], atajo['cuenta']), ('Todo al día', 0))
        with patch.object(self.env.registry[CONVERSACION], '_ids_con_sin_leer', return_value=[4, 5, 6]):
            atajo = self.atajos(self.vendedora)['conversaciones']
        self.assertEqual((atajo['detalle'], atajo['cuenta']), ('3 sin leer', 3))

    def test_quien_no_es_del_equipo_de_ventas_no_lo_ve(self):
        interno = new_test_user(self.env, login='atajo_interno', groups='base.group_user')
        self.assertNotIn('conversaciones', self.atajos(interno))


@tagged('post_install', '-at_install')
class TestAtajosEnElNavegador(PanelUiCase):
    """El Inicio en Chromium: los dos atajos están a la vista y cada uno abre su pantalla."""

    def test_el_inicio_ofrece_productos_y_conversaciones_y_cada_uno_abre_su_pantalla(self):
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
            const atajo = (clave) => document.querySelector(".o_dcasa_atajo_" + clave);
            for (const clave of ["productos", "conversaciones"]) {
                await esperar(() => atajo(clave), "el atajo " + clave);
            }
            // Conversaciones: la vendedora tiene mensajes sin leer y el atajo lo dice.
            const cuenta = await esperar(
                () => atajo("conversaciones").querySelector(".o_dcasa_atajo_cuenta"), "la cuenta");
            if (!/^\\d+$/.test(cuenta.textContent.trim()) || Number(cuenta.textContent) < 1) {
                throw new Error("La cuenta de sin leer no es un número: " + cuenta.textContent);
            }
            atajo("conversaciones").click();
            await esperar(() => document.querySelector(".o_dcj .o_dcj_fila"), "el panel del chat");
            // Vuelve al Inicio y abre Productos: la lista (no las tarjetas), con las categorías a la izquierda,
            // la columna de stock y los botones de orden.
            history.back();
            await esperar(() => atajo("productos"), "el Inicio otra vez");
            atajo("productos").click();
            await esperar(() => document.querySelector(".o_list_view .o_data_row"), "la lista de productos");
            await esperar(() => document.querySelector(".o_search_panel"), "las categorías a la izquierda");
            console.log("test successful");
})();
        """, url='/odoo')
