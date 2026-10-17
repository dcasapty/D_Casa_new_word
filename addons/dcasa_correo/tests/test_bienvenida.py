"""La bienvenida: corta y amigable (la dueña, 17/10/2026), solo a clientes nuevos, una sola vez, cuando ya pueden entrar
a Mi cuenta, y diciendo cómo se entra de verdad. Sin reglas de puntos, sin abonos y sin cifras."""
import re
from unittest.mock import patch

from lxml import html

from odoo.tests import new_test_user, tagged

from ..models.correo import P_BIENVENIDA_DESDE
from .common import CorreoCase

CARGAR_REGLAS = 'odoo.addons.dcasa_socios.models.reglas.cargar_reglas'
REDACTAR = 'odoo.addons.dcasa_conversaciones.models.reglas_clientes.redactar'
MI_CUENTA = 'odoo.addons.dcasa_correo.models.correo.DcasaCorreo._mi_cuenta_instalado'
IMPRESO = 'el código de socio que viene en tu factura'


@tagged('post_install', '-at_install')
class TestBienvenida(CorreoCase):

    def cuerpo(self, ficha=None):
        """El texto de la plantilla (sin el layout)."""
        ficha = ficha or self.ana
        plantilla = self.env.ref('dcasa_correo.plantilla_bienvenida')
        return plantilla._generate_template([ficha.id], ('subject', 'body_html'))[ficha.id]['body_html']

    def correo_completo(self, ficha=None):
        """La bienvenida como queda en la cola, con el layout (botón, WhatsApp, pie)."""
        ficha = ficha or self.ana
        self.env['dcasa.correo'].sudo()._postear(ficha, self.env.ref('dcasa_correo.plantilla_bienvenida'), ficha,
                                                 tipo='bienvenida')
        return self.correos_de(ficha)[-1]

    def socia(self, ficha=None):
        """La ficha con su código de socio y su celular (como queda al terminar de pagar su primera compra)."""
        ficha = ficha or self.ana
        ficha.sudo()._dcasa_asegurar_ficha()
        self.assertTrue(ficha.dcasa_socio_codigo and ficha.dcasa_celular)
        return ficha

    def tienda(self, ficha):
        """La cuenta de la tienda en línea (usuario portal) de esa ficha."""
        return new_test_user(self.env, login=f'tienda_{ficha.id}', groups='base.group_portal', partner_id=ficha.id,
                             name=ficha.name, email=ficha.email)

    def test_sin_reglas_de_puntos_sin_abonos_y_sin_cifras(self):
        self.socia()
        with patch(CARGAR_REGLAS, side_effect=AssertionError('la bienvenida no lee puntos.json')), \
                patch(REDACTAR, side_effect=AssertionError('la bienvenida no explica los puntos')):
            cuerpo = self.cuerpo()
            asunto = self.env.ref('dcasa_correo.plantilla_bienvenida')._generate_template(
                [self.ana.id], ('subject',))[self.ana.id]['subject']
        texto = html.fromstring(cuerpo).text_content()
        self.assertNotIn('abono', (texto + asunto).lower())
        self.assertNotIn('Ganas', texto)
        self.assertNotIn('$', texto)
        self.assertFalse(re.search(r'\d', texto), f'Ni una cifra: {texto}')
        self.assertIn('Gracias por tu compra. En Mi cuenta ves tus compras, tus pagos y tus puntos.', texto)
        self.assertLessEqual(len(texto.split()), 60, 'Corta')

    def test_un_boton_a_mi_cuenta_y_whatsapp_de_texto(self):
        self.encender()
        base = self.env['dcasa.correo']._base()
        with patch(MI_CUENTA, return_value=True):
            correo = self.correo_completo()
        arbol = html.fromstring(correo.body_html)
        (boton,) = [a for a in arbol.iter('a') if a.text_content().strip() == 'Entrar a Mi cuenta']
        self.assertEqual(boton.get('href'), f'{base}/mi-cuenta')
        (whatsapp,) = [a for a in arbol.iter('a') if 'WhatsApp' in a.text_content()]
        self.assertEqual(whatsapp.text_content().strip(), '¿Dudas? Escríbenos por WhatsApp')
        (titular,) = arbol.iter('h1')
        self.assertEqual(titular.text_content().strip(), '¡Te damos la bienvenida, Ana!')
        with patch(MI_CUENTA, return_value=False):
            correo = self.correo_completo()
        (boton,) = [a for a in html.fromstring(correo.body_html).iter('a')
                    if a.text_content().strip() == 'Entrar a Mi cuenta']
        self.assertEqual(boton.get('href'), f'{base}/socios')

    def test_dice_como_entra_cada_quien_sin_prometer_de_mas(self):
        # Código de socio y celular: se registra con el código de su factura (el código no va en el correo).
        self.socia()
        cuerpo = self.cuerpo()
        self.assertIn(IMPRESO, cuerpo)
        self.assertIn('«¿Primera vez? Hazte socio»', cuerpo)
        self.assertNotIn(self.ana.dcasa_socio_codigo, cuerpo)
        # Con PIN: entra con su celular y su PIN.
        self.ana.sudo().write({'dcasa_pin_hash': 'x'})
        self.ana.invalidate_recordset(['dcasa_reclamada'])
        cuerpo = self.cuerpo()
        self.assertIn('Entra con tu celular y tu PIN.', cuerpo)
        self.assertNotIn(IMPRESO, cuerpo)
        # Con cuenta de la tienda en línea: entra con su correo.
        self.tienda(self.beto)
        self.assertIn('Entra con el correo y la contraseña de tu cuenta de la tienda en línea.', self.cuerpo(self.beto))
        # Sin un celular que sirva (no lo encontraría al registrarse): que escriba por WhatsApp.
        rara = self.env['res.partner'].create({
            'name': 'Rara Sin Celular', 'phone': '123', 'email': 'rara@example.com'})
        rara.sudo()._dcasa_asegurar_ficha()
        self.assertTrue(rara.dcasa_socio_codigo)
        self.assertFalse(rara.dcasa_celular)
        cuerpo = self.cuerpo(rara)
        self.assertNotIn('regístrate', cuerpo)
        self.assertIn('Para entrar la primera vez, escríbenos por WhatsApp y te ayudamos.', cuerpo)

    def test_espera_a_que_pueda_entrar(self):
        """Si su primera compra va en abono, el código de socio llega con la factura pagada: la bienvenida, también."""
        self.encender()
        factura = self.factura()
        self.pagar(factura, 80.0)
        self.assertFalse(self.ana.dcasa_socio_codigo)
        self.assertFalse(self.envios(tipo='bienvenida'), 'Todavía no puede entrar: no se le escribe que entre')
        self.pagar(factura)
        self.assertTrue(self.ana.dcasa_socio_codigo)
        (bienvenida,) = self.envios(tipo='bienvenida')
        self.assertEqual(bienvenida.partner_id, self.ana)
        # Con cuenta de la tienda en línea ya puede entrar: la bienvenida va con el primer abono.
        self.tienda(self.beto)
        self.pagar(self.factura(self.beto), 50.0)
        self.assertEqual(self.envios(tipo='bienvenida', partner_id=self.beto.id).tipo, 'bienvenida')

    def test_a_un_cliente_viejo_no_le_llega(self):
        self.encender()
        self.env.cr.execute("UPDATE res_partner SET create_date = '2019-06-01' WHERE id = %s", [self.beto.id])
        self.beto.invalidate_recordset(['create_date'])
        factura = self.factura(self.beto)
        self.pagar(factura)
        self.assertEqual(self.envios().mapped('tipo'), ['factura'], 'La factura sí; la bienvenida no')

    def test_la_fecha_desde_se_guarda_al_instalar_y_sin_ella_nadie_es_nuevo(self):
        Envio = self.env['dcasa.correo.envio'].sudo()
        self.assertTrue(Envio._es_cliente_nuevo(self.ana))
        self.ICP.set_param(P_BIENVENIDA_DESDE, False)
        self.assertFalse(Envio._es_cliente_nuevo(self.ana), 'Sin fecha guardada, nadie recibe la bienvenida')
        self.ICP.set_param(P_BIENVENIDA_DESDE, 'no es una fecha')
        self.assertFalse(Envio._es_cliente_nuevo(self.ana))
        self.ICP.set_param(P_BIENVENIDA_DESDE, '2999-01-01 00:00:00')
        self.assertFalse(Envio._es_cliente_nuevo(self.ana))

    def test_la_instalacion_guarda_la_fecha(self):
        from odoo.addons.dcasa_correo import _dcasa_correo_post_init
        self.ICP.set_param(P_BIENVENIDA_DESDE, False)
        self.ICP.set_param('dcasa_correo.al_pagar', False)
        _dcasa_correo_post_init(self.env)
        self.assertTrue(self.ICP.get_param(P_BIENVENIDA_DESDE))
        self.assertEqual(self.ICP.get_param('dcasa_correo.al_pagar'), 'True')
        self.assertFalse(self.ICP.get_param('dcasa_correo.enviar_a_clientes'), 'El interruptor general, apagado')

    def test_los_del_sistema_anterior_no_son_nuevos(self):
        Envio = self.env['dcasa.correo.envio'].sudo()
        self.env['ir.model.data'].create({'module': '__import__', 'name': 'dcasa_contacto_99001',
                                          'model': 'res.partner', 'res_id': self.beto.id})
        self.assertFalse(Envio._es_cliente_nuevo(self.beto), 'Vino del sistema anterior')
        historica = self.factura(self.ana, publicar=False)
        historica.dcasa_historica = True
        historica.action_post()
        self.assertFalse(Envio._es_cliente_nuevo(self.ana), 'Tiene facturas históricas')

    def test_un_socio_suspendido_no_la_recibe(self):
        self.encender()
        self.ana.sudo().dcasa_socio_estado = 'suspendido'
        self.pagar(self.factura())
        self.procesar()
        (bienvenida,) = self.envios(tipo='bienvenida')
        self.assertEqual((bienvenida.estado, bienvenida.causa), ('omitido', 'suspendido'))
        self.assertFalse(self.correos_de(self.ana))

    def test_con_bienvenida_apagada_no_se_encola(self):
        self.encender()
        self.ICP.set_param('dcasa_correo.bienvenida', False)
        self.pagar(self.factura())
        self.assertEqual(self.envios().mapped('tipo'), ['factura'])
