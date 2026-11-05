"""En el navegador, como lo hace la vendedora (pedido de la dueña, 2026-11-05).

* Entra a CRM › Sofía, toca «Revisar ahora» y ve SOLO lo suyo, con el mensaje que Sofía propone (al cliente sin nombre
  de verdad le pide su nombre y apellido y su correo).
* «Descartar» quita la tarjeta. «Abrir el chat con este mensaje» lleva a Conversaciones con el mensaje escrito en la
  caja, sin enviarlo."""
from datetime import timedelta
from unittest.mock import patch

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

    def test_guarda_sus_datos_en_un_clic(self):
        """El cliente contestó su nombre, su correo y su cumpleaños: la vendedora los revisa, corrige uno y guarda."""
        conv = self._cliente('🌻', '50760004004', self.vendedora)
        ahora = fields.Datetime.now()
        Mensaje = self.env['dcasa.mensaje']
        Mensaje.create({'conversacion_id': conv.id, 'id_mensaje': 'sofia.nav.pedido', 'direccion': 'saliente',
                        'autor': 'vendedora', 'tipo': 'mensaje', 'usuario_id': self.vendedora.id,
                        'texto': '¿Me regalas tu nombre y apellido y tu correo? Si quieres, dime también el día y el '
                                 'mes de tu cumpleaños.', 'ts': ahora - timedelta(hours=6)})
        Mensaje.create({'conversacion_id': conv.id, 'id_mensaje': 'sofia.nav.respuesta', 'direccion': 'entrante',
                        'autor': 'cliente', 'tipo': 'mensaje', 'texto': 'maria ruiz\nMaria.Ruiz@Example.com\n12/03',
                        'ts': ahora - timedelta(hours=5)})
        codigo = '(async () => {' + COMUN + """
            const boton = await esperar(() => document.querySelector('.o_sofia_boton_revisar:not([disabled])'),
                                        'el botón «Revisar ahora»');
            boton.click();
            const tarjeta = await esperar(() => [...document.querySelectorAll('.o_sofia_tarjeta')]
                .find((t) => t.textContent.includes('Guarda sus datos')), 'la tarjeta «Guarda sus datos»');
            sinErrores();
            const nombre = tarjeta.querySelector('input[id^="o_sofia_nombre_"]');
            const correo = tarjeta.querySelector('input[id^="o_sofia_correo_"]');
            const [dia, mes] = tarjeta.querySelectorAll('.o_sofia_cumple select');
            if (nombre.value !== 'Maria Ruiz' || correo.value !== 'maria.ruiz@example.com' || dia.value !== '12'
                    || mes.value !== '3') {
                throw new Error(`No muestra lo que escribió: ${nombre.value} ${correo.value} ${dia.value}/`
                                + mes.value);
            }
            if (!tarjeta.textContent.includes('Su ficha dice: 🌻')) {
                throw new Error('No muestra lo que hoy dice su ficha');
            }
            nombre.value = 'MARÍA ruiz castillo';
            nombre.dispatchEvent(new Event('input', { bubbles: true }));
            dia.value = '5';
            dia.dispatchEvent(new Event('change', { bubbles: true }));
            tarjeta.querySelector('.o_sofia_accion[data-accion="guardar"]').click();
            await esperar(() => !document.body.contains(tarjeta), 'que se vaya la tarjeta guardada');
            sinErrores();
            console.log('test successful');
        })();"""
        self.browser_js('/odoo/sofia', codigo, login='vend_sofia', timeout=120)
        partner = conv.partner_id
        self.assertEqual(partner.name, 'María Ruiz Castillo')
        self.assertEqual(partner.email, 'maria.ruiz@example.com')
        self.assertEqual(partner.dcasa_cumple, '03-05')

    def test_guardar_y_responderle_deja_el_borrador_de_juan_en_el_chat(self):
        """Después de guardar sus datos se abre su chat con el borrador de Juan («Sugerir»), sin enviarlo."""
        conv = self._cliente('🌵', '50760004005', self.vendedora)
        self.env['dcasa.mensaje'].create({
            'conversacion_id': conv.id, 'id_mensaje': 'sofia.nav.responder', 'direccion': 'entrante',
            'autor': 'cliente', 'tipo': 'mensaje', 'texto': 'Me llamo Elsa Barrios, elsa.barrios@example.com',
            'ts': fields.Datetime.now() - timedelta(hours=4)})
        borrador = 'Gracias por tus datos, Elsa. ¿Te muestro los juegos de comedor que tenemos?'
        Cliente = type(self.env['dcasa.juan.cliente'])
        codigo = '(async () => {' + COMUN + """
            const boton = await esperar(() => document.querySelector('.o_sofia_boton_revisar:not([disabled])'),
                                        'el botón «Revisar ahora»');
            boton.click();
            const tarjeta = await esperar(() => [...document.querySelectorAll('.o_sofia_tarjeta')]
                .find((t) => t.textContent.includes('Elsa Barrios')), 'la tarjeta «Guarda sus datos»');
            const solo = tarjeta.querySelector('.o_sofia_accion[data-accion="guardar"]');
            if (!solo || !solo.textContent.includes('Solo guardar')) {
                throw new Error('Falta «Solo guardar»');
            }
            tarjeta.querySelector('.o_sofia_accion[data-accion="responder"]').click();
            const caja = await esperar(() => document.querySelector('#o_dcj_texto'), 'la caja del chat');
            await esperar(() => caja.value === BORRADOR, 'el borrador de Juan en la caja del chat');
            sinErrores();
            console.log('test successful');
        })();""".replace('BORRADOR', repr(borrador))
        with patch.object(Cliente, 'configurado', return_value=True), \
                patch.object(Cliente, 'sugerir', return_value={'ok': True, 'texto': borrador, 'avisos': []}) as sugerir:
            self.browser_js('/odoo/sofia', codigo, login='vend_sofia', timeout=120)
        self.assertEqual(sugerir.call_count, 1, 'el borrador se pide una sola vez')
        self.assertEqual((conv.partner_id.name, conv.partner_id.email), ('Elsa Barrios', 'elsa.barrios@example.com'))
        self.assertFalse(conv.mensaje_ids.filtered(lambda m: m.autor == 'vendedora'), 'no se envió nada')
