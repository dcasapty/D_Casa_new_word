"""«Forma de pago» de cada factura (pedido de la dueña y del jefe, 2026-11-19): con qué se cobró, o sea el diario del
pago, en la lista de Facturas, en el Excel, en el buscador y para agrupar (``models/forma_pago.py``).

* El campo dice los diarios de los pagos aplicados, unidos con « + », en orden alfabético; se pone al día solo cuando
  se paga, se paga en parte con otro diario, se anula, se rechaza, se devuelve o se desconcilia un pago.
* La nota de crédito conciliada contra la factura sale como «Nota de crédito» (no es un diario); la nota misma, las
  facturas de proveedores y los asientos quedan vacíos.
* Cuenta lo mismo que «Cobrado por forma de pago» del tablero: una sola definición de «cobro».
* Se calcula en lote (sin una consulta por factura), sale en el Excel y la lista, el buscador y el formulario la traen.

Fechas fijas de 2025: nada depende del reloj real.
"""
import io
import json
import re
import zipfile
from datetime import date

from odoo import Command, http
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged

from .test_facturado import FacturadoCommon
from .test_inicio_por_rol import crear_usuario

DIA = date(2025, 7, 1)


class FormaPagoCommon(FacturadoCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Diario = cls.env['account.journal']
        cls.efectivo = Diario.create({'name': 'Efectivo forma pago', 'type': 'cash', 'code': 'EFFP'})
        cls.yappy = Diario.create({'name': 'Yappy forma pago', 'type': 'bank', 'code': 'YAFP'})
        cls.tarjeta = Diario.create({'name': 'Tarjeta forma pago', 'type': 'bank', 'code': 'TAFP'})
        cls.caja = crear_usuario(cls.env, 'caja_forma_pago', 'dcasa_base.group_caja')

    def factura(self, precio=1000.0, dia=DIA):
        return self.suelta(dia, self.mueble, precio, vendedor=self.vendedora)

    def pago(self, factura, monto, diario, dia=DIA):
        return self.pagar(factura, monto, dia, diario=diario)

    def forma(self, factura):
        """Lo que dice la columna, leído de la base (como lo lee la lista)."""
        factura.invalidate_recordset(['dcasa_forma_pago', 'dcasa_diario_pago_ids'])
        return factura.dcasa_forma_pago

    def aplicar_nota(self, factura, nota):
        """Concilia la nota de crédito contra la factura (como «Agregar» en créditos pendientes)."""
        por_cobrar = nota.line_ids.filtered(lambda linea: linea.account_id.account_type == 'asset_receivable')
        factura.js_assign_outstanding_line(por_cobrar.id)


@tagged('post_install', '-at_install')
class TestFormaPago(FormaPagoCommon):

    # --- qué dice ------------------------------------------------------------------------------------------
    def test_sin_cobrar_queda_vacia(self):
        borrador = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': DIA,
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 10.0})]})
        publicada = self.factura()
        anulada = self.factura()
        anulada.button_draft()
        anulada.button_cancel()
        for factura in (borrador, publicada, anulada):
            with self.subTest(factura.state):
                self.assertFalse(self.forma(factura))
                self.assertFalse(factura.dcasa_diario_pago_ids)

    def test_un_solo_diario(self):
        factura = self.factura()
        self.pago(factura, 1000.0, self.yappy)
        self.assertEqual(self.forma(factura), 'Yappy forma pago')
        self.assertEqual(factura.dcasa_diario_pago_ids, self.yappy)

    def test_pagada_en_parte_con_un_diario_y_el_resto_con_otro(self):
        """Un abono en efectivo y el resto por Yappy (apartado de ``dcasa_abonos``): sale cada diario; con solo el
        primer abono, solo el primero. El orden es el alfabético, no el de los pagos."""
        factura = self.factura()
        self.pago(factura, 400.0, self.yappy)
        self.assertEqual((factura.payment_state, self.forma(factura)), ('partial', 'Yappy forma pago'))
        self.pago(factura, 600.0, self.efectivo)
        self.assertEqual(factura.payment_state, 'paid')
        self.assertEqual(self.forma(factura), 'Efectivo forma pago + Yappy forma pago')
        self.assertEqual(factura.dcasa_diario_pago_ids, self.efectivo | self.yappy)

    def test_el_mismo_conjunto_de_diarios_da_siempre_el_mismo_texto(self):
        """Pagar primero en efectivo o primero en Yappy da el mismo texto: «Agrupar por Forma de pago» no parte en dos
        el mismo conjunto de diarios."""
        primero_efectivo, primero_yappy = self.factura(), self.factura()
        self.pago(primero_efectivo, 300.0, self.efectivo)
        self.pago(primero_efectivo, 700.0, self.yappy)
        self.pago(primero_yappy, 700.0, self.yappy)
        self.pago(primero_yappy, 300.0, self.efectivo)
        self.assertEqual(self.forma(primero_efectivo), self.forma(primero_yappy))
        grupos = self.env['account.move']._read_group(
            [('id', 'in', (primero_efectivo | primero_yappy).ids)], ['dcasa_forma_pago'], ['__count'])
        self.assertEqual([(forma, cuantas) for forma, cuantas in grupos],
                         [('Efectivo forma pago + Yappy forma pago', 2)])

    def test_orden_alfabetico_sin_importar_mayusculas(self):
        minuscula = self.env['account.journal'].create({'name': 'banco forma pago', 'type': 'bank', 'code': 'BAFP'})
        factura = self.factura()
        self.pago(factura, 500.0, self.efectivo)
        self.pago(factura, 500.0, minuscula)
        self.assertEqual(self.forma(factura), 'banco forma pago + Efectivo forma pago',
                         'con el orden de las letras sueltas, la «E» iría antes que la «b»')

    def test_un_diario_repetido_sale_una_vez(self):
        factura = self.factura()
        self.pago(factura, 250.0, self.efectivo)
        self.pago(factura, 250.0, self.efectivo)
        self.pago(factura, 500.0, self.tarjeta)
        self.assertEqual(self.forma(factura), 'Efectivo forma pago + Tarjeta forma pago')
        self.assertEqual(len(factura.dcasa_diario_pago_ids), 2)

    def test_dos_diarios_con_el_mismo_nombre_son_dos_diarios_pero_un_solo_nombre(self):
        gemelo = self.env['account.journal'].create({'name': self.efectivo.name, 'type': 'cash', 'code': 'EFG2'})
        factura = self.factura()
        self.pago(factura, 500.0, self.efectivo)
        self.pago(factura, 500.0, gemelo)
        self.assertEqual(self.forma(factura), 'Efectivo forma pago')
        self.assertEqual(factura.dcasa_diario_pago_ids, self.efectivo | gemelo)

    # --- se pone al día sola ---------------------------------------------------------------------------------
    def test_pagar_y_pagar_con_otro_diario(self):
        factura = self.factura()
        self.assertFalse(self.forma(factura))
        self.pago(factura, 100.0, self.efectivo)
        self.assertEqual(self.forma(factura), 'Efectivo forma pago')
        self.pago(factura, 900.0, self.tarjeta)
        self.assertEqual(self.forma(factura), 'Efectivo forma pago + Tarjeta forma pago')

    def test_un_pago_anulado_deja_de_contar(self):
        factura = self.factura()
        efectivo = self.pago(factura, 400.0, self.efectivo)
        yappy = self.pago(factura, 600.0, self.yappy)
        yappy.action_cancel()
        self.assertEqual(yappy.state, 'canceled')
        self.assertEqual(self.forma(factura), 'Efectivo forma pago')
        efectivo.action_cancel()
        self.assertFalse(self.forma(factura))
        self.assertFalse(factura.dcasa_diario_pago_ids)

    def test_un_pago_rechazado_no_cuenta_aunque_siga_conciliado(self):
        """El tablero tampoco cuenta lo rechazado: la definición de «cobro» pide pago en proceso o pagado."""
        factura = self.factura()
        self.pago(factura, 400.0, self.efectivo)
        yappy = self.pago(factura, 600.0, self.yappy)
        yappy.action_reject()
        self.assertEqual(yappy.state, 'rejected')
        self.assertEqual(self.forma(factura), 'Efectivo forma pago')

    def test_un_pago_devuelto_a_borrador_deja_de_contar(self):
        factura = self.factura()
        yappy = self.pago(factura, 1000.0, self.yappy)
        yappy.action_draft()
        self.assertEqual(yappy.state, 'draft')
        self.assertFalse(self.forma(factura))

    def test_un_pago_revertido_deja_de_contar(self):
        factura = self.factura()
        efectivo = self.pago(factura, 1000.0, self.efectivo)
        efectivo.move_id._reverse_moves([{'date': DIA}], cancel=True)
        self.assertEqual(factura.payment_state, 'not_paid')
        self.assertFalse(self.forma(factura))

    def test_desconciliar_un_pago_lo_saca_de_la_factura(self):
        """Odoo deja el pago en ``matched_payment_ids`` (y por eso en ``reconciled_payment_ids``) aunque se
        desconcilie: la columna mira la conciliación de verdad."""
        factura = self.factura()
        efectivo = self.pago(factura, 400.0, self.efectivo)
        yappy = self.pago(factura, 600.0, self.yappy)
        self.assertEqual(self.forma(factura), 'Efectivo forma pago + Yappy forma pago')
        parcial = yappy.move_id.line_ids.matched_debit_ids | yappy.move_id.line_ids.matched_credit_ids
        factura.js_remove_outstanding_partial(parcial.id)
        self.assertIn(yappy, factura.reconciled_payment_ids, 'Odoo lo sigue contando como suyo')
        self.assertEqual(factura.payment_state, 'partial')
        self.assertEqual(self.forma(factura), 'Efectivo forma pago')
        # El mismo pago, aplicado de nuevo, vuelve a contar.
        por_cobrar = yappy.move_id.line_ids.filtered(lambda linea: linea.account_id.account_type == 'asset_receivable')
        factura.js_assign_outstanding_line(por_cobrar.id)
        self.assertEqual(self.forma(factura), 'Efectivo forma pago + Yappy forma pago')
        self.assertEqual(efectivo.state, 'paid')

    def test_el_nombre_del_diario_se_actualiza_si_lo_renombran(self):
        factura = self.factura()
        self.pago(factura, 1000.0, self.yappy)
        self.yappy.name = 'Yappy Negocios forma pago'
        self.assertEqual(self.forma(factura), 'Yappy Negocios forma pago')

    # --- notas de crédito, proveedores y asientos ------------------------------------------------------------------
    def test_la_nota_de_credito_conciliada_sale_al_final(self):
        """Odoo aplica solo la nota de crédito que sale de la factura (al publicarla)."""
        factura = self.factura()
        nota = self.nota(factura, DIA, precio=300.0)
        self.assertEqual(factura.amount_residual, 700.0, 'la nota se aplicó a la factura')
        self.assertEqual(self.forma(factura), 'Nota de crédito')
        self.pago(factura, 700.0, self.yappy)
        self.assertEqual(factura.payment_state, 'paid')
        self.assertEqual(self.forma(factura), 'Yappy forma pago + Nota de crédito')
        self.assertEqual(factura.dcasa_diario_pago_ids, self.yappy, 'la nota no es un diario')
        self.assertFalse(self.forma(nota))

    def test_una_nota_de_credito_sin_aplicar_no_cambia_nada(self):
        factura = self.factura()
        suelta = self.env['account.move'].create({
            'move_type': 'out_refund', 'partner_id': self.cliente.id, 'invoice_date': DIA,
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 50.0})]})
        suelta.action_post()
        self.assertEqual(factura.payment_state, 'not_paid')
        self.assertFalse(self.forma(factura))
        self.aplicar_nota(factura, suelta)
        self.assertEqual(self.forma(factura), 'Nota de crédito')

    def test_la_nota_que_anula_toda_la_factura(self):
        factura = self.factura()
        nota = self.nota(factura, DIA, conciliar=True)
        self.assertEqual(factura.payment_state, 'reversed')
        self.assertEqual(self.forma(factura), 'Nota de crédito')
        self.assertFalse(factura.dcasa_diario_pago_ids)
        self.assertFalse(self.forma(nota), 'la nota misma no es un cobro')

    def test_desconciliar_la_nota_quita_la_palabra(self):
        factura = self.factura()
        nota = self.nota(factura, DIA, precio=300.0)
        self.assertEqual(self.forma(factura), 'Nota de crédito')
        parcial = nota.line_ids.matched_debit_ids | nota.line_ids.matched_credit_ids
        factura.js_remove_outstanding_partial(parcial.id)
        self.assertEqual(factura.payment_state, 'not_paid')
        self.assertFalse(self.forma(factura))

    def test_la_nota_de_credito_no_lleva_forma_de_pago(self):
        """Ni aplicada a una factura ni con dinero devuelto: no es un cobro."""
        factura = self.factura()
        self.pago(factura, 1000.0, self.efectivo)
        nota = self.nota(factura, DIA, precio=100.0)
        self.assertEqual(nota.move_type, 'out_refund')
        self.assertFalse(self.forma(nota))
        devolucion = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=nota.ids).create({
                'payment_date': DIA, 'amount': 100.0, 'journal_id': self.yappy.id})._create_payments()
        self.assertEqual(devolucion.payment_type, 'outbound')
        self.assertFalse(self.forma(nota))
        self.assertEqual(self.forma(factura), 'Efectivo forma pago')

    def test_proveedores_y_asientos_no_la_llevan(self):
        proveedor = self.env['res.partner'].create({'name': 'Proveedor forma pago'})
        compra = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': proveedor.id, 'invoice_date': DIA, 'date': DIA,
            'invoice_line_ids': [Command.create({'name': 'Compra', 'quantity': 1, 'price_unit': 200.0})]})
        compra.action_post()
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=compra.ids).create({
                'payment_date': DIA, 'amount': 200.0, 'journal_id': self.efectivo.id})._create_payments()
        self.assertEqual(compra.payment_state, 'paid')
        self.assertFalse(self.forma(compra))
        self.assertFalse(compra.dcasa_diario_pago_ids)
        asiento = compra.reconciled_payment_ids.move_id
        self.assertEqual(asiento.move_type, 'entry')
        self.assertFalse(self.forma(asiento))

    def test_la_copia_de_una_factura_nace_sin_forma_de_pago(self):
        factura = self.factura()
        self.pago(factura, 1000.0, self.efectivo)
        copia = factura.copy()
        self.assertFalse(self.forma(copia))
        self.assertFalse(copia.dcasa_diario_pago_ids)

    # --- la misma cuenta que el tablero ------------------------------------------------------------------------
    def test_la_definicion_de_cobro_es_la_del_tablero(self):
        dominio = self.env['account.move']._dcasa_dominio_de_pago_que_cuenta()
        del_tablero = [c for c in self.tablero._dominio_de_cobros(DIA, DIA) if c[0] != 'date']
        self.assertEqual(dominio, del_tablero)
        self.assertIn(('payment_type', '=', 'inbound'), dominio)
        self.assertIn(('state', 'in', ('in_process', 'paid')), dominio)
        self.assertFalse([c for c in dominio if c[0] == 'date'], 'una factura cuenta el pago sin importar el día')

    def test_el_tablero_y_la_columna_nunca_discrepan(self):
        """Cada cobro que el tablero cuenta para un diario está en una factura que dice ese diario, y cada factura
        que dice un diario tiene un cobro que el tablero cuenta (lo anulado y lo rechazado no cuenta en ninguno)."""
        a, b, c = self.factura(), self.factura(), self.factura()
        self.pago(a, 1000.0, self.efectivo)
        self.pago(b, 400.0, self.yappy)
        self.pago(b, 600.0, self.efectivo)
        self.pago(c, 500.0, self.tarjeta).action_cancel()
        self.pago(c, 300.0, self.yappy).action_reject()
        self.pago(c, 200.0, self.yappy)
        facturas = a | b | c
        cobros = self.tablero.with_user(self.gerencia)._cobros_por_forma(DIA, DIA, 'Cobros de prueba')
        self.assertEqual({fila['clave']: fila['monto'] for fila in cobros['filas']},
                         {self.efectivo.id: 1600.0, self.yappy.id: 600.0}, 'lo que cuenta el tablero')
        Pago, Factura = self.env['account.payment'], self.env['account.move']
        for diario, con_ese_diario in ((self.efectivo, a | b), (self.yappy, b | c), (self.tarjeta, Factura)):
            with self.subTest(diario.name):
                contados = Pago.search(self.tablero._dominio_de_cobros(DIA, DIA) + [('journal_id', '=', diario.id)])
                self.assertEqual(contados.reconciled_invoice_ids & facturas, con_ese_diario)
                con_el_diario = Factura.search(
                    [('id', 'in', facturas.ids), ('dcasa_diario_pago_ids', 'in', diario.ids)])
                self.assertEqual(con_el_diario, con_ese_diario)
        self.assertEqual(self.forma(c), 'Yappy forma pago')

    # --- buscar y agrupar --------------------------------------------------------------------------------------
    def test_buscar_por_el_nombre_de_un_diario(self):
        solo_efectivo, mixta, nada = self.factura(), self.factura(), self.factura()
        self.pago(solo_efectivo, 1000.0, self.efectivo)
        self.pago(mixta, 400.0, self.yappy)
        self.pago(mixta, 600.0, self.efectivo)
        Factura = self.env['account.move']
        base = [('id', 'in', (solo_efectivo | mixta | nada).ids)]
        self.assertEqual(Factura.search(base + [('dcasa_forma_pago', 'ilike', 'yappy')]), mixta)
        self.assertEqual(Factura.search(base + [('dcasa_forma_pago', 'ilike', 'efectivo')]), solo_efectivo | mixta)
        self.assertEqual(Factura.search(base + [('dcasa_diario_pago_ids', 'in', self.yappy.ids)]), mixta)
        self.assertEqual(Factura.search(base + [('dcasa_diario_pago_ids', 'ilike', 'efectivo')]),
                         solo_efectivo | mixta)
        self.assertEqual(Factura.search(base + [('dcasa_forma_pago', '=', False)]), nada)

    def test_agrupar_por_forma_de_pago_no_cuenta_dos_veces(self):
        """Cada factura cae en un solo grupo: los totales por grupo suman el total, sin repetir ninguna."""
        facturas = self.factura(), self.factura(), self.factura(), self.factura()
        self.pago(facturas[0], 1000.0, self.efectivo)
        self.pago(facturas[1], 400.0, self.yappy)
        self.pago(facturas[1], 600.0, self.efectivo)
        self.pago(facturas[2], 1000.0, self.yappy)
        todas = self.env['account.move'].browse([f.id for f in facturas])
        grupos = self.env['account.move']._read_group(
            [('id', 'in', todas.ids)], ['dcasa_forma_pago'], ['__count', 'amount_total:sum'])
        self.assertEqual(
            {forma: (cuantas, total) for forma, cuantas, total in grupos},
            {'Efectivo forma pago': (1, 1000.0), 'Efectivo forma pago + Yappy forma pago': (1, 1000.0),
             'Yappy forma pago': (1, 1000.0), False: (1, 1000.0)})
        self.assertEqual(sum(cuantas for _forma, cuantas, _total in grupos), len(todas))

    def test_la_vendedora_la_lee_y_filtra_sin_ver_los_pagos(self):
        """Lo guardado se calcula con permisos de sistema: quien factura (y no registra cobros) lo lee y lo busca
        aunque no pueda abrir un pago."""
        factura = self.factura()
        self.pago(factura, 1000.0, self.yappy)
        con_ella = self.env['account.move'].with_user(self.vendedora)
        for dominio in ([('dcasa_forma_pago', 'ilike', 'yappy')], [('dcasa_diario_pago_ids', 'ilike', 'yappy')]):
            with self.subTest(dominio):
                self.assertEqual(con_ella.search([('id', '=', factura.id)] + dominio), factura)
        self.assertEqual(con_ella.browse(factura.id).dcasa_forma_pago, 'Yappy forma pago')
        filas = con_ella.web_search_read([('id', '=', factura.id)], {'dcasa_forma_pago': {}})
        self.assertEqual(filas['records'][0]['dcasa_forma_pago'], 'Yappy forma pago')


    def test_el_cliente_del_portal_lee_el_texto_y_no_tropieza_con_los_diarios(self):
        """Los diarios solo los leen quienes pueden leer diarios (el cliente del portal no): el texto sí lo lee quien
        ve la factura, y el campo de diarios ni siquiera se le ofrece."""
        factura = self.factura()
        self.pago(factura, 1000.0, self.yappy)
        portal = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Cliente portal forma pago', 'login': 'portal_forma_pago', 'partner_id': self.cliente.id,
            'group_ids': [Command.set([self.env.ref('base.group_portal').id])]})
        suya = factura.with_user(portal)
        self.assertEqual(suya.read(['dcasa_forma_pago'])[0]['dcasa_forma_pago'], 'Yappy forma pago')
        self.assertNotIn('dcasa_diario_pago_ids', suya.fields_get())
        self.assertIn('dcasa_diario_pago_ids', factura.with_user(self.vendedora).fields_get())


