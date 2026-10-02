from datetime import date

from lxml import etree

from odoo.addons.dcasa_fe_pa.models import catalogos as C
from odoo.addons.dcasa_fe_pa.models import generador as G
from odoo.tests import BaseCase, tagged

# CUFE reales publicados por el portal de consultas de la DGI (dgi-fep.mef.gob.pa).
CUFE_REAL_1 = 'FE01200000045400-2-299934-0900002022050500000000389990117686690628'
CUFE_REAL_2 = 'FE0120000000138-289-35920-0489172020090301000861280010117979798825'


def datos_minimos(**cambios):
    datos = {
        'cufe': C.cufe('01', '2', '155779346-2-2026', '7', '0000', date(2026, 10, 2), '1', '001', '01', '2',
                       '123456789'),
        'gen': {'iAmb': '2', 'iTpEmis': '01', 'iDoc': '01', 'dNroDF': '0000000001', 'dPtoFacDF': '001',
                'dSeg': '123456789', 'dFechaEm': '2026-10-02T09:15:00-05:00', 'iNatOp': '01', 'iTipoOp': '1',
                'iDest': '1', 'iFormCAFE': '3', 'iEntCAFE': '2', 'dEnvFE': '1', 'iProGen': '1',
                'iTipoTranVenta': '1'},
        'emisor': {'tipo_ruc': '2', 'ruc': '155779346-2-2026', 'dv': '07', 'nombre': "D'CASA Panamá",
                   'sucursal': '0000', 'direccion': 'Avenida Las Américas, La Chorrera',
                   'ubicacion': {'codigo': '8-8-8', 'corregimiento': 'X', 'distrito': 'Y', 'provincia': 'Z'},
                   'telefonos': ['6026-1919'], 'correos': ['info@dcasapty.com']},
        'receptor': {'tipo': '02', 'nombre': 'Ana Gómez', 'pais': 'PA', 'telefonos': [], 'correos': []},
        'items': [{'secuencia': 1, 'descripcion': 'CAMA QUEEN', 'codigo': '1062010735N', 'cantidad': 1.0,
                   'precio_unitario': 158.02, 'descuento_unitario': 0.0, 'precio_item': 158.02,
                   'valor_total': 169.08, 'tasa': '01', 'itbms': 11.06}],
        'totales': {'neto': 158.02, 'itbms': 11.06, 'gravado': 11.06, 'total': 169.08, 'recibido': 169.08,
                    'tiempo_pago': '1', 'nro_items': 1, 'total_items': 169.08,
                    'formas_pago': [{'codigo': '02', 'valor': 169.08}]},
    }
    datos.update(cambios)
    return datos


@tagged('post_install', '-at_install')
class TestCufe(BaseCase):

    def test_cufe_reales_de_la_dgi_son_validos(self):
        self.assertTrue(C.cufe_valido(CUFE_REAL_1))
        self.assertTrue(C.cufe_valido(CUFE_REAL_2))
        self.assertFalse(C.cufe_valido(CUFE_REAL_1[:-1] + '9'))
        self.assertFalse(C.cufe_valido('FE01'))

    def test_cufe_reconstruye_los_reales(self):
        """Con los campos del CUFE real 2 se obtiene exactamente el mismo CUFE (incluido el dígito)."""
        self.assertEqual(C.cufe('01', '2', '138-289-35920', '4', '8917', date(2020, 9, 3), '100086128', '001',
                                '01', '1', '797979882'), CUFE_REAL_2)
        self.assertEqual(C.cufe('01', '2', '45400-2-299934', '09', '0000', date(2022, 5, 5), '38', '999',
                                '01', '1', '768669062'), CUFE_REAL_1)

    def test_cufe_de_dcasa(self):
        cufe = C.cufe('01', '2', '155779346-2-2026', '7', '0000', date(2026, 10, 2), '1', '001', '01', '2',
                      '123456789')
        self.assertEqual(len(cufe), C.LARGO_CUFE)
        self.assertTrue(cufe.startswith('FE0120000155779346-2-2026-07000020261002'))
        self.assertTrue(C.cufe_valido(cufe))

    def test_tasas_itbms(self):
        self.assertEqual(C.codigo_tasa(7), '01')
        self.assertEqual(C.codigo_tasa(0), '00')
        self.assertEqual(C.codigo_tasa(10.0), '02')
        self.assertEqual(C.codigo_tasa(15), '03')
        self.assertIsNone(C.codigo_tasa(5))


