from datetime import timedelta
from unittest.mock import patch

from lxml import etree

from odoo import fields
from odoo.addons.dcasa_fe_pa.models import catalogos as C
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import FeComun

NS = {'d': C.NAMESPACE}


@tagged('post_install', '-at_install')
class TestApagado(FeComun):
    """Sin activar (o sin PAC) el flujo de facturación no cambia en nada."""

    def test_por_defecto_esta_apagado(self):
        self.assertFalse(self.company.l10n_pa_fe_activo)
        self.assertFalse(self.company.l10n_pa_fe_adaptador)
        self.assertFalse(self.company._l10n_pa_fe_operando())

    def test_publicar_sin_activar_no_crea_documento_ni_valida(self):
        # Un cliente contribuyente SIN ubicación ni DV: con la FE apagada se factura igual que antes.
        cliente = self.env['res.partner'].create({'name': 'Sin datos', 'vat': '8-123-456'})
        factura = self._factura(cliente)
        self.assertEqual(factura.state, 'posted')
        self.assertFalse(factura.l10n_pa_fe_documento_ids)
        self.assertNotIn('name="dcasa_fe"', self._render(factura))
        factura.button_draft()
        self.assertEqual(factura.state, 'draft')

    def test_activa_pero_sin_pac_no_hace_nada(self):
        self.company.l10n_pa_fe_activo = True
        factura = self._factura()
        self.assertFalse(factura.l10n_pa_fe_documento_ids)
        self.env['dcasa.fe.documento']._cron_procesar()
        self.assertFalse(self.env['dcasa.fe.documento'].search([]))


