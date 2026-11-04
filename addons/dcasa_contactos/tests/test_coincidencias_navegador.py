"""En el navegador, como lo hace la vendedora en la cotización (pedido de la dueña, 2026-11-04).

* «Crear y editar» un cliente cuyo celular ya existe (lo guardó el chat con la frase de su perfil): sale «Ya existe
  esta persona» con su ficha; «Es esta persona» la abre con lo escrito encima; al guardar queda como cliente de la
  cotización, con el nombre corregido. No se crea otra ficha ni sale un error.
* El selector de «Cliente» encuentra por celular y lo muestra; los datos del cliente se corrigen en la misma cotización
  y se guardan en su ficha."""
from odoo.tests import HttpCase, new_test_user, tagged

from .test_fijo_y_copiar_navegador import COMUN

ESCRIBIR = """
    const escribir = (input, valor) => {
        input.focus();
        input.value = valor;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        input.blur();
    };
    const buscarCliente = async (texto) => {
        const cliente = await esperar(() => document.querySelector('.o_form_view div[name="partner_id"] input'),
                                      'el cliente de la cotización');
        cliente.focus();
        cliente.value = texto;
        cliente.dispatchEvent(new Event('input', { bubbles: true }));
        return cliente;
    };
"""


@tagged('post_install', '-at_install')
class TestCoincidenciasEnElNavegador(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        new_test_user(cls.env, login='vend_coinc', password='vend_coinc', name='Vendedora Coincidencias',
                      groups='base.group_user,dcasa_base.group_vendedora')
        Partner = cls.env['res.partner'].sudo()
        cls.del_chat = Partner.create({'name': 'Dios te bendiga 🙏', 'phone': '+507 6000-1201',
                                       'dcasa_creado_por': 'juan', 'customer_rank': 1})
        cls.otra = Partner.create({'name': 'Solo una frase', 'phone': '+507 6000-1202', 'customer_rank': 1})

    def probar(self, url, cuerpo):
        codigo = '(async () => {' + COMUN + ESCRIBIR + cuerpo + "sinErrores(); console.log('test successful'); })();"
        self.browser_js(url, codigo, login='vend_coinc', timeout=120)

    def test_crear_un_cliente_que_ya_existe_usa_su_ficha(self):
        self.probar('/odoo/action-sale.action_quotations_with_onboarding/new', """
            await buscarCliente('MARÍA NAVEGADOR');
            const crear = await esperar(() => [...document.querySelectorAll('.o-autocomplete--dropdown-item a, '
                + '.o-autocomplete--dropdown-item')].find((a) => /Crear y editar|Create and edit/i.test(a.textContent)),
                'la opción «Crear y editar…»');
            crear.click();
            const dialogo = await esperar(() => document.querySelector('.modal .o_form_view'), 'la ficha nueva');
            escribir(await esperar(() => dialogo.querySelector('div[name="phone"] input'), 'el celular'), '6000 1201');
            const aviso = await esperar(() => document.querySelector('.modal .o_dcasa_coincidencias'),
                                        'el aviso «Ya existe esta persona»');
            const texto = aviso.textContent;
            if (!texto.includes('Dios te bendiga') || !texto.includes('Ya existe esta persona')) {
                throw new Error('El aviso no muestra la ficha que ya existe: ' + texto.trim().slice(0, 300));
            }
            if (!aviso.textContent.includes('+507 6000-1201')) { throw new Error('El aviso no muestra su celular'); }
            aviso.querySelector('.o_dcasa_es_esta_persona').click();
            // La misma ventana ahora es la ficha que ya existía, con el nombre que se escribió encima.
            await esperar(() => !document.querySelector('.modal .o_dcasa_coincidencias')
                && document.querySelector('.modal div[name="phone"] input')?.value === '+507 6000-1201'
                && document.querySelector('.modal div[name="name"] input, .modal div[name="name"] textarea')?.value
                    === 'MARÍA NAVEGADOR', 'la ficha que ya existía con lo escrito encima');
            sinScrollDeLado();
            const guardar = await esperar(() => document.querySelector('.modal .o_form_button_save, '
                + '.modal .modal-footer .btn-primary'), 'el botón Guardar');
            guardar.click();
            await esperar(() => !document.querySelector('.modal .o_form_view')
                                || document.querySelector('.o_error_dialog'), 'que se guarde');
            sinErrores();
            await esperar(() => document.querySelector('.o_form_view div[name="partner_id"] input')?.value
                                  .includes('MARÍA NAVEGADOR'), 'la ficha de siempre como cliente de la cotización');
            await esperar(() => document.querySelector('.o_form_view div[name="dcasa_cliente_celular"] input')?.value
                                  === '+507 6000-1201', 'sus datos debajo del cliente');
            document.querySelector('.o_form_status_indicator .o_form_button_cancel').click();
            await esperar(() => !document.querySelector('.o_form_status_indicator_buttons:not(.invisible)'),
                          'descartar la cotización');
        """)
        self.assertEqual(self.del_chat.name, 'MARÍA NAVEGADOR')
        self.assertEqual(self.env['res.partner'].search_count([('name', '=', 'MARÍA NAVEGADOR')]), 1,
                         'no se creó otra ficha')

    def test_buscar_por_celular_y_corregir_en_la_cotizacion(self):
        self.probar('/odoo/action-sale.action_quotations_with_onboarding/new', """
            await buscarCliente('6000-1202');
            const opcion = await esperar(() => [...document.querySelectorAll('.o-autocomplete--dropdown-item')]
                .find((a) => a.textContent.includes('Solo una frase')), 'el cliente encontrado por su celular');
            if (!opcion.textContent.includes('6000-1202')) {
                throw new Error('La lista no muestra el celular: ' + opcion.textContent.trim());
            }
            (opcion.querySelector('a') || opcion).click();
            const nombre = await esperar(() => {
                const i = document.querySelector('.o_form_view div[name="dcasa_cliente_nombre"] input');
                return i && i.value === 'Solo una frase' && i;
            }, 'el nombre del cliente debajo de «Cliente»');
            escribir(nombre, 'PEDRO NAVEGADOR');
            escribir(document.querySelector('.o_form_view div[name="dcasa_cliente_correo"] input'),
                     'pedro.navegador@example.com');
            escribir(document.querySelector('.o_form_view div[name="dcasa_cliente_cedula"] input'), '8-700-1203');
            await new Promise((ok) => setTimeout(ok, 300));
            sinScrollDeLado();
            document.querySelector('.o_form_status_indicator .o_form_button_save').click();
            await esperar(() => !document.querySelector('.o_form_status_indicator_buttons:not(.invisible)')
                                || document.querySelector('.o_error_dialog'), 'que se guarde la cotización');
            sinErrores();
            await esperar(() => document.querySelector('.o_form_view div[name="partner_id"] input')?.value
                                  .includes('PEDRO NAVEGADOR'), 'el nombre nuevo en el cliente');
        """)
        self.assertEqual((self.otra.name, self.otra.email, self.otra.vat),
                         ('PEDRO NAVEGADOR', 'pedro.navegador@example.com', '8-700-1203'))
        self.assertTrue(self.env['sale.order'].search_count([('partner_id', '=', self.otra.id)]))
