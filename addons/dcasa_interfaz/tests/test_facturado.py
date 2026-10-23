"""El Inicio de Gerencia cuenta las ventas sobre las FACTURAS, coherente con Contabilidad (decisión del jefe A1/A2,
2026-10-17, docs/DECISIONES_CONTABLES.md).

* «Facturado» = todas las facturas de cliente publicadas, por su fecha: lo mismo que las «Ventas» de Contabilidad, con
  facturas sin pedido, notas de crédito y facturas del sistema anterior. Debajo, «N de M salieron de un pedido».
* «Con abonos» y «Completadas» parten de ese mismo conjunto (también las facturas sin pedido).
* La vendedora de una factura: la del pedido; sin pedido, la de la factura; sin ninguna, «Sin vendedora».
* La ganancia de una factura sin pedido usa el costo de hoy del producto.
* La semana y «Lo más vendido» siguen la base; la vendedora no ve nada nuevo.

Fechas fijas de 2025 (nada depende del reloj real) y, para no mezclarse con otras pruebas, casi todo se mide con el
filtro de vendedora o en días donde solo hay lo de la prueba.
"""
from datetime import date, datetime, time, timedelta

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, tagged

from .test_comparar import CompararCommon
from .test_inicio_por_rol import ESPERAR_JS, VentasMixin, crear_usuario


class FacturadoCommon(CompararCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # El ITBMS va a su cuenta por pagar, como en producción: si no, Odoo lo dejaría en ingresos.
        cuenta_itbms = cls.env['account.account'].create({
            'name': 'ITBMS por pagar facturado', 'code': '9F0101', 'account_type': 'liability_current'})
        cls.itbms = cls.env['account.tax'].create({
            'name': 'ITBMS facturado 7%', 'amount': 7.0, 'amount_type': 'percent', 'type_tax_use': 'sale',
            'company_id': cls.env.company.id})
        for linea in cls.itbms.invoice_repartition_line_ids | cls.itbms.refund_repartition_line_ids:
            if linea.repartition_type == 'tax':
                linea.account_id = cuenta_itbms
        cls.cama = cls.env['product.product'].create({
            'name': 'CAMA FACTURADO', 'default_code': 'CAMA-FACT-01', 'list_price': 500.0, 'standard_price': 300.0,
            'taxes_id': [Command.set(cls.itbms.ids)]})
        cls.sin_costo = cls.env['product.product'].create({
            'name': 'SILLA FACTURADO SIN COSTO', 'list_price': 80.0, 'standard_price': 0.0,
            'taxes_id': [Command.clear()]})
        cls.flete = cls.env['product.product'].create({
            'name': 'FLETE FACTURADO', 'type': 'service', 'list_price': 25.0, 'taxes_id': [Command.clear()]})

    def suelta(self, dia, producto=None, precio=None, vendedor=None, cantidad=1, hora=time(9, 0), lineas=None):
        """Una factura hecha directo (sin pedido), con su «Vendedor» (``vendedor``; ``False`` = sin vendedor)."""
        producto = producto or self.mueble
        lineas = lineas or [Command.create({
            'product_id': producto.id, 'quantity': cantidad,
            'price_unit': producto.list_price if precio is None else precio})]
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': dia,
            'invoice_line_ids': lineas})
        factura.invoice_user_id = vendedor.id if vendedor else False
        factura.action_post()
        self.registrar(factura, dia, hora)
        return factura

    def nota(self, factura, dia, precio=None, hora=time(12, 0), conciliar=False):
        """Una nota de crédito de ``factura`` (entera o, con ``precio``, por ese monto en su primera línea). Con
        ``conciliar``, la anula: la nota se aplica a la factura (queda «revertida»)."""
        valores = [{'invoice_date': dia, 'date': dia, 'ref': 'Devolución de prueba'}]
        if conciliar:
            nota = factura._reverse_moves(valores, cancel=True)
            self.registrar(nota, dia, hora)
            return nota
        nota = factura._reverse_moves(valores)
        if precio is not None:
            nota.invoice_line_ids[1:].unlink()
            nota.invoice_line_ids.write({'quantity': 1, 'price_unit': precio})
        nota.action_post()
        self.registrar(nota, dia, hora)
        return nota

    def del_sistema_anterior(self, numero, dia, lineas, nota=False, original=None):
        """Una factura cargada del sistema anterior con el mismo camino de ``dcasa_migracion`` (si está instalado; si
        no, con los mismos valores: número propio, fecha, ``dcasa_historica`` y líneas con o sin producto)."""
        datos = {'numero': numero, 'nota': nota, 'fecha': str(dia), 'vencimiento': str(dia), 'referencia': '',
                 'origen': '', 'moneda': self.env.company.currency_id.name, 'original': original,
                 'base': sum(linea['cantidad'] * linea['precio'] for linea in lineas), 'impuesto': 0.0,
                 'lineas': lineas}
        datos['total'] = datos['base']
        if 'dcasa.migracion' in self.env:
            from odoo.addons.dcasa_migracion import historial
            Movimiento = self.env['account.move'].with_context(**historial.CONTEXTO)
            return historial._crear_factura(self.env, Movimiento, datos, 'cliente', self.cliente.id, {})
        valores = []
        for linea in lineas:
            producto = self.env['product.product'].search([('default_code', '=', linea['codigo'])], limit=1) \
                if linea['codigo'] else self.env['product.product']
            valores.append(Command.create({'name': linea['nombre'], 'quantity': linea['cantidad'],
                                           'price_unit': linea['precio'], 'tax_ids': [Command.clear()],
                                           **({'product_id': producto.id} if producto else {})}))
        factura = self.env['account.move'].create({
            'move_type': 'out_refund' if nota else 'out_invoice', 'partner_id': self.cliente.id, 'name': numero,
            'date': dia, 'invoice_date': dia, 'dcasa_historica': True, 'invoice_line_ids': valores})
        factura.action_post()
        return factura

    def contabilidad(self, d0, d1):
        """Las «Ventas» de Contabilidad para esas fechas: los apuntes de ingresos publicados."""
        grupos = self.env['account.move.line']._read_group(
            [('parent_state', '=', 'posted'), ('account_id.account_type', '=', 'income'), ('date', '>=', d0),
             ('date', '<=', d1), ('company_id', 'in', self.env.companies.ids)], [], ['balance:sum'])
        return round(-(grupos[0][0] or 0.0), 2)

    def ids(self, medida):
        return sorted(fila['id'] for fila in medida['filas'])


