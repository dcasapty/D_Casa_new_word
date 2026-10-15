"""Las pantallas propias (reportes, conciliación, «En desarrollo») comparten la raíz ``.o_dc_conta.o_action``.

Odoo pone a todo ``.o_action`` en columna con ``overflow: hidden`` (webclient_layout.scss) y esa regla pesa más que una
clase suelta: sin una regla propia más fuerte la pantalla no baja y sus bloques se encogen (la barra de pestañas sale
cortada y, con muchas filas, el cuadro tapa el menú). Se comprobó en el navegador; aquí se vigila que la regla siga."""
import re
from pathlib import Path

from odoo.tests import TransactionCase, tagged

RAIZ = Path(__file__).resolve().parents[1] / 'static' / 'src'


@tagged('post_install', '-at_install')
class TestPantallasPropias(TransactionCase):

    def _bloque(self, scss, selector):
        """El cuerpo de la regla ``selector { ... }`` (con sus reglas anidadas, sin contarlas aparte)."""
        inicio = scss.index(selector + ' {')
        profundidad, i = 0, scss.index('{', inicio)
        for j in range(i, len(scss)):
            profundidad += {'{': 1, '}': -1}.get(scss[j], 0)
            if profundidad == 0:
                return scss[i + 1:j]
        raise AssertionError('regla sin cerrar')

    def test_las_pantallas_vuelven_a_bajar_con_scroll(self):
        scss = (RAIZ / 'scss' / 'contabilidad.scss').read_text()
        regla = self._bloque(scss, '.o_web_client > .o_action_manager > .o_dc_conta.o_action')
        self.assertRegex(regla, r'overflow-y:\s*auto', 'sin scroll propio la pantalla queda cortada')
        self.assertRegex(regla, r'>\s*\*\s*\{\s*flex-shrink:\s*0', 'los bloques no deben encogerse')

    def test_todas_las_raices_son_o_dc_conta_o_action(self):
        """Si una pantalla nueva usa otra raíz, no recibe la regla de arriba."""
        for xml in ('reportes.xml', 'conciliacion.xml'):
            texto = (RAIZ / 'xml' / xml).read_text()
            raices = re.findall(r'<div class="(o_dc_conta [^"]*)">', texto)
            self.assertTrue(raices, xml)
            for clases in raices:
                self.assertIn('o_action', clases.split(), f'{xml}: {clases}')

    def test_la_barra_de_periodo_es_una_sola_y_las_tarjetas_dicen_su_fecha(self):
        """Los diez reportes comparten UNA barra de atajos (la de ``periodos()``), el atajo activo se resalta y escribir
        una fecha a mano no deja ninguno marcado; cada reporte con tarjetas pone la fecha o el periodo de cada cifra."""
        xml = (RAIZ / 'xml' / 'reportes.xml').read_text()
        js = (RAIZ / 'js' / 'reportes.js').read_text()
        self.assertEqual(xml.count('o_dc_conta_chips'), 1, 'una sola barra de atajos')
        self.assertEqual(xml.count('t-foreach="periodos"'), 1)
        self.assertIn("p.clave === state.periodo ? 'o_activa'", xml)
        editar_a_mano = js[js.index('cambiarFecha(campo, ev) {'):js.index('cambiarReporte(clave) {')]
        self.assertIn('this.state.periodo = null', editar_a_mano, 'escribir una fecha a mano desmarca el atajo')
        self.assertIn('p.clave === "mes"', js, 'abre con «Este mes»')
        patron = r'<t t-name="dcasa_contabilidad\.Reportes\.(\w+)">([\s\S]*?)(?=\n    <t t-name=|\n</templates>)'
        bloques = dict(re.findall(patron, xml))
        for tarjetas in ('resumen', 'flujo', 'antiguedad', 'resultados', 'balance', 'itbms'):
            self.assertIn('o_dc_kpi_cuando', bloques[tarjetas], f'las tarjetas de «{tarjetas}» dicen su fecha')
