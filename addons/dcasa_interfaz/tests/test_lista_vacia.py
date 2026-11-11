"""El mensaje de «no hay nada» de las listas y las tarjetas (``sin_odoo.js``).

Dos cosas que salieron en la auditoría visual del 2026-11-11:

* decía «Toca «Nuevo» para crear el primero» también donde no hay botón «Nuevo» (Libro de puntos, Abonos por vencer,
  Posibles duplicados…): la persona buscaba un botón que no existe;
* las listas cuya acción no trae texto de ayuda quedaban con cuatro renglones en blanco y sin decir nada.

Se prueba en el navegador con listas hechas aquí mismo (etiquetas de contacto, filtradas para que salgan vacías)."""
from odoo.tests import HttpCase, tagged

from .test_inicio_por_rol import ESPERAR_JS

CON_NUEVO = 'Toca «Nuevo» para crear el primero'
SIN_NUEVO = 'Cuando haya algo, sale aquí'


@tagged('post_install', '-at_install')
class TestListaVacia(HttpCase):

    def _accion(self, nombre, vista, arch, ayuda=False):
        vista_bd = self.env['ir.ui.view'].create({
            'name': f'dcasa.prueba.vacia.{nombre}', 'model': 'res.partner.category', 'arch': arch})
        return self.env['ir.actions.act_window'].create({
            'name': f'Prueba vacía {nombre}', 'res_model': 'res.partner.category', 'view_mode': vista,
            'view_id': vista_bd.id, 'domain': "[('id', '=', 0)]", 'help': ayuda})

    def _probar(self, accion, boton, esperado, prohibido):
        codigo = '(async () => {' + ESPERAR_JS + f"""
            const ayuda = await esperar(() => document.querySelector('.o_view_nocontent'), 'el mensaje de lista vacía');
            const texto = ayuda.textContent.replace(/\\s+/g, ' ').trim();
            const dice = (parte) => texto.includes(parte);
            for (const parte of ['Aquí todavía no hay nada', {esperado!r}, 'revisa los filtros']) {{
                if (!dice(parte)) {{ throw new Error(`se esperaba «${{parte}}» y se vio: ${{texto}}`); }}
            }}
            if (dice({prohibido!r})) {{ throw new Error('no debía decir ' + {prohibido!r} + ': ' + texto); }}
            const hayBoton = Boolean(document.querySelector('.o_list_button_add, .o-kanban-button-new'));
            if (hayBoton !== {'true' if boton else 'false'}) {{
                throw new Error('el botón «Nuevo»: se esperaba {boton} y se vio ' + hayBoton);
            }}
            console.log('test successful');
        }})();"""
        self.browser_js(f'/odoo/action-{accion.id}', codigo, login='admin')

    def test_lista_con_boton_nuevo_invita_a_tocarlo(self):
        accion = self._accion('lista con nuevo', 'list', '<list><field name="name"/></list>')
        self._probar(accion, True, CON_NUEVO, SIN_NUEVO)

    def test_lista_sin_boton_nuevo_no_lo_menciona(self):
        accion = self._accion('lista sin nuevo', 'list', '<list create="false"><field name="name"/></list>')
        self._probar(accion, False, SIN_NUEVO, '«Nuevo»')

    def test_lista_sin_texto_de_ayuda_tambien_avisa(self):
        """Antes solo avisaban las acciones con ``help``; la de arriba no lo trae y esta sí: las dos dicen lo mismo."""
        accion = self._accion('lista con ayuda de Odoo', 'list', '<list create="false"><field name="name"/></list>',
                              ayuda='<p class="o_view_nocontent_smiling_face">Create a tag</p>')
        self._probar(accion, False, SIN_NUEVO, 'Create a tag')

    def test_tarjetas_con_y_sin_boton_nuevo(self):
        tarjeta = '<templates><t t-name="card"><field name="name"/></t></templates>'
        con = self._accion('tarjetas con nuevo', 'kanban', f'<kanban>{tarjeta}</kanban>',
                           ayuda='<p>Crea una etiqueta</p>')
        self._probar(con, True, CON_NUEVO, SIN_NUEVO)
        sin = self._accion('tarjetas sin nuevo', 'kanban', f'<kanban create="false">{tarjeta}</kanban>',
                           ayuda='<p>Crea una etiqueta</p>')
        self._probar(sin, False, SIN_NUEVO, '«Nuevo»')