@tagged('post_install', '-at_install')
class TestFacturadoComoContabilidad(FacturadoCommon):

    def test_facturado_es_lo_que_dice_contabilidad(self):
        """Marzo de 2025: una venta de pedido, una factura sin pedido, una nota de crédito y facturas del sistema
        anterior (con y sin producto conocido, y una nota). «Facturado» da lo mismo que Contabilidad, sin nota de
        diferencia, y lo mismo que el reporte de ventas de Contabilidad (Estado de resultados)."""
        d0, d1 = date(2025, 3, 1), date(2025, 3, 31)
        self.assertEqual(self.contabilidad(d0, d1), 0.0, 'marzo de 2025 empieza vacío')
        _orden, de_pedido = self.vender(date(2025, 3, 3), vendedor=self.vendedora, producto=self.cama)
        self.suelta(date(2025, 3, 5), self.cama, 450.0, vendedor=self.otra)                     # sin pedido
        self.nota(de_pedido, date(2025, 3, 20), precio=100.0)                           # devuelve $100 + ITBMS
        historica = self.del_sistema_anterior('INV/2025/91001', date(2025, 3, 10), [
            {'nombre': 'Juego de sala del sistema anterior', 'codigo': '', 'cantidad': 1, 'precio': 900.0,
             'descuento': 0.0, 'impuesto': ''},
            {'nombre': 'Cama del sistema anterior', 'codigo': 'CAMA-FACT-01', 'cantidad': 2, 'precio': 250.0,
             'descuento': 0.0, 'impuesto': ''}])
        self.assertTrue(historica.dcasa_historica)
        self.assertTrue(historica.invoice_user_id, 'Odoo le pone como vendedor a quien la carga…')
        self.del_sistema_anterior('RINV/2025/91001', date(2025, 3, 12), [
            {'nombre': 'Devolución del sistema anterior', 'codigo': '', 'cantidad': 1, 'precio': 50.0,
             'descuento': 0.0, 'impuesto': ''}], nota=True, original='INV/2025/91001')
        medida = self.medir(d0, d1, 'facturado')
        esperado = 500.0 + 450.0 - 100.0 + 1400.0 - 50.0
        self.assertEqual(medida['sin_itbms'], esperado)
        self.assertEqual(medida['sin_itbms'], self.contabilidad(d0, d1), 'Facturado = Contabilidad')
        self.assertEqual((medida['cuantas'], medida['notas']), (3, 2))
        self.assertIn(historica.id, self.ids(self.medir(d0, d1, 'facturado', 'sin')),
                      '…pero el sistema anterior no trae la vendedora: va a «Sin vendedora»')
        self.assertAlmostEqual(medida['itbms'], round((500.0 + 450.0 - 100.0) * 0.07, 2), places=2)
        self.assertAlmostEqual(medida['sin_itbms'] + medida['itbms'], medida['total'], places=2)
        reportes = self.env.get('dcasa.reporte.contable')
        if reportes is not None:
            ventas = reportes.estado_resultados(str(d0), str(d1))['secciones'][0]
            self.assertEqual(ventas['clave'], 'ventas')
            self.assertAlmostEqual(ventas['total'], medida['sin_itbms'], places=2,
                                   msg='el reporte de ventas de Contabilidad dice lo mismo')
        tarjeta = self.tablero.with_user(self.gerencia).ventas_del_periodo('rango', str(d0), str(d1))
        self.assertEqual(tarjeta['base'], 'facturado', 'abre en «Facturado»')
        self.assertIsNone(tarjeta['cuadre'], 'en «Facturado» no hay nota de «Contabilidad dice…»: es lo mismo')
        self.assertEqual(tarjeta['actual']['sin_itbms'], esperado)
        lista = self.env['account.move'].with_user(self.gerencia).search(tarjeta['accion']['domain'])
        self.assertEqual(sorted(lista.ids), self.ids(medida), 'la lista abre las mismas facturas y notas')
        self.assertEqual(tarjeta['accion']['res_model'], 'account.move')
        # Cada día de la semana y del rango suma lo que Contabilidad dice ese día.
        for dia in (date(2025, 3, 3), date(2025, 3, 5), date(2025, 3, 10), date(2025, 3, 12), date(2025, 3, 20)):
            with self.subTest(dia=dia):
                self.assertEqual(self.medir(dia, dia, 'facturado')['sin_itbms'], self.contabilidad(dia, dia))

    def test_si_algo_que_no_es_factura_toca_los_ingresos_se_dice(self):
        """Un asiento a mano a una cuenta de ingresos: Contabilidad lo suma y el Inicio no (no es una venta). El ⓘ
        dice la resta exacta y abre ese asiento."""
        dia = date(2025, 4, 2)
        self.suelta(dia, self.mueble, 700.0)
        tarjeta = self.tablero.with_user(self.gerencia).ventas_del_periodo('rango', str(dia), str(dia))
        self.assertIsNone(tarjeta['cuadre'])
        ingresos = self.env['account.account'].search([('account_type', '=', 'income')], limit=1)
        caja = self.env['account.account'].search([('account_type', '=', 'asset_cash')], limit=1)
        diario = self.env['account.journal'].search([('type', '=', 'general')], limit=1)
        asiento = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': diario.id, 'date': dia,
            'line_ids': [Command.create({'account_id': caja.id, 'debit': 35.0}),
                         Command.create({'account_id': ingresos.id, 'credit': 35.0})]})
        asiento.action_post()
        cuadre = self.tablero.with_user(self.gerencia).ventas_del_periodo('rango', str(dia), str(dia))['cuadre']
        self.assertEqual((cuadre['diferencia'], cuadre['cuantas']), (35.0, 1))
        self.assertEqual(self.env['account.move'].search(cuadre['accion']['domain']), asiento)

    def test_n_de_m_salieron_de_un_pedido_de_una_vendedora(self):
        dia = date(2025, 4, 7)
        self.vender(dia, vendedor=self.vendedora)
        self.vender(dia, vendedor=self.otra)
        self.vender(dia, sin_vendedora=True)                       # pedido de la web: sin vendedora
        sin_pedido = self.suelta(dia, vendedor=self.vendedora)     # factura directa: no salió de un pedido
        self.nota(sin_pedido, dia)                                 # una nota no es una factura más
        Tablero = self.tablero.with_user(self.gerencia)
        tarjeta = Tablero.ventas_del_periodo('rango', str(dia), str(dia))
        actual = tarjeta['actual']
        self.assertEqual((actual['de_pedido'], actual['cuantas'], actual['notas']), (2, 4, 1))
        self.assertEqual(actual['sin_itbms'], 3000.0, 'cuatro de $1,000 menos la nota de $1,000')
        brian = self.env['brian.herramientas'] if 'brian.herramientas' in self.env else None
        if brian is not None:
            self.assertEqual(brian._b_de_un_pedido(actual), '2 de 4 salieron de un pedido de una vendedora')
            self.assertEqual(brian._b_de_un_pedido({'de_pedido': 1, 'cuantas': 1}),
                             '1 de 1 salió de un pedido de una vendedora')
        # La de una vendedora: solo lo suyo (su pedido y su factura directa con su nota).
        de_ana = Tablero.ventas_del_periodo('rango', str(dia), str(dia), vendedor=self.vendedora.id)['actual']
        self.assertEqual((de_ana['de_pedido'], de_ana['cuantas'], de_ana['sin_itbms']), (1, 2, 1000.0))


