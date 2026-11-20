"""La tercera vuelta de revisión (RV7) del dinero y los permisos de Yappy directo: cada hallazgo con su prueba. Las
pruebas «rojas» del revisor independiente están aquí ADAPTADAS: ya no demuestran el hallazgo, comprueban que el
arreglo se sostiene. Cada prueba de dinero o permisos se comprobó ROMPIENDO el arreglo a propósito (docs/YAPPY.md §14).

* R7-1: la Vendedora no deja «hecha» una transacción de Yappy con un ``write`` (la regla vive en ``dcasa_base``, para
  cualquier proveedor; ver ``dcasa_base/tests/test_transaccion_de_pago.py``).
* R7-2: el apartado nocturno salta un pedido con un cobro de Yappy abierto SIN borrarle la fecha de vencimiento.
* R7-3: el texto que manda quien llama a la dirección del aviso no llega al pendiente de Caja.
* R7-4: «Administra la nómina» entra por contabilidad y puede confirmar (política documentada, no un hueco).
* R7-5: un cobro suelto de Caja en el diario Yappy cuenta como dinero de otra vía.
* R7-6: el botón de Caja no confirma un borrador que Yappy nunca recibió.

Datos inventados; ninguna prueba toca la red.
"""
import re
from datetime import timedelta

from odoo import Command, fields
from odoo.addons.dcasa_pago_yappy.models import yappy_api as api
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .common import YappyFalso
from .test_dinero_revision import BaseDinero


class BaseRv7(BaseDinero):

    def cobro_abierto(self, pedido=None):
        """Una transacción abierta (``pending``) con su orden, como la deja ``/iniciar``."""
        with YappyFalso() as yappy:
            tx, _orden, _datos = self.abrir(yappy, pedido)
        self.assertEqual(tx.state, 'pending')
        return tx

    def cobros_contables(self, pedido):
        """Los cobros contables de las transacciones de ESTE pedido."""
        return self.env['account.payment'].sudo().search([
            ('payment_transaction_id', 'in', pedido.sudo().transaction_ids.ids)])

    def apartado(self, dias_atras=1):
        """Un pedido de la web confirmado (como el de «pago en tienda») con su apartado vencido hace ``dias_atras``."""
        pedido = self.pedido()
        if 'dcasa_apartado_vence' not in pedido._fields:
            self.skipTest('sin website_dcasa')
        pedido.action_confirm()
        self.assertEqual(pedido.state, 'sale')
        pedido.dcasa_apartado_vence = fields.Date.context_today(pedido) - timedelta(days=dias_atras)
        return pedido


# ======================================================================================================================
# R7-1 · la vendedora no deja «hecha» una transacción con un write
# ======================================================================================================================

