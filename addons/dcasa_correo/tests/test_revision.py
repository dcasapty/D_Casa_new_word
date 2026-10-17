"""Lo que encontró la revisión adversarial del 17/10/2026, cada hallazgo con su prueba."""
import os
import re
import shutil
from unittest import skipUnless
from unittest.mock import patch

import psycopg2

from odoo import Command
from odoo.tests import HttpCase, new_test_user, tagged

from ..models import politica
from ..models.correo_envio import MAX_ARMAR
from .common import PDF, RUTA_PDF, CorreoCase

ENCOLAR = 'odoo.addons.dcasa_correo.models.correo_envio.DcasaCorreoEnvio._encolar_pagos'
LOG_COLA = 'odoo.addons.dcasa_correo.models.correo_envio'
LOG_GANCHO = 'odoo.addons.dcasa_correo.models.account_move_line'
HAY_PDF_REAL = bool(shutil.which('wkhtmltopdf') and shutil.which('pdftotext'))


@tagged('post_install', '-at_install')
class TestRevision(CorreoCase):

    # ------------------------------------------------------------------
    # El pago y lo que deja para el commit
    # ------------------------------------------------------------------

    def centinela(self):
        """Algo que el pago dejó para el commit (como el seguimiento del chatter o un aviso del bus)."""
        cr = self.env.cr
        hecho = []

        def tarea():
            hecho.append(True)

        cr.precommit.add(tarea)

        def limpiar():
            if tarea in cr.precommit._funcs:
                cr.precommit._funcs.remove(tarea)

        self.addCleanup(limpiar)
        return lambda: bool(hecho) or tarea in cr.precommit._funcs

    def test_si_falla_el_correo_lo_que_el_pago_dejo_para_el_commit_no_se_pierde(self):
        """El savepoint que se deshace solo borra lo de adentro: lo que el pago dejó para el commit ya corrió."""
        for falla in ('encolar', 'choque'):
            with self.subTest(falla=falla):
                self.encender()
                factura = self.factura()
                sigue = self.centinela()
                if falla == 'encolar':
                    with patch(ENCOLAR, side_effect=Exception('se cayó la cola')), \
                            self.assertLogs(LOG_GANCHO, level='ERROR'):
                        self.pagar(factura)
                else:   # otro proceso encoló el mismo correo (UNIQUE): se ignora
                    Envio = type(self.env['dcasa.correo.envio'])
                    with patch.object(Envio, 'create', side_effect=psycopg2.IntegrityError('duplicado')):
                        self.pagar(factura)
                self.assertEqual(factura.payment_state, 'paid')
                self.assertTrue(sigue(), 'Lo pendiente del pago corrió o sigue esperando el commit')
                self.assertFalse(self.envios(move_id=factura.id))

    def test_apagado_el_pago_no_hace_nada_del_correo(self):
        """Como hoy en producción (sin clave, o con el interruptor apagado): ni lee saldos ni abre un savepoint."""
        factura = self.factura()
        lineas = factura.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        self.assertNotIn('dcasa_correo_antes', lineas._reconcile_pre_hook())
        self.con_clave()
        self.assertNotIn('dcasa_correo_antes', lineas._reconcile_pre_hook(), 'Con clave pero apagado, tampoco')
        self.encender()
        self.assertIn('dcasa_correo_antes', lineas._reconcile_pre_hook())

    # ------------------------------------------------------------------
    # Nadie de afuera marca su mensaje como «factura»
    # ------------------------------------------------------------------

    def publicar(self, usuario, sudo):
        """Un mensaje en una cotización de Ana con el contexto ``dcasa_correo_tipo='factura'``, a Beto."""
        orden = self.env['sale.order'].with_user(self.vendedora).create({
            'partner_id': self.ana.id, 'user_id': self.vendedora.id,
            'order_line': [Command.create({'product_id': self.mueble.id, 'product_uom_qty': 1})]})
        registro = orden.with_user(usuario)
        if sudo:
            registro = registro.sudo()   # como /mail/message/post, el chatter del portal
        mensaje = registro.with_context(dcasa_correo_tipo='factura', mail_notify_force_send=False).message_post(
            body='Mira esto: https://ejemplo.invalid', message_type='comment', subtype_xmlid='mail.mt_comment',
            partner_ids=self.beto.ids)
        return self.env['mail.mail'].sudo().search(
            [('mail_message_id', '=', mensaje.id), ('recipient_ids', 'in', self.beto.ids)])

    def test_un_cliente_del_portal_no_marca_su_mensaje_como_factura(self):
        """/mail/message/post publica con sudo() y deja pasar el context del navegador."""
        self.encender()
        portal = new_test_user(self.env, login='correo_portal', name='Portal Correo', email='portal@example.com',
                               groups='base.group_portal')
        (correo,) = self.publicar(portal, sudo=True)
        self.assertNotIn(politica.CABECERA_CORREO, correo.headers or '')
        self.assertEqual(correo._dcasa_clase(), 'odoo')
        with self.transporte():
            correo.send()
        self.post.assert_not_called()
        self.assertIn('Odoo sin permiso', correo.failure_reason)

    def test_una_persona_del_equipo_si_lo_marca(self):
        self.encender()
        (correo,) = self.publicar(self.vendedora, sudo=False)
        self.assertIn("'X-Dcasa-Correo': 'factura'", correo.headers)

    # ------------------------------------------------------------------
    # El abono sale con el papel de ABONO
    # ------------------------------------------------------------------

    def adjunto(self, factura):
        (envio,) = self.envios(move_id=factura.id).filtered(lambda e: e.estado == 'enviado')
        (adjunto,) = envio.message_id.attachment_ids
        return adjunto

    def test_el_abono_se_llama_como_el_papel_de_abono(self):
        self.encender()
        factura = self.factura()
        self.pagar(factura, 80.0)
        self.procesar()
        numero = factura.name.replace('/', '_')
        self.assertEqual(self.adjunto(factura).name, f'Abono {numero}.pdf', 'El mismo nombre que «Imprimir»')
        self.assertEqual(self.adjunto(factura).name, factura._get_invoice_report_filename())
        (correo,) = self.correos_de(factura)
        self.assertIn('abono', correo.subject.lower())

    def test_una_venta_pagada_completa_nunca_recibe_el_texto_del_abono(self):
        self.encender()
        de_una = self.factura()
        self.pagar(de_una)
        en_dos = self.factura(self.beto)
        self.pagar(en_dos, 80.0)
        self.procesar()
        self.pagar(en_dos)
        self.procesar()
        for factura in (de_una, en_dos):
            with self.subTest(factura=factura.name):
                correo = self.correos_de(factura)[-1]
                self.assertNotIn('abono', (correo.subject + correo.body_html).lower())
                self.assertIn('¡TU COMPRA ESTÁ PAGADA!', correo.body_html)
                self.assertIn('Ver en Mi cuenta', correo.body_html)
        (abono,) = self.correos_de(en_dos)[:1]
        self.assertIn('Te falta', abono.body_html, 'El primer pago sí fue un abono')

    def test_una_ficha_nueva_con_lo_de_un_cliente_de_antes_no_es_nueva(self):
        """Fusionar la ficha vieja de un cliente EN una ficha nueva le pasa sus facturas, ventas y contactos."""
        Envio = self.env['dcasa.correo.envio'].sudo()
        casos = {
            'factura de antes': lambda ficha: self.env.cr.execute(
                "UPDATE account_move SET create_date = '2019-06-01' WHERE id = %s", [self.factura(ficha).id]),
            'venta de antes': lambda ficha: self.env.cr.execute(
                "UPDATE sale_order SET create_date = '2019-06-01' WHERE id = %s", [self.env['sale.order'].create({
                    'partner_id': ficha.id,
                    'order_line': [Command.create({'product_id': self.mueble.id, 'product_uom_qty': 1})]}).id]),
            'contacto de antes': lambda ficha: self.env.cr.execute(
                "UPDATE res_partner SET create_date = '2019-06-01' WHERE id = %s", [self.env['res.partner'].create({
                    'name': 'Contacto Viejo', 'parent_id': ficha.id}).id]),
            'contacto importado': lambda ficha: self.env['ir.model.data'].create({
                'module': '__import__', 'name': f'dcasa_contacto_{ficha.id}9', 'model': 'res.partner',
                'res_id': self.env['res.partner'].create({'name': 'Importado', 'parent_id': ficha.id}).id}),
        }
        for numero, (caso, preparar) in enumerate(casos.items()):
            with self.subTest(caso=caso):
                ficha = self.env['res.partner'].create({
                    'name': f'Empresa Nueva {numero}', 'is_company': True, 'email': f'nueva{numero}@example.com'})
                self.assertTrue(Envio._es_cliente_nuevo(ficha))
                preparar(ficha)
                self.env.invalidate_all()
                self.assertFalse(Envio._es_cliente_nuevo(ficha), caso)

    def test_una_sola_bienvenida_por_persona_aunque_tenga_dos_fichas(self):
        self.encender()
        gemela = self.env['res.partner'].create({
            'name': 'Ana Repetida', 'phone': '6000-0101', 'email': 'ana.repetida@example.com'})
        # Hoy un correo es de una sola ficha (dcasa_contactos); una vieja o importada puede repetirlo.
        self.env.cr.execute("UPDATE res_partner SET email = 'ANA@example.com', email_normalized = 'ana@example.com' "
                            "WHERE id = %s", [gemela.id])
        gemela.invalidate_recordset()
        self.pagar(self.factura())
        self.pagar(self.factura(gemela))
        self.procesar()
        por_ficha = {envio.partner_id: envio for envio in self.envios(tipo='bienvenida')}
        self.assertEqual(por_ficha[self.ana].estado, 'enviado')
        self.assertEqual((por_ficha[gemela].estado, por_ficha[gemela].causa), ('omitido', 'repetida'))
        self.assertFalse(self.correos_de(gemela))
        # Fusión: Odoo pasa los envíos de la ficha que se borra a la que queda (y la que queda es nueva).
        nueva = self.env['res.partner'].create({
            'name': 'Ana Fusionada', 'phone': '6000-0102', 'email': 'ana.fusionada@example.com'})
        self.env.cr.execute('UPDATE dcasa_correo_envio SET partner_id = %s WHERE partner_id = %s',
                            [nueva.id, self.ana.id])
        self.env.invalidate_all()
        self.pagar(self.factura(nueva))
        self.assertFalse(self.envios(tipo='bienvenida', huella=f'bienvenida:{nueva.id}'))

    # ------------------------------------------------------------------
    # Que no quede sin salir
    # ------------------------------------------------------------------

    def test_desconciliar_y_volver_a_conciliar_antes_de_armarlo_igual_sale(self):
        self.encender()
        factura = self.factura()
        self.pagar(factura, 80.0)
        (envio,) = self.envios(move_id=factura.id)
        cobro = factura.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        pago = cobro.matched_credit_ids.credit_move_id
        cobro.remove_move_reconcile()
        self.procesar()
        self.assertEqual((envio.estado, envio.causa), ('omitido', 'cambio'))
        (cobro | pago).reconcile()
        self.assertEqual(factura.amount_residual, 120.0)
        self.assertEqual(envio.estado, 'pendiente', 'El mismo pago vuelve a la cola: nunca había salido')
        self.procesar()
        self.assertEqual(envio.estado, 'enviado')
        self.assertEqual(len(self.correos_de(factura)), 1)

    def test_un_correo_ya_enviado_no_se_rearma(self):
        self.encender()
        factura = self.factura()
        self.pagar(factura, 80.0)
        self.procesar()
        (envio,) = self.envios(move_id=factura.id)
        self.assertEqual(envio.estado, 'enviado')
        cobro = factura.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        pago = cobro.matched_credit_ids.credit_move_id
        cobro.remove_move_reconcile()
        (cobro | pago).reconcile()
        self.procesar()
        self.assertEqual(envio.estado, 'enviado')
        self.assertEqual(len(self.correos_de(factura)), 1, 'Sin duplicados')

    def test_si_falla_el_pdf_se_reintenta_y_al_tercero_queda_fallido(self):
        self.encender()
        factura = self.factura()
        self.pagar(factura)
        (envio,) = self.envios(move_id=factura.id)
        for intento in range(1, MAX_ARMAR):
            with patch(RUTA_PDF, side_effect=ValueError('wkhtmltopdf se cayó')), \
                    self.assertLogs(LOG_COLA, level='WARNING'):
                self.env['dcasa.correo.envio'].sudo()._procesar()
            self.assertEqual((envio.estado, envio.intentos), ('pendiente', intento))
            self.assertIn('wkhtmltopdf', envio.motivo)
        with patch(RUTA_PDF, return_value=PDF):
            self.env['dcasa.correo.envio'].sudo()._procesar()
        self.assertEqual(envio.estado, 'enviado', 'Un tropiezo pasajero no deja al cliente sin su factura')

        otra = self.factura(self.beto)
        self.pagar(otra)
        (mala,) = self.envios(move_id=otra.id)
        with patch(RUTA_PDF, side_effect=ValueError('wkhtmltopdf se cayó')), \
                self.assertLogs(LOG_COLA, level='WARNING') as logs:
            for _vuelta in range(MAX_ARMAR):
                self.env['dcasa.correo.envio'].sudo()._procesar()
        self.assertEqual((mala.estado, mala.causa, mala.intentos), ('fallido', 'error', MAX_ARMAR))
        self.assertEqual(len([r for r in logs.records if r.levelname == 'ERROR']), 1, 'Error solo al darlo por fallido')

    # ------------------------------------------------------------------
    # Lo que se apaga, se apaga también para lo que estaba por salir
    # ------------------------------------------------------------------

    def test_apagar_la_factura_al_pagar_o_la_bienvenida_frena_lo_pendiente(self):
        self.encender()
        factura = self.factura()
        self.pagar(factura)
        self.ICP.set_param('dcasa_correo.al_pagar', False)
        self.ICP.set_param('dcasa_correo.bienvenida', False)
        self.procesar()
        por_tipo = {e.tipo: e for e in self.envios()}
        self.assertEqual((por_tipo['factura'].estado, por_tipo['factura'].causa), ('omitido', 'apagado'))
        self.assertEqual((por_tipo['bienvenida'].estado, por_tipo['bienvenida'].causa), ('omitido', 'apagado'))
        self.assertFalse(self.correos_de(factura))
        self.assertFalse(self.correos_de(self.ana))
        # Lo que pide una persona («mándasela por correo», Brian) sí sale aunque lo automático esté apagado.
        factura._dcasa_correo_enviar_factura()
        self.procesar()
        self.assertEqual(len(self.correos_de(factura)), 1)

    # ------------------------------------------------------------------
    # Solo producción le escribe a clientes
    # ------------------------------------------------------------------

    def test_un_servidor_sin_entorno_no_le_escribe_a_clientes(self):
        self.encender()
        Correo = self.env['dcasa.correo']
        self.assertTrue(Correo._activo_para_clientes())
        with patch.dict(os.environ, {'DCASA_ENTORNO': ''}):
            self.assertFalse(Correo._activo_para_clientes())
            self.assertIn('DCASA_ENTORNO', Correo._motivo_apagado())
            factura = self.factura()
            self.pagar(factura)
            self.assertFalse(self.envios(move_id=factura.id))
            self.assertEqual(politica.puede_salir('factura', True, Correo._entorno(), ['ana@example.com'], []),
                             (False, politica.MOTIVO_NO_PRODUCCION))