@tagged('post_install', '-at_install')
class TestTresVistasSobreFacturas(FacturadoCommon):

    def test_el_sofa_de_la_duena_da_lo_mismo_que_antes(self):
        """Sofá de $1,000 el 5 de octubre, abono de $200 ese día y $800 el 20 de noviembre (sobre la factura)."""
        oct0, oct1, nov0, nov1 = date(2025, 10, 1), date(2025, 10, 31), date(2025, 11, 1), date(2025, 11, 30)
        _orden, factura = self.vender(date(2025, 10, 5))
        self.pagar(factura, 200.0, date(2025, 10, 5), time(10, 0))
        self.pagar(factura, 800.0, date(2025, 11, 20), time(15, 0))
        ana = self.vendedora.id
        self.assertEqual(self.medir(oct0, oct1, 'facturado', ana)['sin_itbms'], 1000.0)
        self.assertEqual(self.medir(nov0, nov1, 'facturado', ana)['sin_itbms'], 0.0)
        self.assertEqual(self.medir(oct0, oct1, 'completadas', ana)['sin_itbms'], 0.0)
        noviembre = self.medir(nov0, nov1, 'completadas', ana)
        self.assertEqual((noviembre['sin_itbms'], self.ids(noviembre)), (1000.0, factura.ids))
        octubre = self.medir(oct0, oct1, 'con_abonos', ana)
        self.assertEqual((octubre['sin_itbms'], octubre['falta_por_cobrar']), (1000.0, 800.0))
        self.assertEqual(self.medir(nov0, nov1, 'con_abonos', ana)['sin_itbms'], 0.0)

    def test_una_factura_sin_pedido_entra_en_las_tres_segun_su_caso(self):
        """$500 sin pedido el 3 de octubre: abono de $100 ese día y el resto el 15. Otra sin pedido y sin pago."""
        abonada = self.suelta(date(2025, 10, 3), self.mueble, 500.0, vendedor=self.otra)
        self.pagar(abonada, 100.0, date(2025, 10, 3))
        sin_pago = self.suelta(date(2025, 10, 3), self.mueble, 300.0, vendedor=self.otra)
        otra = self.otra.id
        dia3 = date(2025, 10, 3)
        self.assertEqual(self.ids(self.medir(dia3, dia3, 'facturado', otra)), sorted((abonada | sin_pago).ids))
        con_abonos = self.medir(dia3, dia3, 'con_abonos', otra)
        self.assertEqual((self.ids(con_abonos), con_abonos['falta_por_cobrar']), (abonada.ids, 400.0))
        self.assertFalse(self.medir(date(2025, 10, 1), date(2025, 10, 14), 'completadas', otra)['filas'])
        self.pagar(abonada, 400.0, date(2025, 10, 15))
        quince = self.medir(date(2025, 10, 15), date(2025, 10, 15), 'completadas', otra)
        self.assertEqual((self.ids(quince), quince['sin_itbms']), (abonada.ids, 500.0))
        self.assertEqual(self.medir(dia3, date(2025, 10, 15), 'con_abonos', otra)['falta_por_cobrar'], 0.0)
        self.assertNotIn(sin_pago.id, self.ids(self.medir(dia3, date(2025, 10, 31), 'completadas', otra)))

    def test_las_notas_de_credito_restan_en_las_tres(self):
        """Devolución parcial de una factura pagada: resta su día en las tres. Devolución entera de una sin pago: no
        suma en ninguna. Una nota suelta (sin factura) solo resta en «Facturado»."""
        ana = self.vendedora.id
        dia, devolucion = date(2025, 10, 21), date(2025, 10, 24)
        _orden, pagada = self.vender(dia)
        self.pagar(pagada, 1000.0, dia)
        self.nota(pagada, devolucion, precio=250.0)
        _orden, anulada = self.vender(dia)
        self.nota(anulada, dia, conciliar=True)                   # anulada con su nota: queda «revertida»
        self.assertEqual(anulada.payment_state, 'reversed')
        semana = (dia, devolucion)
        self.assertEqual(self.medir(*semana, 'facturado', ana)['sin_itbms'], 750.0)
        self.assertEqual(self.medir(*semana, 'completadas', ana)['sin_itbms'], 750.0)
        self.assertEqual(self.medir(*semana, 'con_abonos', ana)['sin_itbms'], 750.0)
        self.assertEqual(self.medir(devolucion, devolucion, 'completadas', ana)['sin_itbms'], -250.0,
                         'la nota resta el día de la nota')
        self.assertNotIn(anulada.id, self.ids(self.medir(*semana, 'completadas', ana)))
        self.assertNotIn(anulada.id, self.ids(self.medir(*semana, 'con_abonos', ana)))
        suelta = self.env['account.move'].create({
            'move_type': 'out_refund', 'partner_id': self.cliente.id, 'invoice_date': devolucion,
            'invoice_user_id': self.vendedora.id,
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'price_unit': 40.0})]})
        suelta.action_post()
        self.assertEqual(self.medir(*semana, 'facturado', ana)['sin_itbms'], 710.0)
        self.assertEqual(self.medir(*semana, 'completadas', ana)['sin_itbms'], 750.0)

    def test_una_nota_aplicada_antes_de_completar_resta_el_dia_que_se_completa(self):
        """Factura de $1,000 con abono de $500, nota de $100 aplicada y el resto ($400) días después: el día que se
        completa suman $900."""
        ana = self.vendedora.id
        _orden, factura = self.vender(date(2025, 10, 25))
        self.pagar(factura, 500.0, date(2025, 10, 25))
        nota = self.nota(factura, date(2025, 10, 26), precio=100.0)
        (nota.line_ids | factura.line_ids).filtered(
            lambda linea: linea.account_id.account_type == 'asset_receivable' and not linea.reconciled).reconcile()
        self.assertEqual(factura.payment_state, 'partial')
        self.assertEqual(self.medir(date(2025, 10, 26), date(2025, 10, 27), 'completadas', ana)['sin_itbms'], 0.0)
        self.pagar(factura, 400.0, date(2025, 10, 28))
        completa = self.medir(date(2025, 10, 28), date(2025, 10, 28), 'completadas', ana)
        self.assertEqual((completa['sin_itbms'], completa['cuantas'], completa['notas']), (900.0, 1, 1))