@tagged('post_install', '-at_install')
class TestR71LaVendedoraNoMarcaPagadaUnaTransaccion(BaseRv7):

    def test_a12_el_write_de_la_vendedora_se_niega_y_el_cron_no_encuentra_nada_que_cerrar(self):
        """La prueba del revisor: ``write(state='done')`` y después el cron creaba el cobro en el diario Yappy y
        confirmaba el pedido, sin dinero y sin el botón de Caja."""
        vendedora = self.usuario('r71_vendedora_yappy', 'dcasa_base.group_vendedora')
        pedido = self.pedido()
        tx = self.cobro_abierto(pedido)
        with self.assertRaises(AccessError):
            tx.with_user(vendedora).write({'state': 'done'})
        tx.sudo()._post_process()
        self.assertEqual((tx.state, len(self.cobros_contables(pedido))), ('pending', 0))
        self.assertNotEqual(pedido.state, 'sale', 'el pedido no se confirmó con un write de la vendedora')

    def test_los_campos_de_yappy_tampoco_los_escribe_la_vendedora(self):
        """El revisor también escribió ``amount``, ``is_live``, ``dcasa_yappy_revision`` y ``dcasa_yappy_orden``."""
        vendedora = self.usuario('r71_vendedora_campos', 'dcasa_base.group_vendedora')
        tx = self.cobro_abierto()
        for campo, valor in (('amount', 0.01), ('is_live', True), ('dcasa_yappy_revision', False),
                             ('dcasa_yappy_orden', 'ZZZ'), ('dcasa_yappy_estado', 'E'),
                             ('dcasa_yappy_confirmada_por', vendedora.id)):
            with self.subTest(campo=campo), self.assertRaises(AccessError):
                tx.with_user(vendedora).write({campo: valor})
        self.assertEqual(tx.state, 'pending')

    def test_a13_la_vendedora_no_crea_una_transaccion_hecha_de_la_nada(self):
        vendedora = self.usuario('r71_vendedora_crea', 'dcasa_base.group_vendedora')
        pedido = self.pedido()
        with self.assertRaises(AccessError):
            self.env['payment.transaction'].with_user(vendedora).create({
                'provider_id': self.proveedor.id, 'payment_method_id': self.metodo.id,
                'amount': pedido.amount_total, 'currency_id': pedido.currency_id.id,
                'partner_id': pedido.partner_id.id, 'operation': 'online_direct',
                'sale_order_ids': [Command.set(pedido.ids)], 'state': 'done'})

    def test_lo_legitimo_de_yappy_sigue_funcionando(self):
        """El aviso de Yappy y el botón de Caja escriben con ``sudo``: no pasan por la regla nueva."""
        caja = self.usuario('r71_caja_yappy', 'dcasa_base.group_caja')
        pedido = self.pedido()
        tx = self.cobro_abierto(pedido)
        self.aviso(tx, 'E')
        self.assertEqual(tx.state, 'done')
        pedido2 = self.pedido()
        tx2 = self.cobro_abierto(pedido2)
        tx2.with_user(caja).action_dcasa_yappy_confirmar_cobro()
        self.assertEqual((tx2.state, tx2.dcasa_yappy_confirmada_por), ('done', caja))
        tx2.sudo()._post_process()
        self.assertEqual(len(self.cobros_contables(pedido2)), 1)


# ======================================================================================================================
# R7-2 · el apartado nocturno se salta esta noche, sin perder la fecha
# ======================================================================================================================

@tagged('post_install', '-at_install')
class TestR72ElApartadoNoPierdeSuFecha(BaseRv7):

    def test_b1_el_barrido_con_un_cobro_abierto_no_anula_el_pedido(self):
        pedido = self.apartado()
        self.cobro_abierto(pedido)
        self.env['sale.order']._dcasa_cron_vencer_apartados()
        self.assertEqual(pedido.state, 'sale')

    def test_b2_el_barrido_no_borra_la_fecha_y_el_pedido_vuelve_a_vencer(self):
        """Antes (``_dcasa_apartado_reclamado``) el barrido borraba ``dcasa_apartado_vence`` («deja de vigilarse») con
        solo un cobro de Yappy abierto: si la clienta nunca aprobaba, el pedido quedaba apartado para siempre."""
        pedido = self.apartado()
        fecha = pedido.dcasa_apartado_vence
        tx = self.cobro_abierto(pedido)
        self.env['sale.order']._dcasa_cron_vencer_apartados()
        self.assertEqual(pedido.dcasa_apartado_vence, fecha, 'la fecha no se borra')
        # la clienta nunca aprueba: Yappy expira la solicitud
        self.aviso(tx, 'X')
        self.envejecer(tx, minutes=40)
        self.assertEqual(tx.state, 'cancel')
        self.env['sale.order']._dcasa_cron_vencer_apartados()
        self.assertEqual(pedido.state, 'cancel', 'el apartado se suelta esta noche (el cobro ya murió)')

    def test_b3_un_apartado_que_vence_en_cinco_dias_conserva_su_fecha(self):
        """``_dcasa_avisar_apartados_por_vencer`` ya no trata un cobro abierto como «reclamado»."""
        pedido = self.apartado(dias_atras=-5)
        fecha = pedido.dcasa_apartado_vence
        self.cobro_abierto(pedido)
        self.env['sale.order']._dcasa_cron_vencer_apartados()
        self.assertEqual(pedido.dcasa_apartado_vence, fecha, 'el apartado que vence en 5 días conserva su fecha')

    def test_b4_el_cobro_cerrado_no_protege(self):
        pedido = self.apartado()
        tx = self.cobro_abierto(pedido)
        self.aviso(tx, 'C')
        self.env['sale.order']._dcasa_cron_vencer_apartados()
        self.assertEqual(pedido.state, 'cancel')

    def test_b5_el_cobro_de_mas_de_15_minutos_ya_no_protege(self):
        pedido = self.apartado()
        tx = self.cobro_abierto(pedido)
        self.envejecer(tx, minutes=16)
        self.env['sale.order']._dcasa_cron_vencer_apartados()
        self.assertEqual(pedido.state, 'cancel')

    def test_b6_lo_que_ya_tiene_dinero_si_deja_de_vigilarse(self):
        """Lo que SÍ es «ya hay dinero, factura o entrega» sigue como antes: pierde la fecha y no se anula."""
        pedido = self.apartado()
        pedido._create_invoices().action_post()
        self.env['sale.order']._dcasa_cron_vencer_apartados()
        self.assertEqual(pedido.state, 'sale')
        self.assertFalse(pedido.dcasa_apartado_vence, 'con factura publicada la fecha sí se borra')