@tagged('post_install', '-at_install')
class TestFormaPagoEnLote(FormaPagoCommon):

    def con_pagos(self, cuantas):
        """``cuantas`` facturas con cinco combinaciones de pagos que se repiten (la misma mezcla de diarios que
        tendría la base real: pocas combinaciones, muchas facturas)."""
        facturas = self.env['account.move']
        for i in range(cuantas):
            factura = self.factura(precio=100.0 + i)
            caso = i % 5
            self.pago(factura, 40.0, self.efectivo)
            if caso == 1:
                self.pago(factura, 60.0 + i, self.yappy)
            elif caso == 2:
                self.pago(factura, 10.0, self.tarjeta)
                self.pago(factura, 50.0 + i, self.yappy)
            elif caso == 3:
                self.nota(factura, DIA, precio=10.0)
            elif caso == 4:
                factura.button_draft()
                factura.button_cancel()
            facturas |= factura
        return facturas

    def consultas(self, facturas):
        """Cuántas consultas cuesta que el campo de estas facturas nazca desde cero, como al actualizar el módulo en
        producción (se marca por calcular y se calcula y se guarda todo), contando con la memoria fría."""
        self.env.flush_all()
        self.env.invalidate_all()                   # (esto también guarda lo pendiente: va antes de marcar)
        for nombre in ('dcasa_forma_pago', 'dcasa_diario_pago_ids'):
            self.env.add_to_compute(self.env['account.move']._fields[nombre], facturas)
        antes = self.env.cr.sql_log_count
        self.env.flush_all()
        return self.env.cr.sql_log_count - antes

    def test_no_hay_una_consulta_por_factura(self):
        """Al actualizar el módulo en producción el campo se calcula para todas las facturas ya cobradas: 15 o 30
        cuestan lo mismo (una consulta para las conciliaciones y lecturas agrupadas), no una tanda por factura."""
        facturas = self.con_pagos(30)
        self.consultas(facturas)                    # calienta lo que se guarda aparte (referencias, diarios)
        mitad = self.consultas(facturas[:15])
        todas = self.consultas(facturas)
        self.assertGreater(mitad, 3, 'la cuenta tiene que haber medido algo: sin consultas no se calculó nada')
        self.assertEqual(todas, mitad, f'15 facturas costaron {mitad} consultas y 30 costaron {todas}: ¿una por cada?')
        self.assertLessEqual(todas, 40, 'son pocas consultas por cada combinación de diarios, no por factura')
        # Sale lo que debe: la cuarta de cada cinco lleva la nota de crédito y la quinta, anulada, no lleva nada.
        esperado = ['Efectivo forma pago', 'Efectivo forma pago + Yappy forma pago',
                    'Efectivo forma pago + Tarjeta forma pago + Yappy forma pago',
                    'Efectivo forma pago + Nota de crédito', False]
        self.assertEqual([facturas[i].dcasa_forma_pago for i in range(5)], esperado)
        self.assertEqual([facturas[i + 25].dcasa_forma_pago for i in range(5)], esperado)

    def test_recalcular_todas_las_facturas_da_lo_mismo_que_el_dia_a_dia(self):
        """Lo que hace la actualización del módulo en una base con facturas ya cobradas (el campo nace vacío)."""
        a, b = self.factura(), self.factura()
        self.pago(a, 1000.0, self.yappy)
        self.pago(b, 500.0, self.efectivo)
        self.pago(b, 500.0, self.tarjeta)
        esperado = {a.id: 'Yappy forma pago', b.id: 'Efectivo forma pago + Tarjeta forma pago'}
        self.env.flush_all()
        ids = tuple((a | b).ids)
        self.env.cr.execute('UPDATE account_move SET dcasa_forma_pago = NULL WHERE id IN %s', (ids,))
        self.env.cr.execute('DELETE FROM dcasa_move_diario_pago_rel WHERE move_id IN %s', (ids,))
        self.env.invalidate_all()
        self.assertFalse(a.dcasa_forma_pago)
        self.consultas(a | b)
        self.assertEqual({a.id: a.dcasa_forma_pago, b.id: b.dcasa_forma_pago}, esperado)
        self.assertEqual(b.dcasa_diario_pago_ids, self.efectivo | self.tarjeta)


