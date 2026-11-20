"""La segunda revisión independiente (RV6) del dinero y los permisos de Yappy directo: cada hallazgo con su prueba. Las
pruebas «rojas» del revisor (``test_c1``, ``test_c2``, ``test_c3``, ``test_d6``) están aquí ADAPTADAS: ya no demuestran
el hallazgo, comprueban que el arreglo se sostiene. Datos inventados; ninguna prueba toca la red.

* H2: un cobro a mano y después el aviso tardío NO es un segundo cobro; el pendiente «sin aviso» se cierra solo cuando
llega el aviso; Caja tiene un botón (mismo camino que el aviso) para confirmar el cobro, y queda quién y cuándo.
* H3: un aviso «E» sobre un pedido cancelado va a revisión humana (nunca «hecho»).
* H5: el celular de Yappy es de Caja y superiores a nivel de campo; ni el pedido ni su nota lo dejan ver a la vendedora.
"""
import re
from datetime import timedelta

from odoo import Command, fields
from odoo.addons.dcasa_pago_yappy.models import payment_transaction as modelo_tx
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from .common import ComunYappy, YappyFalso

CELULAR_DE_YAPPY = '6111 2222'
CELULAR_DE_YAPPY_LIMPIO = '61112222'
GRUPOS_CAJA = ('dcasa_base.group_caja', 'dcasa_base.group_gerencia', 'account.group_account_user', 'base.group_system')


class BaseDinero(ComunYappy, TransactionCase):

    def actividades(self, pedido, texto=None):
        dominio = [('res_model', '=', 'sale.order'), ('res_id', '=', pedido.id)]
        if texto:
            dominio.append(('summary', 'ilike', texto))
        return self.env['mail.activity'].sudo().search(dominio)

    def notas(self, pedido):
        return ' '.join(pedido.message_ids.mapped(lambda m: re.sub(r'<[^>]+>', ' ', str(m.body or ''))))

    def diario_yappy(self):
        return self.env['account.journal'].search([('code', '=', 'YAPPY')], limit=1)

    def pagos_del_diario(self, pedido):
        return self.env['account.payment'].search([
            ('journal_id', '=', self.diario_yappy().id), ('partner_id', '=', pedido.partner_id.id)])

    def facturar_y_cobrar_a_mano(self, pedido):
        """Lo que haría Caja: confirmar, facturar y registrar el cobro en el diario Yappy con el asistente «Pagar»."""
        if pedido.state != 'sale':
            pedido.action_confirm()
        factura = pedido._create_invoices()
        factura.action_post()
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create({
                'journal_id': self.diario_yappy().id}).action_create_payments()
        return factura

    def usuario(self, login, grupo):
        return new_test_user(self.env, login=login, groups=grupo)

    def sin_aviso(self, tx, minutos=30):
        """El cobro sin aviso pasados ``minutos``: la tarea le deja su pendiente a Caja."""
        self.envejecer(tx, minutes=minutos)
        self.assertEqual(self.env['payment.transaction']._cron_dcasa_yappy_sin_aviso(), 1)
        self.assertTrue(self.actividades(tx.sale_order_ids, 'sin aviso'), 'el pendiente a Caja salió')


# ======================================================================================================================
# H2 · cobro a mano + aviso tardío
# ======================================================================================================================

