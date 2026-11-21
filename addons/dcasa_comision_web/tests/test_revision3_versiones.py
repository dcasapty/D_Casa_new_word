"""Tercera revisión: qué versión de las reglas le toca a cada venta y quién se la queda (hallazgos 2 y 3), la pantalla de
una versión «tapada» y el aviso de una nota sin producto. Cada prueba dice en su nombre lo que se intentó.
Cifras y personas de PRUEBA."""
# ruff: noqa: E501, UP031, B007, B023, F841, PLW0108, RUF012
from datetime import date, timedelta

from odoo import Command, fields
from odoo.tests import tagged

from .test_endurecimiento import Liquida
from .test_vendedoras import VendedoraCommon


@tagged('post_install', '-at_install')
class TestVersionesYDiaDeCobro(Liquida):

    def pago_de(self, factura):
        return factura._get_reconciled_payments()

    # ------------------------------------------------------------------ hallazgo 3: pago con fecha futura

    def test_un_cobro_con_fecha_futura_no_escoge_una_version_programada(self):
        """A rige hoy (10 %) y B (50 %) está programada para dentro de 10 días. Caja registra hoy el pago con fecha de
        dentro de 10 días: la venta se calcula con la versión de HOY, no con la programada."""
        self.version(10.0)
        self.version(50.0, rige_desde=fields.Datetime.now() + timedelta(days=10))
        factura = self.venta_web(fecha='2030-03-14')
        venta = self.venta(factura)
        self.assertEqual(venta.reglas_id.numero, 1)
        self.assertEqual(venta.comision_centavos, 10000, '10 % de 1,000, no 50 %')

    def test_un_cobro_con_fecha_futura_queda_senalado_en_ventas_del_sitio(self):
        self.version(10.0)
        futura = self.venta(self.venta_web(fecha='2030-03-14'))
        normal = self.venta(self.venta_web())
        self.assertTrue(futura.cobro_adelantado)
        self.assertFalse(futura.cobro_atrasado)
        self.assertFalse(normal.cobro_adelantado)
        con_fecha_futura = self.env['dcasa.web.venta'].with_user(self.u_nomina).search([('cobro_adelantado', '=', True)])
        self.assertEqual(con_fecha_futura, futura)

    def test_cuando_llega_el_dia_de_un_cobro_futuro_el_barrido_la_calcula_con_la_version_que_rige_ese_dia(self):
        """Cuarta revisión: un pago con fecha futura se calcula con la versión de HOY; al llegar el día (aquí el 14, cuando
        empieza a regir la de 50 %) el barrido la vuelve a escoger, igual que si se cobrara desde cero con esa fecha.
        Antes se quedaba con la versión de hoy para siempre."""
        self.version(10.0)
        self.version(50.0, rige_desde=fields.Datetime.now() + timedelta(days=10))
        venta = self.venta(self.venta_web(fecha='2030-03-14'))
        self.assertEqual((venta.reglas_id.numero, venta.comision_centavos), (1, 10000), 'hoy rige la de 10 %')
        self.avanzar('2030-03-20 15:00:00')
        self.env['dcasa.web.venta']._barrido()
        self.assertEqual((venta.reglas_id.numero, venta.comision_centavos), (2, 50000))
        desde_cero = self.venta(self.venta_web(fecha='2030-03-14'))
        self.assertEqual((desde_cero.reglas_id.numero, desde_cero.comision_centavos), (2, 50000))
        self.assertTrue(venta.cobro_adelantado, 'la señal de la fecha futura se queda')

    # ------------------------------------------------------------------ versión tapada

    def test_una_version_tapada_dice_tapada_y_no_programada(self):
        """B (pausa) se guarda para dentro de 16 días y luego C (5 %) para dentro de 6: desde el día 6 manda C y B nunca
        manda. Antes la pantalla de B decía «Programada» hasta su día."""
        self.version(10.0)
        B = self.version(0.0, rige_desde=fields.Datetime.now() + timedelta(days=16))
        self.assertEqual(B.estado, 'programada')
        C = self.version(5.0, rige_desde=fields.Datetime.now() + timedelta(days=6))
        self.env.invalidate_all()       # el estado se calcula al abrir la pantalla: no se queda con lo de antes
        Reglas = self.env['dcasa.web.reglas']
        self.assertEqual(Reglas._vigente(self.company, fields.Datetime.now() + timedelta(days=20)), C)
        self.assertEqual((B.estado, C.estado), ('tapada', 'programada'))
        self.assertEqual(B.tapada_por_id, C)
        self.assertIn(f'versión {C.numero}', B.aviso_tapada)

    def test_una_version_que_tapa_a_otra_avisa_mientras_se_escribe_y_despues_de_guardar(self):
        self.version(10.0)
        B = self.version(0.0, rige_desde=fields.Datetime.now() + timedelta(days=16))
        Reglas = self.env['dcasa.web.reglas']
        nueva = Reglas.new({'company_id': self.company.id, 'rige_desde': fields.Datetime.now() + timedelta(days=6)})
        self.assertEqual(nueva.tapa_a_ids._origin, B)
        self.assertIn(f'versión {B.numero}', nueva.aviso_tapa)
        mas_lejos = Reglas.new({'company_id': self.company.id, 'rige_desde': fields.Datetime.now() + timedelta(days=20)})
        self.assertFalse(mas_lejos.aviso_tapa, 'una versión más lejana no tapa a ninguna')
        C = self.version(5.0, rige_desde=fields.Datetime.now() + timedelta(days=6))
        self.assertEqual(C.tapa_a_ids, B)
        self.assertIn(f'versión {B.numero}', C.aviso_tapa)
        self.assertFalse(B.aviso_tapa)

    def test_una_version_tapada_se_puede_anular_y_la_otra_vuelve_a_mandar(self):
        self.version(10.0)
        B = self.version(0.0, rige_desde=fields.Datetime.now() + timedelta(days=16))
        C = self.version(5.0, rige_desde=fields.Datetime.now() + timedelta(days=6))
        self.env.invalidate_all()
        self.assertEqual(B.estado, 'tapada')
        C.with_user(self.u_nomina).write({'motivo_anulacion': 'se puso mal'})
        C.with_user(self.u_nomina).action_anular()
        self.env.invalidate_all()
        self.assertEqual((B.estado, C.estado), ('programada', 'anulada'))
        B.with_user(self.u_nomina).write({'motivo_anulacion': 'otra prueba'})
        B.with_user(self.u_nomina).action_anular()
        self.assertEqual(B.estado, 'anulada')

    def test_lo_ya_registrado_no_cambia_cuando_se_guarda_una_version_con_fecha_de_hoy(self):
        self.version(10.0)
        venta = self.venta(self.venta_web())
        self.version(50.0)       # hoy mismo, más tarde
        self.env['dcasa.web.venta']._barrido()
        self.assertEqual((venta.porcentaje, venta.comision_centavos), (10.0, 10000))

    # ------------------------------------------------------------------ hallazgo 2: re-cobro

    def test_un_pago_cancelado_y_repuesto_despues_de_otra_version_se_calcula_con_la_version_de_ese_dia(self):
        """A (10 %) hoy y B (5 %) desde el 14. El cobro se cancela y se vuelve a hacer el día 21: manda B. El libro lo
        cuenta con filas: la venta, el reverso que la cierra y la venta nueva (nunca se edita una fila)."""
        self.version(10.0)
        B = self.version(5.0, rige_desde=fields.Datetime.now() + timedelta(days=10))
        factura = self.venta_web()
        venta = self.venta(factura)
        self.pago_de(factura).action_cancel()
        self.env['dcasa.web.venta']._barrido()
        self.assertEqual(venta.comision_centavos, 0)
        self.avanzar('2030-03-21 15:00:00')
        self.pagar(factura, '2030-03-21')
        self.assertTrue(venta.cobrada)
        self.assertEqual((venta.fecha_cobro, venta.mes, venta.reglas_id, venta.porcentaje),
                         (date(2030, 3, 21), date(2030, 3, 1), B, 5.0))
        self.assertEqual(venta.comision_centavos, 5000, 'el día de cobro vigente es el 21: manda B')
        self.assertEqual(sorted(self.libro(venta=venta).mapped('tipo')), ['reverso'] * 2 + ['venta'] * 4)

    def test_un_re_cobro_sin_pasar_por_el_barrido_tambien_cierra_y_abre(self):
        """El pago se cancela y se registra otra vez de corrido (nadie compara el libro en medio): el día de cobro
        cambió, y eso basta para cerrar lo anotado y calcularlo de nuevo con las reglas de ese día."""
        self.version(10.0)
        B = self.version(5.0, rige_desde=fields.Datetime.now() + timedelta(days=10))
        factura = self.venta_web()
        venta = self.venta(factura)
        self.assertEqual(venta.comision_centavos, 10000)
        self.pago_de(factura).action_cancel()
        self.avanzar('2030-03-21 15:00:00')
        self.pagar(factura, '2030-03-21')
        self.assertEqual((venta.reglas_id, venta.fecha_cobro, venta.comision_centavos), (B, date(2030, 3, 21), 5000))
        self.assertEqual(sorted(self.libro(venta=venta).mapped('tipo')), ['reverso'] * 2 + ['venta'] * 4)
        self.env['dcasa.web.venta']._barrido()
        self.assertEqual(venta.comision_centavos, 5000, 'el barrido no cambia nada')
        self.assertEqual(len(self.libro(venta=venta)), 6)

    def test_cambiar_la_fecha_de_un_pago_ya_hecho_se_ve_al_armar(self):
        """La huella incluye la fecha de cada conciliación: corregir la fecha de un pago (a borrador, nueva fecha,
        publicar) cambia el día de cobro y armar lo ve sin esperar al barrido de la noche."""
        self.version(10.0)
        self.avanzar('2030-03-06 15:00:00')
        factura = self.facturar(self.orden(), '2030-03-02')
        self.pagar(factura, '2030-03-06')
        venta = self.venta(factura)
        self.assertEqual((venta.fecha_cobro, venta.comision_centavos), (date(2030, 3, 6), 10000))
        pago = self.pago_de(factura)
        pago.action_draft()
        pago.date = '2030-03-05'
        pago.action_post()
        self.env['dcasa.web.venta']._poner_al_dia()
        self.assertEqual((venta.fecha_cobro, venta.mes, venta.comision_centavos), (date(2030, 3, 5), date(2030, 3, 1), 10000))
        self.assertEqual(sorted(self.libro(venta=venta).mapped('tipo')), ['venta'] * 2,
                         'es la misma versión: el libro no se mueve (ni se paga doble)')

    def test_un_re_cobro_el_mismo_dia_no_cambia_la_version_ni_la_fecha(self):
        self.version(10.0)
        factura = self.venta_web()
        venta = self.venta(factura)
        self.pago_de(factura).action_cancel()
        self.env['dcasa.web.venta']._barrido()
        self.pagar(factura)
        self.assertEqual((venta.reglas_id.numero, venta.fecha_cobro, venta.comision_centavos), (1, date(2030, 3, 4), 10000))

    def test_un_re_cobro_con_la_liquidacion_ya_aprobada_deja_saldo_en_contra_y_no_toca_lo_liquidado(self):
        """Lo ya liquidado no se recalcula: el re-cobro cierra el ciclo anterior con un reverso (asiento contrario) y abre
        otro con la versión de ese día. Si lo anterior ya se mandó a pagar, queda un saldo en contra que lo nuevo
        compensa en parte: nada se edita ni se borra."""
        self.version(10.0)
        self.version(5.0, rige_desde=fields.Datetime.now() + timedelta(days=10))
        factura = self.venta_web()
        venta = self.venta(factura)
        self.avanzar('2030-03-05 15:00:00')
        liquidacion = self.liquidar(usuario=self.u_nomina, hasta='2030-03-31')
        liquidacion.with_user(self.u_nomina).action_aprobar()
        self.assertEqual((liquidacion.estado, liquidacion.total), ('aprobada', 100.0))
        filas_antes = self.libro().ids
        self.pago_de(factura).action_cancel()
        self.avanzar('2030-03-21 15:00:00')
        self.pagar(factura, '2030-03-21')
        self.assertEqual(liquidacion.estado, 'aprobada')
        self.assertEqual(liquidacion.total, 100.0, 'la liquidación aprobada no se toca')
        self.assertTrue(set(filas_antes) <= set(self.libro().ids), 'no se borró ninguna fila')
        self.assertEqual(venta.comision_centavos, 5000)
        self.assertEqual((self.saldo(self.ana), self.saldo(self.beto)), (-3000, -2000),
                         '100 pagados - 100 reversados + 50 nuevos = 50 menos de lo pagado, repartidos 60/40')

    # ------------------------------------------------------------------ otros avisos

    def test_una_nota_sin_producto_queda_senalada_en_ventas_del_sitio(self):
        """Una nota libre, sin producto, no se puede atribuir al envío: resta de lo vendido (decisión de la segunda
        revisión) y se avisa para que alguien la mire."""
        self.version(10.0)
        factura = self.facturar(self.orden(lineas=[(self.mueble, 1000.0, 1, {}),
                                                   (self.envio, 50.0, 1, {'is_delivery': True})]))
        self.pagar(factura)
        venta = self.venta(factura)
        self.assertEqual((venta.comision_centavos, venta.nota_sin_producto), (10000, False))
        self.nota(factura, 50.0)       # ``self.nota`` no pone producto
        self.assertTrue(venta.nota_sin_producto)
        self.assertEqual(venta.comision_centavos, 9500, 'se resta de lo vendido: 50 menos de base')
        con_aviso = self.env['dcasa.web.venta'].with_user(self.u_nomina).search([('nota_sin_producto', '=', True)])
        self.assertEqual(con_aviso, venta)

    def test_una_nota_con_producto_no_se_senala(self):
        self.version(10.0)
        factura = self.venta_web()
        venta = self.venta(factura)
        nota = self.env['account.move'].create({
            'move_type': 'out_refund', 'partner_id': factura.partner_id.id, 'invoice_date': '2030-03-04',
            'reversed_entry_id': factura.id,
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'name': 'Devolución', 'quantity': 1,
                                                 'price_unit': 100.0})]})
        nota.action_post()
        self.assertFalse(venta.nota_sin_producto)

    def test_un_pago_cancelado_no_reversa_en_el_acto_lo_hace_armar_o_el_barrido(self):
        """Constancia (hallazgo menor 26): cancelar un pago no tiene gancho, así que la venta sigue «con comisión» hasta
        el próximo armar, aprobar o el barrido de la noche; armar compara antes de sumar, así que nunca paga de más."""
        self.version(10.0)
        factura = self.venta_web()
        venta = self.venta(factura)
        self.pago_de(factura).action_cancel()
        self.assertEqual(venta.comision_centavos, 10000, 'todavía no se compara con el libro')
        liquidacion = self.liquidar(usuario=self.u_nomina, hasta='2030-03-31')
        self.assertFalse(liquidacion.linea_ids, 'armar compara antes: no paga lo de un pago cancelado')
        self.assertEqual((venta.cobrada, venta.comision_centavos), (False, 0))