@tagged('post_install', '-at_install')
class TestFormaPagoPantallas(FormaPagoCommon):

    def arch(self, xmlid, tipo='list', modelo='account.move', usuario=None):
        Modelo = self.env[modelo].with_user(usuario) if usuario else self.env[modelo]
        return Modelo.get_view(view_id=self.env.ref(xmlid).id, view_type=tipo)['arch']

    def test_la_columna_esta_en_la_lista_de_facturas_y_se_ve_por_defecto(self):
        arch = self.arch('account.view_out_invoice_tree')
        self.assertRegex(arch, r'<field name="dcasa_forma_pago"[^>]*optional="show"')
        self.assertLess(arch.index('name="status_in_payment"'), arch.index('name="dcasa_forma_pago"'),
                        'junto al Estado, después de él: «Total · Estado · Forma de pago»')
        self.assertLess(arch.index('name="amount_total_in_currency_signed"'), arch.index('name="dcasa_forma_pago"'))
        self.assertIn('name="action_dcasa_imprimir_documentos"', arch, 'lo de los otros módulos sigue en su lugar')
        self.assertIn('name="dcasa_origen"', arch)

    def test_otras_listas_de_facturas_quedan_como_estaban(self):
        for xmlid in ('account.view_out_credit_note_tree', 'account.view_in_invoice_tree',
                      'account.view_in_invoice_bill_tree'):
            with self.subTest(xmlid):
                self.assertNotIn('dcasa_forma_pago', self.arch(xmlid))

    def test_la_lista_se_arma_para_cada_rol(self):
        for usuario in (self.vendedora, self.caja, self.gerencia):
            with self.subTest(usuario.login):
                self.assertIn('name="dcasa_forma_pago"', self.arch('account.view_out_invoice_tree', usuario=usuario))

    def test_en_el_celular_la_tarjeta_de_la_factura_la_trae(self):
        arch = self.arch('account.view_account_move_kanban', 'kanban')
        self.assertRegex(arch, r'<field name="dcasa_forma_pago"')
        self.assertLess(arch.index('name="dcasa_forma_pago"'), arch.index('<footer'))
        self.assertIn('name="amount_total_in_currency_signed"', arch, 'lo de siempre sigue en su lugar')

    def test_el_buscador_la_trae_y_agrupa(self):
        arch = self.arch('account.view_account_invoice_filter', 'search')
        self.assertRegex(arch, r'<field name="dcasa_forma_pago"[^>]*string="Forma de pago"')
        self.assertIn('name="dcasa_por_forma_pago"', arch)
        self.assertIn("'group_by': 'dcasa_forma_pago'", arch)
        self.assertIn('name="dcasa_origen_chatbot"', arch, 'lo de los otros módulos sigue en su lugar')

    def test_el_formulario_la_muestra_solo_para_leer(self):
        arch = self.arch('account.view_move_form', 'form')
        self.assertRegex(arch, r'<field name="dcasa_forma_pago"[^>]*readonly="1"')
        self.assertLess(arch.index('name="sale_info_group"'), arch.index('name="dcasa_forma_pago"'))

    def test_el_campo_se_puede_exportar(self):
        campos = self.env['account.move'].fields_get(['dcasa_forma_pago', 'dcasa_diario_pago_ids'],
                                                     attributes=['string', 'exportable', 'store', 'type'])
        self.assertEqual(campos['dcasa_forma_pago']['string'], 'Forma de pago')
        self.assertEqual(campos['dcasa_forma_pago']['type'], 'char')
        for nombre, campo in campos.items():
            with self.subTest(nombre):
                self.assertTrue(campo.get('exportable', True))
                self.assertTrue(campo['store'])


