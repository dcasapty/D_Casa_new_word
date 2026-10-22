"""Mermas, daños, muestras y regalos (F6): código, costo, cuenta propia en el estado de resultados, reclamo al
proveedor y el aviso cuando el mes pasa del 0.5 % de lo comprado."""
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .comun import BodegaComun


@tagged('post_install', '-at_install')
class TestMermas(BodegaComun):

    def test_la_vendedora_reporta_en_borrador_pero_no_da_de_baja(self):
        scrap = self._merma(usuario=self.vendedora, validar=False)
        self.assertEqual(scrap.state, 'draft')
        with self.assertRaisesRegex(AccessError, 'Solo Gerencia'):
            scrap.with_user(self.vendedora).action_validate()
        with self.assertRaises(AccessError):
            scrap.with_user(self.vendedora).do_scrap()
        self.assertEqual(self.producto.qty_available, 10)

    def test_gerencia_da_de_baja_con_su_costo_y_queda_en_la_bitacora(self):
        scrap = self._merma(cantidad=2, dcasa_nota='Llegó con la pata quebrada')
        self.assertEqual(scrap.state, 'done')
        self.assertEqual(self.producto.qty_available, 8)
        self.assertEqual((scrap.dcasa_costo_unitario, scrap.dcasa_costo), (200.0, 400.0))
        self.assertEqual(scrap.dcasa_proveedor_id, self.proveedor)          # el primer proveedor del producto
        self.assertEqual(scrap.dcasa_reclamo, 'por_reclamar')
        fila = self.env['dcasa.bitacora.bodega'].search([('scrap_id', '=', scrap.id)])
        self.assertEqual((fila.antes, fila.despues, fila.diferencia, fila.origen), (10.0, 8.0, -2.0, 'merma'))
        self.assertIn('pata quebrada', fila.motivo)
        self.assertEqual(fila.usuario_id, self.gerencia)

    def test_sin_codigo_o_sin_costo_no_se_da_de_baja(self):
        sin_codigo = self.env['stock.scrap'].with_user(self.gerencia).create({
            'product_id': self.producto.id, 'scrap_qty': 1, 'location_id': self.ubicacion.id})
        with self.assertRaisesRegex(UserError, 'código'):
            sin_codigo.action_validate()
        with self.assertRaisesRegex(UserError, 'no tiene costo'):
            self._merma(producto=self.sin_costo)
        self.assertEqual(self.sin_costo.qty_available, 3)

    def test_una_muestra_o_un_regalo_no_se_reclaman(self):
        self.assertEqual(self._merma(motivo='regalo').dcasa_reclamo, 'no_aplica')
        self.assertEqual(self._merma(motivo='muestra').dcasa_reclamo, 'no_aplica')

    # ------------------------------------------------------------------
    # Contabilidad: la cuenta la elige la contadora
    # ------------------------------------------------------------------

    def test_sin_cuentas_queda_pendiente_y_la_pantalla_lo_dice(self):
        scrap = self._merma()
        self.assertEqual(scrap.dcasa_contabilidad, 'falta_cuenta')
        self.assertFalse(scrap.dcasa_asiento_id)
        resumen = self.env['dcasa.merma.resumen'].with_user(self.gerencia).create({})
        self.assertIn('Cuenta de las mermas', resumen.faltan_cuentas)
        self.assertEqual(resumen.pendientes, 1)

    def test_con_cuentas_va_a_su_cuenta_y_sale_en_el_estado_de_resultados(self):
        self._con_cuentas()
        scrap = self._merma(cantidad=3)
        self.assertEqual(scrap.dcasa_contabilidad, 'hecho')
        asiento = scrap.dcasa_asiento_id
        self.assertEqual(asiento.state, 'posted')
        self.assertEqual(asiento.journal_id, self.diario)
        gasto = asiento.line_ids.filtered(lambda ln: ln.account_id == self.c_mermas)
        contra = asiento.line_ids.filtered(lambda ln: ln.account_id == self.c_contra)
        self.assertEqual((gasto.debit, contra.credit), (600.0, 600.0))
        self.assertEqual(gasto.partner_id, self.proveedor)
        hoy = fields.Date.context_today(scrap)
        reporte = self.env['dcasa.reporte.contable'].estado_resultados(hoy.replace(day=1), hoy)
        filas = [f for s in reporte['secciones'] for f in s['filas']]
        propia = [f for f in filas if f['id'] == self.c_mermas.id]
        self.assertEqual(len(propia), 1, 'las mermas son su propia línea del estado de resultados')
        self.assertEqual(propia[0]['monto'], 600.0)

    def test_las_pendientes_se_contabilizan_despues(self):
        scrap = self._merma()
        self._con_cuentas()
        aviso = self.config.with_user(self.gerencia).action_contabilizar_pendientes()
        self.assertIn('1 merma', aviso['params']['message'])
        self.assertEqual(scrap.dcasa_contabilidad, 'hecho')
        self.assertTrue(scrap.dcasa_asiento_id)
        with self.assertRaises(AccessError):
            self.config.with_user(self.vendedora).action_contabilizar_pendientes()

    def test_solo_gerencia_cambia_las_cuentas(self):
        with self.assertRaises(AccessError):
            self.config.with_user(self.vendedora).write({'mermas_tope_pct': 9})
        self.config.with_user(self.gerencia).write({'mermas_cuenta_gasto_id': self.c_mermas.id})
        self.assertEqual(self.config.mermas_cuenta_gasto_id, self.c_mermas)

    def test_el_tope_de_fabrica_es_el_de_la_gerencia(self):
        self.assertEqual(self.config.mermas_tope_pct, 0.5)

    # ------------------------------------------------------------------
    # El mes contra lo comprado (0.5 %)
    # ------------------------------------------------------------------

    def test_el_mes_contra_lo_comprado_y_el_aviso_del_tope(self):
        recepcion = self._recibir(500, 200.0)
        comprado = sum(recepcion.move_ids.mapped('value'))
        self.assertTrue(comprado)
        Scrap = self.env['stock.scrap']
        hoy = fields.Date.context_today(Scrap)
        resumen = Scrap._dcasa_resumen_mes(self.env.company, hoy)
        self.assertEqual((resumen['total'], resumen['compras'], resumen['pasa']), (0.0, comprado, False))
        self._merma(cantidad=1)        # 200 de 100,000 = 0.2 %: dentro del tope
        resumen = Scrap._dcasa_resumen_mes(self.env.company, hoy)
        self.assertEqual(resumen['total'], 200.0)
        self.assertFalse(resumen['pasa'])
        scrap = self._merma(cantidad=2, motivo='merma')    # 600 = 0.6 %: pasa
        resumen = Scrap._dcasa_resumen_mes(self.env.company, hoy)
        self.assertTrue(resumen['pasa'])
        self.assertEqual(resumen['por_motivo']['merma'], 400.0)
        self.assertEqual(resumen['por_motivo']['dano'], 200.0)
        self.assertTrue(any('pasan del 0.5' in m.body for m in scrap.message_ids), 'la merma que lo pasa lo dice')
        # La pantalla del mes y el Inicio de Gerencia lo dicen
        pantalla = self.env['dcasa.merma.resumen'].with_user(self.gerencia).create({})
        self.assertTrue(pantalla.pasa)
        self.assertEqual(pantalla.porcentaje, round(60000.0 / comprado, 2))
        self.assertIn('o_dcasa_merma_pasa', pantalla.tabla_anio)
        self.assertIn('PROVEEDOR DE PRUEBA BODEGA', pantalla.tabla_proveedores)
        datos = {'atencion': [], 've_utilidad': False}
        self.env['dcasa.tablero'].with_user(self.gerencia)._atencion(datos, hoy)
        self.assertIn('mermas_tope', [a['clave'] for a in datos['atencion']])
        datos = {'atencion': [], 've_utilidad': False}
        self.env['dcasa.tablero'].with_user(self.vendedora)._atencion(datos, hoy)
        self.assertNotIn('mermas_tope', [a['clave'] for a in datos['atencion']])

    def test_sin_compras_en_el_mes_cualquier_merma_pasa(self):
        self._merma()
        resumen = self.env['stock.scrap']._dcasa_resumen_mes(self.env.company)
        self.assertTrue(resumen['pasa'])
        self.assertIsNone(resumen['pct'])

    # ------------------------------------------------------------------
    # Reclamo al proveedor
    # ------------------------------------------------------------------

    def test_reclamo_al_proveedor_en_pdf_y_marcar_reclamadas(self):
        dano = self._merma(cantidad=1, dcasa_nota='Rayado de fábrica')
        self._merma(cantidad=1, motivo='regalo')
        reclamo = self.env['dcasa.merma.reclamo'].with_user(self.gerencia).create({'proveedor_id': self.proveedor.id})
        self.assertEqual(reclamo.merma_ids, dano, 'solo lo reclamable de ese proveedor')
        self.assertEqual(reclamo.total, 200.0)
        accion = reclamo.action_imprimir()
        self.assertEqual(accion['report_name'], 'dcasa_existencias.reclamo_pdf')
        html, _tipo = self.env['ir.actions.report']._render_qweb_html('dcasa_existencias.reclamo_pdf', reclamo.ids)
        html = html.decode()
        for texto in ('Mercancía dañada o perdida', 'PROVEEDOR DE PRUEBA BODEGA', 'SOFA DE PRUEBA BODEGA',
                      'Rayado de fábrica', 'Total a costo'):
            self.assertIn(texto, html)
        reclamo.action_marcar_reclamadas()
        self.assertEqual(dano.dcasa_reclamo, 'reclamado')
        self.assertFalse(self.env['dcasa.merma.reclamo'].with_user(self.gerencia).create(
            {'proveedor_id': self.proveedor.id}).merma_ids, 'ya no queda nada por reclamar')
        with self.assertRaises(AccessError):
            self.env['dcasa.merma.reclamo'].with_user(self.vendedora).create({'proveedor_id': self.proveedor.id})

    def test_un_asiento_que_falla_no_hace_fallar_la_merma(self):
        self._con_cuentas()
        with patch('odoo.addons.account.models.account_move.AccountMove.action_post',
                   side_effect=UserError('Mes cerrado (prueba)')):
            scrap = self._merma()
        self.assertEqual(scrap.state, 'done')
        self.assertEqual(scrap.dcasa_contabilidad, 'error')
        self.assertTrue(any('Mes cerrado' in m.body for m in scrap.message_ids))