@tagged('post_install', '-at_install')
class TestVendedoraDeLaFactura(FacturadoCommon):

    def test_sin_pedido_es_de_su_vendedor_y_sin_vendedor_va_a_sin_vendedora(self):
        dia = date(2025, 5, 6)
        de_otra = self.suelta(dia, precio=600.0, vendedor=self.otra)
        sin_nadie = self.suelta(dia, precio=200.0, vendedor=False)
        self.assertFalse(sin_nadie.invoice_user_id)
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'user_id': self.vendedora.id,
            'order_line': [Command.create({'product_id': self.mueble.id, 'product_uom_qty': 1})]})
        orden.action_confirm()
        de_pedido = orden._create_invoices()
        de_pedido.write({'invoice_date': dia, 'invoice_user_id': self.otra.id})   # dice otra: manda el pedido
        de_pedido.action_post()
        self.assertEqual(de_pedido.invoice_user_id, self.otra)
        self.assertIn(de_otra.id, self.ids(self.medir(dia, dia, 'facturado', self.otra.id)))
        self.assertNotIn(de_pedido.id, self.ids(self.medir(dia, dia, 'facturado', self.otra.id)))
        self.assertIn(de_pedido.id, self.ids(self.medir(dia, dia, 'facturado', self.vendedora.id)))
        self.assertIn(sin_nadie.id, self.ids(self.medir(dia, dia, 'facturado', 'sin')))
        resultado = self.comparar('rango', datetime(2025, 5, 20, 10, 0), a_desde='2025-05-06', a_hasta='2025-05-06',
                                  b_desde='2025-04-29', por_vendedora=True)
        filas = {fila['vendedor']: fila for fila in resultado['por_vendedora']}
        self.assertEqual(filas[self.otra.id]['a'], 600.0)
        self.assertEqual(filas[self.vendedora.id]['a'], 1000.0)
        self.assertEqual(filas['sin']['a'], 200.0)
        self.assertEqual(filas['sin']['nombre'], 'Sin vendedora')

    def test_el_cobrado_de_una_vendedora_son_los_pagos_a_sus_facturas(self):
        dia = date(2025, 5, 8)
        de_otra = self.suelta(dia, precio=600.0, vendedor=self.otra)
        self.pagar(de_otra, 600.0, dia, usuario=self.gerencia)    # lo registra Caja
        sin_nadie = self.suelta(dia, precio=200.0, vendedor=False)
        self.pagar(sin_nadie, 50.0, dia)
        self.assertEqual(self.medir(dia, dia, 'facturado', self.otra.id)['cobrado'], 600.0)
        self.assertEqual(self.medir(dia, dia, 'facturado', self.gerencia.id)['cobrado'], 0.0)
        self.assertEqual(self.medir(dia, dia, 'facturado', 'sin')['cobrado'], 50.0)

    def test_quien_tiene_facturas_sin_pedido_sale_en_el_selector(self):
        cajera = crear_usuario(self.env, 'cajera_facturado', 'account.group_account_invoice')
        self.suelta(date(2026, 9, 2), precio=100.0, vendedor=cajera)
        ids = [v['id'] for v in self.tablero.with_user(self.gerencia)._opciones_de_comparar(date(2026, 10, 17))
               ['vendedoras']]
        self.assertIn(cajera.id, ids, 'su factura directa es de ella: tiene que poder elegirse')
        self.assertEqual(ids[-1], 'sin')