@tagged('post_install', '-at_install')
class TestSinDuenoTrasRepago(VendedoraCommon):
    """La venta cobrada otra vez es de UNA sola parte: ni de nadie ni de las dos (el bono usa el día de cobro en vivo)."""

    def test_cobrada_antes_de_la_primera_version_cancelada_y_cobrada_otra_vez_despues_es_del_sitio(self):
        factura = self.vender(web=True, pago='2030-03-03')
        self.assertEqual(self.bono().cobrado, 1000.0, 'antes de la regla es de la vendedora')
        factura._get_reconciled_payments().action_cancel()
        self.version(10.0)
        self.pagar(factura, '2030-03-05')
        self.env['dcasa.web.venta']._barrido()
        venta = self.venta(factura)
        self.assertEqual(self.bono().cobrado, 0.0, 'cobrada el 5, después de la regla: ya no es de la vendedora')
        self.assertEqual((venta.fecha_cobro, venta.comision_centavos), (date(2030, 3, 5), 10000))

    def test_cobrada_despues_de_la_regla_cancelada_y_cobrada_otra_vez_con_fecha_anterior_es_de_la_vendedora(self):
        """Versión desde el 4 de marzo. Venta online cobrada el 6 (del sitio): se cancela el pago y se vuelve a registrar
        con fecha del 2 (antes de la regla). Ahora cuenta para el bono y deja de pagar al sitio: paga a una sola parte."""
        self.version(10.0)
        self.avanzar('2030-03-06 15:00:00')
        orden = self.orden(web=True, vendedora=self.u_vendedora, lineas=[(self.mueble, 1000.0, 1, {})])
        factura = self.facturar(orden, '2030-03-02')        # facturada ANTES de la regla, cobrada DESPUÉS
        self.pagar(factura, '2030-03-06')
        venta = self.venta(factura)
        self.assertEqual((self.bono().cobrado, venta.comision_centavos), (0.0, 10000), 'online después de la regla: del sitio')
        factura._get_reconciled_payments().action_cancel()
        self.env['dcasa.web.venta']._barrido()
        self.pagar(factura, '2030-03-02')
        self.env['dcasa.web.venta']._barrido()
        self.assertEqual((self.bono().cobrado, venta.comision_centavos), (1000.0, 0), 'ahora es solo de la vendedora')
        self.assertEqual((venta.estado, venta.fecha_cobro), ('medida', date(2030, 3, 2)))
        self.assertTrue(venta.cobro_atrasado, 'la fecha atrasada queda señalada')
        self.assertEqual(sum(self.libro(venta=venta).mapped('centavos')), 0)
