"""En el navegador, como lo hace la vendedora (pedido de la dueña, 2026-11-05).

* Entra a CRM › Sofía, toca «Revisar ahora» y ve SOLO lo suyo, con el mensaje que Sofía propone (al cliente sin nombre
  de verdad le pide su nombre y apellido y su correo).
* «Descartar» quita la tarjeta. «Abrir el chat con este mensaje» lleva a Conversaciones con el mensaje escrito en la
  caja, sin enviarlo."""
from datetime import timedelta

from odoo import fields
from odoo.addons.dcasa_contactos.tests.test_fijo_y_copiar_navegador import COMUN
from odoo.addons.dcasa_conversaciones.models import crm_reglas as CRM
from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestSofiaEnElNavegador(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['dcasa.juan.ajustes'].obtener().reparto_activa_minutos = 0
        cls.vendedora = new_test_user(cls.env, login='vend_sofia', password='vend_sofia', name='Ana Sofía',
                                      groups='base.group_user,sales_team.group_sale_salesman')
        cls.otra = new_test_user(cls.env, login='otra_sofia', password='otra_sofia', name='Otra Vendedora',
                                 groups='base.group_user,sales_team.group_sale_salesman')
        cls.emoji = cls._cliente('🙏', '50760004001', cls.vendedora)
        cls.descartar = cls._cliente('Bruno Castillo', '50760004002', cls.vendedora, correo='bruno@example.com')
        cls.ajeno = cls._cliente('Cliente Ajeno', '50760004003', cls.otra, correo='ajeno@example.com')

    @classmethod
    def _cliente(cls, nombre, celular, vendedora, correo=False):
        ahora = fields.Datetime.now()
        partner = cls.env['res.partner'].create({'name': nombre, 'phone': f'+{celular}', 'email': correo})
        conv = cls.env['dcasa.conversacion'].create({
            'canal': 'whatsapp_qr', 'id_externo': celular, 'partner_id': partner.id, 'estado': 'bot',
            'ultimo_mensaje_cliente': ahora - timedelta(hours=5), 'ultimo_mensaje_autor': 'bot',
            'ultima_actividad': ahora - timedelta(hours=5)})
        lead = cls.env['crm.lead'].with_context(dcasa_auto=True).create({
            'name': 'WhatsApp (QR): juego de comedor', 'type': 'opportunity', 'partner_id': partner.id,
            'user_id': vendedora.id, 'dcasa_temperatura': CRM.CALIENTE})
        conv.oportunidad_id = lead
        conv.seguimiento_proximo = False   # sin seguimiento de Juan en camino
        return conv

    def test_revisar_descartar_y_abrir_el_chat_con_el_mensaje(self):
        codigo = '(async () => {' + COMUN + """
            const boton = await esperar(() => document.querySelector('.o_sofia_boton_revisar:not([disabled])'),
                                        'el botón «Revisar ahora»');
            boton.click();
            const tarjetas = () => [...document.querySelectorAll('.o_sofia_tarjeta')];
            await esperar(() => tarjetas().length === 2, 'las dos propuestas de la vendedora');
            sinErrores();
            // La pantalla baja con scroll (bug del 2026-11-05: Odoo corta las pantallas propias con overflow hidden).
            const pantalla = document.querySelector('.o_action.o_sofia');
            // Por código se puede mover aunque esté cortada: lo que bloquea la rueda y el dedo es overflow hidden.
            const desborde = getComputedStyle(pantalla).overflowY;
            if (!['auto', 'scroll'].includes(desborde)) {
                throw new Error('Sofía no baja con scroll: la pantalla tiene overflow-y: ' + desborde);
            }
            if (pantalla.scrollHeight <= pantalla.clientHeight + 50) {
                throw new Error('La pantalla no es más alta que la ventana: no se puede probar el scroll');
            }
            pantalla.scrollTop = 100000;
            await new Promise((ok) => setTimeout(ok, 150));
            if (pantalla.scrollTop < 50) {
                throw new Error('Sofía no baja con scroll (overflow-y: ' + getComputedStyle(pantalla).overflowY + ')');
            }
            const ultima = tarjetas().at(-1).getBoundingClientRect();
            if (ultima.bottom > window.innerHeight + 2) {
                throw new Error('Abajo del todo, la última tarjeta sigue cortada');
            }
            pantalla.scrollTop = 0;
            if (document.body.textContent.includes('Cliente Ajeno')) {
                throw new Error('La vendedora ve lo de otra');
            }
            const delEmoji = tarjetas().find((t) => t.querySelector('.o_sofia_cliente').textContent.includes('🙏'));
            const mensaje = delEmoji.querySelector('textarea.o_sofia_mensaje').value;
            if (!mensaje.includes('tu nombre y apellido y tu correo') || !mensaje.includes('Soy Ana de')) {
                throw new Error('El mensaje no pide los datos: ' + mensaje);
            }
            const deBruno = tarjetas().find((t) => t.textContent.includes('Bruno Castillo'));
            deBruno.querySelector('.o_sofia_descartar').click();
            await esperar(() => tarjetas().length === 1, 'que se vaya la descartada');
            const area = document.querySelector('textarea.o_sofia_mensaje');
            area.value = mensaje + ' ¡Gracias!';
            area.dispatchEvent(new Event('input', { bubbles: true }));
            document.querySelector('.o_sofia_accion[data-accion="chat"]').click();
            const caja = await esperar(() => document.querySelector('#o_dcj_texto'), 'la caja del chat');
            await esperar(() => caja.value === mensaje + ' ¡Gracias!', 'el mensaje escrito en la caja del chat');
            sinErrores();
            console.log('test successful');
        })();"""
        self.browser_js('/odoo/sofia', codigo, login='vend_sofia', timeout=120)
        Propuesta = self.env['dcasa.sofia.propuesta'].sudo()
        self.assertEqual(Propuesta.search([('conversacion_id', '=', self.descartar.id)]).estado, 'descartada')
        self.assertEqual(Propuesta.search([('conversacion_id', '=', self.emoji.id)]).estado, 'aplicada')
        self.assertFalse(self.env['dcasa.mensaje'].search([('conversacion_id', '=', self.emoji.id),
                                                           ('tipo', '=', 'mensaje')]),
                         'abrir el chat no envía nada')