@tagged('post_install', '-at_install')
class TestAbonoEnPdf(CorreoCase, HttpCase):
    """El PDF de verdad (wkhtmltopdf): HttpCase, para que wkhtmltopdf pueda pedir los estilos al servidor de pruebas
    (con TransactionCase la petición se queda esperando a la transacción de la prueba)."""

    def adjunto(self, factura):
        (envio,) = self.envios(move_id=factura.id).filtered(lambda e: e.estado == 'enviado')
        (adjunto,) = envio.message_id.attachment_ids
        return adjunto

    @skipUnless(HAY_PDF_REAL, 'sin wkhtmltopdf o pdftotext')
    def test_el_pdf_del_abono_es_el_papel_de_abono_y_el_de_la_pagada_no(self):
        from odoo.addons.dcasa_invoice.tests.test_paquete import textos_de_pdf_real

        self.encender()
        factura = self.factura(precio=500.0)
        self.pagar(factura, 120.0)
        self.env['dcasa.correo.envio'].sudo()._procesar()   # el PDF de verdad (wkhtmltopdf)
        adjunto = self.adjunto(factura)
        self.assertTrue(adjunto.raw.startswith(b'%PDF'))
        texto = re.sub(r'\s+', ' ', ' '.join(textos_de_pdf_real(adjunto.raw)))
        self.assertIn('ABONO', texto.upper())
        self.assertIn('SALDO POR PAGAR', texto)
        self.assertIn('$380.00', texto)
        self.assertEqual(adjunto.name, f"Abono {factura.name.replace('/', '_')}.pdf")

        pagada = self.factura(self.beto)
        self.pagar(pagada)
        self.env['dcasa.correo.envio'].sudo()._procesar()
        adjunto = self.adjunto(pagada)
        texto = re.sub(r'\s+', ' ', ' '.join(textos_de_pdf_real(adjunto.raw)))
        self.assertNotIn('SALDO POR PAGAR', texto)
        self.assertEqual(adjunto.name, f"{pagada.name.replace('/', '_')}.pdf")
