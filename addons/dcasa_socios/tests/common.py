import copy
import os
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase

from ..models import reglas as R

# Las reglas de VENDEDORES para probar el código (no son las cifras reales: esas viven en puntos.json y las decide
# la dueña). Cada prueba las cambia en ``self.reglas['vendedores']``.
VENDEDORES_DE_PRUEBA = {
    'programaActivo': True,
    'comision': {'puntosPorDolarNeto': 4, 'baseDeCalculo': 'neto', 'compraMinimaCentavos': 2000,
                 'pagaEn': 'cada-compra', 'escalones': [], 'diasParaEscalon': 90},
    'vinculacion': {'meses': 0},
    'patrocinio': {'puntosPorDolarNetoDelDirecto': 0.4, 'topeDeDirectos': 3},
    'retencion': {'dias': 30},
    'techos': {'totalPorVentaPorcentajeDelNeto': 8, 'porVendedorAlMesPuntos': None,
               'patrocinioPorPatrocinadorAlMesPuntos': None},
    'canje': {'puntosMinimosParaCanjear': 500, 'vigenciaDelCodigoHoras': 72, 'canjesPorVendedorAlMes': None,
              'externosHabilitado': True},
    'bloquearComprasDentroDeLaColmena': True,
}


class SociosCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.company = cls.env.ref('base.main_company')
        # El ITBMS de venta por defecto de la empresa: se suma al precio, como en la factura real.
        cls.itbms = cls.company.account_sale_tax_id
        cls.producto = cls.env['product.product'].create({
            'name': 'CAMA QUEEN GREY CON ESTANTES', 'type': 'consu', 'invoice_policy': 'order',
            'list_price': 100.0, 'taxes_id': [(6, 0, cls.itbms.ids)],
        })
        Partner = cls.env['res.partner']
        # Con celular y correo: sin ellos la vendedora no confirma la venta (dcasa_contactos, 2026-10-16).
        cls.padrino = Partner.create({'name': 'Ana Pérez', 'phone': '+507 6000-0001', 'email': 'ana.perez@example.com'})
        cls.padrino._dcasa_asegurar_ficha()
        cls.cliente = Partner.create({'name': 'Eric Gómez', 'phone': '6000-0002', 'email': 'eric.gomez@example.com'})

    def setUp(self):
        super().setUp()
        patcher = patch.dict(os.environ, {'DCASA_PIN_PEPPER': 'pimienta-de-prueba'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def reglas_con(self, **cambios):
        """Reglas reales con algunos valores cambiados (p. ej. topes más bajos)."""
        reglas = R.cargar_reglas()
        for ruta, valor in cambios.items():
            seccion, clave = ruta.split('__')
            reglas[seccion][clave] = valor
        return patch('odoo.addons.dcasa_socios.models.reglas.cargar_reglas', return_value=reglas)

    def factura(self, partner=None, precio=100.0, pagar=True, vendedor=None, vendedora=None):
        """Factura de cliente con ITBMS; pagada por defecto. Con ``vendedor``, el código va en la venta. Con
        ``vendedora`` (un usuario), la factura es suya («Vendedor» de la factura, ``invoice_user_id``)."""
        valores = {
            'move_type': 'out_invoice',
            'partner_id': (partner or self.cliente).id,
            'invoice_date': fields.Date.today(),
            'dcasa_vendedor_id': vendedor.id if vendedor else False,
            'invoice_line_ids': [(0, 0, {'product_id': self.producto.id, 'quantity': 1, 'price_unit': precio})],
        }
        if vendedora:
            valores['invoice_user_id'] = vendedora.id
        factura = self.env['account.move'].create(valores)
        factura.action_post()
        if pagar:
            self.pagar(factura)
        return factura

    def pagar(self, factura):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids,
        ).create({'payment_date': factura.invoice_date})._create_payments()

    def activar_vendedores(self, **cambios):
        """Enciende el programa de vendedores con las reglas de prueba (``seccion__clave=valor`` para variarlas).
        Devuelve el diccionario de reglas: la prueba lo puede seguir cambiando."""
        reglas = R.cargar_reglas()
        reglas['vendedores'] = copy.deepcopy(VENDEDORES_DE_PRUEBA)
        for ruta, valor in cambios.items():
            if '__' in ruta:
                seccion, clave = ruta.split('__')
                reglas['vendedores'][seccion][clave] = valor
            else:
                reglas['vendedores'][ruta] = valor
        patcher = patch('odoo.addons.dcasa_socios.models.reglas.cargar_reglas', return_value=reglas)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.reglas = reglas
        return reglas

    def vendedor(self, nombre, cedula, celular, tipo='externo', patrocinador=None, correo=None):
        """Una persona afiliada como vendedor (con cédula, celular y términos aceptados)."""
        persona = self.env['res.partner'].create({
            'name': nombre, 'vat': cedula, 'phone': celular, 'email': correo or False})
        persona._dcasa_afiliar_vendedor(tipo, patrocinador, autor='prueba', acepto_terminos=True)
        return persona

    def comisiones(self, partner=None, tipo=None):
        dominio = ([('partner_id', '=', partner.id)] if partner else []) + ([('tipo', '=', tipo)] if tipo else [])
        return self.env['dcasa.vend.comision'].search(dominio)

    def movimientos(self, partner, tipo=None):
        dominio = [('partner_id', '=', partner.id)] + ([('tipo', '=', tipo)] if tipo else [])
        return self.env['dcasa.movimiento'].search(dominio)