@tagged('post_install', '-at_install')
class TestGenerador(BaseCase):

    def _xml(self, **cambios):
        return etree.fromstring(G.generar_xml(datos_minimos(**cambios)))

    def _t(self, raiz, ruta):
        return raiz.findtext(ruta, namespaces={'d': C.NAMESPACE})

    def test_estructura_basica(self):
        raiz = self._xml()
        self.assertEqual(raiz.tag, f'{{{C.NAMESPACE}}}rFE')
        hijos = [etree.QName(h).localname for h in raiz]
        self.assertEqual(hijos, ['dVerForm', 'dId', 'gDGen', 'gItem', 'gTot'])
        self.assertEqual(self._t(raiz, 'd:dVerForm'), '1.00')
        self.assertTrue(C.cufe_valido(self._t(raiz, 'd:dId')))
        orden = [etree.QName(h).localname for h in raiz.find('d:gDGen', namespaces={'d': C.NAMESPACE})]
        # El orden que coincide en las fuentes (sin dSeg/iTipoTranVenta que una de ellas omite).
        comunes = ['iAmb', 'iTpEmis', 'iDoc', 'dNroDF', 'dPtoFacDF', 'dFechaEm', 'iNatOp', 'iTipoOp', 'iDest',
                   'iFormCAFE', 'iEntCAFE', 'dEnvFE', 'iProGen', 'gEmis', 'gDatRec']
        self.assertEqual([n for n in orden if n in comunes], comunes)

    def test_emisor_receptor_items_y_totales(self):
        raiz = self._xml()
        self.assertEqual(self._t(raiz, 'd:gDGen/d:gEmis/d:gRucEmi/d:dRuc'), '155779346-2-2026')
        self.assertEqual(self._t(raiz, 'd:gDGen/d:gEmis/d:gRucEmi/d:dDV'), '07')
        self.assertEqual(self._t(raiz, 'd:gDGen/d:gDatRec/d:iTipoRec'), '02')
        self.assertIsNone(raiz.find('d:gDGen/d:gDatRec/d:gRucRec', namespaces={'d': C.NAMESPACE}))
        self.assertEqual(self._t(raiz, 'd:gItem/d:gPrecios/d:dPrUnit'), '158.02')
        self.assertEqual(self._t(raiz, 'd:gItem/d:dCantCodInt'), '1.00')
        self.assertEqual(self._t(raiz, 'd:gItem/d:gITBMSItem/d:dTasaITBMS'), '01')
        self.assertEqual(self._t(raiz, 'd:gTot/d:dVTot'), '169.08')
        self.assertEqual(self._t(raiz, 'd:gTot/d:gFormaPago/d:iFormaPago'), '02')

    def test_contingencia_y_referencia(self):
        datos = datos_minimos()
        datos['gen'].update(iTpEmis='02', dFechaCont='2026-10-02T08:00:00-05:00', dMotCont='Sin internet en la tienda')
        datos['referencias'] = [{'emisor': datos['emisor'], 'cufe': CUFE_REAL_1, 'fecha': '2026-10-01T10:00:00-05:00'}]
        raiz = etree.fromstring(G.generar_xml(datos))
        self.assertEqual(self._t(raiz, 'd:gDGen/d:dMotCont'), 'Sin internet en la tienda')
        self.assertEqual(self._t(raiz, 'd:gDGen/d:gDFRef/d:gDFRefNum/d:gDFRefFE/d:dCUFERef'), CUFE_REAL_1)

    def test_montos(self):
        self.assertEqual(G.monto(10), '10.00')
        self.assertEqual(G.monto(147.6822429, 6), '147.682243')
        self.assertEqual(G.monto(158.02, 6), '158.02')

    def test_xsd(self):
        """Sin XSD oficial no se afirma nada (None); con uno, valida."""
        xml = G.generar_xml(datos_minimos())
        self.assertIsNone(G.validar_xsd(xml, ruta='/no/existe.xsd'))
        resultado = G.validar_xsd(xml)
        if resultado is None:
            self.skipTest('El XSD oficial (FE_v1.00.xsd) aún no está en dcasa_fe_pa/xsd/.')
        self.assertEqual(resultado, [])
