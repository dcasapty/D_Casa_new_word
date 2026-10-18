"""Brian y las reglas contables de la gerencia (17 oct 2026): la Vendedora no cobra por Brian, el primer abono es al
menos la mitad (si no, Gerencia) y el vencimiento del abono sale de ``_dcasa_estado_abono`` (30 días continuos)."""
from contextlib import contextmanager
from datetime import date, timedelta

from odoo import Command, fields
from odoo.addons.dcasa_base.tests.test_roles import crear_usuario
from odoo.addons.dcasa_brian.models.registro import BrianError
from odoo.tests import TransactionCase, tagged


@contextmanager
def negado(prueba, excepcion, texto):
    """``assertRaisesRegex`` con el savepoint de Odoo (``assertRaises``): lo que se escribió antes del error se deshace,
    como en una llamada real."""
    with prueba.assertRaises(excepcion) as contexto:
        yield contexto
    prueba.assertRegex(str(contexto.exception), texto)


MENSAJE = 'El primer abono debe ser de al menos la mitad: $100.00. Si es menos, lo registra Gerencia.'


@tagged('post_install', '-at_install')
class TestBrianReglasGerencia(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.vendedora = crear_usuario(env, 'brg_vendedora', 'dcasa_base.group_vendedora')
        cls.caja = crear_usuario(env, 'brg_caja', 'dcasa_base.group_caja')
        cls.gerencia = crear_usuario(env, 'brg_gerencia', 'dcasa_base.group_gerencia')
        cls.cliente = env['res.partner'].create({
            'name': 'Brianzeta Abono', 'phone': '+507 6555-0401', 'email': 'brianzeta.abono@example.com'})
        cls.mueble = env['product.product'].create({
            'name': 'Brianzeta Comedor', 'type': 'consu', 'list_price': 200.0, 'taxes_id': [Command.clear()]})

    def _factura(self):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_user_id': self.vendedora.id,
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 200.0,
                                                 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        return factura

    def ejecutar(self, usuario, nombre, argumentos=None):
        return self.env['brian.herramientas'].with_user(usuario).ejecutar(nombre, argumentos or {})

    def pagar(self, usuario, factura, monto, forma_pago='Efectivo'):
        respuesta = self.ejecutar(usuario, 'registrar_pago', {
            'factura': factura.name, 'monto': monto, 'forma_pago': forma_pago})
        self.assertTrue(respuesta.get('requiere_confirmacion'), respuesta)
        return self.env['brian.herramientas'].with_user(usuario).confirmar(respuesta['accion_id'])

    def test_la_vendedora_no_cobra_por_brian(self):
        factura = self._factura()
        catalogo = {h['name'] for h in self.env['brian.herramientas'].with_user(self.vendedora).catalogo()}
        self.assertNotIn('registrar_pago', catalogo)
        self.assertIn('ver_factura', catalogo, 'sigue viendo sus facturas')
        respuesta = self.ejecutar(self.vendedora, 'registrar_pago', {'factura': factura.name, 'monto': 200.0})
        self.assertFalse(respuesta['ok'])
        self.assertIn('no tienes permiso', respuesta['error'])
        # Aunque alguien llamara la herramienta por dentro, la herramienta (y el servidor) se lo niegan.
        with negado(self, BrianError, 'Los cobros los registra Caja'):
            self.env['brian.herramientas'].with_user(self.vendedora)._h_registrar_pago(factura.name, 200.0)
        self.assertEqual(factura.payment_state, 'not_paid')
        # Y Brian sabe decírselo.
        conversacion = self.env['brian.conversacion'].with_user(self.vendedora).create({})
        self.assertIn('los cobros los registra Caja', conversacion._sistema({})[1])
        self.assertIn('solo de Gerencia', conversacion._sistema({})[1])

    def test_caja_cobra_por_brian_y_el_primer_abono_bajo_lo_niega(self):
        factura = self._factura()
        self.assertIn('registrar_pago',
                      {h['name'] for h in self.env['brian.herramientas'].with_user(self.caja).catalogo()})
        respuesta = self.pagar(self.caja, factura, 98.0)
        self.assertFalse(respuesta['ok'])
        self.assertEqual(respuesta['error'], MENSAJE)
        self.assertEqual(factura.payment_state, 'not_paid')
        self.assertTrue(self.pagar(self.caja, factura, 100.0, forma_pago='Tafi')['ok'])
        self.assertEqual(factura.amount_residual, 100.0)
        self.assertTrue(self.pagar(self.caja, factura, 5.0)['ok'], 'los siguientes son libres')
        conversacion = self.env['brian.conversacion'].with_user(self.caja).create({})
        self.assertNotIn('no registra cobros', conversacion._sistema({})[1])

    def test_gerencia_registra_el_primer_abono_bajo(self):
        factura = self._factura()
        self.assertTrue(self.pagar(self.gerencia, factura, 98.0)['ok'])
        self.assertEqual(factura.amount_residual, 102.0)

    def test_el_vencimiento_del_abono_sale_de_la_misma_funcion(self):
        factura = self._factura()
        self.pagar(self.caja, factura, 120.0)
        estado = factura._dcasa_estado_abono()
        self.assertEqual(estado['vence'], estado['inicio'] + timedelta(days=30))
        datos = self.ejecutar(self.caja, 'ver_factura', {'factura': factura.name})['datos']
        self.assertEqual(datos['abono'], {
            'inicio': estado['inicio'].strftime('%d/%m/%Y'), 'pagado': '$120.00', 'saldo': '$80.00',
            'vence': estado['vence'].strftime('%d/%m/%Y'), 'vencido': False})
        fila = next(f for f in self.ejecutar(self.caja, 'facturas_pendientes')['datos']['facturas']
                    if f['factura'] == factura.name)
        self.assertEqual(fila['abono']['vence'], estado['vence'].strftime('%d/%m/%Y'))
        self.assertIsInstance(estado['inicio'], date)