@tagged('post_install', '-at_install')
class TestGananciaDeFacturas(FacturadoCommon):

    def test_sin_pedido_usa_el_costo_de_hoy_y_el_pedido_el_suyo(self):
        dia = date(2025, 6, 3)
        _orden, de_pedido = self.vender(dia, vendedor=self.vendedora)           # $1,000, costo 600 guardado
        directa = self.suelta(dia, vendedor=self.vendedora)                     # $1,000, costo de hoy 600
        ganancia = self.medir(dia, dia, 'facturado', self.vendedora.id)['ganancia']
        self.assertEqual((ganancia['valor'], ganancia['ventas_con_costo'], ganancia['ventas_sin_costo']),
                         (800.0, 2, 0))
        self.assertEqual(ganancia['porcentaje'], 40.0)
        self.mueble.standard_price = 700.0
        ganancia = self.medir(dia, dia, 'facturado', self.vendedora.id)['ganancia']
        self.assertEqual(ganancia['valor'], 400.0 + 300.0, 'el pedido guardó su costo; la directa usa el de hoy')
        self.assertTrue(de_pedido and directa)

    def test_sin_costo_se_avisa_y_no_inventa_ganancia(self):
        dia = date(2025, 6, 4)
        self.suelta(dia, self.sin_costo, 80.0, vendedor=self.otra)
        self.suelta(dia, vendedor=self.otra, lineas=[
            Command.create({'name': 'Algo del sistema anterior', 'quantity': 1, 'price_unit': 90.0,
                            'tax_ids': [Command.clear()]})])
        conocida = self.suelta(dia, self.mueble, 1000.0, vendedor=self.otra, lineas=[
            Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 1000.0}),
            Command.create({'product_id': self.flete.id, 'quantity': 1, 'price_unit': 25.0})])
        ganancia = self.medir(dia, dia, 'facturado', self.otra.id)['ganancia']
        self.assertEqual((ganancia['valor'], ganancia['ventas_sin_costo'], ganancia['ventas_con_costo']),
                         (400.0, 2, 1), 'el flete no entra; lo sin costo se cuenta aparte')
        self.assertEqual(ganancia['porcentaje'], 40.0)
        # La devolución entera de lo vendido con costo resta su ganancia (y no cuenta como una venta más).
        self.nota(conocida, dia)
        ganancia = self.medir(dia, dia, 'facturado', self.otra.id)['ganancia']
        self.assertEqual((ganancia['valor'], ganancia['ventas_con_costo']), (0.0, 1))

    def test_el_aviso_de_productos_sin_costo_sigue(self):
        avisos = {a['clave'] for a in self.tablero.with_user(self.gerencia).obtener_datos()['atencion']}
        self.assertIn('productos_sin_costo', avisos)