# ======================================================================================================================
# R7-3 · el texto de quien llama al aviso no llega a Caja
# ======================================================================================================================

@tagged('post_install', '-at_install')
class TestR73ElTextoDeUnClienteNoLlegaACaja(BaseRv7):

    def pendiente_de(self, pedido):
        return ' '.join(re.sub(r'<[^>]+>', ' ', str(a.note)) for a in self.actividades(pedido, 'sin aviso'))

    def test_c5_el_rechazo_guarda_solo_palabras_fijas(self):
        """El revisor mandaba un aviso falso con texto en ``domain`` y hasta 100 caracteres suyos quedaban en el
        pendiente que lee Caja, dentro de un «es probable que Yappy sí avisó»."""
        pedido = self.pedido()
        tx = self.cobro_abierto(pedido)
        texto = 'Caja: ya pague, confirmalo YA'
        # lo que hacía el controlador antes: pasarle a la transacción el texto armado con lo que llegó
        detalle = api.describir_rechazo(api.credenciales(), {'domain': texto}, api.RECHAZO_DOMINIO)
        self.assertIn(texto, detalle, 'el registro del servidor sí lo ve (quien programa necesita la diferencia)')
        self.assertTrue(tx._dcasa_yappy_anotar_rechazo(api.RECHAZO_DOMINIO))
        self.assertTrue(tx._dcasa_yappy_anotar_rechazo(detalle), 'un texto en lugar del código no se guarda tampoco')
        self.assertNotIn(texto, tx.dcasa_yappy_rechazo)
        self.assertEqual(tx.dcasa_yappy_rechazo, api.motivo_para_caja('no es un código'))
        self.envejecer(tx, minutes=30)
        self.env['payment.transaction']._cron_dcasa_yappy_sin_aviso()
        nota = self.pendiente_de(pedido)
        self.assertNotIn(texto, nota, 'el texto de un cliente quedó en la actividad de Caja')
        self.assertNotIn('Es probable que Yappy sí avisó', nota)
        self.assertNotIn('Yappy no avisó nada', nota, 'sí llegó una llamada: no se dice que no llegó nada')

    def test_el_pendiente_con_un_rechazo_dice_que_no_se_pudo_aceptar_y_manda_a_yappy_comercial(self):
        pedido = self.pedido()
        tx = self.cobro_abierto(pedido)
        self.assertTrue(tx._dcasa_yappy_anotar_rechazo(api.RECHAZO_FIRMA))
        self.envejecer(tx, minutes=30)
        self.env['payment.transaction']._cron_dcasa_yappy_sin_aviso()
        nota = self.pendiente_de(pedido)
        self.assertIn('NO se pudo aceptar ningún aviso', nota)
        self.assertIn('Mira Yappy Comercial', nota)
        self.assertIn('no se sabe si el dinero entró', nota)
        self.assertIn('la firma del aviso no coincide', nota)
        self.assertIn('Confirmar que el dinero entró', nota, 'y sigue diciendo qué hacer si el dinero sí entró')

    def test_cada_motivo_tiene_su_frase_fija_y_ninguna_lleva_texto_ajeno(self):
        for motivo in api.RECHAZOS_CON_RASTRO:
            with self.subTest(motivo=motivo):
                frase = api.motivo_para_caja(motivo)
                self.assertTrue(frase)
                self.assertNotIn('«', frase, 'nada citado de lo que llegó')
        self.assertEqual(api.motivo_para_caja('x' * 500), api.motivo_para_caja(None))