@tagged('post_install', '-at_install')
class TestFormaPagoEnElExcel(FormaPagoCommon, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.exporta = crear_usuario(cls.env, 'exporta_forma_pago', 'dcasa_base.group_gerencia')
        cls.exporta.group_ids = [Command.link(cls.env.ref('base.group_allow_export').id)]

    def setUp(self):
        super().setUp()
        self.mixta = self.factura()
        self.pago(self.mixta, 400.0, self.yappy)
        self.pago(self.mixta, 600.0, self.efectivo)
        self.sin_pago = self.factura(precio=250.0)

    def test_export_data_trae_el_texto(self):
        facturas = (self.mixta | self.sin_pago).with_user(self.exporta)
        datos = facturas.export_data(['name', 'dcasa_forma_pago', 'dcasa_diario_pago_ids']).get('datas')
        por_numero = {fila[0]: fila[1:] for fila in datos if fila[0]}
        self.assertEqual(por_numero[self.mixta.name][0], 'Efectivo forma pago + Yappy forma pago')
        self.assertEqual(por_numero[self.sin_pago.name][0], '')
        self.assertIn('Efectivo forma pago', por_numero[self.mixta.name][1])

    def test_la_plantilla_de_exportar_trae_las_columnas_de_la_lista_y_la_forma_de_pago(self):
        """«Acción › Exportar › Plantilla › Facturas con forma de pago»: sin buscar campo por campo."""
        plantilla = self.env.ref('dcasa_interfaz.exportacion_facturas_forma_pago').with_user(self.exporta)
        self.assertEqual((plantilla.name, plantilla.resource), ('Facturas con forma de pago', 'account.move'))
        campos = plantilla.export_fields.mapped('name')
        for campo in ('name', 'invoice_partner_display_name', 'invoice_date', 'invoice_date_due', 'ref',
                      'invoice_user_id', 'dcasa_origen', 'amount_tax', 'amount_total', 'status_in_payment',
                      'dcasa_forma_pago'):
            self.assertIn(campo, campos)
        datos = (self.mixta | self.sin_pago).with_user(self.exporta).export_data(campos)['datas']
        fila = next(f for f in datos if f[0] == self.mixta.name)
        self.assertEqual(len(fila), len(campos))
        self.assertEqual(fila[campos.index('dcasa_forma_pago')], 'Efectivo forma pago + Yappy forma pago')

    def test_exportar_lo_pide_el_permiso_de_exportar_y_asi_sigue(self):
        """Lo que ya era así y no se tocó: sin el permiso «Exportar» (``base.group_allow_export``) el servidor lo niega
        (Gerencia, Caja y Vendedora no lo traen; sí los administradores)."""
        for usuario in (self.vendedora, self.caja, self.gerencia):
            with self.subTest(usuario.login), self.assertRaises(UserError):
                self.mixta.with_user(usuario).export_data(['name', 'dcasa_forma_pago'])

    def test_el_xlsx_trae_la_forma_de_pago(self):
        """El archivo de verdad: «Acción › Exportar» con la columna, abierto por dentro."""
        self.authenticate('exporta_forma_pago', 'exporta_forma_pago')
        campos = [('name', 'Número', 'char'), ('dcasa_forma_pago', 'Forma de pago', 'char'),
                  ('amount_total', 'Total', 'monetary')]
        respuesta = self.url_open('/web/export/xlsx', data={
            'data': json.dumps({
                'context': {}, 'domain': [], 'groupby': [], 'ids': (self.mixta | self.sin_pago).ids,
                'import_compat': False, 'model': 'account.move',
                'fields': [{'name': n, 'label': e, 'type': t} for n, e, t in campos]}),
            'csrf_token': http.Request.csrf_token(self)})
        self.assertEqual(respuesta.status_code, 200, respuesta.text[:300])
        with zipfile.ZipFile(io.BytesIO(respuesta.content)) as libro:
            textos = libro.read('xl/sharedStrings.xml').decode()
        self.assertIn('Forma de pago', textos, 'el encabezado de la columna')
        self.assertIn('Efectivo forma pago + Yappy forma pago', textos)
        self.assertIn(self.mixta.name, re.sub('<[^>]+>', ' ', textos))
