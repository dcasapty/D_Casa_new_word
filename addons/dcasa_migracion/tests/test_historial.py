"""Las facturas y los pagos del año: quedan publicados con su número, cuadran con el archivo, se aplican a sus
facturas y no tocan la DGI ni los puntos de Socios. Todo con los ejemplos inventados de la receta."""
from unittest import mock

from odoo.addons.dcasa_base import itbms_de_venta
from odoo.addons.dcasa_migracion import contactos as C
from odoo.addons.dcasa_migracion import historial as H
from odoo.addons.dcasa_migracion import reglas, reglas_historial
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from . import ejemplos


def _facturas(rol):
    cabecera, lineas = ((ejemplos.FACTURAS_CLIENTES, ejemplos.FACTURAS_CLIENTES_LINEAS) if rol == 'cliente'
                        else (ejemplos.FACTURAS_PROVEEDORES, ejemplos.FACTURAS_PROVEEDORES_LINEAS))
    facturas, errores = reglas_historial.filas_facturas(cabecera, lineas, rol)
    assert not errores
    return facturas


@tagged('post_install', '-at_install')
class TestHistorialDelAno(TransactionCase):

    def setUp(self):
        super().setUp()
        C.cargar_clientes(self.env, reglas.filas_clientes(ejemplos.CLIENTES)[0])
        C.cargar_proveedores(self.env, reglas.filas_proveedores(ejemplos.PROVEEDORES)[0])
        Diario = self.env['account.journal']
        self.caja = Diario.create({'name': 'Caja Ejemplo', 'type': 'cash', 'code': 'CEJ'})
        self.banco = Diario.create({'name': 'Banco Ejemplo', 'type': 'bank', 'code': 'BEJ'})
        self.clientes, self.proveedores = _facturas('cliente'), _facturas('proveedor')
        self.pagos = reglas_historial.filas_pagos(ejemplos.PAGOS)[0]

    def _ficha(self, id_viejo):
        return self.env.ref(f'__import__.{C.xmlid_contacto(id_viejo)}')

    def _factura(self, numero):
        return self.env.ref(f'__import__.{reglas_historial.xmlid_factura(numero)}')

    def _cargar_todo(self):
        H.cargar_facturas(self.env, self.clientes, 'cliente', H.Presupuesto())
        H.cargar_facturas(self.env, self.proveedores, 'proveedor', H.Presupuesto())
        return H.cargar_pagos(self.env, self.pagos, H.Presupuesto())

    # --- facturas -------------------------------------------------------------------------------------------------

    def test_facturas_de_clientes_quedan_publicadas_con_su_numero(self):
        resumen = H.cargar_facturas(self.env, self.clientes, 'cliente', H.Presupuesto())
        self.assertEqual(resumen['con_error'], [])
        self.assertEqual(sorted(resumen['creados']), sorted(f['numero'] for f in self.clientes))
        factura = self._factura('INV/2026/90002')
        self.assertEqual((factura.move_type, factura.state, factura.name, factura.partner_id, factura.ref,
                          factura.invoice_origin, str(factura.invoice_date), str(factura.invoice_date_due)),
                         ('out_invoice', 'posted', 'INV/2026/90002', self._ficha(90002), 'FE-0000000001', 'S90002',
                          '2026-08-15', '2026-09-14'))
        self.assertTrue(factura.dcasa_historica)
        self.assertEqual((factura.amount_untaxed, factura.amount_tax, factura.amount_total), (250.0, 17.5, 267.5))
        (linea, ) = factura.invoice_line_ids
        self.assertEqual((linea.name, linea.quantity, linea.price_unit, linea.tax_ids),
                         ('Producto Ejemplo 2', 2.0, 125.0, itbms_de_venta(self.env, self.env.company)))

    def test_descuento_y_linea_sin_producto(self):
        H.cargar_facturas(self.env, self.clientes, 'cliente', H.Presupuesto())
        factura = self._factura('INV/2026/90003')
        (linea,) = factura.invoice_line_ids
        self.assertEqual((linea.product_id.id, linea.discount, linea.price_subtotal), (False, 10.0, 45.0))
        self.assertEqual(factura.amount_total, 48.15)

    def test_nota_de_credito_resta_y_se_enlaza_a_su_factura(self):
        H.cargar_facturas(self.env, self.clientes, 'cliente', H.Presupuesto())
        nota = self._factura('RINV/2026/90001')
        self.assertEqual((nota.move_type, nota.state, nota.amount_total, nota.reversed_entry_id),
                         ('out_refund', 'posted', 21.4, self._factura('INV/2026/90001')))

    def test_facturas_de_proveedores_con_su_referencia_y_sin_impuesto(self):
        resumen = H.cargar_facturas(self.env, self.proveedores, 'proveedor', H.Presupuesto())
        self.assertEqual(resumen['con_error'], [])
        factura = self._factura('BILL/2026/90001')
        self.assertEqual((factura.move_type, factura.name, factura.ref, factura.partner_id, factura.amount_total),
                         ('in_invoice', 'BILL/2026/90001', 'FAC-EJ-1001', self._ficha(70001), 5350.0))
        exenta = self._factura('BILL/2026/90002')
        self.assertEqual((exenta.amount_tax, exenta.amount_total, exenta.invoice_line_ids.tax_ids.ids),
                         (0.0, 12000.0, []))
        self.assertEqual(self._factura('RBILL/2026/90001').move_type, 'in_refund')

    def test_lo_cargado_lleva_su_marca_y_no_va_a_la_dga(self):
        H.cargar_facturas(self.env, self.clientes, 'cliente', H.Presupuesto())
        marcadas = self.env['account.move'].search([('dcasa_historica', '=', True)])
        self.assertEqual(len(marcadas), len(self.clientes))
        self.assertFalse(marcadas.filtered(lambda m: m.state != 'posted'))

    def test_la_numeracion_nueva_sigue_desde_la_ultima(self):
        H.cargar_facturas(self.env, self.clientes, 'cliente', H.Presupuesto())
        cliente = self._ficha(90001)
        nueva = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': cliente.id,
            'invoice_line_ids': [(0, 0, {'name': 'x', 'quantity': 1, 'price_unit': 1})]})
        nueva.action_post()
        self.assertEqual(nueva.name, 'INV/2026/90005', 'Sigue donde quedó la última factura cargada')
        self.assertFalse(nueva.dcasa_historica)

    def test_volver_a_cargar_no_repite_nada(self):
        H.cargar_facturas(self.env, self.clientes, 'cliente', H.Presupuesto())
        resumen = H.cargar_facturas(self.env, self.clientes, 'cliente', H.Presupuesto())
        self.assertEqual((resumen['creados'], len(resumen['ya_estaban'])), ([], len(self.clientes)))
        self.assertEqual(self.env['account.move'].search_count([('dcasa_historica', '=', True)]), len(self.clientes))

    def test_una_factura_que_no_cuadra_no_entra_y_dice_cuanto_difiere(self):
        factura = dict(self.clientes[0], total=999.0)
        resumen = H.cargar_facturas(self.env, [factura], 'cliente', H.Presupuesto())
        self.assertEqual(resumen['creados'], [])
        (numero, motivo), = resumen['con_error']
        self.assertEqual(numero, 'INV/2026/90001')
        self.assertIn('el total no cuadra', motivo)
        self.assertIn('999.00', motivo)
        self.assertFalse(self.env['account.move'].search([('name', '=', 'INV/2026/90001')]), 'No queda nada a medias')

    def test_un_impuesto_que_no_existe_es_un_error_claro(self):
        facturas = _facturas('cliente')
        facturas[0]['lineas'][0]['impuesto'] = 'IVA Marciano 99%'
        resumen = H.cargar_facturas(self.env, facturas, 'cliente', H.Presupuesto())
        self.assertEqual([n for n, _m in resumen['con_error']], ['INV/2026/90001'])
        self.assertIn('IVA Marciano 99%', resumen['con_error'][0][1])
        self.assertEqual(len(resumen['creados']), 4, 'Las demás siguen')

    def test_un_cliente_que_no_esta_cargado_es_un_error(self):
        self._ficha(90004).unlink()
        resumen = H.cargar_facturas(self.env, self.clientes, 'cliente', H.Presupuesto())
        self.assertEqual([n for n, _m in resumen['con_error']], ['INV/2026/90004'])
        self.assertIn('clientes.csv', resumen['con_error'][0][1])

    def test_una_factura_con_total_cero_o_fecha_futura_entra_pero_se_avisa(self):
        futura = dict(self.proveedores[4], numero='BILL/2099/00001', fecha='2099-01-01', vencimiento=None)
        cero = dict(self.proveedores[4], numero='BILL/2026/00000', base=0.0, impuesto=0.0, total=0.0,
                    lineas=[dict(self.proveedores[4]['lineas'][0], precio=0.0)])
        resumen = H.cargar_facturas(self.env, [futura, cero], 'proveedor', H.Presupuesto())
        self.assertEqual(resumen['con_error'], [])
        self.assertEqual(sorted(resumen['para_revisar']), [
            ('BILL/2026/00000', 'total 0'), ('BILL/2099/00001', 'fecha futura (2099-01-01)')])

    def test_la_carga_trabaja_por_tandas_y_retoma_donde_se_quedo(self):
        resumen = H.cargar_facturas(self.env, self.clientes, 'cliente', H.Presupuesto(documentos=2))
        self.assertEqual((len(resumen['creados']), resumen['faltan']), (2, 3))
        segunda = H.cargar_facturas(self.env, self.clientes, 'cliente', H.Presupuesto(documentos=10))
        self.assertEqual((len(segunda['ya_estaban']), len(segunda['creados']), segunda['faltan']), (2, 3, 0))
        self.assertEqual(self.env['account.move'].search_count([('dcasa_historica', '=', True)]), 5)

    def test_una_factura_que_falla_no_deja_nada_a_medias(self):
        original = H._crear_factura

        def falla_en_la_segunda(env, Movimiento, factura, *args):
            movimiento = original(env, Movimiento, factura, *args)
            if factura['numero'] == 'INV/2026/90002':
                raise UserError('falló después de publicar')
            return movimiento

        with mock.patch.object(H, '_crear_factura', side_effect=falla_en_la_segunda):
            resumen = H.cargar_facturas(self.env, self.clientes, 'cliente', H.Presupuesto())
        self.assertEqual([n for n, _m in resumen['con_error']], ['INV/2026/90002'])
        self.assertFalse(self.env['account.move'].search([('name', '=', 'INV/2026/90002')]))
        self.assertEqual(len(resumen['creados']), 4)

    # --- pagos -----------------------------------------------------------------------------------------------------

    def test_pagos_publicados_y_aplicados_a_sus_facturas(self):
        resumen = self._cargar_todo()
        self.assertEqual(resumen['con_error'], [])
        self.assertEqual(len(resumen['creados']), 5)
        self.assertEqual(self._factura('INV/2026/90001').payment_state, 'paid')
        parcial = self._factura('INV/2026/90002')
        self.assertEqual((parcial.payment_state, parcial.amount_residual), ('partial', 167.5))
        self.assertEqual(self._factura('INV/2026/90003').amount_residual, 48.15)
        self.assertEqual(self._factura('BILL/2026/90001').payment_state, 'paid')
        self.assertEqual(self._factura('BILL/2026/90002').amount_residual, 6000.0)

    def test_conciliado_va_directo_al_banco_y_sin_conciliar_queda_en_transito(self):
        self._cargar_todo()
        Pago = self.env['account.payment']
        conciliado = Pago.search([('journal_id', '=', self.caja.id)])
        (linea_del_banco,) = conciliado.move_id.line_ids.filtered(
            lambda linea: linea.account_id.account_type != 'asset_receivable')
        self.assertEqual(linea_del_banco.account_id, self.caja.default_account_id)
        en_transito = Pago.search([('journal_id', '=', self.banco.id), ('partner_id', '=', self._ficha(90002).id)])
        cuentas = en_transito.move_id.line_ids.mapped('account_id')
        self.assertNotIn(self.banco.default_account_id, cuentas, 'Sin conciliar: espera el extracto del banco')

    def test_un_pago_que_cita_una_factura_que_no_existe_se_avisa(self):
        resumen = self._cargar_todo()
        self.assertEqual([n for _rotulo, n in resumen['facturas_no_cargadas']], [['INV/2026/90005']])
        self.assertEqual(self._factura('INV/2026/90004').payment_state, 'paid', 'La que sí está se paga')

    def test_pagos_no_se_repiten(self):
        self._cargar_todo()
        resumen = H.cargar_pagos(self.env, self.pagos, H.Presupuesto())
        self.assertEqual((resumen['creados'], len(resumen['ya_estaban'])), ([], 5))
        self.assertEqual(
            self.env['account.payment'].search_count([('memo', 'ilike', 'Cargado del sistema anterior')]), 5)

    def test_un_diario_que_no_existe_es_un_error_que_lo_nombra(self):
        self.caja.name = 'Otra caja'
        H.cargar_facturas(self.env, self.clientes, 'cliente', H.Presupuesto())
        resumen = H.cargar_pagos(self.env, self.pagos, H.Presupuesto())
        self.assertEqual(len(resumen['con_error']), 1)
        self.assertIn('Caja Ejemplo', resumen['con_error'][0][1])
        self.assertEqual(len(resumen['creados']), 4)

    def test_un_pago_sin_facturas_queda_como_saldo_a_favor(self):
        suelto = dict(self.pagos[0], clave='suelto_1', facturas=[])
        resumen = H.cargar_pagos(self.env, [suelto], H.Presupuesto())
        self.assertEqual((len(resumen['creados']), resumen['sin_facturas']), (1, 1))

    def test_un_pago_que_quedo_a_medias_se_aplica_cuando_llega_su_factura(self):
        # Primero los pagos (sus facturas aún no están cargadas) y después las facturas: la segunda pasada los aplica.
        H.cargar_pagos(self.env, self.pagos, H.Presupuesto())
        self.assertFalse(self.env['account.move'].search([('dcasa_historica', '=', True)]))
        H.cargar_facturas(self.env, self.clientes, 'cliente', H.Presupuesto())
        H.cargar_facturas(self.env, self.proveedores, 'proveedor', H.Presupuesto())
        H.cargar_pagos(self.env, self.pagos, H.Presupuesto())
        self.assertEqual(self._factura('INV/2026/90001').payment_state, 'paid')
        self.assertEqual(self._factura('BILL/2026/90001').payment_state, 'paid')

    # --- revisión y cuadre ------------------------------------------------------------------------------------------

    def test_revision_previa_de_todo_el_archivo(self):
        self.caja.name = 'Otra caja'
        self._ficha(90004).unlink()
        facturas = _facturas('cliente')
        facturas[1]['lineas'][0]['impuesto'] = 'IVA Marciano 99%'
        previa = H.revisar_previa(self.env, facturas, self.proveedores, self.pagos)
        self.assertEqual(previa['contactos'], [('cliente', 90004, 2)], '1 factura y 1 pago de ese cliente')
        self.assertEqual([nombre for nombre, _mensaje, _n in previa['impuestos']], ['IVA Marciano 99%'])
        self.assertEqual(previa['diarios'], [('Caja Ejemplo', 1)])
        self.assertEqual(previa['facturas'], ['INV/2026/90005'])
        self.assertIn(('EJ-001', 4), previa['productos'], 'Producto Ejemplo 1: 2 facturas de cliente y 2 de proveedor')

    def test_cuadre_contra_el_archivo(self):
        self._cargar_todo()
        resumen = H.cargar_historial(self.env, {
            'facturas_clientes': (self.clientes, []), 'facturas_proveedores': (self.proveedores, []),
            'pagos': (self.pagos, [])}, H.Presupuesto())
        self.assertEqual(resumen['faltan'], 0)
        clientes = resumen['cuadre']['cliente']
        self.assertEqual(clientes['cargadas'], 5)
        self.assertEqual(clientes['archivo']['total'], clientes['aqui']['total'])
        self.assertEqual(round(clientes['aqui']['total'], 2), 107 + 267.5 + 48.15 - 21.4 + 1284)
        # Cada factura quedó con el saldo del archivo...
        self.assertEqual((clientes['saldos'], resumen['cuadre']['proveedor']['saldos']), ([], []))
        # ...pero el ejemplo trae notas de crédito «pagadas» sin pago que las respalde: Odoo las aplica a su factura y
        # el cobro de esa factura sobra. El libro lo muestra: debe 21.40 menos que la suma de los saldos del archivo.
        self.assertEqual(round(clientes['archivo']['saldo'] - clientes['libro'], 2), 21.4)
        proveedores = resumen['cuadre']['proveedor']
        self.assertEqual(round(proveedores['archivo']['saldo'] - proveedores['libro'], 2), 107.0)

    def test_el_cuadre_no_se_da_mientras_falten_documentos(self):
        resumen = H.cargar_historial(self.env, {
            'facturas_clientes': (self.clientes, []), 'pagos': (self.pagos, [])}, H.Presupuesto(documentos=2))
        self.assertGreater(resumen['faltan'], 0)
        self.assertNotIn('cuadre', resumen)