# ======================================================================================================================
# R7-4 · «Administra la nómina» entra por contabilidad (política documentada)
# ======================================================================================================================

@tagged('post_install', '-at_install')
class TestR74NominaEntraPorContabilidad(BaseRv7):

    def test_quien_administra_la_nomina_puede_confirmar_porque_es_contabilidad(self):
        """No es un poder nuevo: ``dcasa_nomina.group_nomina`` implica ``account.group_account_user`` y contabilidad ya
        cobra (A5). Se deja dicho en ``docs/YAPPY.md`` §3.4/§14 y en la Guía; si alguien cambia esa implicación, esta
        prueba avisa para que se cambie también el texto."""
        grupo = self.env.ref('dcasa_nomina.group_nomina', raise_if_not_found=False)
        if not grupo:
            self.skipTest('sin dcasa_nomina')
        nomina = new_test_user(self.env, login='r74_nomina', groups='dcasa_nomina.group_nomina')
        self.assertTrue(nomina.has_group('account.group_account_user'), 'Nómina implica contabilidad')
        self.assertTrue(nomina.has_group('dcasa_nomina.group_nomina'))
        pedido = self.pedido()
        tx = self.cobro_abierto(pedido)
        resultado = tx.with_user(nomina).action_dcasa_yappy_confirmar_cobro()
        self.assertEqual(resultado['params']['type'], 'success')
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.dcasa_yappy_confirmada_por, nomina)

    def test_la_vendedora_el_interno_sin_rol_y_el_portal_siguen_fuera(self):
        for nombre, grupo in (('vendedora', 'dcasa_base.group_vendedora'), ('interno', 'base.group_user'),
                              ('portal', 'base.group_portal')):
            with self.subTest(rol=nombre):
                usuario = new_test_user(self.env, login=f'r74_{nombre}', groups=grupo)
                tx = self.cobro_abierto()
                with self.assertRaises(AccessError):
                    tx.with_user(usuario).action_dcasa_yappy_confirmar_cobro()
                self.assertEqual(tx.state, 'pending')


# ======================================================================================================================
# R7-5 · un cobro suelto de Caja en el diario Yappy es dinero de otra vía
# ======================================================================================================================

