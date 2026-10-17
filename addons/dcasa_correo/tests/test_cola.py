"""La cola: el cron arma el PDF nuevo, deja el correo en el chatter (al cliente correcto) y la cola de Odoo lo manda."""
import base64
from unittest.mock import patch

from odoo.tests import tagged

from ..models.correo_envio import MAX_ARMAR
from .common import PDF, RUTA_PDF, CorreoCase


@tagged('post_install', '-at_install')
class TestCola(CorreoCase):

    def pagada(self, partner=None, monto=None):
        factura = self.factura(partner)
        self.pagar(factura, monto)
        return factura

    def test_publica_en_la_factura_con_el_pdf_y_la_marca(self):
        self.encender()
        factura = self.pagada()
        self.procesar()
        (envio,) = self.envios(move_id=factura.id)
        self.assertEqual(envio.estado, 'enviado')
        self.assertEqual(envio.correo, 'ana@example.com')
        mensaje = envio.message_id
        self.assertEqual((mensaje.model, mensaje.res_id), ('account.move', factura.id))
        self.assertEqual(mensaje.email_layout_xmlid, 'dcasa_correo.layout_correo')
        self.assertEqual(mensaje.partner_ids, self.ana)
        (adjunto,) = mensaje.attachment_ids
        self.assertTrue(adjunto.raw.startswith(b'%PDF'))
        self.assertEqual(adjunto.name, f"{factura.name.replace('/', '_')}.pdf", 'El mismo nombre que «Imprimir»')
        (correo,) = self.correos_de(factura)
        self.assertEqual(correo.recipient_ids, self.ana)
        self.assertIn("'X-Dcasa-Correo': 'factura'", correo.headers)
        self.assertIn('dcasa_base/static/img/logo.png', correo.body_html)
        self.assertIn('Escríbenos por WhatsApp', correo.body_html)
        self.assertIn('¡TU COMPRA ESTÁ PAGADA!', correo.body_html)
        self.assertEqual(correo.subject, f'Tu factura {factura.name} está pagada')
        self.assertFalse(factura.access_token, 'Ningún correo crea un access_token')
        self.assertFalse(factura.invoice_pdf_report_id, 'El PDF del correo no reemplaza el de la factura')

    def test_sale_por_resend_al_cliente_correcto_con_su_pdf(self):
        self.encender()
        empresa = self.env['res.partner'].create({
            'name': 'Muebles Ana S.A.', 'is_company': True, 'phone': '6000-0011', 'email': 'empresa@example.com'})
        contacto = self.env['res.partner'].create({
            'name': 'Ana Compras', 'parent_id': empresa.id, 'type': 'invoice', 'email': 'compras@example.com'})
        factura = self.pagada(contacto)
        self.procesar()
        (correo,) = self.correos_de(factura)
        self.assertEqual(correo.recipient_ids, contacto, 'Primero el correo de la dirección de la factura')
        with self.transporte():
            correo.send()
        (llamada,) = [c for c in self.post.call_args_list if 'compras@example.com' in c.kwargs['json']['to']]
        datos = llamada.kwargs['json']
        self.assertEqual(datos['to'], ['compras@example.com'])
        self.assertNotIn('empresa@example.com', repr(datos))
        (adjunto,) = datos['attachments']
        self.assertEqual(base64.b64decode(adjunto['content']), PDF[0])
        self.assertFalse(correo.exists(), 'Enviado: Odoo lo saca de la cola (auto_delete)')
        aviso = self.envios(move_id=factura.id).message_id.notification_ids
        self.assertEqual((aviso.res_partner_id, aviso.notification_status), (contacto, 'sent'))

    def test_sin_correo_en_la_direccion_usa_el_de_la_ficha(self):
        self.encender()
        empresa = self.env['res.partner'].create({
            'name': 'Muebles Beto S.A.', 'is_company': True, 'phone': '6000-0012', 'email': 'empresa.beto@example.com'})
        contacto = self.env['res.partner'].create({'name': 'Beto Compras', 'parent_id': empresa.id, 'type': 'invoice'})
        factura = self.pagada(contacto)
        self.procesar()
        self.assertEqual(self.envios(move_id=factura.id).correo, 'empresa.beto@example.com')

    def test_el_abono_dice_lo_mismo_que_estado_abono(self):
        self.encender()
        factura = self.pagada(monto=80.0)
        self.procesar()
        estado = factura._dcasa_estado_abono()
        correo_modelo = self.env['dcasa.correo']
        (correo,) = self.correos_de(factura)
        cuerpo = correo.body_html
        self.assertIn('RECIBIMOS TU ABONO', cuerpo)
        self.assertEqual(correo.subject, f'Recibimos tu abono · Factura {factura.name}')
        for clave in ('total', 'pagado', 'saldo'):
            with self.subTest(clave=clave):
                self.assertIn(correo_modelo._monto(estado[clave], factura.currency_id), cuerpo)
        self.assertIn('$120.00', cuerpo)
        self.assertIn(correo_modelo._fecha(estado['vence']), cuerpo)
        self.assertNotIn('puntos', cuerpo.lower(), 'Lo esencial: total, pagado, lo que falta y hasta cuándo')
        (adjunto,) = self.envios(move_id=factura.id).message_id.attachment_ids
        self.assertEqual(adjunto.name, f"Abono {factura.name.replace('/', '_')}.pdf", 'Como el papel de ABONO')

    def test_un_correo_viejo_no_sale(self):
        self.encender()
        # El saldo cambió antes de procesar (llegó otro pago): el primero se omite y sale el más reciente.
        factura = self.pagada(monto=50.0)
        self.pagar(factura, 50.0)
        self.procesar()
        envios = self.envios(move_id=factura.id)
        self.assertEqual(envios.mapped('estado'), ['omitido', 'enviado'])
        # Una factura cancelada antes de procesar.
        otra = self.pagada(self.beto, monto=50.0)
        otra.button_draft()
        otra.button_cancel()
        self.procesar()
        self.assertEqual(self.envios(move_id=otra.id).estado, 'omitido')

    def test_si_se_apagan_los_correos_antes_de_procesar_no_sale(self):
        self.encender()
        factura = self.pagada()
        self.apagar()
        self.procesar()
        (envio,) = self.envios(move_id=factura.id)
        self.assertEqual((envio.estado, envio.causa), ('omitido', 'apagado'))
        self.assertFalse(self.correos_de(factura))

    def test_sin_correo_queda_una_nota_y_no_sale(self):
        self.encender()
        factura = self.pagada(self.sin_correo)
        self.procesar()
        (envio,) = self.envios(move_id=factura.id)
        self.assertEqual((envio.estado, envio.causa), ('omitido', 'sin_correo'))
        nota = factura.message_ids.filtered(lambda m: 'No se envió por correo' in (m.body or ''))
        self.assertTrue(nota)
        self.assertTrue(nota.subtype_id.internal, 'Nota interna, no un mensaje al cliente')
        self.assertFalse(self.correos_de(factura))

    def test_un_correo_mal_escrito_no_cuenta(self):
        self.encender()
        cliente = self.env['res.partner'].create({'name': 'Dedo', 'phone': '6000-0013', 'email': 'dedo@@example.com'})
        factura = self.pagada(cliente)
        self.procesar()
        self.assertEqual(self.envios(move_id=factura.id).causa, 'sin_correo')

    def test_la_bienvenida_va_despues_y_una_sola_vez(self):
        self.encender()
        primera = self.pagada(monto=100.0)
        self.pagar(primera)
        self.procesar()
        envios = self.envios()
        # La bienvenida espera a que pueda entrar a Mi cuenta: con el pago que termina su primera compra.
        self.assertEqual(envios.mapped('tipo'), ['abono', 'factura', 'bienvenida'])
        bienvenida = envios.filtered(lambda e: e.tipo == 'bienvenida')
        self.assertEqual(bienvenida.estado, 'enviado')
        self.assertEqual(bienvenida.message_id.model, 'res.partner')
        (correo,) = self.correos_de(self.ana)
        self.assertIn('¡Te damos la bienvenida, Ana!', correo.body_html)
        segunda = self.pagada()
        self.procesar()
        self.assertEqual(len(self.envios(tipo='bienvenida')), 1)
        self.assertEqual(len(self.correos_de(self.ana)), 1)
        self.assertEqual(self.envios(move_id=segunda.id).estado, 'enviado')

    def test_la_bienvenida_sin_correo_se_vuelve_a_armar_cuando_lo_tenga(self):
        self.encender()
        self.pagada(self.sin_correo)
        self.procesar()
        (bienvenida,) = self.envios(tipo='bienvenida')
        self.assertEqual(bienvenida.causa, 'sin_correo')
        self.sin_correo.email = 'carla@example.com'
        self.pagada(self.sin_correo)
        self.procesar()
        self.assertEqual(bienvenida.estado, 'enviado')
        self.assertEqual(len(self.envios(tipo='bienvenida')), 1)

    def test_un_error_al_armar_no_toca_la_factura_ni_frena_a_los_demas(self):
        self.encender()
        mala = self.pagada()
        buena = self.pagada(self.beto)

        def pdf(informe, res_ids, *args, **kwargs):
            if res_ids == [mala.id]:
                raise ValueError('wkhtmltopdf se cayó')
            return PDF

        with patch(RUTA_PDF, side_effect=pdf), \
                self.assertLogs('odoo.addons.dcasa_correo.models.correo_envio', level='WARNING'):
            for _vuelta in range(MAX_ARMAR):   # se reintenta en cada vuelta del cron; al tercero, «Falló»
                self.env['dcasa.correo.envio'].sudo()._procesar()
        self.assertEqual(self.envios(move_id=mala.id).estado, 'fallido')
        self.assertEqual(self.envios(move_id=buena.id).estado, 'enviado')
        self.assertEqual((mala.state, mala.payment_state), ('posted', 'paid'))
