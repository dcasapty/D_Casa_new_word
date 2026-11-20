"""Tercera revisión, la HUELLA de cada venta (armar y aprobar solo recomponen las ventas cuya factura cambió).

Idea: tras cada suceso que mueve el dinero se llama a ``_poner_al_dia`` (lo que usan armar y aprobar una liquidación) y
el libro se compara con el cálculo «desde cero» de cada venta (``verdad``: ``_componentes`` + ``base_de_la_venta``,
sin mirar la huella). Cada suceso se corre dos veces: con los ganchos del sistema encendidos (lo normal) y «a ciegas»
(``ciego``: ``_reconciliar`` no hace nada salvo dentro de ``_poner_al_dia``), que prueba que la huella SOLA basta.
Incluye el hallazgo 4 (armar y aprobar también reponen una venta «apagada») y el menor de la pasarela guardada
después del pago.

Cifras y personas de PRUEBA."""
# ruff: noqa: E501, UP031, B007, B023, F841, PLW0108, RUF012
from contextlib import contextmanager, nullcontext
from unittest.mock import patch

from odoo import Command
from odoo.addons.dcasa_comision_web.models import calculo
from odoo.addons.dcasa_comision_web.tests.common import DIA
from odoo.addons.dcasa_comision_web.tests.test_endurecimiento import Liquida
from odoo.tests import tagged


class HuellaBase(Liquida):

    def setUp(self):
        super().setUp()
        self.Venta = self.env['dcasa.web.venta']

    # ------------------------------------------------------------------ la verdad «desde cero»
    def verdad(self):
        """{venta_id: {empleado_id: centavos}} calculado de la factura, sin huella ni libro."""
        self.env.flush_all()
        self.env.invalidate_all()
        resultado = {}
        for venta in self.Venta.sudo().search([('reglas_id', '!=', False)]):
            move = venta.move_id
            pagada = self.Venta._pagada(move) if move else False
            if move and move.state == 'posted':
                c, _o = self.Venta._componentes(move)
            else:
                c = {k: venta[f'{k}_centavos'] for k in calculo.COMPONENTES}
            reglas = venta.reglas_id
            base = calculo.base_de_la_venta(c, reglas._opciones())
            debe = calculo.porcentaje_de(base, reglas.porcentaje) if pagada else 0
            resultado[venta.id] = {e: c_ for e, c_ in calculo.repartir(
                debe, [(r.empleado_id.id, r.porcentaje) for r in reglas.reparto_ids]).items() if c_}
        return resultado

    def asentado(self):
        resultado = {}
        for fila in self.env['dcasa.web.movimiento'].sudo().search([
                ('venta_id', '!=', False), ('tipo', 'in', ('venta', 'devolucion', 'reverso'))]):
            por = resultado.setdefault(fila.venta_id.id, {})
            por[fila.empleado_id.id] = por.get(fila.empleado_id.id, 0) + fila.centavos
        return {v: {e: c for e, c in por.items() if c} for v, por in resultado.items()}

    def diferencias(self):
        v, a = self.verdad(), self.asentado()
        return {k: {'verdad': v.get(k, {}), 'libro': a.get(k, {})} for k in set(v) | set(a)
                if v.get(k, {}) != a.get(k, {})}

    def al_dia(self):
        """Lo que hacen armar y aprobar antes de sumar un centavo."""
        return self.Venta.with_context(huella_permitir=True)._poner_al_dia()

    def cuadra(self, que):
        """Tras ``_poner_al_dia`` el libro debe ser igual a la verdad. Si no, se dice si el barrido lo arregla."""
        self.al_dia()
        dif = self.diferencias()
        if dif:
            self.env.cr.execute('UPDATE dcasa_web_venta SET huella = NULL')
            self.Venta.invalidate_model()
            self.al_dia()
            arreglado = not self.diferencias()
            self.fail('%s: tras _poner_al_dia el libro NO coincide con el calculo desde cero: %s (con la huella borrada %s)'
                      % (que, dif, 'si queda bien: la huella no vio el cambio' if arreglado else 'sigue mal'))

    @contextmanager
    def ciego(self):
        """Ganchos apagados: ``_reconciliar`` solo corre con ``huella_permitir`` (es decir, dentro de ``al_dia``)."""
        clase = type(self.Venta)
        original = clase._reconciliar

        def envuelto(venta):
            if venta.env.context.get('huella_permitir'):
                return original(venta)
            return None
        with patch.object(clase, '_reconciliar', envuelto):
            yield

    def modos(self):
        return (('ganchos', nullcontext), ('ciego', self.ciego))

    def pagada(self, **kw):
        factura = self.venta_web(**kw)
        return factura, self.venta(factura)

    def pago_de(self, factura):
        return factura._get_reconciled_payments()

    def nota_con(self, factura, producto, monto, impuestos=(), fecha=DIA):
        nota = self.env['account.move'].create({
            'move_type': 'out_refund', 'partner_id': factura.partner_id.id, 'invoice_date': fecha,
            'reversed_entry_id': factura.id,
            'invoice_line_ids': [Command.create({'product_id': producto.id, 'name': 'Devolucion', 'quantity': 1,
                                                 'price_unit': monto, 'tax_ids': [Command.set(list(impuestos))]})]})
        nota.action_post()
        return nota


