"""Brian y lo nuevo de bodega (mermas, bitácora), nómina (adelantos, comprobantes) y el ZIP de comprobantes.

Las de bodega y nómina viven en módulos que ``dcasa_brian`` no exige: si no están instalados, la prueba se salta (en el
CI se instala todo)."""
from datetime import date
from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestBodegaNominaBrian(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        Usuarios = cls.env['res.users'].with_context(no_reset_password=True)

        def usuario(login, grupos):
            return Usuarios.create({'name': login.replace('_', ' ').title(), 'login': login,
                                    'group_ids': [Command.set([ref(g).id for g in ('base.group_user', *grupos)])]})
        cls.gerencia = usuario('brian_bn_gerencia', ('dcasa_base.group_gerencia',))
        cls.vendedora = usuario('brian_bn_vendedora', ('dcasa_base.group_vendedora',))
        cls.producto = cls.env['product.product'].create({
            'name': 'BRIANZETA BAUL PRUEBA', 'default_code': 'BRN-BAUL', 'is_storable': True, 'standard_price': 80.0})
        almacen = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.env['stock.quant']._update_available_quantity(cls.producto, almacen.lot_stock_id, 5)

    def ejecutar(self, usuario, nombre, argumentos=None):
        return self.env['brian.herramientas'].with_user(usuario).ejecutar(nombre, argumentos or {})

    def confirmar(self, usuario, respuesta):
        self.assertTrue(respuesta.get('requiere_confirmacion'), respuesta)
        return self.env['brian.herramientas'].with_user(usuario).confirmar(respuesta['accion_id'])

    def ok(self, respuesta):
        self.assertTrue(respuesta.get('ok'), respuesta)
        return respuesta['datos']

    def _requiere(self, modelo):
        if modelo not in self.env:
            self.skipTest(f'{modelo} no está instalado en esta base')

    # ------------------------------------------------------------------
    # Bodega
    # ------------------------------------------------------------------

    def test_registrar_una_merma_pide_confirmacion_y_queda_con_su_costo(self):
        self._requiere('dcasa.bitacora.bodega')
        propuesta = self.ejecutar(self.gerencia, 'registrar_merma', {
            'producto': 'BRN-BAUL', 'cantidad': 2, 'codigo': 'daño', 'que_paso': 'Se mojó en la bodega'})
        self.assertEqual(self.producto.qty_available, 5, 'nada cambia antes del clic')
        hecho = self.ok(self.confirmar(self.gerencia, propuesta))
        self.assertIn('$160.00', hecho['mensaje'])
        self.assertEqual(self.producto.qty_available, 3)
        self.assertIn('cuenta contable', hecho.get('aviso', ''))
        resumen = self.ok(self.ejecutar(self.gerencia, 'resumen_de_mermas'))
        self.assertEqual(resumen['por_codigo']['dano'], '$160.00')
        self.assertEqual(resumen['tope_de_la_gerencia'], '0.5 %')
        bitacora = self.ok(self.ejecutar(self.gerencia, 'bitacora_de_bodega', {'producto': 'BRN-BAUL'}))
        self.assertEqual(bitacora['ajustes'][0]['antes'], 5)
        self.assertEqual(bitacora['ajustes'][0]['despues'], 3)
        self.assertIn('Se mojó', bitacora['ajustes'][0]['motivo'])

    def test_la_vendedora_no_usa_las_herramientas_de_bodega(self):
        self._requiere('dcasa.bitacora.bodega')
        nombres = {h['name'] for h in self.env['brian.herramientas'].with_user(self.vendedora).catalogo()}
        self.assertFalse({'registrar_merma', 'resumen_de_mermas', 'bitacora_de_bodega'} & nombres)

    def test_ajustar_existencias_exige_el_motivo_y_lo_anota(self):
        sin_motivo = self.ejecutar(self.gerencia, 'ajustar_existencias', {'producto': 'BRN-BAUL', 'cantidad': 4})
        self.assertFalse(sin_motivo['ok'])
        self.assertIn('motivo', sin_motivo['error'])
        self.ok(self.confirmar(self.gerencia, self.ejecutar(self.gerencia, 'ajustar_existencias', {
            'producto': 'BRN-BAUL', 'cantidad': 4, 'motivo': 'conteo de prueba'})))
        self.assertEqual(self.producto.qty_available, 4)
        if 'dcasa.bitacora.bodega' in self.env:
            fila = self.env['dcasa.bitacora.bodega'].search([('producto_id', '=', self.producto.id)])
            self.assertEqual((fila.motivo, fila.origen, fila.usuario_id), ('conteo de prueba', 'brian', self.gerencia))

    # ------------------------------------------------------------------
    # Nómina
    # ------------------------------------------------------------------

    def test_registrar_y_ver_un_adelanto(self):
        self._requiere('dcasa.nomina.prestamo')
        empleado = self.env['hr.employee'].create({'name': 'Brianzeta Colaboradora Prueba', 'wage': 900})
        hecho = self.ok(self.ejecutar(self.gerencia, 'registrar_adelanto', {
            'colaborador': 'Brianzeta Colaboradora', 'monto': 150, 'quincenas': 3}))
        self.assertIn('$50.00 cada una', hecho['mensaje'])
        self.assertIn('por autorizar', hecho['mensaje'])
        lista = self.ok(self.ejecutar(self.gerencia, 'adelantos_y_prestamos', {'colaborador': empleado.name}))
        self.assertEqual(lista['adelantos'][0]['monto'], '$150.00')
        self.assertEqual(lista['adelantos'][0]['estado'], 'Por autorizar')
        no_puede = self.ejecutar(self.vendedora, 'adelantos_y_prestamos', {})
        self.assertFalse(no_puede['ok'])

    def test_enviar_comprobantes_con_los_correos_apagados_lo_dice(self):
        self._requiere('dcasa.nomina.planilla')
        planilla = self.env['dcasa.nomina.planilla'].create({
            'tipo': 'quincenal', 'fecha_desde': date(2031, 1, 1), 'fecha_hasta': date(2031, 1, 15),
            'fecha_pago': date(2031, 1, 15)})
        planilla.sudo().estado = 'confirmada'
        with patch('odoo.addons.dcasa_nomina.models.comprobante.DcasaNominaLinea._motivo_correo_apagado',
                   return_value='Los correos están apagados (prueba).'):
            respuesta = self.confirmar(self.gerencia, self.ejecutar(self.gerencia, 'enviar_comprobantes_de_pago',
                                                                    {'planilla': 'la última'}))
        self.assertFalse(respuesta['ok'])
        self.assertIn('apagados', respuesta['error'])

    # ------------------------------------------------------------------
    # ZIP de comprobantes
    # ------------------------------------------------------------------

    def test_preparar_el_zip_de_comprobantes(self):
        sin_nada = self.ejecutar(self.gerencia, 'preparar_zip_de_comprobantes', {'anio': 1990})
        self.assertFalse(sin_nada['ok'])
        self.assertIn('No hay comprobantes', sin_nada['error'])
        self.assertFalse(self.env['dcasa.comprobantes.paquete'].search([('anio', '=', 1990)]))
        no_puede = self.ejecutar(self.vendedora, 'preparar_zip_de_comprobantes', {'anio': 2026})
        self.assertFalse(no_puede['ok'])
