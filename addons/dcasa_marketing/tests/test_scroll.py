"""La pantalla de Marketing baja con scroll (la dueña, 23 oct: «no se puede hacer scroll»).

Odoo pone a todo ``.o_action`` en columna con ``overflow: hidden`` (webclient_layout.scss) y esa regla pesa más que una
clase suelta: sin una regla propia más fuerte la pantalla queda cortada abajo. La prueba del navegador lo mide de
verdad; aquí se vigila que la regla siga."""
from pathlib import Path

from odoo.tests import TransactionCase, tagged

SCSS = Path(__file__).resolve().parents[1] / 'static' / 'src' / 'scss' / 'marketing.scss'


@tagged('post_install', '-at_install')
class TestMarketingScroll(TransactionCase):

    def _bloque(self, scss, selector):
        """El cuerpo de la regla ``selector { ... }`` (con sus reglas anidadas)."""
        inicio = scss.index(selector + ' {')
        profundidad, i = 0, scss.index('{', inicio)
        for j in range(i, len(scss)):
            profundidad += {'{': 1, '}': -1}.get(scss[j], 0)
            if profundidad == 0:
                return scss[i + 1:j]
        raise AssertionError('regla sin cerrar')

    def test_marketing_baja_con_scroll(self):
        scss = SCSS.read_text()
        regla = self._bloque(scss, '.o_web_client > .o_action_manager > .o_dcasa_mk.o_action')
        self.assertRegex(regla, r'overflow-y:\s*auto', 'sin scroll propio la página queda cortada')
        self.assertRegex(regla, r'>\s*\*\s*\{\s*flex-shrink:\s*0', 'los bloques no deben encogerse')
        suelta = self._bloque(scss, '.o_dcasa_mk')
        propia = suelta.split('.o_dcasa_mk_')[0]   # solo las líneas de la raíz, antes de las reglas anidadas
        self.assertNotRegex(propia, r'overflow', 'el scroll va en la regla fuerte, no en la suelta')