@tagged('post_install', '-at_install')
class TestHuellaSucesos(HuellaBase):

    def test_pago_parcial_y_luego_completo(self):
        self.version(10.0)
        factura = self.facturar(self.orden())
        self.pagar(factura, monto=500.0)
        self.assertFalse(self.venta(factura), 'un abono a medias no cuenta')
        self.cuadra('despues del abono')
        self.pagar(factura)
        venta = self.venta(factura)
        self.assertEqual(venta.comision_centavos, 10000)
        self.cuadra('despues del pago completo')

    def test_nota_de_credito_parcial_enlazada(self):
        self.version(10.0)
        for modo, ctx in self.modos():
            with self.subTest(modo=modo):
                factura, venta = self.pagada()
                with ctx():
                    self.nota(factura, 400.0)
                self.cuadra('nota parcial ' + modo)
                self.assertEqual(venta.comision_centavos, 6000, modo)

    def test_nota_de_credito_total(self):
        self.version(10.0)
        for modo, ctx in self.modos():
            with self.subTest(modo=modo):
                factura, venta = self.pagada()
                with ctx():
                    self.nota(factura, 1000.0)
                self.cuadra('nota total ' + modo)
                self.assertEqual(venta.comision_centavos, 0, modo)

    def test_nota_de_credito_cancelada_repone_la_comision(self):
        self.version(10.0)
        for modo, ctx in self.modos():
            with self.subTest(modo=modo):
                factura, venta = self.pagada()
                nota = self.nota(factura, 400.0)
                with ctx():
                    nota.button_draft()
                    nota.button_cancel()
                self.cuadra('nota cancelada ' + modo)
                self.assertEqual(venta.comision_centavos, 10000, modo)

    def test_nota_de_credito_a_borrador_y_otra_vez_publicada_con_otro_producto_mismo_total(self):
        """La huella de una nota solo trae id, estado, base e ITBMS: si se cambia el PRODUCTO de la linea (envio en vez
        de mueble) con el mismo total, la huella no cambia. Los ganchos de ``_post`` lo cubren; a ciegas, no."""
        self.version(10.0)
        for modo, ctx in self.modos():
            with self.subTest(modo=modo):
                factura = self.facturar(self.orden(lineas=[(self.mueble, 1000.0, 1, {}),
                                                           (self.envio, 50.0, 1, {'is_delivery': True})]))
                self.pagar(factura)
                venta = self.venta(factura)
                nota = self.nota_con(factura, self.mueble, 50.0)
                self.assertEqual(venta.comision_centavos, 9500, 'la nota devolvio 50 de mueble')
                nota.button_draft()
                nota.invoice_line_ids.write({'product_id': self.envio.id, 'price_unit': 50.0, 'tax_ids': [Command.clear()]})
                self.assertEqual(nota.amount_untaxed, 50.0)
                with ctx():
                    nota.action_post()
                self.cuadra('nota re-publicada ' + modo)
                self.assertEqual(venta.comision_centavos, 10000, modo + ': lo devuelto era solo el envio y el envio no cuenta')

    def test_pago_cancelado_o_vuelto_a_borrador_reversa_lo_anotado(self):
        self.version(10.0)
        for modo, ctx in self.modos():
            for como in ('cancelar',):
                with self.subTest(modo=modo, como=como):
                    factura, venta = self.pagada()
                    pago = self.pago_de(factura)
                    self.assertTrue(pago)
                    with ctx():
                        pago.action_cancel()
                    self.cuadra(f'pago {como} {modo}')
                    self.assertEqual((venta.cobrada, venta.comision_centavos), (False, 0), f'{modo}/{como}')

    def test_pago_vuelto_a_borrador_en_odoo_19_no_despaga_la_factura(self):
        """Constancia: en Odoo 19 un pago en borrador sigue conciliado, la factura sigue pagada y la comision se queda."""
        self.version(10.0)
        factura, venta = self.pagada()
        self.pago_de(factura).action_draft()
        self.cuadra('pago en borrador')
        self.assertEqual((factura.payment_state, venta.cobrada, venta.comision_centavos), ('paid', True, 10000))

    def test_reverso_del_asiento_del_pago(self):
        self.version(10.0)
        for modo, ctx in self.modos():
            with self.subTest(modo=modo):
                factura, venta = self.pagada()
                pago = self.pago_de(factura)
                with ctx():
                    self.env['account.move.reversal'].with_context(
                        active_model='account.move', active_ids=pago.move_id.ids).create({
                            'journal_id': pago.move_id.journal_id.id, 'reason': 'prueba', 'date': DIA}).reverse_moves()
                self.cuadra('reverso del asiento del pago ' + modo)

    def test_conciliacion_deshecha_por_otra_via(self):
        self.version(10.0)
        for modo, ctx in self.modos():
            for via in ('remove_move_reconcile', 'partial_unlink'):
                with self.subTest(modo=modo, via=via):
                    factura, venta = self.pagada()
                    cuentas = factura.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
                    with ctx():
                        if via == 'remove_move_reconcile':
                            cuentas.remove_move_reconcile()
                        else:
                            (cuentas.matched_debit_ids | cuentas.matched_credit_ids).unlink()
                    self.cuadra(f'conciliacion deshecha {via} {modo}')
                    self.assertEqual((venta.cobrada, venta.comision_centavos), (False, 0), f'{modo}/{via}')

    def test_factura_a_borrador_cancelada_y_borrada(self):
        self.version(10.0)
        for modo, ctx in self.modos():
            for como in ('borrador', 'cancelada', 'borrada'):
                with self.subTest(modo=modo, como=como):
                    factura, venta = self.pagada()
                    with ctx():
                        if como == 'borrador':
                            factura.button_draft()
                        elif como == 'cancelada':
                            factura.button_cancel()
                        else:
                            factura.button_draft()
                            factura.unlink()
                    self.cuadra(f'factura {como} {modo}')
                    self.assertEqual((venta.cobrada, venta.comision_centavos), (False, 0), f'{modo}/{como}')

    def test_factura_a_borrador_y_otra_vez_publicada_sin_cambios_repone_la_comision(self):
        """Corregir un dato de una factura pagada (a borrador y publicar): en Odoo 19 las conciliaciones se quedan y la
        comisión se repone sin esperar al barrido de la noche (hallazgo 4)."""
        self.version(10.0)
        factura, venta = self.pagada()
        factura.button_draft()
        self.assertFalse(venta.cobrada)
        factura.action_post()
        self.assertEqual(factura.payment_state in ('paid', 'in_payment'), True, 'las conciliaciones se quedan')
        self.cuadra('borrador y publicada otra vez, sin esperar al barrido')

    def test_precio_y_descuento_editado_en_borrador_y_pagada_otra_vez(self):
        self.version(10.0)
        for modo, ctx in self.modos():
            for que in ('precio', 'descuento'):
                with self.subTest(modo=modo, que=que):
                    factura, venta = self.pagada()
                    factura.button_draft()
                    linea = factura.invoice_line_ids.filtered(lambda ln: ln.product_id == self.mueble)
                    if que == 'precio':
                        linea.price_unit = 800.0
                    else:
                        linea.discount = 25.0
                    with ctx():
                        factura.action_post()
                        if factura.payment_state not in ('paid', 'in_payment'):
                            self.pagar(factura)
                    self.cuadra(f'{que} editado {modo}')
                    self.assertEqual(venta.comision_centavos, 8000 if que == 'precio' else 7500, f'{modo}/{que}')

    def test_cambio_de_impuesto_con_itbms_en_la_base(self):
        self.version(10.0, base_itbms='con')
        for modo, ctx in self.modos():
            with self.subTest(modo=modo):
                factura, venta = self.pagada()
                self.assertEqual(venta.comision_centavos, 10700)
                factura.button_draft()
                factura.invoice_line_ids.filtered(lambda ln: ln.product_id == self.mueble).tax_ids = [Command.clear()]
                with ctx():
                    factura.action_post()
                    if factura.payment_state not in ('paid', 'in_payment'):
                        self.pagar(factura)
                self.cuadra('impuesto cambiado ' + modo)
                self.assertEqual(venta.comision_centavos, 10000, modo)

    def test_conciliacion_creada_por_otra_via_partial_reconcile_directo(self):
        """Una factura cuyo pago se concilia creando ``account.partial.reconcile`` a mano: no pasa por el gancho de
        pago; solo el barrido nocturno la anota. ``_poner_al_dia`` no la ve (no tiene fila): se mide el retraso."""
        self.version(10.0)
        factura = self.facturar(self.orden())
        pago = self.env['account.payment'].create({
            'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': factura.partner_id.id,
            'amount': 1070.0, 'date': DIA})
        pago.action_post()
        deuda = factura.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        abono = pago.move_id.line_ids.filtered(lambda ln: ln.account_id == deuda.account_id)
        self.env['account.partial.reconcile'].create({
            'debit_move_id': deuda.id, 'credit_move_id': abono.id, 'amount': 1070.0,
            'debit_amount_currency': 1070.0, 'credit_amount_currency': 1070.0})
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))
        self.assertFalse(self.venta(factura), 'sin gancho no hay fila')
        self.al_dia()
        self.assertFalse(self.venta(factura), '_poner_al_dia no anota facturas nuevas: lo hace el barrido')
        self.Venta._barrido()
        self.assertEqual(self.venta(factura).comision_centavos, 10000)
        self.cuadra('despues del barrido')

    def test_pago_cancelado_y_repuesto_por_una_via_sin_gancho_se_repone_en_armar(self):
        """Hallazgo 4: ``_poner_al_dia`` también mira las ventas «apagadas»: si un pago se canceló y el cliente vuelve a
        pagar por una vía sin gancho (``account.partial.reconcile`` directo), armar y aprobar ya no se quedan sin
        reponerla hasta el barrido de la noche."""
        self.version(10.0)
        factura, venta = self.pagada()
        pago = self.pago_de(factura)
        pago.action_cancel()
        self.al_dia()
        self.assertFalse(venta.cobrada)
        nuevo = self.env['account.payment'].create({
            'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': factura.partner_id.id,
            'amount': 1070.0, 'date': DIA})
        nuevo.action_post()
        deuda = factura.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        abono = nuevo.move_id.line_ids.filtered(lambda ln: ln.account_id == deuda.account_id)
        self.env['account.partial.reconcile'].create({
            'debit_move_id': deuda.id, 'credit_move_id': abono.id, 'amount': 1070.0,
            'debit_amount_currency': 1070.0, 'credit_amount_currency': 1070.0})
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))
        self.cuadra('pago repuesto por otra via, antes del barrido')
        self.assertEqual((venta.cobrada, venta.comision_centavos), (True, 10000))

    def test_armar_repone_la_comision_de_una_factura_vuelta_a_borrador_y_publicada_otra_vez(self):
        """Hallazgo 4: en Odoo 19 ``button_draft`` no deshace las conciliaciones; al publicar de nuevo la factura sigue
        pagada y no hay gancho de pago: la venta quedaba apagada hasta el barrido. Ahora armar la repone."""
        self.version(10.0)
        factura, venta = self.pagada()
        factura.button_draft()
        factura.action_post()
        self.assertFalse(venta.cobrada)
        self.al_dia()
        self.assertEqual(venta.comision_centavos, 10000, 'armar la repone')
        self.assertFalse(self.diferencias())
        self.Venta._barrido()
        self.assertEqual(venta.comision_centavos, 10000, 'y el barrido de la noche no cambia nada')
        self.assertFalse(self.diferencias())

    def test_comision_de_la_pasarela_escrita_despues_del_pago(self):
        """Con «restar lo que cobra la pasarela», si la pasarela guarda su cobro DESPUÉS del pago, la huella lo ve y armar
        no paga de más (30.00 de cobro: 97.00 y no 100.00)."""
        self.version(10.0, base_pasarela='resta')
        orden = self.orden(pago='pasarela')
        self.transaccion(orden, 'pasarela')
        factura = self.facturar(orden)
        self.pagar(factura)
        venta = self.venta(factura)
        self.assertEqual(venta.comision_centavos, 10000)
        orden.transaction_ids.sudo().dcasa_comision_pasarela = 30.0
        self.cuadra('pasarela guardo su cobro despues')
        self.assertEqual(venta.comision_centavos, 9700)

    def test_factura_de_varios_pedidos_mezclando_online_y_tienda(self):
        self.version(10.0)
        online = self.orden()
        tienda = self.orden(web=False)
        facturas = (online | tienda)._create_invoices()
        self.assertEqual(len(facturas), 1)
        facturas.invoice_date = DIA
        facturas.action_post()
        self.pagar(facturas)
        venta = self.venta(facturas)
        self.assertEqual(venta.comision_centavos, 10000, 'solo cuenta la parte online (1,000 de 2,000)')
        self.cuadra('mixta pagada')
        for modo, ctx in self.modos():
            with self.subTest(modo=modo):
                v = self.venta(facturas)
                antes = v.comision_centavos
                with ctx():
                    nota = self.nota(facturas, 400.0)
                self.cuadra('mixta con nota ' + modo)
                self.assertEqual(v.comision_centavos, 10000 - 2000, modo + ': 400 repartidos en proporcion: 200 de la parte online')
                with ctx():
                    nota.button_draft()
                    nota.button_cancel()
                self.cuadra('mixta con nota cancelada ' + modo)

    def test_el_barrido_deja_todo_igual_a_la_verdad(self):
        self.version(10.0)
        facturas = [self.pagada()[0] for _i in range(3)]
        self.nota(facturas[0], 300.0)
        self.pago_de(facturas[1]).action_draft()
        facturas[2].button_draft()
        self.Venta._barrido()
        self.assertFalse(self.diferencias())
