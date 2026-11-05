"""Las pantallas propias de Inicio bajan con scroll en el computador.

Odoo pone a todo ``.o_action`` en columna con ``overflow: hidden`` (webclient_layout.scss) y esa regla pesa más que una
clase suelta: sin una regla propia más fuerte la pantalla queda cortada abajo (en el celular sí bajaba, por eso no se
notó). Se comprobó en el navegador; aquí se vigila que la regla siga."""
import re
from pathlib import Path

from odoo.tests import TransactionCase, tagged

SCSS = Path(__file__).resolve().parents[1] / 'static' / 'src' / 'scss' / 'interfaz.scss'
ADDONS = Path(__file__).resolve().parents[2]
# Pantallas propias que NO deben bajar enteras, a propósito (cada una con su porqué).
SIN_SCROLL_DE_PANTALLA = {
    'o_dcj': 'Conversaciones: ocupa toda la ventana y cada columna (lista, chat, ficha) tiene su propio scroll.',
    'o_dcasa_vista_previa': 'Vista previa del sitio: un marco a pantalla completa; se baja dentro del marco.',
    'o_dcasa_armar_combo': 'Armar combo se abre en una ventana encima (target new): baja dentro de ella.',
}
RAIZ = re.compile(r'<div\s+class="([^"]*\bo_action\b[^"]*)"')


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

    def test_toda_pantalla_propia_baja_con_scroll(self):
        """El bug de siempre (Inicio, Contabilidad, Juan, Estadísticas y, el 2026-11-05, Sofía): una pantalla nueva nace
        sin la regla fuerte y queda cortada. Revisa TODAS las pantallas propias de ``addons/`` (la raíz de su plantilla
        lleva ``o_action``): alguna de sus clases necesita su regla
        ``.o_web_client > .o_action_manager > .<clase>.o_action`` con scroll y bloques que no se encogen."""
        hojas = '\n'.join(p.read_text() for p in ADDONS.glob('*/static/src/**/*.scss'))
        pantallas = set()
        for plantilla in ADDONS.glob('*/static/src/**/*.xml'):
            for clases in RAIZ.findall(plantilla.read_text()):
                pantallas.add((plantilla.relative_to(ADDONS).as_posix(), tuple(clases.split())))
        self.assertGreater(len(pantallas), 10, 'no encontró las pantallas propias')
        for archivo, clases in sorted(pantallas):
            propias = [c for c in clases if c != 'o_action']
            if any(c in SIN_SCROLL_DE_PANTALLA for c in propias):
                continue
            with self.subTest(pantalla=archivo, clases=' '.join(propias)):
                con_regla = []
                for clase in propias:
                    selector = f'.o_web_client > .o_action_manager > .{clase}.o_action'
                    if selector + ' {' in hojas:
                        regla = self._bloque(hojas, selector)
                        baja = re.search(r'overflow-y:\s*auto', regla)
                        no_encoge = re.search(r'>\s*\*\s*\{\s*flex-shrink:\s*0', regla)
                        if baja and no_encoge:
                            con_regla.append(clase)
                self.assertTrue(con_regla, f'{archivo}: la pantalla ({" ".join(propias)}) no baja con scroll. '
                                           'Agrega la regla fuerte .o_web_client > .o_action_manager > '
                                           '.<clase>.o_action { overflow-y: auto; > * { flex-shrink: 0; } } '
                                           '(ver docs/CONTEXTO_AGENTICO.md).')
