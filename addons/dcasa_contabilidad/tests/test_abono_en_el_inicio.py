"""«Con abonos» del Inicio de Gerencia y la regla del primer abono (A3) hablan del mismo abono (tanda 2, 2026-10-18).

El Inicio lee las conciliaciones de todo un periodo de una vez (y corta a una hora), así que no llama factura por
factura a ``account.move._dcasa_estado_abono`` (dcasa_invoice); la regla del primer abono pregunta
``_dcasa_tiene_pagos``. Las tres tienen que decir lo mismo: una factura tiene un abono si tiene un pago aplicado que no
es una nota de crédito (ni una diferencia de cambio), y lo que falta por cobrar es su saldo. Esta prueba las amarra con
los casos de la tienda: sin pago, abono de la mitad o más, primer abono menor que registró Gerencia, pagada completa,
anulada con su nota y nota aplicada más un abono. Vive aquí porque dcasa_contabilidad depende de los dos módulos.
"""
from datetime import date

from odoo.addons.dcasa_interfaz.tests.test_facturado import FacturadoCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestConAbonosEsElAbonoDeLaFactura(FacturadoCommon):

    def test_con_abonos_y_el_primer_abono_dicen_lo_mismo(self):
        dia = date(2025, 5, 12)
        ana = self.vendedora.id
        casos = {}
        _o, casos['sin pago'] = self.vender(dia)
        _o, casos['abono de la mitad o más'] = self.vender(dia)
        self.pagar(casos['abono de la mitad o más'], 600.0, dia)
        _o, casos['primer abono menor, de Gerencia'] = self.vender(dia)
        self.pagar(casos['primer abono menor, de Gerencia'], 300.0, dia, usuario=self.gerencia)
        _o, casos['pagada completa'] = self.vender(dia)
        self.pagar(casos['pagada completa'], 1000.0, dia)
        _o, casos['anulada con su nota'] = self.vender(dia)
        self.nota(casos['anulada con su nota'], dia, conciliar=True)
        _o, casos['nota aplicada y un abono'] = self.vender(dia)
        nota = self.nota(casos['nota aplicada y un abono'], dia, precio=100.0)
        (nota | casos['nota aplicada y un abono']).line_ids.filtered(
            lambda linea: linea.account_id.account_type == 'asset_receivable' and not linea.reconciled).reconcile()
        self.pagar(casos['nota aplicada y un abono'], 500.0, dia)
        con_abonos = self.medir(dia, dia, 'con_abonos', ana)
        en_el_inicio = set(self.ids(con_abonos))
        saldos = 0.0
        for nombre, factura in casos.items():
            with self.subTest(nombre):
                estado = factura._dcasa_estado_abono()
                tiene_abono = bool(estado['inicio'])
                self.assertEqual(factura._dcasa_tiene_pagos(), tiene_abono, 'la regla del primer abono')
                self.assertEqual(factura.id in en_el_inicio, tiene_abono, '«Con abonos» del Inicio')
                if tiene_abono:
                    self.assertEqual(estado['inicio'], dia)
                    saldos += estado['saldo']
        self.assertEqual(
            {nombre for nombre, factura in casos.items() if factura.id in en_el_inicio},
            {'abono de la mitad o más', 'primer abono menor, de Gerencia', 'pagada completa',
             'nota aplicada y un abono'})
        self.assertAlmostEqual(con_abonos['falta_por_cobrar'], saldos, places=2,
                               msg='«Falta por cobrar» es el saldo de esas facturas (_dcasa_estado_abono)')
        self.assertAlmostEqual(saldos, 400.0 + 700.0 + 0.0 + 400.0, places=2)