@tagged('post_install', '-at_install')
class TestSemanaYLoMasVendido(FacturadoCommon):

    def test_la_semana_y_lo_mas_vendido_siguen_la_base(self):
        hoy = date(2025, 7, 10)
        ana = self.vendedora.id
        _o, pagada = self.vender(hoy, vendedor=self.vendedora, producto=self.cama)          # completa hoy
        self.pagar(pagada, pagada.amount_total, hoy)
        _o, abonada = self.vender(hoy - timedelta(days=1), vendedor=self.vendedora)         # con abono ayer
        self.pagar(abonada, 100.0, hoy - timedelta(days=1))
        directa = self.suelta(hoy - timedelta(days=2), self.cama, 500.0, vendedor=self.vendedora, cantidad=3)
        for base in ('facturado', 'con_abonos', 'completadas'):
            with self.subTest(base=base):
                filas = self.tablero._filas(hoy - timedelta(days=30), hoy, base, ana)
                semana, top = self.tablero._semana_y_top(hoy, filas)
                for atras, barra in zip(range(6, -1, -1), semana, strict=True):
                    dia = hoy - timedelta(days=atras)
                    self.assertEqual(barra['monto'], self.medir(dia, dia, base, ana)['sin_itbms'], dia)
                unidades = {fila['nombre']: fila['cantidad'] for fila in top}
                esperado = {'facturado': {'CAMA FACTURADO': 4, 'MUEBLE COMPARAR': 1},
                            'con_abonos': {'CAMA FACTURADO': 1, 'MUEBLE COMPARAR': 1},
                            'completadas': {'CAMA FACTURADO': 1}}[base]
                self.assertEqual(unidades, esperado)
        # Una nota de crédito resta las unidades devueltas.
        self.nota(directa, hoy, precio=500.0)
        filas = self.tablero._filas(hoy - timedelta(days=30), hoy, 'facturado', ana)
        top = {fila['nombre']: fila['cantidad'] for fila in self.tablero._semana_y_top(hoy, filas)[1]}
        self.assertEqual(top['CAMA FACTURADO'], 3)

    def test_la_grafica_del_inicio_valida_y_es_de_quien_controla_la_tienda(self):
        Tablero = self.tablero.with_user(self.gerencia)
        grafica = Tablero.grafica_de_ventas()
        self.assertEqual(grafica['base'], 'facturado')
        self.assertEqual(len(grafica['semana']), 7)
        self.assertEqual(Tablero.grafica_de_ventas('completadas', self.otra.id)['vendedor'], self.otra.id)
        for malo in (dict(base='vendido'), dict(base='todo'), dict(vendedor='x'), dict(vendedor=99999999)):
            with self.subTest(**{k: str(v) for k, v in malo.items()}), self.assertRaises(UserError):
                Tablero.grafica_de_ventas(**malo)
        with self.assertRaises(AccessError):
            self.tablero.with_user(self.vendedora).grafica_de_ventas()
        contador = crear_usuario(self.env, 'contador_grafica', 'account.group_account_user')
        contador.group_ids = [Command.link(self.env.ref('sales_team.group_sale_salesman').id)]
        with self.assertRaises(AccessError):
            self.tablero.with_user(contador).grafica_de_ventas(vendedor=self.vendedora.id)
        self.assertEqual(self.tablero.with_user(contador).grafica_de_ventas()['base'], 'facturado')

    def test_el_inicio_abre_con_la_semana_en_facturado(self):
        datos = self.tablero.with_user(self.gerencia).obtener_datos()
        self.assertEqual(datos['base'], 'facturado')
        grafica = self.tablero.with_user(self.gerencia).grafica_de_ventas('facturado')
        self.assertEqual(datos['semana'], grafica['semana'], 'la semana del Inicio es la de «Facturado»')
        self.assertEqual(datos['top'], grafica['top'])
        hoy = next(c for c in datos['cifras'] if c['clave'] == 'ventas_hoy')
        self.assertEqual(hoy['valor'], datos['ventas']['actual']['sin_itbms'], '«Vendido hoy» es la tarjeta en Hoy')
        self.assertEqual(hoy['valor'], datos['semana'][-1]['monto'])


