"""El cálculo de la comisión, el libro y la verdad: base con cada interruptor, reparto exacto, devoluciones, pago
revertido, factura anulada, versiones hacia adelante, libro inmutable, mes de Panamá, savepoint y barrido.

Cifras de PRUEBA: porcentajes y precios inventados aquí."""
from datetime import datetime
from unittest.mock import patch

from freezegun import freeze_time
from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import ComisionCommon

HOY = '2030-03-04 15:00:00'      # lunes, 10:00 en Panamá


class ComisionReloj(ComisionCommon):

    def setUp(self):
        super().setUp()
        self.reloj = freeze_time(HOY)
        self.reloj.start()
        self.addCleanup(self.reloj.stop)

    def avanzar(self, texto):
        """Mueve el reloj (UTC, sin zona) a ``texto``."""
        self.reloj.stop()
        self.reloj = freeze_time(texto)
        self.reloj.start()

    def centavos(self, empleado, venta=None):
        return sum(self.libro(empleado=empleado, venta=venta).mapped('centavos'))


@tagged('post_install', '-at_install')
class TestMedirYComisionar(ComisionReloj):

    def test_sin_version_solo_mide_y_lo_medido_antes_de_la_primera_version_no_cobra_nunca(self):
        antes = self.venta_web()
        self.avanzar('2030-03-05 15:00:00')
        self.version(10.0)
        self.assertFalse(self.libro(), 'la venta de antes ya estaba medida y no cobra')
        self.venta(antes)._reconciliar()
        self.env['dcasa.web.venta']._barrido()
        self.assertFalse(self.libro(), 'ni con el barrido ni al compararla con el libro')
        self.assertEqual(self.venta(antes).estado, 'medida')
        despues = self.venta_web(fecha='2030-03-05')
        self.assertEqual(self.venta(despues).estado, 'comisionada')
        self.assertTrue(self.libro(venta=self.venta(despues)))

    def test_con_una_version_vigente_se_anota_el_reparto_sin_perder_un_centavo(self):
        self.version(3.333, reparto=[(self.ana, 60.0), (self.beto, 40.0)])
        factura = self.venta_web()
        venta = self.venta(factura)
        self.assertEqual(venta.base_centavos, 100000)
        self.assertEqual(venta.comision_centavos, 3333, '3.333 % de 1,000.00')
        self.assertEqual((self.centavos(self.ana), self.centavos(self.beto)), (2000, 1333),
                         'el centavo que sobra va a la primera persona de la lista')
        self.assertEqual(self.libro(venta=venta, tipo='venta').mapped('tipo'), ['venta', 'venta'])
        self.assertEqual(venta.reglas_id, self.env['dcasa.web.reglas']._vigente(self.company))

    def test_el_saldo_es_siempre_la_suma_del_libro_y_no_hay_columna_de_saldo(self):
        self.version(10.0)
        self.venta_web()
        self.assertEqual(self.saldo(self.ana), 6000)
        self.assertEqual(self.saldo(self.ana), self.centavos(self.ana))
        self.assertNotIn('saldo', self.env['dcasa.web.movimiento']._fields)
        self.assertNotIn('saldo', self.env['hr.employee']._fields)

    def test_cada_interruptor_cambia_lo_que_se_anota(self):
        """Una venta con premio de 100, envío de 50, ITBMS y una devolución de 200: la base de cada interruptor."""
        lineas = [(self.mueble, 1000.0, 1, {}), (self.premio, -100.0, 1, {}),
                  (self.envio, 50.0, 1, {'is_delivery': True})]
        casos = [({}, 90000 - 20000), ({'base_envio': 'con'}, 90000 + 5000 - 20000),
                 ({'base_descuentos': 'antes'}, 100000 - 20000), ({'base_devoluciones': 'no_resta'}, 90000)]
        for i, (opciones, base) in enumerate(casos):
            with self.subTest(opciones=opciones):
                self.avanzar(f'2030-03-{10 + i} 15:00:00')
                self.version(10.0, **opciones)
                factura = self.facturar(self.orden(lineas=lineas), f'2030-03-{10 + i}')
                self.pagar(factura, f'2030-03-{10 + i}')
                self.nota(factura, 200.0, fecha=f'2030-03-{10 + i}')
                self.assertEqual(self.venta(factura).base_centavos, base)
                self.assertEqual(self.venta(factura).comision_centavos, base // 10)

    def test_con_itbms_la_base_suma_el_impuesto_de_la_venta_y_resta_el_de_la_devolucion(self):
        self.version(10.0, base_itbms='con')
        factura = self.venta_web()
        venta = self.venta(factura)
        itbms = venta.itbms_centavos
        self.assertGreater(itbms, 0)
        self.assertEqual(venta.base_centavos, 100000 + itbms)
        self.nota(factura, 200.0)
        venta = self.venta(factura)
        self.assertEqual(venta.base_centavos, 100000 + itbms - 20000 - venta.devuelto_itbms_centavos)

    def test_la_comision_de_la_pasarela_se_resta_solo_si_el_interruptor_lo_dice(self):
        self.version(10.0, base_pasarela='resta')
        orden = self.orden()
        pago = self.env['payment.transaction'].sudo().create({
            'provider_id': self.env.ref('payment.payment_provider_transfer').id, 'amount': 1070.0,
            'currency_id': self.company.currency_id.id, 'partner_id': self.cliente.id, 'reference': 'PASARELA-PRUEBA-1',
            'payment_method_id': self.env['payment.method'].search([], limit=1).id,
            'sale_order_ids': [(6, 0, orden.ids)],
            'state': 'done', 'dcasa_comision_pasarela': 30.0})
        self.assertEqual(pago.dcasa_comision_pasarela, 30.0)
        factura = self.facturar(orden)
        self.pagar(factura)
        self.assertEqual(self.venta(factura).pasarela_centavos, 3000)
        self.assertEqual(self.venta(factura).base_centavos, 100000 - 3000)

    # ------------------------------------------------------------------ devoluciones y verdad

    def test_una_devolucion_parcial_resta_y_el_mes_de_la_venta_no_cambia(self):
        self.version(10.0)
        factura = self.venta_web()
        venta = self.venta(factura)
        venta_original = self.libro(venta=venta, tipo='venta')
        self.avanzar('2030-04-02 15:00:00')
        self.nota(factura, 400.0, fecha='2030-04-02')
        self.assertEqual(self.venta(factura).devuelto_centavos, 40000)
        self.assertEqual((self.centavos(self.ana), self.centavos(self.beto)), (3600, 2400), '10 % de 600')
        devoluciones = self.libro(venta=venta, tipo='devolucion')
        self.assertEqual(sum(devoluciones.mapped('centavos')), -4000)
        self.assertEqual(set(devoluciones.mapped('mes')), {datetime(2030, 4, 1).date()})
        self.assertEqual(set(venta_original.mapped('mes')), {datetime(2030, 3, 1).date()},
                         'el mes de la venta no se mueve nunca')
        self.assertTrue(all(devoluciones.mapped('motivo')))

    def test_una_devolucion_total_deja_la_comision_en_cero_y_no_se_pasa(self):
        self.version(10.0)
        factura = self.venta_web()
        self.nota(factura, 1000.0)
        self.assertEqual((self.centavos(self.ana), self.centavos(self.beto)), (0, 0))
        self.nota(factura, 500.0)         # una nota de más: la base nunca baja de cero
        self.assertEqual((self.centavos(self.ana), self.centavos(self.beto)), (0, 0))

    def test_la_devolucion_no_resta_si_las_devoluciones_no_restan(self):
        self.version(10.0, base_devoluciones='no_resta')
        factura = self.venta_web()
        self.nota(factura, 400.0)
        self.assertEqual(self.centavos(self.ana), 6000)

    def test_una_nota_aplicada_suelta_sin_enlazar_tambien_resta(self):
        self.version(10.0)
        factura = self.facturar(self.orden())
        nota = self.nota(factura, 400.0, enlazada=False)
        linea_nota = nota.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        factura.js_assign_outstanding_line(linea_nota.id)
        self.pagar(factura)
        self.assertEqual(factura.payment_state in ('paid', 'in_payment'), True)
        self.env['dcasa.web.venta']._barrido()
        venta = self.venta(factura)
        self.assertEqual(venta.devuelto_centavos, 40000)
        self.assertEqual(venta.base_centavos, 60000)
        self.assertEqual(self.centavos(self.ana), 3600)

    def test_un_pago_revertido_lo_reversa_el_barrido_y_volver_a_pagar_lo_repone(self):
        self.version(10.0)
        factura = self.venta_web()
        venta = self.venta(factura)
        self.assertEqual(self.centavos(self.ana), 6000)
        factura.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable').remove_move_reconcile()
        self.assertEqual(factura.payment_state, 'not_paid')
        self.assertEqual(self.centavos(self.ana), 6000, 'hasta el barrido nadie lo sabe')
        self.env['dcasa.web.venta']._barrido()
        self.assertEqual((self.centavos(self.ana), self.centavos(self.beto)), (0, 0))
        self.assertEqual(venta.estado, 'revertida')
        self.assertEqual(self.libro(venta=venta, tipo='reverso').mapped('tipo'), ['reverso', 'reverso'])
        self.pagar(factura)
        self.assertEqual((self.centavos(self.ana), self.centavos(self.beto)), (6000, 4000), 'volvió a quedar pagada')
        self.assertEqual(venta.estado, 'comisionada')

    def test_una_factura_cancelada_o_vuelta_a_borrador_se_reversa(self):
        self.version(10.0)
        factura = self.venta_web()
        self.assertEqual(self.centavos(self.ana), 6000)
        factura.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable').remove_move_reconcile()
        factura.button_draft()
        self.env['dcasa.web.venta']._barrido()
        self.assertEqual(self.centavos(self.ana), 0)
        factura.button_cancel()
        self.env['dcasa.web.venta']._barrido()
        self.assertEqual(self.centavos(self.ana), 0)

    def test_el_gancho_y_el_barrido_son_idempotentes(self):
        self.version(10.0)
        factura = self.venta_web()
        filas = len(self.libro())
        for _ in range(3):
            self.env['dcasa.web.venta']._registrar(factura)
            factura._invoice_paid_hook()
            self.env['dcasa.web.venta']._barrido()
        self.assertEqual(len(self.libro()), filas)
        self.assertEqual(len(self.venta(factura)), 1)

    def test_una_version_nueva_no_recalcula_lo_ya_anotado(self):
        self.version(10.0)
        factura = self.venta_web()
        self.avanzar('2030-03-06 15:00:00')
        nueva = self.version(50.0, reparto=[(self.ana, 100.0)])
        self.env['dcasa.web.venta']._barrido()
        self.assertEqual(self.venta(factura).porcentaje, 10.0)
        self.assertEqual((self.centavos(self.ana), self.centavos(self.beto)), (6000, 4000))
        otra = self.venta_web(fecha='2030-03-06')
        self.assertEqual(self.venta(otra).reglas_id, nueva)
        self.assertEqual(self.centavos(self.ana, self.venta(otra)), 50000)
        self.assertEqual(self.centavos(self.beto, self.venta(otra)), 0)

    def test_una_devolucion_usa_el_reparto_con_que_nacio_la_venta(self):
        self.version(10.0)
        factura = self.venta_web()
        self.avanzar('2030-03-06 15:00:00')
        self.version(10.0, reparto=[(self.ana, 100.0)])
        self.nota(factura, 500.0, fecha='2030-03-06')
        self.assertEqual((self.centavos(self.ana), self.centavos(self.beto)), (3000, 2000), 'las mismas partes: 60/40')

    # ------------------------------------------------------------------ el libro

    def test_el_libro_no_se_edita_ni_se_borra_ni_con_sudo(self):
        self.version(10.0)
        self.venta_web()
        fila = self.libro()[0]
        with self.assertRaisesRegex(UserError, 'no se edita'):
            fila.sudo().write({'centavos': 1})
        with self.assertRaisesRegex(UserError, 'no se borra'):
            fila.sudo().unlink()
        self.rechaza(lambda: fila.with_user(self.u_nomina).write({'centavos': 1}))
        self.rechaza(lambda: fila.with_user(self.u_gerencia).unlink())

    def test_las_reglas_del_libro(self):
        Libro = self.env['dcasa.web.movimiento']
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            Libro._asentar(self.ana, 'ajuste', 0, self.company, motivo='cero')
        with self.assertRaisesRegex(ValidationError, 'lleva motivo'):
            Libro._asentar(self.ana, 'ajuste', 100, self.company)
        with self.assertRaisesRegex(ValidationError, 'lleva motivo'):
            Libro._asentar(self.ana, 'reverso', -100, self.company)
        fila = Libro._asentar(self.ana, 'ajuste', 500, self.company, motivo='Saldo de prueba')
        contraria = fila._contraria('Se corrige', autor='prueba')
        self.assertEqual((contraria.centavos, contraria.reversa_id), (-500, fila))
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            fila._contraria('Otra vez')
        self.assertEqual(self.saldo(self.ana), 0)

    def test_el_mes_de_panama_se_calcula_en_los_bordes(self):
        Libro = self.env['dcasa.web.movimiento']
        for utc, mes in (('2030-04-01 04:59:59', '2030-03-01'), ('2030-04-01 05:00:00', '2030-04-01'),
                         ('2030-03-01 04:59:00', '2030-02-01')):
            with self.subTest(utc=utc):
                self.avanzar(utc)
                fila = Libro._asentar(self.ana, 'ajuste', 100, self.company, motivo='borde')
                self.assertEqual(str(fila.mes), mes)

    def test_lo_anotado_en_un_mes_se_queda_en_ese_mes_aunque_el_pago_tenga_fecha_atrasada(self):
        self.version(10.0)
        self.avanzar('2030-04-03 15:00:00')
        factura = self.facturar(self.orden(), '2030-03-28')
        self.pagar(factura, '2030-03-28')
        venta = self.venta(factura)
        self.assertEqual(str(venta.fecha_cobro), '2030-03-28')
        self.assertEqual(set(self.libro(venta=venta).mapped('mes')), {datetime(2030, 4, 1).date()},
                         'cobrada el 28/03 pero anotada el 03/04: el libro dice abril')

    # ------------------------------------------------------------------ un error nunca frena un cobro

    def test_un_error_de_la_comision_nunca_frena_el_cobro_y_el_barrido_lo_anota_despues(self):
        self.version(10.0)
        factura = self.facturar(self.orden())
        falla = patch.object(type(self.env['dcasa.web.venta']), '_registrar', side_effect=RuntimeError('falla'))
        with falla, \
                mute_logger('odoo.addons.dcasa_comision_web.models.account_move'):
            self.pagar(factura)
        self.assertEqual(factura.payment_state in ('paid', 'in_payment'), True, 'el cobro quedó hecho')
        self.assertFalse(self.venta(factura))
        self.avanzar('2030-03-05 15:00:00')
        self.env['dcasa.web.venta']._barrido()
        self.assertEqual(len(self.venta(factura)), 1)
        self.assertEqual(self.centavos(self.ana), 6000, 'cobrada el 04 con la versión del 04: cobra')

    def test_un_error_al_restar_una_nota_nunca_impide_publicarla(self):
        self.version(10.0)
        factura = self.venta_web()
        with patch.object(type(self.env['dcasa.web.venta']), '_reconciliar', side_effect=RuntimeError('falla')), \
                mute_logger('odoo.addons.dcasa_comision_web.models.account_move'):
            nota = self.nota(factura, 100.0)
        self.assertEqual(nota.state, 'posted')
        self.env['dcasa.web.venta']._barrido()
        self.assertEqual(self.venta(factura).devuelto_centavos, 10000)

    def test_el_barrido_usa_la_version_del_dia_del_cobro_no_la_de_hoy(self):
        antes = self.facturar(self.orden(), '2030-03-04')
        with patch.object(type(self.env['dcasa.web.venta']), '_registrar', side_effect=RuntimeError('falla')), \
                mute_logger('odoo.addons.dcasa_comision_web.models.account_move'):
            self.pagar(antes, '2030-03-04')
        self.avanzar('2030-03-07 15:00:00')
        self.version(10.0)
        self.avanzar('2030-03-09 15:00:00')
        self.env['dcasa.web.venta']._barrido()
        self.assertEqual(self.venta(antes).estado, 'medida', 'se cobró antes de la primera versión: nunca cobra')
        self.assertFalse(self.libro())

    def test_una_factura_historica_o_sin_pedido_no_se_mide(self):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': '2030-03-04',
            'invoice_line_ids': [Command.create({'name': 'Suelta', 'quantity': 1, 'price_unit': 100.0})]})
        factura.action_post()
        self.pagar(factura)
        self.assertFalse(self.venta(factura))
        web = self.facturar(self.orden())
        web.dcasa_historica = True
        self.pagar(web)
        self.assertFalse(self.venta(web), 'lo cargado del sistema anterior es historia')

    def test_el_barrido_y_el_gancho_comparten_la_misma_verdad_de_pagada_por_completo(self):
        """La definición de «pagada por completo y qué día» es la del bono por meta (``_dias_de_cobro``) y la del Inicio
        (``_dia_completada``): las dos dan el mismo día."""
        Tablero = self.env['dcasa.tablero']
        Bono = self.env['dcasa.nomina.meta.bono']
        normal = self.facturar(self.orden(), '2030-03-04')
        self.pagar(normal, '2030-03-04')
        apartado = self.facturar(self.orden(), '2030-03-04')
        self.pagar(apartado, '2030-03-04', monto=300.0)
        self.pagar(apartado, '2030-03-09')
        parcial = self.facturar(self.orden(), '2030-03-04')
        self.pagar(parcial, '2030-03-05', monto=100.0)
        facturas = normal | apartado | parcial
        dias, _notas = Bono._dias_de_cobro(facturas)
        pagos = Tablero._pagos_de_facturas(facturas)
        del_inicio = {f.id: Tablero._dia_completada(f, pagos) for f in facturas}
        self.assertEqual({f.id: dias.get(f.id) for f in facturas}, del_inicio)
        self.assertEqual(str(dias[apartado.id]), '2030-03-09')
        self.assertNotIn(parcial.id, dias)

    def test_el_estado_de_la_venta_para_filtrar_la_pantalla(self):
        factura = self.venta_web()
        Venta = self.env['dcasa.web.venta']
        self.assertEqual(Venta.search([('estado', '=', 'medida')]), self.venta(factura))
        self.assertFalse(Venta.search([('estado', 'in', ('comisionada', 'revertida'))]))
        self.assertEqual(len(Venta.search([('estado', 'in', ('medida', 'revertida'))])), 1)
        with self.assertRaises(ValueError):
            Venta.search([('estado', '!=', 'medida')])