@tagged('post_install', '-at_install')
class TestR75ElCobroSueltoCuentaComoDineroDeOtraVia(BaseRv7):

    def cobro_suelto(self, pedido, monto=None, **extra):
        pago = self.env['account.payment'].create({
            'journal_id': self.diario_yappy().id, 'partner_id': pedido.partner_id.id,
            'amount': pedido.amount_total if monto is None else monto, 'payment_type': 'inbound',
            'partner_type': 'customer', **extra})
        pago.action_post()
        return pago

    def test_c2_el_aviso_E_tras_un_cobro_suelto_va_a_revision_y_no_cobra_otra_vez(self):
        pedido = self.pedido()
        tx = self.cobro_abierto(pedido)
        suelto = self.cobro_suelto(pedido)
        antes = len(self.pagos_del_diario(pedido))
        self.aviso(tx, 'E')
        tx._post_process()
        self.assertEqual((tx.state, tx.dcasa_yappy_revision), ('error', True))
        self.assertFalse(tx.payment_id, 'el aviso no cobra otra vez')
        self.assertEqual(len(self.pagos_del_diario(pedido)), antes, 'sigue UN solo cobro')
        alerta = self.actividades(pedido, 'ya estaba pagado')
        self.assertTrue(alerta)
        self.assertIn(suelto.name, alerta[0].note, 'la alerta dice cuál es el cobro suelto')
        self.assertIn('ya figuraba como pagado', tx.state_message)

    def test_tambien_el_boton_de_caja_respeta_el_cobro_suelto(self):
        caja = self.usuario('r75_caja', 'dcasa_base.group_caja')
        pedido = self.pedido()
        tx = self.cobro_abierto(pedido)
        self.cobro_suelto(pedido)
        resultado = tx.with_user(caja).action_dcasa_yappy_confirmar_cobro()
        self.assertEqual(resultado['params']['type'], 'warning')
        self.assertEqual((tx.state, tx.dcasa_yappy_revision), ('error', True))
        self.assertEqual(len(self.pagos_del_diario(pedido)), 1, 'nunca un segundo cobro')

    def test_el_cobro_suelto_de_otro_cliente_no_detiene_un_pago_normal(self):
        pedido = self.pedido()
        tx = self.cobro_abierto(pedido)
        otro = self.env['res.partner'].create({'name': 'Otro cliente R7-5'})
        self.env['account.payment'].create({
            'journal_id': self.diario_yappy().id, 'partner_id': otro.id, 'amount': 5.0, 'payment_type': 'inbound',
            'partner_type': 'customer'}).action_post()
        self.aviso(tx, 'E')
        self.assertEqual((tx.state, tx.dcasa_yappy_revision), ('done', False))

    def test_lo_que_no_es_dinero_de_otra_via_no_detiene_el_pago(self):
        """Un cobro en borrador, uno cancelado, uno en otro diario, uno saliente y uno de ANTES de abrir el cobro no
        cuentan."""
        pedido = self.pedido()
        tx = self.cobro_abierto(pedido)
        base = {'partner_id': pedido.partner_id.id, 'amount': pedido.amount_total, 'payment_type': 'inbound',
                'partner_type': 'customer', 'journal_id': self.diario_yappy().id}
        self.env['account.payment'].create(base)                                   # borrador
        cancelado = self.env['account.payment'].create(base)
        cancelado.action_post()
        cancelado.action_cancel()
        otro_diario = self.env['account.journal'].search([('type', '=', 'cash')], limit=1)
        self.env['account.payment'].create({**base, 'journal_id': otro_diario.id}).action_post()
        antes = self.env['account.payment'].create(base)
        antes.action_post()
        self.env.cr.execute('UPDATE account_payment SET create_date = create_date - interval \'2 hours\' WHERE id = %s',
                            [antes.id])
        antes.invalidate_recordset(['create_date'])
        tx.invalidate_recordset(['create_date'])
        self.assertEqual(tx._dcasa_yappy_cobros_sueltos(), self.env['account.payment'])
        self.aviso(tx, 'E')
        self.assertEqual((tx.state, tx.dcasa_yappy_revision), ('done', False))

    def test_un_cobro_aplicado_a_una_factura_de_otro_pedido_no_cuenta_como_suelto(self):
        """Lo aplicado a una factura se cuenta por la factura de ESTE pedido (``test_c1`` de ``test_dinero_revision``);
        un cobro aplicado a la factura de otro pedido del mismo cliente no es de este."""
        pedido = self.pedido()
        tx = self.cobro_abierto(pedido)
        otro = self.pedido()
        self.facturar_y_cobrar_a_mano(otro)
        self.assertEqual(tx._dcasa_yappy_cobros_sueltos(), self.env['account.payment'])
        self.aviso(tx, 'E')
        self.assertEqual((tx.state, tx.dcasa_yappy_revision), ('done', False))


# ======================================================================================================================
# R7-6 · el botón de Caja no confirma un borrador que Yappy nunca recibió
# ======================================================================================================================