@tagged('post_install', '-at_install')
class TestLaVendedoraNoVeNadaNuevo(FacturadoCommon):

    def test_su_inicio_sigue_con_sus_pedidos(self):
        hoy = self.hoy
        _o, suya = self.vender(hoy, vendedor=self.vendedora)
        directa = self.suelta(hoy, vendedor=self.vendedora)         # una factura directa a su nombre no es «su venta»
        Tablero = self.tablero.with_user(self.vendedora)
        datos = Tablero.obtener_datos()
        self.assertEqual((datos['bases'], datos['base'], datos['comparar'], datos['ventas']), ([], None, None, None))
        self.assertFalse(datos['semana'])
        self.assertFalse(datos['top'])
        cifras = {c['clave']: c for c in datos['cifras']}
        self.assertEqual(set(cifras), {'ventas_hoy', 'mis_cotizaciones'})
        self.assertEqual(cifras['ventas_hoy']['accion']['res_model'], 'sale.order')
        self.assertEqual(cifras['ventas_hoy']['detalle'], '1 venta tuya')
        propio = Tablero.ventas_del_periodo('hoy', base='facturado')
        self.assertEqual(propio['base'], 'vendido', 'su tarjeta no tiene interruptor')
        self.assertIsNone(propio['cuadre'])
        self.assertEqual(propio['accion']['res_model'], 'sale.order')
        self.assertEqual(self.env['sale.order'].search(propio['accion']['domain']), suya.invoice_line_ids.sale_line_ids
                         .order_id)
        self.assertTrue(directa)