@tagged('post_install', '-at_install')
class TestCobroAManoYAvisoTardio(BaseDinero):

    def test_c1_cobro_a_mano_y_luego_el_aviso_tarde_NO_crea_un_segundo_cobro(self):
        """RV6-C1. Caja registró el cobro a mano y DESPUÉS llegó el aviso tardío: el diario Yappy tenía 2 cobros de
        107.00 por un pedido de 107.00 y nadie recibía alerta. Ahora el aviso va a revisión humana, con alerta clara,
        y no crea ningún cobro."""
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _orden, _d = self.abrir(yappy, pedido)
        self.sin_aviso(tx)
        self.facturar_y_cobrar_a_mano(pedido)
        antes = len(self.pagos_del_diario(pedido))
        self.assertEqual(antes, 1)
        self.aviso(tx, 'E')
        tx._post_process()
        self.assertEqual(len(self.pagos_del_diario(pedido)), antes, 'ningún segundo cobro del mismo pedido')
        self.assertFalse(tx.payment_id)
        self.assertEqual(tx.state, 'error')
        self.assertTrue(tx.dcasa_yappy_revision, 'lo resuelve una persona')
        alerta = self.actividades(pedido, 'ya estaba pagado')
        self.assertTrue(alerta, 'alerta clara de que el pedido ya estaba pagado')
        self.assertIn('NO se registró otro cobro', alerta[0].note)
        self.assertIn('Si es el mismo dinero', alerta[0].note)
        self.assertIn('Si el cliente pagó dos veces', alerta[0].note)

    def test_c1b_a_la_clienta_no_se_le_dice_que_confirmamos_su_pedido(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        self.facturar_y_cobrar_a_mano(pedido)
        self.aviso(tx, 'E')
        self.assertIn('ya figuraba como pagado', tx.state_message)
        self.assertNotIn('Confirmamos tu pedido', tx.state_message)

    def test_c1c_un_cobro_a_mano_parcial_tampoco_deja_pasar_el_aviso(self):
        """Cualquier dinero que ya figure en una factura del pedido cuenta (``partial``): el aviso no suma otro."""
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        pedido.action_confirm()
        factura = pedido._create_invoices()
        factura.action_post()
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create({
                'journal_id': self.diario_yappy().id, 'amount': 10.0}).action_create_payments()
        self.assertEqual(factura.payment_state, 'partial')
        self.aviso(tx, 'E')
        self.assertEqual((tx.state, tx.dcasa_yappy_revision), ('error', True))
        self.assertFalse(tx.payment_id)

    def test_c1d_un_pedido_sin_ningun_pago_por_otra_via_se_paga_como_siempre(self):
        """Lo contrario: una factura sin cobrar (o nada facturado) no es dinero de otra vía."""
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        pedido.action_confirm()
        pedido._create_invoices().action_post()
        self.aviso(tx, 'E')
        self.assertEqual(tx.state, 'done')
        self.assertFalse(tx.dcasa_yappy_revision)

    def test_c7_dos_cobros_de_yappy_el_segundo_va_a_revision_y_no_se_registra(self):
        """Lo que antes era «dos cobros hechos + una alerta»: el segundo aviso E ya no crea otro cobro (el dinero
        entró y lo revisa una persona, que decide si devuelve uno desde Yappy Comercial)."""
        pedido = self.pedido()
        with YappyFalso() as yappy:
            primera, _o, _d = self.abrir(yappy, pedido)
            segunda, _o2, _d2 = self.abrir(yappy, pedido)
        self.aviso(primera, 'E')
        self.aviso(segunda, 'E')
        self.assertEqual(primera.state, 'done')
        self.assertEqual((segunda.state, segunda.dcasa_yappy_revision), ('error', True))
        alerta = self.actividades(pedido, 'ya estaba pagado')
        self.assertTrue(alerta)
        self.assertIn(primera.reference, alerta[0].note, 'dice cuál es el otro cobro')
        primera._post_process()
        segunda._post_process()
        self.assertEqual(len(self.pagos_del_diario(pedido)), 1)

    def test_c7b_otra_pasarela_ya_pago_el_pedido_y_llega_el_E_de_yappy(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        otro_proveedor = self.env['payment.provider'].sudo().search([('code', '=', 'custom')], limit=1)
        otra = self.env['payment.transaction'].create({
            'provider_id': otro_proveedor.id, 'payment_method_id': otro_proveedor.payment_method_ids[:1].id,
            'amount': pedido.amount_total, 'currency_id': pedido.currency_id.id,
            'partner_id': pedido.partner_invoice_id.id, 'operation': 'online_direct',
            'sale_order_ids': [Command.set(pedido.ids)]})
        otra._set_done()
        self.aviso(tx, 'E')
        self.assertEqual((tx.state, tx.dcasa_yappy_revision), ('error', True))
        self.assertTrue(self.actividades(pedido, 'ya estaba pagado'))
        self.assertIn(otra.reference, self.actividades(pedido, 'ya estaba pagado')[0].note)

    def test_c1e_el_aviso_repetido_sobre_la_revision_no_duplica_la_alerta(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        self.facturar_y_cobrar_a_mano(pedido)
        for _vez in range(4):
            self.aviso(tx, 'E')
        actividad = self.actividades(pedido, 'ya estaba pagado')
        self.assertEqual(len(actividad), len(actividad.mapped('user_id')), 'una por persona')
        self.assertEqual(len((tx.dcasa_yappy_avisos or '').splitlines()), 1, 'un aviso repetido no escribe de nuevo')

    # ------------------------------------------------------------------ el pendiente «sin aviso» se cierra solo

    def test_c2_el_pendiente_sin_aviso_se_cierra_cuando_llega_el_aviso_tarde(self):
        """RV6-C2. Quedaba «Yappy no avisó nada… si el cobro entró, registra el pago a mano» sobre un pedido ya
        pagado."""
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        self.sin_aviso(tx)
        self.aviso(tx, 'E')
        tx._post_process()
        self.assertEqual(tx.state, 'done')
        self.assertFalse(self.actividades(pedido, 'sin aviso'), 'el pendiente se cerró solo')
        self.assertIn('Llegó el aviso de Yappy', self.notas(pedido), 'y quedó dicho qué lo cerró')

    def test_c2b_se_cierra_con_cualquier_estado_del_aviso(self):
        for estado in ('E', 'R', 'C', 'X'):
            with self.subTest(estado=estado):
                pedido = self.pedido()
                with YappyFalso() as yappy:
                    tx, _o, _d = self.abrir(yappy, pedido)
                self.sin_aviso(tx)
                self.aviso(tx, estado)
                self.assertFalse(self.actividades(pedido, 'sin aviso'), estado)

    def test_c2c_tambien_se_cierra_si_el_aviso_va_a_revision(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        self.sin_aviso(tx)
        pedido.order_line.product_uom_qty = 3         # el total cambió: el aviso va a revisión
        self.aviso(tx, 'E')
        self.assertTrue(tx.dcasa_yappy_revision)
        self.assertFalse(self.actividades(pedido, 'sin aviso'))
        self.assertTrue(self.actividades(pedido, 'no cuadra con el pedido'), 'la alerta de la revisión queda abierta')

    def test_c2d_solo_se_cierra_el_pendiente_de_esa_orden(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            una, _o, _d = self.abrir(yappy, pedido)
            otra, _o2, _d2 = self.abrir(yappy, pedido)
        self.envejecer(una, minutes=30)
        self.envejecer(otra, minutes=30)
        self.env['payment.transaction']._cron_dcasa_yappy_sin_aviso()
        antes = self.actividades(pedido, 'sin aviso')
        self.assertTrue(antes)
        self.aviso(una, 'R')
        restantes = self.actividades(pedido, 'sin aviso')
        self.assertTrue(restantes, 'el de la otra orden sigue abierto')
        for actividad in restantes:
            self.assertIn(otra.dcasa_yappy_orden, actividad.summary)
            self.assertNotIn(una.dcasa_yappy_orden, actividad.summary)

    def test_c2e_el_pendiente_ya_no_manda_a_registrar_el_cobro_a_mano(self):
        """Las tres instrucciones de Caja (la actividad, YAPPY.md y la Guía) dicen lo mismo."""
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, orden, _d = self.abrir(yappy, pedido)
        self.sin_aviso(tx)
        nota = re.sub(r'<[^>]+>', ' ', self.actividades(pedido, 'sin aviso')[0].note)
        self.assertIn('Confirmar que el dinero entró', nota)
        self.assertIn('NO registres el cobro a mano', nota)
        self.assertNotIn('registra el pago a mano', nota)
        self.assertIn(orden, nota)
        self.assertIn('Yappy no avisó nada', nota)

    # ------------------------------------------------------------------ el botón de Caja

    def test_caja_confirma_el_cobro_y_pasa_por_el_mismo_camino_que_el_aviso(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, orden, _d = self.abrir(yappy, pedido)
        self.sin_aviso(tx)
        caja = self.usuario('caja_confirma', 'dcasa_base.group_caja')
        resultado = tx.with_user(caja).action_dcasa_yappy_confirmar_cobro()
        self.assertEqual(resultado['params']['type'], 'success')
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.dcasa_yappy_confirmada_por, caja, 'queda quién')
        self.assertTrue(tx.dcasa_yappy_confirmada_fecha, 'y cuándo')
        self.assertIn(f'cobro confirmado a mano por {caja.name}', tx.dcasa_yappy_avisos)
        self.assertIn(f'{caja.name} confirmó a mano', self.notas(pedido))
        self.assertFalse(self.actividades(pedido, 'sin aviso'), 'el pendiente se cierra')
        tx._post_process()
        self.assertEqual(pedido.state, 'sale')
        self.assertEqual(len(self.pagos_del_diario(pedido)), 1, 'UN solo cobro, en el diario Yappy')
        self.assertEqual(tx.payment_id.journal_id, self.diario_yappy())
        self.assertEqual(tx.payment_id.amount, pedido.amount_total)
        self.assertTrue(orden)

    def test_el_aviso_tardio_despues_de_confirmar_a_mano_no_hace_nada(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        caja = self.usuario('caja_tarde', 'dcasa_base.group_caja')
        tx.with_user(caja).action_dcasa_yappy_confirmar_cobro()
        tx._post_process()
        actividades = self.actividades(pedido)
        mensajes = pedido.message_ids.ids
        for _vez in range(3):
            self.aviso(tx, 'E')
        pedido.invalidate_recordset(['message_ids'])
        self.assertEqual(pedido.message_ids.ids, mensajes, 'ni una nota nueva en el pedido')
        self.assertEqual(tx.state, 'done')
        self.assertFalse(tx.dcasa_yappy_revision)
        self.assertEqual(len(self.pagos_del_diario(pedido)), 1, 'sigue UN solo cobro')
        self.assertEqual(self.actividades(pedido), actividades, 'ni una alerta nueva')
        lineas = tx.dcasa_yappy_avisos.splitlines()
        self.assertEqual(len(lineas), 2, 'la confirmación a mano y el aviso tardío, cada uno una vez')
        self.assertTrue(lineas[0].startswith('M '))
        self.assertTrue(lineas[1].startswith('E '))
        self.assertEqual(tx.dcasa_yappy_confirmada_por, caja)

    def test_confirmar_dos_veces_no_cobra_dos_veces(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        caja = self.usuario('caja_doble', 'dcasa_base.group_caja')
        tx.with_user(caja).action_dcasa_yappy_confirmar_cobro()
        segunda = tx.with_user(caja).action_dcasa_yappy_confirmar_cobro()
        self.assertEqual(segunda['params']['type'], 'info')
        tx._post_process()
        self.assertEqual(len(self.pagos_del_diario(pedido)), 1)

    def test_solo_caja_gerencia_y_contabilidad_pueden_confirmar(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        sin_permiso = {
            'vendedora': self.usuario('vend_confirma', 'dcasa_base.group_vendedora'),
            'interno': self.usuario('interno_confirma', 'base.group_user'),
            'portal': self.usuario('portal_confirma', 'base.group_portal'),
            'publico': self.env.ref('base.public_user'),
        }
        for nombre, usuario in sin_permiso.items():
            with self.subTest(usuario=nombre), self.assertRaises(AccessError):
                tx.with_user(usuario).action_dcasa_yappy_confirmar_cobro()
        self.assertEqual(tx.state, 'pending')
        self.assertFalse(tx.dcasa_yappy_confirmada_por)
        for grupo in ('dcasa_base.group_gerencia', 'account.group_account_user', 'base.group_system'):
            with self.subTest(grupo=grupo):
                pedido2 = self.pedido()
                with YappyFalso() as yappy:
                    tx2, _o2, _d2 = self.abrir(yappy, pedido2)
                tx2.with_user(self.usuario('quien_' + grupo.split('.')[-1], grupo)).action_dcasa_yappy_confirmar_cobro()
                self.assertEqual(tx2.state, 'done')

    def test_una_transaccion_cerrada_no_se_confirma_a_mano(self):
        caja = self.usuario('caja_cerrada', 'dcasa_base.group_caja')
        for estado in ('R', 'C', 'X'):
            with self.subTest(estado=estado):
                with YappyFalso() as yappy:
                    tx, _o, _d = self.abrir(yappy)
                self.aviso(tx, estado)
                self.assertEqual(tx.state, 'cancel')
                with self.assertRaises(UserError):
                    tx.with_user(caja).action_dcasa_yappy_confirmar_cobro()
                self.assertEqual(tx.state, 'cancel')
                self.assertFalse(tx.payment_id)

    def test_una_transaccion_en_revision_tampoco(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        self.aviso(tx, 'R')
        self.aviso(tx, 'E')
        self.assertTrue(tx.dcasa_yappy_revision)
        caja = self.usuario('caja_revision', 'dcasa_base.group_caja')
        with self.assertRaises(UserError):
            tx.with_user(caja).action_dcasa_yappy_confirmar_cobro()

    def test_solo_sirve_para_yappy_directo_con_su_orden(self):
        caja = self.usuario('caja_otro', 'dcasa_base.group_caja')
        pedido = self.pedido()
        tx = self.transaccion(pedido)         # nace en borrador y sin orden: todavía no se mandó nada a Yappy
        with self.assertRaises(UserError):
            tx.with_user(caja).action_dcasa_yappy_confirmar_cobro()
        self.assertEqual(tx.state, 'draft')

    def test_confirmar_a_mano_pasa_por_las_mismas_comprobaciones_que_el_aviso(self):
        caja = self.usuario('caja_filtros', 'dcasa_base.group_caja')
        # 1) el pedido cambió de total
        cambiado = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, cambiado)
        cambiado.order_line.product_uom_qty = 2
        resultado = tx.with_user(caja).action_dcasa_yappy_confirmar_cobro()
        self.assertEqual(resultado['params']['type'], 'warning')
        self.assertEqual((tx.state, tx.dcasa_yappy_revision), ('error', True))
        self.assertFalse(tx.dcasa_yappy_confirmada_por, 'no quedó confirmada: pasó a revisión')
        # 2) el pedido está cancelado
        anulado = self.pedido()
        with YappyFalso() as yappy:
            tx2, _o2, _d2 = self.abrir(yappy, anulado)
        anulado._action_cancel()
        tx2.with_user(caja).action_dcasa_yappy_confirmar_cobro()
        self.assertEqual((tx2.state, tx2.dcasa_yappy_revision), ('error', True))
        # 3) el pedido ya tenía un cobro a mano
        cobrado = self.pedido()
        with YappyFalso() as yappy:
            tx3, _o3, _d3 = self.abrir(yappy, cobrado)
        self.facturar_y_cobrar_a_mano(cobrado)
        tx3.with_user(caja).action_dcasa_yappy_confirmar_cobro()
        self.assertEqual((tx3.state, tx3.dcasa_yappy_revision), ('error', True))
        self.assertEqual(len(self.pagos_del_diario(cobrado)), 1, 'nunca un segundo cobro')

    def test_el_boton_esta_en_la_vista_solo_para_caja(self):
        vista = self.env.ref('payment.payment_transaction_form')
        caja = self.usuario('caja_vista', 'dcasa_base.group_caja')
        vendedora = self.usuario('vend_vista', 'dcasa_base.group_vendedora')
        arch_caja = self.env['payment.transaction'].with_user(caja).get_view(vista.id)['arch']
        arch_vendedora = self.env['payment.transaction'].with_user(vendedora).get_view(vista.id)['arch']
        self.assertIn('action_dcasa_yappy_confirmar_cobro', arch_caja)
        self.assertNotIn('action_dcasa_yappy_confirmar_cobro', arch_vendedora)

    def test_el_pendiente_cuando_el_aviso_se_rechazo_no_dice_que_yappy_no_aviso(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        self.assertTrue(tx._dcasa_yappy_anotar_rechazo('dominio: llegó «http://otro.example» y el declarado es «x»'))
        self.sin_aviso(tx)
        nota = re.sub(r'<[^>]+>', ' ', self.actividades(pedido, 'sin aviso')[0].note)
        self.assertIn('se RECHAZÓ', nota)
        self.assertIn('http://otro.example', nota, 'se ve la diferencia')
        self.assertNotIn('Yappy no avisó nada', nota)
        self.assertIn('Confirmar que el dinero entró', nota)

    def test_el_rastro_de_rechazos_tiene_tope_y_solo_de_cobros_abiertos(self):
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy)
        anotados = [tx._dcasa_yappy_anotar_rechazo(f'firma {i}') for i in range(modelo_tx.TOPE_DE_RECHAZOS + 3)]
        self.assertEqual(anotados.count(True), modelo_tx.TOPE_DE_RECHAZOS)
        self.assertEqual(tx.dcasa_yappy_rechazos, modelo_tx.TOPE_DE_RECHAZOS)
        self.aviso(tx, 'E')
        self.assertFalse(tx._dcasa_yappy_anotar_rechazo('otro'), 'una transacción cerrada ya no espera aviso')


# ======================================================================================================================
# H3 · pedido cancelado con el cobro abierto
# ======================================================================================================================

@tagged('post_install', '-at_install')
class TestPedidoCanceladoYAvisoE(BaseDinero):

    def test_c3_pedido_cancelado_con_cobro_abierto_y_aviso_E_va_a_revision(self):
        """RV6-C3. El pedido se anula (una vendedora, o el apartado nocturno) mientras la clienta aprueba en su app:
        la transacción quedaba «hecha» con un cobro contable de 107.00 sobre un pedido anulado y la clienta leía
        «Confirmamos tu pedido». Ahora: revisión humana, nunca se paga sola."""
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        pedido._action_cancel()
        self.assertEqual(tx.state, 'pending', 'anular el pedido no cierra el cobro abierto')
        self.aviso(tx, 'E')
        self.assertEqual(tx.state, 'error', 'NUNCA «hecha»')
        self.assertTrue(tx.dcasa_yappy_revision)
        tx._post_process()
        self.assertFalse(tx.payment_id, 'ningún cobro contable sobre un pedido anulado')
        self.assertEqual(pedido.state, 'cancel')
        alerta = self.actividades(pedido, 'ya no está vivo')
        self.assertTrue(alerta)
        self.assertIn('CANCELADO', alerta[0].note)
        self.assertIn('NO se tomó como pago de ningún pedido', alerta[0].note)
        self.assertEqual(len(alerta), len(alerta.mapped('user_id')), 'una por persona')

    def test_c3b_la_clienta_lee_el_mensaje_correcto_no_confirmamos_tu_pedido(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        pedido._action_cancel()
        self.aviso(tx, 'E')
        self.assertEqual(tx.state_message, modelo_tx.MENSAJE_PEDIDO_ANULADO)
        self.assertIn('ya no estaba vigente', tx.state_message)
        self.assertIn('Nuestro equipo lo revisa y te escribe', tx.state_message)
        self.assertNotIn('Confirmamos tu pedido', tx.state_message)
        self.assertNotEqual(tx.state_message, self.proveedor.done_msg)

    def test_c3c_otro_aviso_E_sobre_lo_marcado_para_revision_no_cambia_nada(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        pedido._action_cancel()
        self.aviso(tx, 'E')
        actividades = self.actividades(pedido)
        for _vez in range(3):
            self.aviso(tx, 'E')
        self.assertEqual(tx.state, 'error')
        self.assertEqual(self.actividades(pedido), actividades)

    def test_c3d_pedido_reabierto_despues_no_paga_solo_lo_marcado(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        pedido._action_cancel()
        self.aviso(tx, 'E')
        pedido.action_draft()
        self.aviso(tx, 'E')
        tx._post_process()
        self.assertEqual(tx.state, 'error', 'marcado para una persona: nunca se paga solo')
        self.assertFalse(tx.payment_id)

    def test_c3e_cancelado_justo_despues_del_aviso_deja_su_alerta(self):
        """La ventana entre el aviso y la tarea que confirma: el pedido se anula en medio."""
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        self.aviso(tx, 'E')
        self.assertEqual(tx.state, 'done')
        pedido._action_cancel()
        tx._post_process()
        self.assertEqual(pedido.state, 'cancel', 'no se confirma solo')
        self.assertTrue(self.actividades(pedido, 'ya no está vivo'))

    def test_c3f_el_apartado_que_vence_no_anula_un_pedido_con_un_cobro_de_yappy_abierto(self):
        """La causa: el barrido de la noche no contaba un cobro de Yappy abierto como «reclamado»."""
        pedido = self.pedido()
        if 'dcasa_apartado_vence' not in pedido._fields:
            self.skipTest('sin website_dcasa')
        pedido.action_confirm()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        pedido.dcasa_apartado_vence = fields.Date.context_today(pedido) - timedelta(days=2)
        self.assertTrue(pedido._dcasa_apartado_reclamado(), 'cobro de Yappy abierto hace un momento')
        self.env['sale.order']._dcasa_cron_vencer_apartados()
        self.assertEqual(pedido.state, 'sale', 'el barrido no lo anuló')
        # pasados los 15 minutos de espera sin aviso, ya no protege (para eso está el pendiente a Caja)
        self.envejecer(tx, minutes=30)
        self.assertFalse(pedido._dcasa_apartado_reclamado())

    def test_c3g_un_cobro_de_yappy_ya_cerrado_no_protege_el_apartado(self):
        pedido = self.pedido()
        if 'dcasa_apartado_vence' not in pedido._fields:
            self.skipTest('sin website_dcasa')
        pedido.action_confirm()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        self.aviso(tx, 'R')
        self.assertFalse(pedido._dcasa_apartado_reclamado())


# ======================================================================================================================
# H5 · el celular de Yappy es de Caja y superiores
# ======================================================================================================================

@tagged('post_install', '-at_install')
class TestElCelularDeYappyEsDeCaja(BaseDinero):

    def setUp(self):
        super().setUp()
        self.pedido_ = self.pedido()
        with YappyFalso() as yappy:
            self.tx, self.orden, _d = self.abrir(yappy, self.pedido_, celular=CELULAR_DE_YAPPY)
        self.assertEqual(self.tx.dcasa_yappy_celular, CELULAR_DE_YAPPY_LIMPIO)
        self.vendedora = self.usuario('vend_celular', 'dcasa_base.group_vendedora')

    def test_d6_la_vendedora_no_lee_por_rpc_el_celular_de_yappy_de_nadie(self):
        """RV6-D6. La vendedora (que tiene permiso de leer transacciones por Facturación) leía el celular de Yappy de
        TODAS las clientas con un ``search_read``. Ahora el campo es de Caja y superiores A NIVEL DE CAMPO."""
        Tx = self.env['payment.transaction'].with_user(self.vendedora)
        with self.assertRaises(AccessError):
            Tx.search_read([('dcasa_yappy_orden', '!=', False)], ['dcasa_yappy_celular', 'amount'])
        with self.assertRaises(AccessError):
            Tx.browse(self.tx.id).read(['dcasa_yappy_celular'])
        with self.assertRaises(AccessError):
            Tx.browse(self.tx.id).dcasa_yappy_celular  # noqa: B018
        with self.assertRaises(AccessError):
            Tx.search([('dcasa_yappy_celular', '=', CELULAR_DE_YAPPY_LIMPIO)])

    def test_la_vendedora_tampoco_lee_el_id_de_yappy_ni_la_huella_de_la_conexion(self):
        Tx = self.env['payment.transaction'].with_user(self.vendedora)
        for campo in ('dcasa_yappy_id', 'dcasa_yappy_huella', 'dcasa_yappy_confirmada_por',
                      'dcasa_yappy_confirmada_fecha'):
            with self.subTest(campo=campo), self.assertRaises(AccessError):
                Tx.browse(self.tx.id).read([campo])

    def test_un_read_sin_campos_no_trae_los_de_caja_y_lo_demas_sigue_leyendose(self):
        Tx = self.env['payment.transaction'].with_user(self.vendedora)
        fila = Tx.browse(self.tx.id).read()[0]
        for campo in ('dcasa_yappy_celular', 'dcasa_yappy_id', 'dcasa_yappy_huella'):
            self.assertNotIn(campo, fila)
        self.assertEqual(fila['amount'], self.tx.amount)
        # lo que no es de nadie en particular (la orden, el estado) se lee como antes
        leido = Tx.browse(self.tx.id).read(['dcasa_yappy_orden', 'dcasa_yappy_estado', 'state'])[0]
        self.assertEqual(leido['dcasa_yappy_orden'], self.orden)

    def test_caja_gerencia_contabilidad_y_administracion_si_lo_leen(self):
        for grupo in GRUPOS_CAJA:
            with self.subTest(grupo=grupo):
                usuario = self.usuario('lee_' + grupo.split('.')[-1], grupo)
                fila = self.tx.with_user(usuario).read(['dcasa_yappy_celular', 'dcasa_yappy_id'])[0]
                self.assertEqual(fila['dcasa_yappy_celular'], CELULAR_DE_YAPPY_LIMPIO)
                self.assertEqual(fila['dcasa_yappy_id'], self.tx.dcasa_yappy_id)

    def test_la_vendedora_ve_el_pedido_y_cobro_en_el_pedido_sin_el_celular_de_yappy(self):
        self.aviso(self.tx, 'E', confirmationNumber='CONF-H5')
        pedido = self.pedido_.with_user(self.vendedora)
        # los campos calculados del pedido arman el texto con sudo: nunca llevan el celular de Yappy
        visto = pedido.read(['dcasa_pago_texto', 'dcasa_entrega_texto', 'dcasa_origen_texto'])[0]
        self.assertIn('Yappy', visto['dcasa_pago_texto'])
        self.assertIn(self.orden, visto['dcasa_pago_texto'])
        self.assertNotIn(CELULAR_DE_YAPPY_LIMPIO, str(visto))
        self.assertNotIn('6111', str(visto))
        # la nota «Qué compró» del chatter (que la vendedora lee) tampoco
        notas = self.notas(self.pedido_)
        self.assertIn('Yappy confirmó el pago de este pedido', notas)
        self.assertNotIn(CELULAR_DE_YAPPY_LIMPIO, notas)
        self.assertNotIn(CELULAR_DE_YAPPY, notas)
        self.assertNotIn('Celular de Yappy', notas)
        # el celular DEL CLIENTE sí sale (es del pedido y ya lo veía)
        self.assertIn('6000', notas)

    def test_el_pendiente_y_las_alertas_no_llevan_el_celular_de_yappy(self):
        self.envejecer(self.tx, minutes=30)
        self.env['payment.transaction']._cron_dcasa_yappy_sin_aviso()
        for actividad in self.actividades(self.pedido_):
            self.assertNotIn(CELULAR_DE_YAPPY_LIMPIO, actividad.note or '')
            self.assertNotIn(CELULAR_DE_YAPPY, actividad.note or '')

    def test_la_vista_de_la_vendedora_no_trae_el_campo_y_la_de_caja_si(self):
        vista = self.env.ref('payment.payment_transaction_form')
        caja = self.usuario('caja_vista_celular', 'dcasa_base.group_caja')
        arch_caja = self.env['payment.transaction'].with_user(caja).get_view(vista.id)['arch']
        arch_vendedora = self.env['payment.transaction'].with_user(self.vendedora).get_view(vista.id)['arch']
        self.assertIn('dcasa_yappy_celular', arch_caja)
        self.assertNotIn('dcasa_yappy_celular', arch_vendedora)
        self.assertNotIn('dcasa_yappy_huella', arch_vendedora)

    def test_el_flujo_de_la_clienta_no_se_rompe_por_el_permiso_del_campo(self):
        """La clienta (sesión pública o de portal) abre el cobro y el servidor escribe el celular con ``sudo``: no
        necesita el grupo. Se prueba con el ``sudo`` del controlador y con el usuario público, y con un cobro nuevo."""
        publico = self.env.ref('base.public_user')
        pedido = self.pedido()
        tx = self.transaccion(pedido)
        with YappyFalso():
            tx.with_user(publico).sudo()._dcasa_yappy_iniciar(CELULAR_DE_YAPPY)
        self.assertEqual(tx.dcasa_yappy_celular, CELULAR_DE_YAPPY_LIMPIO)
        self.assertEqual(tx.state, 'pending')
        self.aviso(tx, 'E')
        self.assertEqual(tx.state, 'done')