@tagged('post_install', '-at_install')
class TestFlujoSimulado(FeComun):

    def _doc(self, factura):
        self.assertEqual(len(factura.l10n_pa_fe_documento_ids), 1)
        return factura.l10n_pa_fe_documento_ids

    def test_autorizado(self):
        self._activar('autorizar')
        factura = self._factura(self.contribuyente)
        doc = self._doc(factura)
        self.assertEqual(doc.estado, 'por_enviar')
        self.assertEqual((doc.tipo_documento, doc.punto, doc.numero), ('01', '001', '0000000001'))
        self.assertTrue(C.cufe_valido(doc.cufe))
        self.assertEqual(doc.validacion_xsd, 'sin_xsd')
        raiz = etree.fromstring(doc.payload.encode())
        self.assertEqual(raiz.findtext('d:gDGen/d:gDatRec/d:iTipoRec', namespaces=NS), '01')
        self.assertEqual(raiz.findtext('d:gDGen/d:gDatRec/d:gRucRec/d:dDV', namespaces=NS), '45')
        self.assertEqual(raiz.findtext('d:gTot/d:dVTot', namespaces=NS), '169.08')
        self.assertNotIn('name="dcasa_fe"', self._render(factura), 'Sin autorizar no se imprime CUFE')

        self.env['dcasa.fe.documento']._cron_procesar()
        self.assertEqual(doc.estado, 'autorizado')
        self.assertTrue(doc.protocolo.startswith('SIM'))
        self.assertIn('FacturasPorQR', doc.qr)
        self.assertEqual(doc.intento_ids.sorted('id', reverse=True).mapped('operacion'), ['enviar', 'generar'])
        html = self._render(factura)
        self.assertIn('o_dcasa_fe', html)
        self.assertIn(doc.cufe, html)
        self.assertIn('data:image/png;base64,', html)
        self.assertIn('155779346-2-2026 DV7', html, 'El formato de dcasa_invoice sigue igual')

    def test_numeracion_consecutiva_por_punto(self):
        self._activar()
        uno = self._doc(self._factura())
        dos = self._doc(self._factura())
        self.assertEqual(int(dos.numero), int(uno.numero) + 1)

    def test_rechazado_se_corrige_y_reintenta_con_el_mismo_numero(self):
        self._activar('rechazar')
        factura = self._factura()
        doc = self._doc(factura)
        doc._procesar()
        self.assertEqual(doc.estado, 'rechazado')
        self.assertIn('SIM-99', doc.error)
        self.assertNotIn('name="dcasa_fe"', self._render(factura))
        # Rechazada: se puede volver a borrador, corregir y volver a publicar.
        factura.button_draft()
        factura.action_post()
        self.assertEqual(factura.l10n_pa_fe_documento_ids, doc)
        self.assertEqual(doc.estado, 'por_enviar')
        self._modo('autorizar')
        doc.with_user(self.admin).action_procesar()
        self.assertEqual(doc.estado, 'autorizado')
        self.assertEqual(doc.numero, '0000000001')

    def test_reintentos_y_contingencia_automatica(self):
        self._activar('caido', l10n_pa_fe_reintentos=3)
        doc = self._doc(self._factura())
        cufe_normal = doc.cufe
        doc._procesar()
        self.assertEqual((doc.estado, doc.intentos), ('por_enviar', 1))
        self.assertGreater(doc.proximo_intento, fields.Datetime.now())
        # El cron respeta la espera: no reintenta antes de tiempo.
        self.env['dcasa.fe.documento']._cron_procesar()
        self.assertEqual(doc.intentos, 1)
        doc._procesar()
        doc._procesar()
        self.assertEqual(doc.estado, 'contingencia')
        self.assertEqual(doc.tipo_emision, C.EMISION_CONTINGENCIA)
        self.assertNotEqual(doc.cufe, cufe_normal, 'iTpEmis cambia y con él el CUFE')
        self.assertIn('<dMotCont>', doc.payload)
        self.assertTrue(C.cufe_valido(doc.cufe))
        # Se imprime con la leyenda de contingencia (sin QR todavía).
        html = self._render(doc.move_id)
        self.assertIn('Emitida en contingencia', html)
        # Vuelve el PAC: se transmite y queda autorizado.
        self._modo('autorizar')
        doc.proximo_intento = False
        self.env['dcasa.fe.documento']._cron_procesar()
        self.assertEqual(doc.estado, 'autorizado')

    def test_excepcion_del_adaptador_cuenta_como_falla_de_comunicacion(self):
        self._activar()
        doc = self._doc(self._factura())
        with patch.object(type(self.env['dcasa.fe.pac.simulado']), '_enviar', side_effect=TimeoutError('lento')):
            doc._procesar()
        self.assertEqual((doc.estado, doc.intentos), ('por_enviar', 1))
        self.assertIn('TimeoutError', doc.error)

    def test_modo_contingencia_manual(self):
        with self.assertRaises(ValidationError):
            self.company.write({'l10n_pa_fe_contingencia': True, 'l10n_pa_fe_contingencia_motivo': 'corto'})
        self._activar('caido', l10n_pa_fe_contingencia=True,
                      l10n_pa_fe_contingencia_motivo='Sin internet en la tienda de La Chorrera',
                      l10n_pa_fe_contingencia_inicio=fields.Datetime.now() - timedelta(hours=80))
        doc = self._doc(self._factura())
        self.assertEqual((doc.estado, doc.tipo_emision), ('contingencia', '02'))
        self.assertIn('Sin internet en la tienda', doc.payload)
        self.assertTrue(doc.contingencia_vencida, 'Más de 72 h en contingencia: se avisa')
        self.assertIn(doc, self.env['dcasa.fe.documento']._resumen()['atencion'])

    def test_estado_enviado_se_consulta(self):
        self._activar('pendiente')
        doc = self._doc(self._factura())
        doc._procesar()
        self.assertEqual(doc.estado, 'enviado')
        self._modo('autorizar')
        doc._procesar()
        self.assertEqual(doc.estado, 'autorizado')
        self.assertEqual(doc.intento_ids.sorted('id', reverse=True)[0].operacion, 'consultar')

    def test_nota_de_credito_referencia_la_factura_autorizada(self):
        self._activar()
        factura = self._factura(self.contribuyente)
        original = self._doc(factura)
        original._procesar()
        reverso = self.env['account.move.reversal'].with_context(
            active_model='account.move', active_ids=factura.ids).create({
                'reason': 'Devolución', 'journal_id': factura.journal_id.id})
        nota = self.env['account.move'].browse(reverso.refund_moves()['res_id'])
        nota.action_post()
        doc = self._doc(nota)
        self.assertEqual((doc.tipo_documento, doc.referencia_id), (C.DOC_NC_REFERENCIA, original))
        self.assertEqual(doc.numero, '0000000001', 'Las notas llevan su propia numeración')
        raiz = etree.fromstring(doc.payload.encode())
        self.assertEqual(raiz.findtext('d:gDGen/d:iNatOp', namespaces=NS), '11')
        self.assertEqual(raiz.findtext('.//d:dCUFERef', namespaces=NS), original.cufe)
        doc._procesar()
        self.assertEqual(doc.estado, 'autorizado')

    def test_nota_de_credito_generica(self):
        self._activar()
        nota = self._factura(move_type='out_refund')
        self.assertEqual(self._doc(nota).tipo_documento, C.DOC_NC_GENERICA)

    def test_anular_y_bloqueos(self):
        self._activar()
        factura = self._factura()
        doc = self._doc(factura)
        with self.assertRaises(UserError):
            factura.button_draft()
        doc._procesar()
        with self.assertRaises(UserError):
            factura.button_cancel()
        self.assertEqual(doc.action_anular()['context'], {'default_documento_id': doc.id})
        Asistente = self.env['dcasa.fe.anular.wizard'].with_user(self.admin)
        with self.assertRaises(UserError):
            Asistente.create({'documento_id': doc.id, 'motivo': 'corto'}).action_confirmar()
        Asistente.create({'documento_id': doc.id,
                          'motivo': 'Factura emitida por error, el cliente no compró'}).action_confirmar()
        self.assertEqual(doc.estado, 'anulado')
        self.assertEqual(doc.intento_ids.sorted('id', reverse=True)[0].operacion, 'anular')
        # Anulada ante la DGI: en Odoo se puede cancelar, pero no volver a borrador.
        with self.assertRaises(UserError):
            factura.button_draft()
        factura.button_cancel()
        self.assertEqual(factura.state, 'cancel')

    def test_documento_e_historial_inmutables(self):
        self._activar()
        doc = self._doc(self._factura())
        doc._procesar()
        with self.assertRaises(UserError):
            doc.sudo().write({'cufe': 'FE0'})
        with self.assertRaises(UserError):
            doc.sudo().write({'numero': '0000000099'})
        with self.assertRaises(UserError):
            doc.sudo().unlink()
        with self.assertRaises(UserError):
            doc.intento_ids[:1].sudo().write({'mensaje': 'otro'})
        with self.assertRaises(UserError):
            doc.intento_ids.sudo().unlink()

    def test_solo_facturacion_usa_los_botones(self):
        self._activar()
        doc = self._doc(self._factura())
        vendedora = self.env['res.users'].create({
            'name': 'Vendedora', 'login': 'vendedora_fe',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        with self.assertRaises(AccessError):
            doc.with_user(vendedora).action_procesar()
        self.assertEqual(doc.estado, 'por_enviar')