@tagged('post_install', '-at_install')
class TestAyudaEnElNavegador(VentasMixin, HttpCase):
    """Las notas largas pasan a un ícono ⓘ junto al título (2026-10-17): cerrado no se ve texto largo; se abre al
    tocarlo (es un botón: con el teclado y en el celular), «Escape» lo cierra y devuelve el foco, y tocar fuera
    también. El de «Contabilidad dice…» solo sale si el Inicio se aparta de Contabilidad (en «Facturado» no). A 1440
    y a 390 px."""

    def setUp(self):
        super().setUp()
        banco = self.env['account.journal'].create({'name': 'Banco ayuda', 'type': 'bank', 'code': 'BAYU'})
        producto = self.env['product.product'].create({
            'name': 'MUEBLE AYUDA', 'list_price': 300.0, 'standard_price': 180.0, 'taxes_id': [Command.clear()]})
        for vendedor, pago in ((self.vendedora, 1.0), (self.vendedora, 1.0), (self.otra, 0.0)):
            factura = self.facturar(self.pedido(vendedor=vendedor, producto=producto), fecha=self.hoy)
            if pago:
                self.env['account.payment.register'].with_context(
                    active_model='account.move', active_ids=factura.ids).create({
                        'payment_date': self.hoy, 'amount': factura.amount_total * pago,
                        'journal_id': banco.id})._create_payments()

    def test_el_icono_de_ayuda_a_1440_y_a_390(self):
        codigo = '(async () => {' + ESPERAR_JS + r"""
            const raiz = () => document.querySelector('.o_dcasa_inicio');
            const sinScrollDeCostado = (que) => {
                if (raiz().scrollWidth > raiz().clientWidth + 1) {
                    throw new Error(`scroll de costado (${que}): ${raiz().scrollWidth} > ${raiz().clientWidth}`);
                }
            };
            const dentro = (elemento, que) => {
                const caja = elemento.getBoundingClientRect();
                if (caja.left < 0 || caja.right > document.documentElement.clientWidth + 1) {
                    throw new Error(`${que} se sale de la pantalla: ${caja.left}–${caja.right}`);
                }
            };
            await esperar(() => document.querySelector('.o_dcasa_ventas .o_dcasa_ganancia'), 'la tarjeta de ganancia');
            await esperar(() => document.querySelector('.o_dcasa_base_facturado.o_activo'), 'abre en «Facturado»');
            // Las tres posiciones en una fila y la línea corta, que cabe.
            const arriba = [...document.querySelectorAll('.o_dcasa_interruptor_opcion')].map((b) => b.offsetTop);
            if (arriba.length !== 3 || new Set(arriba).size !== 1) {
                throw new Error('las tres posiciones van en una fila: ' + arriba);
            }
            const detalle = document.querySelector('.o_dcasa_base_detalle');
            igual(detalle.textContent.trim(), 'Todas las facturas, igual que Contabilidad', 'la línea');
            if (detalle.scrollWidth > detalle.clientWidth + 1
                    || detalle.offsetHeight > parseFloat(getComputedStyle(detalle).lineHeight) * 1.5) {
                throw new Error('la línea corta tiene que caber en una línea');
            }
            // «N de M salieron de un pedido de una vendedora» debajo del número.
            const linea = document.querySelector('.o_dcasa_de_pedido');
            const patron = /^\d+ de \d+ (salió|salieron) de un pedido de una vendedora$/;
            if (!linea || !patron.test(linea.textContent.trim())) {
                throw new Error('falta la línea «N de M salieron de un pedido»: ' + (linea && linea.textContent));
            }
            // Cerrado: nada de texto largo a la vista; en «Facturado» no hay nota de Contabilidad (es lo mismo).
            for (const largo of ['No resta gastos', 'Contabilidad dice', 'costo de hoy', 'antes de que existiera']) {
                if (raiz().innerText.includes(largo)) { throw new Error('texto largo a la vista: ' + largo); }
            }
            if (document.querySelector('.o_dcasa_ayuda_boton_ventas')) {
                throw new Error('en «Facturado» no hay ⓘ de Contabilidad');
            }
            sinScrollDeCostado('al abrir');
            const boton = document.querySelector('.o_dcasa_ayuda_boton_ganancia');
            igual([boton.tagName, boton.getAttribute('type'), boton.getAttribute('aria-expanded')],
                  ['BUTTON', 'button', 'false'], 'el ⓘ es un botón cerrado');
            if (!boton.getAttribute('aria-label')) { throw new Error('el ⓘ necesita su nombre para el lector'); }
            igual(getComputedStyle(boton).color, 'rgb(19, 64, 177)', 'el ⓘ va en azul de la marca');
            if (boton.getBoundingClientRect().width < 32) { throw new Error('el ⓘ es muy chico para el dedo'); }
            // Con el teclado: se enfoca y se abre (Enter o Espacio en un botón es un clic).
            boton.focus();
            if (document.activeElement !== boton) { throw new Error('el ⓘ se tiene que poder enfocar'); }
            boton.click();
            const texto = await esperar(() => document.querySelector('#o_dcasa_ayuda_ganancia'), 'la ayuda abierta');
            igual(boton.getAttribute('aria-expanded'), 'true', 'abierto');
            for (const frase of ['No resta gastos', 'costo de hoy del producto']) {
                if (!texto.textContent.includes(frase)) { throw new Error('la ayuda debe decir: ' + frase); }
            }
            igual(getComputedStyle(texto).boxShadow, 'none', 'sin sombras');
            dentro(texto, 'la ayuda');
            sinScrollDeCostado('con la ayuda abierta');
            // «Escape» la cierra y el foco vuelve al ícono.
            texto.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
            await esperar(() => !document.querySelector('#o_dcasa_ayuda_ganancia'), 'Escape la cierra');
            if (document.activeElement !== boton) { throw new Error('el foco vuelve al ícono'); }
            // Tocar fuera la cierra (en el celular no hay «pasar el mouse»).
            boton.click();
            await esperar(() => document.querySelector('#o_dcasa_ayuda_ganancia'), 'la ayuda otra vez');
            document.querySelector('.o_dcasa_inicio_hero h1').click();
            await esperar(() => !document.querySelector('#o_dcasa_ayuda_ganancia'), 'tocar fuera la cierra');
            // «Completadas»: hay una factura sin pago, así que el Inicio se aparta de Contabilidad: sale su ⓘ, cerrado.
            document.querySelector('.o_dcasa_base_completadas').click();
            const ventas = await esperar(() => document.querySelector('.o_dcasa_ayuda_boton_ventas'), 'el ⓘ de Ventas');
            igual(ventas.getAttribute('aria-expanded'), 'false', 'cerrado');
            if (raiz().innerText.includes('Contabilidad dice')) { throw new Error('cerrado no se ve el texto'); }
            if (document.querySelector('.o_dcasa_de_pedido')) { throw new Error('«N de M» es solo de «Facturado»'); }
            await esperar(() => (document.querySelector('.o_dcasa_semana h2 small')?.textContent || '')
                .includes('Completadas'), 'la gráfica de la semana sigue la base');
            ventas.click();
            const nota = await esperar(() => document.querySelector('#o_dcasa_ayuda_ventas'), 'la nota abierta');
            if (!nota.textContent.includes('Contabilidad dice')) { throw new Error('dice «Contabilidad dice…»'); }
            if (!nota.querySelector('.o_dcasa_ayuda_ver')) { throw new Error('abre las facturas que lo explican'); }
            dentro(nota, 'la nota de Contabilidad');
            sinScrollDeCostado('con la nota de Contabilidad');
            nota.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
            await esperar(() => !document.querySelector('#o_dcasa_ayuda_ventas'), 'Escape cierra la nota');
            if (document.activeElement !== ventas) { throw new Error('el foco vuelve al ícono de Ventas'); }
        """ + "console.log('test successful'); })();"
        for tamano in ('1440x900', '390x844'):
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/action-dcasa_interfaz.action_dcasa_inicio', codigo, login='gerencia_rol',
                                timeout=120)
