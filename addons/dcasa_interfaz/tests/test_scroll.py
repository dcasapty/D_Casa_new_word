"""Las pantallas propias de Inicio bajan con scroll en el computador.

Odoo pone a todo ``.o_action`` en columna con ``overflow: hidden`` (webclient_layout.scss) y esa regla pesa más que una
clase suelta: sin una regla propia más fuerte la pantalla queda cortada abajo (en el celular sí bajaba, por eso no se
notó). Se comprobó en el navegador; aquí se vigila que la regla siga."""
from pathlib import Path

from odoo.tests import TransactionCase, tagged

SCSS = Path(__file__).resolve().parents[1] / 'static' / 'src' / 'scss' / 'interfaz.scss'


@tagged('post_install', '-at_install')
class TestInicioScroll(TransactionCase):

    def _bloque(self, scss, selector):
        """El cuerpo de la regla ``selector { ... }`` (con sus reglas anidadas)."""
        inicio = scss.index(selector + ' {')
        profundidad, i = 0, scss.index('{', inicio)
        for j in range(i, len(scss)):
            profundidad += {'{': 1, '}': -1}.get(scss[j], 0)
            if profundidad == 0:
                return scss[i + 1:j]
        raise AssertionError('regla sin cerrar')

    def test_el_inicio_baja_con_scroll(self):
        scss = SCSS.read_text()
        for raiz in ('.o_dcasa_inicio',):
            regla = self._bloque(scss, f'.o_web_client > .o_action_manager > {raiz}.o_action')
            self.assertRegex(regla, r'overflow-y:\s*auto', f'{raiz}: sin scroll propio queda cortada')
            self.assertRegex(regla, r'>\s*\*\s*\{\s*flex-shrink:\s*0', f'{raiz}: los bloques no deben encogerse')
            suelta = self._bloque(scss, raiz)
            self.assertNotRegex(suelta, r'overflow-y', f'{raiz}: el scroll va en la regla fuerte, no en la suelta')
