"""Las reglas puras del programa de vendedores: entra un número, sale un número, sin tocar la base."""
import copy
from datetime import datetime

from odoo.tests import BaseCase, tagged

from ..models import reglas as R
from ..models import reglas_vendedores as RV
from .common import VENDEDORES_DE_PRUEBA


@tagged('post_install', '-at_install')
class TestReglasDeVendedores(BaseCase):

    def reglas(self, **cambios):
        reglas = {**R.cargar_reglas(), 'vendedores': copy.deepcopy(VENDEDORES_DE_PRUEBA)}
        for ruta, valor in cambios.items():
            seccion, clave = ruta.split('__')
            reglas['vendedores'][seccion][clave] = valor
        return reglas

    # --- ¿Está lista la economía? ---------------------------------------------------------

    def test_apagado_no_acredita_y_lo_dice(self):
        reglas = self.reglas()
        reglas['vendedores']['programaActivo'] = False
        self.assertIn('apagado', ' '.join(RV.falta_para_comisionar(reglas)))
        with self.assertRaises(R.FaltaConfigurar):
            RV.comision_directa(10000, reglas)

    def test_encendido_pero_con_cifras_en_null_no_acredita(self):
        for ruta in ('comision__puntosPorDolarNeto', 'comision__pagaEn', 'retencion__dias',
                     'techos__totalPorVentaPorcentajeDelNeto'):
            with self.subTest(ruta):
                reglas = self.reglas(**{ruta: None})
                self.assertTrue(RV.falta_para_comisionar(reglas), ruta)
                with self.assertRaises(R.FaltaConfigurar):
                    RV.comision_directa(10000, reglas)

    def test_la_seccion_ausente_no_acredita(self):
        reglas = {**R.cargar_reglas()}
        reglas.pop('vendedores', None)
        self.assertTrue(RV.falta_para_comisionar(reglas))

    def test_con_todo_puesto_no_falta_nada(self):
        reglas = self.reglas()
        self.assertEqual(RV.falta_para_comisionar(reglas), [])
        self.assertEqual(RV.falta_para_patrocinar(reglas), [])

    def test_sin_cifra_de_patrocinio_el_patrocinador_no_gana_pero_el_directo_si(self):
        reglas = self.reglas(patrocinio__puntosPorDolarNetoDelDirecto=None)
        self.assertGreater(RV.comision_directa(10000, reglas), 0)
        with self.assertRaises(R.FaltaConfigurar):
            RV.comision_patrocinio(10000, reglas)

    # --- Los puntos -------------------------------------------------------------------------

    def test_comision_directa_redondea_hacia_abajo(self):
        reglas = self.reglas(comision__puntosPorDolarNeto=4)
        self.assertEqual(RV.comision_directa(14500, reglas), 580)      # $145.00 neto × 4
        self.assertEqual(RV.comision_directa(10049, reglas), 401)      # 401.96 → 401
        reglas = self.reglas(comision__puntosPorDolarNeto=2.5)
        self.assertEqual(RV.comision_directa(10001, reglas), 250)      # 250.0025 → 250

    def test_la_venta_minima_no_da_puntos(self):
        reglas = self.reglas(comision__compraMinimaCentavos=2000)
        self.assertEqual(RV.comision_directa(1999, reglas), 0)
        self.assertEqual(RV.comision_directa(2000, reglas), 80)

    def test_la_venta_va_en_centavos_enteros(self):
        for malo in (-1, 1.5, True):
            with self.subTest(malo), self.assertRaises(ValueError):
                RV.comision_directa(malo, self.reglas())

    def test_escalones_suben_la_tasa_con_lo_vendido_en_el_periodo(self):
        reglas = self.reglas(comision__escalones=[
            {'desdeVentasNetasCentavos': 50000, 'puntosPorDolarNeto': 5},
            {'desdeVentasNetasCentavos': 200000, 'puntosPorDolarNeto': 6}])
        self.assertEqual(RV.comision_directa(10000, reglas, 0), 400)
        self.assertEqual(RV.comision_directa(10000, reglas, 50000), 500)
        self.assertEqual(RV.comision_directa(10000, reglas, 999999), 600)

    def test_patrocinio_es_aparte_y_tambien_redondea_hacia_abajo(self):
        reglas = self.reglas(patrocinio__puntosPorDolarNetoDelDirecto=0.4)
        self.assertEqual(RV.comision_patrocinio(14500, reglas), 58)
        self.assertEqual(RV.comision_patrocinio(10049, reglas), 40)    # 40.196 → 40

    # --- El techo por venta -------------------------------------------------------------------

    def test_techo_total_por_venta(self):
        self.assertEqual(RV.techo_total_por_venta(14500, self.reglas()), 1160)   # 8 % de $145.00

    def test_dentro_del_techo_no_se_recorta(self):
        # neto $145: techo 1,160; el cliente ya recibió 155; vendedor 580 + patrocinio 58 caben.
        self.assertEqual(RV.repartir_bajo_el_techo(580, 58, 155, 14500, self.reglas()), (580, 58, False))

    def test_pasado_el_techo_se_recorta_primero_el_patrocinio(self):
        reglas = self.reglas(techos__totalPorVentaPorcentajeDelNeto=5)           # techo 725
        # lo que cabe: 725 − 155 = 570. El vendedor (580) se recorta a 570 y el patrocinador a 0.
        self.assertEqual(RV.repartir_bajo_el_techo(580, 58, 155, 14500, reglas), (570, 0, True))
        reglas = self.reglas(techos__totalPorVentaPorcentajeDelNeto=5.5)         # techo 797 → caben 642
        self.assertEqual(RV.repartir_bajo_el_techo(580, 100, 155, 14500, reglas), (580, 62, True))

    def test_si_el_cliente_ya_se_comio_el_techo_no_queda_nada(self):
        reglas = self.reglas(techos__totalPorVentaPorcentajeDelNeto=1)
        self.assertEqual(RV.repartir_bajo_el_techo(580, 58, 155, 14500, reglas), (0, 0, True))

    def test_la_recompra_paga_una_fraccion_y_sin_cifra_paga_entera(self):
        self.assertEqual(RV.aplicar_factor_de_recompra(400, self.reglas()), 400)
        reglas = self.reglas(comision__factorDeRecompra=0.5)
        self.assertEqual(RV.aplicar_factor_de_recompra(400, reglas), 200)
        self.assertEqual(RV.aplicar_factor_de_recompra(401, reglas), 200, 'Hacia abajo, como todo')

    def test_el_patrocinio_en_recompras_y_las_ventas_minimas_vienen_apagados(self):
        self.assertFalse(RV.patrocinio_paga_en_recompras(self.reglas()))
        self.assertTrue(RV.patrocinio_paga_en_recompras(self.reglas(vinculacion__pagaPatrocinio=True)))
        self.assertEqual(RV.ventas_propias_minimas_para_patrocinar(self.reglas()), 0)
        reglas = self.reglas(patrocinio__ventasPropiasMinimasAlMes=2)
        self.assertEqual(RV.ventas_propias_minimas_para_patrocinar(reglas), 2)

    def test_el_patrocinio_se_topa_contra_la_comision_propia_del_mes(self):
        self.assertEqual(RV.topar_patrocinio(100, 0, 0, self.reglas()), 100, 'Sin cifra no hay tope')
        reglas = self.reglas(patrocinio__topeComoMultiploDeSuComisionDelMes=0.5)
        self.assertEqual(RV.topar_patrocinio(100, 0, 1000, reglas), 100)       # tope 500
        self.assertEqual(RV.topar_patrocinio(100, 450, 1000, reglas), 50)
        self.assertEqual(RV.topar_patrocinio(100, 500, 1000, reglas), 0)
        self.assertEqual(RV.topar_patrocinio(100, 0, 0, reglas), 0, 'Sin ventas propias no hay patrocinio')

    def test_freno_global_recorta_primero_el_patrocinio(self):
        reglas = self.reglas(techos__frenoGlobalPorcentajeDeLaVentaNeta=2)
        # 2 % de $10,000.00 = 20,000 puntos; ya se emitieron 19,500 → caben 500.
        self.assertEqual(RV.repartir_bajo_el_freno_global(400, 40, 19500, 1000000, reglas), (400, 40, False))
        self.assertEqual(RV.repartir_bajo_el_freno_global(480, 40, 19500, 1000000, reglas), (480, 20, True))
        self.assertEqual(RV.repartir_bajo_el_freno_global(600, 40, 19500, 1000000, reglas), (500, 0, True))
        self.assertEqual(RV.repartir_bajo_el_freno_global(600, 40, 25000, 1000000, reglas), (0, 0, True))
        self.assertEqual(RV.repartir_bajo_el_freno_global(600, 40, 0, 0, reglas), (0, 0, True),
                         'Sin ventas en la tienda no hay con qué pagar')

    def test_sin_cifra_de_freno_global_no_se_recorta(self):
        self.assertEqual(RV.repartir_bajo_el_freno_global(600, 40, 10**9, 0, self.reglas()), (600, 40, False))

    def test_tope_al_mes(self):
        self.assertEqual(RV.topar_al_mes(100, 0, None), 100)
        self.assertEqual(RV.topar_al_mes(100, 950, 1000), 50)
        self.assertEqual(RV.topar_al_mes(100, 1000, 1000), 0)
        self.assertEqual(RV.topar_al_mes(100, 1200, 1000), 0, 'Un mes ya pasado del tope no da negativo')

    # --- Tiempos y códigos -----------------------------------------------------------------------

    def test_ventana_de_devoluciones(self):
        hoy = datetime(2026, 10, 14, 12, 0)
        self.assertEqual(RV.disponible_desde(hoy, self.reglas()), datetime(2026, 11, 13, 12, 0))
        self.assertEqual(RV.disponible_desde(hoy, self.reglas(retencion__dias=0)), hoy)

    def test_vinculacion_en_meses(self):
        self.assertEqual(RV.meses_de_vinculacion(self.reglas(vinculacion__meses=0)), 0)
        self.assertEqual(RV.meses_de_vinculacion(self.reglas(vinculacion__meses=12)), 12)
        self.assertEqual(RV.meses_de_vinculacion({'vendedores': {}}), 0)

    def test_codigos_de_vendedor(self):
        codigo = RV.nuevo_codigo_vendedor()
        self.assertTrue(codigo.startswith('VEN') and len(codigo) == 9)
        self.assertTrue(RV.es_codigo_vendedor_valido(codigo))
        self.assertTrue(RV.es_codigo_vendedor_valido(RV.codigo_vendedor_normal(f' {codigo[:3]}-{codigo[3:].lower()} ')))
        self.assertFalse(RV.es_codigo_vendedor_valido('DCA7K2M9P'), 'Un código de socio no es de vendedor')
        self.assertFalse(RV.es_codigo_vendedor_valido('VEN0O1IL2'), 'Sin O/0 ni I/1/L')
