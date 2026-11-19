"""Datos comunes de las pruebas de la comisión del sitio web.

Todas las cifras son de PRUEBA y las crean las propias pruebas: el módulo no trae ninguna (ni porcentaje, ni tarifa, ni
reparto). Los pedidos «de la web» llevan ``website_id`` (nacen como venta online); los de la tienda no.
"""
from datetime import timedelta

from odoo import Command, fields
from odoo.addons.dcasa_nomina.tests.common import NominaCommon
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user

DIA = '2030-03-04'          # un lunes: la semana y la quincena arrancan con él en las pruebas de tarifa
ANTES = '2030-03-01'


class ComisionCommon(NominaCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.itbms = cls.company.account_sale_tax_id
        cls.website = cls.env['website'].search([], limit=1)
        Producto = cls.env['product.product']
        cls.mueble = Producto.create({'name': 'MUEBLE DE PRUEBA COMISION', 'type': 'consu', 'invoice_policy': 'order',
                                      'list_price': 1000.0, 'taxes_id': [Command.set(cls.itbms.ids)]})
        cls.premio = Producto.create({'name': 'PREMIO DE PRUEBA COMISION', 'type': 'service',
                                      'invoice_policy': 'order', 'list_price': 0.0,
                                      'taxes_id': [Command.set(cls.itbms.ids)]})
        cls.envio = Producto.create({'name': 'ENVIO DE PRUEBA COMISION', 'type': 'service', 'invoice_policy': 'order',
                                     'list_price': 0.0, 'default_code': 'FLETE', 'taxes_id': [Command.set([])]})
        cls.cliente = cls.env['res.partner'].create({
            'name': 'Cliente comisión web', 'phone': '+507 6555-0301', 'email': 'cliente.comision.web@example.com'})
        cls.u_gerencia = new_test_user(cls.env, login='com_gerencia', name='Gerencia Prueba',
                                       groups='base.group_user,dcasa_base.group_gerencia')
        cls.u_nomina = new_test_user(cls.env, login='com_nomina', name='Nómina Prueba',
                                     groups='base.group_user,dcasa_nomina.group_nomina')
        cls.u_vendedora = new_test_user(cls.env, login='com_vendedora', name='Vendedora Comisión',
                                        groups='base.group_user,dcasa_base.group_vendedora')
        cls.u_tecnico = new_test_user(cls.env, login='com_tecnico', name='Técnico Comisión',
                                      groups='base.group_user,base.group_system')
        cls.u_caja = new_test_user(cls.env, login='com_caja', name='Caja Comisión',
                                   groups='base.group_user,dcasa_base.group_caja')
        cls.u_ana = new_test_user(cls.env, login='com_ana', name='Ana Reparto',
                                  groups='base.group_user,dcasa_nomina.group_nomina')
        cls.ana.user_id = cls.u_ana
        cls.empleado_nomina = cls._empleado('Quien aprueba', 1200, '2029-01-01', user_id=cls.u_nomina.id)

    def rechaza(self, funcion):
        """La operación la rechaza Odoo (``UserError`` o ``AccessError``), sin dejar nada a medias."""
        try:
            with self.env.cr.savepoint():
                funcion()
        except (UserError, AccessError):
            return
        self.fail('Se esperaba que Odoo rechazara la operación y la dejó pasar.')

    # ------------------------------------------------------------------
    # Reglas
    # ------------------------------------------------------------------

    def version(self, porcentaje=10.0, reparto=None, tarifa=0.0, **extra):
        """Guarda una versión de las reglas que rige ahora (cifras de PRUEBA). ``reparto``: [(empleado, %)]."""
        reparto = reparto if reparto is not None else ([(self.ana, 60.0), (self.beto, 40.0)]
                                                       if porcentaje or tarifa else [])
        return self.env['dcasa.web.reglas'].create({
            'company_id': self.company.id, 'porcentaje': porcentaje, 'tarifa_fija': tarifa, **extra,
            'reparto_ids': [Command.create({'empleado_id': e.id, 'porcentaje': p}) for e, p in reparto]})

    # ------------------------------------------------------------------
    # Pedidos, facturas y pagos
    # ------------------------------------------------------------------

    def orden(self, web=True, lineas=None, cliente=None, vendedora=None, confirmar=True, pago='a_mano', **extra):
        """Un pedido confirmado. ``lineas``: [(producto, precio, cantidad, extras)]; por defecto un mueble de 1,000.
        ``web=True`` lo hace nacer en la tienda en línea."""
        lineas = lineas or [(self.mueble, 1000.0, 1, {})]
        valores = {
            'partner_id': (cliente or self.cliente).id, 'company_id': self.company.id,
            'order_line': [Command.create({'product_id': p.id, 'product_uom_qty': q, 'price_unit': precio, **plus})
                           for p, precio, q, plus in lineas], **extra}
        if web:
            valores['website_id'] = self.website.id
        if vendedora:
            valores['user_id'] = vendedora.id
        orden = self.env['sale.order'].with_context(mail_notrack=True).create(valores)
        if web and pago == 'a_mano':
            self.transaccion(orden, 'a_mano')
        if confirmar:
            orden.with_context(mail_notrack=True).action_confirm()
        return orden

    def transaccion(self, orden, como):
        """El intento de pago de un pedido de la web: ``a_mano`` (transferencia o Yappy que registra Caja),
        ``en_tienda`` (el apartado) o ``pasarela`` (una pasarela de pago)."""
        Proveedor = self.env['payment.provider'].sudo()
        if como == 'pasarela':
            proveedor = Proveedor.search([('code', '=', 'none'), ('name', '=', 'Pasarela de prueba')], limit=1) \
                or Proveedor.create({'name': 'Pasarela de prueba', 'code': 'none', 'state': 'test'})
        elif como == 'en_tienda':
            proveedor = self.env.ref('delivery.payment_provider_cod')
        else:
            proveedor = self.env.ref('payment.payment_provider_transfer')
        return self.env['payment.transaction'].sudo().create({
            'provider_id': proveedor.id, 'amount': 1070.0, 'currency_id': self.company.currency_id.id,
            'partner_id': orden.partner_id.id, 'reference': f'PRUEBA-{orden.name}-{como}',
            'payment_method_id': self.env['payment.method'].search([], limit=1).id,
            'sale_order_ids': [Command.set(orden.ids)], 'state': 'done'})

    def facturar(self, orden, fecha=DIA):
        factura = orden._create_invoices()
        factura.invoice_date = fecha
        factura.action_post()
        return factura

    def pagar(self, factura, fecha=DIA, monto=None):
        valores = {'payment_date': fecha}
        if monto:
            valores['amount'] = monto
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create(valores)._create_payments()

    def venta_web(self, fecha=DIA, pagar=True, **kw):
        """Un pedido de la web facturado (y pagado). Devuelve la factura."""
        factura = self.facturar(self.orden(**kw), fecha)
        if pagar:
            self.pagar(factura, fecha)
        return factura

    def nota(self, factura, monto, fecha=DIA, enlazada=True):
        """Nota de crédito de ``monto`` SIN ITBMS (publicada)."""
        valores = {'move_type': 'out_refund', 'partner_id': factura.partner_id.id, 'invoice_date': fecha,
                   'invoice_line_ids': [Command.create({'name': 'Devolución', 'quantity': 1, 'price_unit': monto,
                                                        'tax_ids': [Command.set(self.itbms.ids)]})]}
        if enlazada:
            valores['reversed_entry_id'] = factura.id
        nota = self.env['account.move'].create(valores)
        nota.action_post()
        return nota

    def venta(self, factura):
        return self.env['dcasa.web.venta'].search([('move_id', '=', factura.id)])

    def libro(self, empleado=None, venta=None, tipo=None):
        dominio = ([('empleado_id', '=', empleado.id)] if empleado else []) + (
            [('venta_id', '=', venta.id)] if venta else []) + ([('tipo', '=', tipo)] if tipo else [])
        return self.env['dcasa.web.movimiento'].search(dominio, order='id')

    def saldo(self, empleado, concepto='comision', hasta=None):
        saldos = self.env['dcasa.web.movimiento']._saldos(empleado, hasta=hasta)
        return saldos.get((empleado.id, concepto), 0)

    def hablar(self, cliente, autor, hace_dias=1, id_externo='50761999001'):
        """Un mensaje en el chat de Juan con ``cliente`` (``bot`` o ``vendedora``), de hace ``hace_dias``."""
        ts = fields.Datetime.now() - timedelta(days=hace_dias)
        conv = self.env['dcasa.conversacion']._registrar_mensaje({
            'canal': 'whatsapp_qr', 'id_externo': id_externo, 'id_mensaje': f'wamid.com.{id_externo}.{autor}.{ts}',
            'direccion': 'entrante' if autor == 'cliente' else 'saliente', 'autor': autor, 'texto': 'Hola',
            'ts': ts, 'nombre': None, 'celular': None, 'adjuntos': []})[0]
        conv.sudo().partner_id = cliente
        return conv