@tagged('post_install', '-at_install')
class TestR76ElBotonNoConfirmaUnBorradorQueYappyNoRecibio(BaseRv7):

    def borrador_con_orden(self, con_id=False):
        """Lo que deja un corte a mitad de ``/iniciar``: la orden ya se guardó (ANTES de llamar a Yappy) y Yappy nunca
        contestó."""
        pedido = self.pedido()
        tx = self.transaccion(pedido)
        tx.write({'dcasa_yappy_orden': 'S9999AAAAA', 'dcasa_yappy_iniciada': fields.Datetime.now(),
                  **({'dcasa_yappy_id': 'ID-DE-YAPPY'} if con_id else {})})
        tx.flush_recordset()
        self.assertEqual(tx.state, 'draft')
        return pedido, tx

    def test_a4_un_borrador_con_orden_y_sin_identificador_de_yappy_no_se_confirma(self):
        caja = self.usuario('r76_caja', 'dcasa_base.group_caja')
        pedido, tx = self.borrador_con_orden()
        with self.assertRaises(UserError):
            tx.with_user(caja).action_dcasa_yappy_confirmar_cobro()
        self.assertEqual(tx.state, 'draft')
        self.assertFalse(tx.dcasa_yappy_confirmada_por)
        self.assertFalse(self.cobros_contables(pedido))
        self.assertNotEqual(pedido.state, 'sale')

    def test_el_borrador_sigue_sin_confirmarse_aunque_se_pulse_dos_veces(self):
        """Mientras se llama a Yappy (la transacción sigue en borrador) el botón tampoco sirve."""
        caja = self.usuario('r76_caja_ventana', 'dcasa_base.group_caja')
        _pedido, tx = self.borrador_con_orden()
        for _vez in range(2):
            with self.assertRaises(UserError):
                tx.with_user(caja).action_dcasa_yappy_confirmar_cobro()

    def test_con_el_identificador_de_yappy_si_se_confirma(self):
        caja = self.usuario('r76_caja_con_id', 'dcasa_base.group_caja')
        _pedido, tx = self.borrador_con_orden(con_id=True)
        resultado = tx.with_user(caja).action_dcasa_yappy_confirmar_cobro()
        self.assertEqual(resultado['params']['type'], 'success')
        self.assertEqual(tx.state, 'done')

    def test_una_orden_pendiente_aunque_Yappy_no_contestara_si_se_confirma(self):
        """Si la llamada se cortó a medias, la orden pudo crearse en Yappy: la transacción queda ``pending`` (no se
        sabe) y Caja, mirando Yappy Comercial, la puede confirmar."""
        caja = self.usuario('r76_caja_pendiente', 'dcasa_base.group_caja')
        _pedido, tx = self.borrador_con_orden()
        tx._set_pending()
        resultado = tx.with_user(caja).action_dcasa_yappy_confirmar_cobro()
        self.assertEqual(resultado['params']['type'], 'success')

    def test_el_pendiente_de_un_borrador_sin_identificador_no_manda_a_pulsar_el_boton(self):
        """El pendiente de las 15 minutos no puede mandar a Caja a pulsar un botón que se va a negar."""
        pedido, tx = self.borrador_con_orden()
        self.envejecer(tx, minutes=30)
        self.assertEqual(self.env['payment.transaction']._cron_dcasa_yappy_sin_aviso(), 1)
        nota = re.sub(r'<[^>]+>', ' ', ' '.join(a.note for a in self.actividades(pedido, 'sin aviso')))
        self.assertIn('se quedó a medio abrir', nota)
        self.assertIn('NO la acepta', nota)
        self.assertNotIn('pulsa «Confirmar que el dinero entró»', nota)
        self.assertIn('NO registres el cobro a mano', nota)

    def test_el_pendiente_de_una_orden_normal_sigue_mandando_al_boton(self):
        pedido = self.pedido()
        tx = self.cobro_abierto(pedido)
        self.envejecer(tx, minutes=30)
        self.env['payment.transaction']._cron_dcasa_yappy_sin_aviso()
        nota = re.sub(r'<[^>]+>', ' ', ' '.join(a.note for a in self.actividades(pedido, 'sin aviso')))
        self.assertIn('pulsa «Confirmar que el dinero entró»', nota)
        self.assertNotIn('se quedó a medio abrir', nota)
