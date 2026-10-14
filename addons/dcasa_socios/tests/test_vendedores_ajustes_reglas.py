"""Los ajustes de Gerencia, en puro: la capa que va ENCIMA de puntos.json. Entra un número, sale un número; sin base."""
import copy
from datetime import datetime, timedelta

from odoo.tests import BaseCase, tagged

from ..models import reglas as R
from ..models import reglas_ajustes as A
from ..models import reglas_vendedores as RV

AHORA = datetime(2026, 10, 14, 12, 0)


def version(numero, desde, **ajustes):
    return {'numero': numero, 'vigente_desde': desde, 'ajustes': {k.replace('__', '.'): v for k, v in ajustes.items()}}


@tagged('post_install', '-at_install')
class TestReglasEfectivas(BaseCase):
    """fábrica + ajustes vigentes = lo que se paga; los cambios solo rigen hacia adelante."""

    def setUp(self):
        super().setUp()
        self.base = R.cargar_reglas()

    def test_sin_versiones_rige_puntos_json_tal_cual(self):
        self.assertIs(A.reglas_efectivas(self.base, [], AHORA), self.base)
        # Una versión que todavía no empezó tampoco cuenta.
        futura = version(1, AHORA + timedelta(days=1), comision__puntosPorDolarNeto=6)
        self.assertIs(A.reglas_efectivas(self.base, [futura], AHORA), self.base)

    def test_la_version_vigente_depende_de_la_fecha(self):
        v1 = version(1, AHORA - timedelta(days=10), comision__puntosPorDolarNeto=5)
        v2 = version(2, AHORA + timedelta(days=1), comision__puntosPorDolarNeto=6)

        def tasa(ahora):
            return RV.seccion(A.reglas_efectivas(self.base, [v1, v2], ahora))['comision']['puntosPorDolarNeto']

        self.assertEqual(tasa(AHORA - timedelta(days=11)), 4, 'Antes de la primera versión: la fábrica')
        self.assertEqual(tasa(AHORA - timedelta(days=10)), 5, 'Rige desde el instante exacto de su vigencia')
        self.assertEqual(tasa(AHORA), 5)
        self.assertEqual(tasa(AHORA + timedelta(days=1)), 6)
        self.assertEqual(RV.ajuste_aplicado(A.reglas_efectivas(self.base, [v1, v2], AHORA)), 1)
        self.assertEqual(RV.ajuste_aplicado(A.reglas_efectivas(self.base, [v1, v2], AHORA + timedelta(days=2))), 2)
        self.assertEqual(RV.ajuste_aplicado(self.base), 0)

    def test_en_un_empate_manda_la_de_mayor_numero(self):
        v1 = version(1, AHORA, comision__puntosPorDolarNeto=5)
        v2 = version(2, AHORA, comision__puntosPorDolarNeto=6)
        self.assertEqual(A.version_vigente([v1, v2], AHORA)['numero'], 2)
        self.assertEqual(A.version_vigente([v2, v1], AHORA)['numero'], 2)

    def test_las_reglas_de_fabrica_no_se_tocan(self):
        antes = copy.deepcopy(self.base)
        efectivas = A.reglas_efectivas(self.base, [version(1, AHORA, comision__puntosPorDolarNeto=5)], AHORA)
        self.assertEqual(self.base, antes)
        self.assertIsNot(efectivas, self.base)
        efectivas['vendedores']['comision']['puntosPorDolarNeto'] = 99
        self.assertEqual(self.base['vendedores']['comision']['puntosPorDolarNeto'], 4)

    def test_lo_que_no_se_ajusta_sigue_siendo_de_fabrica(self):
        efectivas = A.reglas_efectivas(self.base, [version(1, AHORA, comision__puntosPorDolarNeto=5)], AHORA)
        self.assertEqual(efectivas['vendedores']['comision']['escalones'],
                         self.base['vendedores']['comision']['escalones'])
        self.assertEqual(efectivas['acumulacion'], self.base['acumulacion'])
        self.assertEqual(efectivas['canje'], self.base['canje'])

    def test_los_interruptores_legales_y_lo_antifraude_no_se_ajustan_ni_con_una_fila_manipulada(self):
        """Aunque alguien escribiera estas rutas directo en la base, al leer se descartan."""
        manipulada = version(
            1, AHORA, canje__externosHabilitado=True, canje__efectivoHabilitado=True,
            bloquearComprasDentroDeLaColmena=False, techos__pesoDelPuntoDeVendedor=0.1,
            patrocinio__soloClientesNuevos=False, vinculacion__pagaPatrocinio=True, comision__pagaEn='primera-compra',
            comision__baseDeCalculo='total', techos__margenBrutoSupuestoPorcentaje=99)
        manipulada['ajustes']['acumulacion.puntosPorDolar'] = 1000
        manipulada['ajustes']['canje.puntosPorDolar'] = 1
        manipulada['ajustes']['comision.puntosPorDolarNeto'] = 5            # esta sí vale
        efectivas = A.reglas_efectivas(self.base, [manipulada], AHORA)
        v = efectivas['vendedores']
        self.assertIs(v['canje']['externosHabilitado'], False)
        self.assertIs(v['canje']['efectivoHabilitado'], False)
        self.assertIs(v['bloquearComprasDentroDeLaColmena'], True)
        self.assertEqual(v['techos']['pesoDelPuntoDeVendedor'], 0.7)
        self.assertIs(v['patrocinio']['soloClientesNuevos'], True)
        self.assertIs(v['vinculacion']['pagaPatrocinio'], False)
        self.assertEqual(v['comision']['pagaEn'], 'cada-compra')
        self.assertEqual(v['techos']['margenBrutoSupuestoPorcentaje'], 35)
        self.assertEqual(efectivas['acumulacion']['puntosPorDolar'], 1)
        self.assertEqual(efectivas['canje']['puntosPorDolar'], 100)
        self.assertEqual(v['comision']['puntosPorDolarNeto'], 5)

    def test_los_valores_mal_formados_se_descartan(self):
        malos = {
            'programaActivo': 'si', 'comision.puntosPorDolarNeto': True, 'comision.compraMinimaCentavos': 20.5,
            'comision.diasParaEscalon': -1, 'retencion.dias': 'treinta',
            'techos.frenoGlobalPorcentajeDeLaVentaNeta': None,
            'techos.totalPorVentaPorcentajeDelNeto': float('nan'), 'patrocinio.topeDeDirectos': float('inf'),
            'comision.escalones': [{'desdeVentasNetasCentavos': 'mucho', 'puntosPorDolarNeto': 5}],
        }
        self.assertEqual(A.ajustes_validos(malos), {})
        efectivas = A.reglas_efectivas(self.base, [{'numero': 1, 'vigente_desde': AHORA, 'ajustes': malos}], AHORA)
        self.assertEqual(efectivas['vendedores'], self.base['vendedores'])
        self.assertEqual(A.ajustes_validos('no soy un diccionario'), {})
        self.assertEqual(A.ajustes_validos(None), {})

    def test_una_cifra_sin_tope_si_puede_quedar_en_null(self):
        validos = A.ajustes_validos({'techos.patrocinioPorPatrocinadorAlMesPuntos': None,
                                     'techos.porVendedorAlMesPuntos': None})
        self.assertEqual(validos, {'techos.patrocinioPorPatrocinadorAlMesPuntos': None})

    def test_la_escalera_se_ajusta_entera_y_se_limpia(self):
        nueva = [{'desdeVentasNetasCentavos': 100000, 'puntosPorDolarNeto': 5, 'topeAlMesPuntos': 30000, 'basura': 1}]
        efectivas = A.reglas_efectivas(self.base, [version(1, AHORA, comision__escalones=nueva)], AHORA)
        self.assertEqual(efectivas['vendedores']['comision']['escalones'],
                         [{'desdeVentasNetasCentavos': 100000, 'puntosPorDolarNeto': 5, 'topeAlMesPuntos': 30000}])
        comision = efectivas['vendedores']['comision']
        self.assertEqual(RV.puntos_por_dolar_de_escalon(100000, comision), 5)
        self.assertEqual(RV.puntos_por_dolar_de_escalon(99999, comision), 4)
        demasiados = [{'desdeVentasNetasCentavos': 1000 * (n + 1), 'puntosPorDolarNeto': 5 + n}
                      for n in range(A.MAX_ESCALONES + 1)]
        self.assertEqual(A.ajustes_validos({'comision.escalones': demasiados}), {})

    def test_la_marca_dice_que_version_rige_y_desde_cuando(self):
        v = version(3, AHORA, comision__puntosPorDolarNeto=5)
        v['id'], v['tipo'] = 77, 'fabrica'
        marca = A.reglas_efectivas(self.base, [v], AHORA)['ajusteVendedores']
        self.assertEqual(marca, {'numero': 3, 'id': 77, 'tipo': 'fabrica', 'vigenteDesde': '2026-10-14 12:00:00'})


@tagged('post_install', '-at_install')
class TestLaPantallaYLosAjustes(BaseCase):
    """De la pantalla (dólares, porcentajes) a puntos.json (centavos, puntos, fracciones) y de vuelta."""

    def setUp(self):
        super().setUp()
        self.base = R.cargar_reglas()
        self.pantalla = A.valores_de_pantalla(self.base)

    def cambio(self, ajustes_actuales=None, actuales=None, **cambios):
        pantalla = {**self.pantalla, **cambios}
        return A.calcular_cambio(self.base, actuales or self.base, ajustes_actuales or {}, pantalla)

    def test_cada_cifra_ajustable_existe_en_puntos_json(self):
        v = RV.seccion(self.base)
        for campo in A.CAMPOS:
            with self.subTest(campo.clave):
                if campo.cero_es_vacio:
                    continue                        # «sin tope» es null en la fábrica
                self.assertIsNotNone(A.leer(v, campo.ruta), campo.ruta_texto)

    def test_ida_y_vuelta_de_todas_las_cifras_de_fabrica(self):
        v, ppd = RV.seccion(self.base), A.puntos_por_dolar(self.base)
        for campo in A.CAMPOS:
            with self.subTest(campo.clave):
                original = A.leer(v, campo.ruta)
                vuelta = A.de_pantalla(campo, A.a_pantalla(campo, original, ppd), ppd)
                self.assertEqual(vuelta, original)

    def test_sin_tocar_nada_no_cambia_nada(self):
        resultado = self.cambio()
        self.assertEqual((resultado['cambios'], resultado['ajustes'], resultado['problemas']), ([], {}, []))
        self.assertEqual(resultado['candidato'], self.base)

    def test_la_pantalla_muestra_dolares_y_porcentajes_no_centavos_ni_puntos(self):
        p = self.pantalla
        self.assertEqual((p['comision_base'], p['compra_minima'], p['tope_base'], p['canje_minimo']),
                         (4.0, 20.0, 200.0, 30.0))
        self.assertEqual((p['recompra'], p['existente']), (50.0, 50.0))
        self.assertEqual((p['esc1_desde'], p['esc1_tasa'], p['esc1_tope']), (3000.0, 5.0, 300.0))
        self.assertEqual((p['esc3_desde'], p['esc3_tasa'], p['esc3_tope']), (18000.0, 8.0, 900.0))
        self.assertEqual((p['esc4_desde'], p['esc4_tasa'], p['esc4_tope']), (0.0, 0.0, 0.0), 'Sin usar')
        self.assertEqual(p['patrocinio_tope'], 0.0, 'La fábrica no pone tope de patrocinio: null → 0')
        self.assertIs(p['programa'], True)

    def test_un_cambio_se_convierte_a_las_unidades_del_programa(self):
        r = self.cambio(compra_minima=25, tope_base=250, recompra=75, existente=40, patrocinio_tope=50,
                        canje_minimo=45.5, comision_base=4.5, patrocinio_multiplo=1.5)
        self.assertEqual(r['problemas'], [])
        self.assertEqual(r['ajustes'], {
            'comision.compraMinimaCentavos': 2500, 'techos.porVendedorAlMesPuntos': 25000,
            'comision.factorDeRecompra': 0.75, 'comision.factorClienteExistente': 0.4,
            'techos.patrocinioPorPatrocinadorAlMesPuntos': 5000, 'canje.puntosMinimosParaCanjear': 4550,
            'comision.puntosPorDolarNeto': 4.5, 'patrocinio.topeComoMultiploDeSuComisionDelMes': 1.5})
        v = RV.seccion(r['candidato'])
        self.assertEqual(RV.comision_directa(14500, r['candidato']), 652)         # 4.5 % de $145.00
        self.assertEqual(RV.aplicar_factor_de_recompra(1000, r['candidato']), 750)
        self.assertEqual(v['techos']['patrocinioPorPatrocinadorAlMesPuntos'], 5000)

    def test_el_cambio_dice_el_antes_y_el_despues_en_palabras(self):
        r = self.cambio(comision_base=4.5, programa=False, vinculo_meses=6)
        dichos = {c['campo']: (c['antes'], c['despues']) for c in r['cambios']}
        self.assertEqual(dichos['Comisión base (% de la venta neta)'], ('4 %', '4.5 %'))
        self.assertEqual(dichos['El programa de vendedores está encendido'], ('Encendido', 'Apagado'))
        self.assertEqual(dichos['Meses que el cliente queda ligado a su vendedor'], ('12 meses', '6 meses'))

    def test_los_ajustes_se_acumulan_y_volver_al_valor_de_fabrica_quita_el_ajuste(self):
        primero = self.cambio(comision_base=4.5)
        actuales = primero['candidato']
        pantalla_ahora = A.valores_de_pantalla(actuales)
        segundo = A.calcular_cambio(self.base, actuales, primero['ajustes'], {**pantalla_ahora, 'vinculo_meses': 6})
        self.assertEqual(segundo['ajustes'], {'comision.puntosPorDolarNeto': 4.5, 'vinculacion.meses': 6})
        self.assertEqual([c['campo'] for c in segundo['cambios']], ['Meses que el cliente queda ligado a su vendedor'])
        tercero = A.calcular_cambio(self.base, segundo['candidato'], segundo['ajustes'],
                                    {**A.valores_de_pantalla(segundo['candidato']), 'comision_base': 4})
        self.assertEqual(tercero['ajustes'], {'vinculacion.meses': 6}, 'Lo que vuelve a la fábrica deja de ser ajuste')
        self.assertEqual(tercero['cambios'][0]['antes'], '4.5 %')

    def test_las_cifras_con_mas_decimales_de_los_que_caben_no_cuentan_como_cambio(self):
        base = copy.deepcopy(self.base)
        base['vendedores']['patrocinio']['puntosPorDolarNetoDelDirecto'] = 0.125
        # El campo de la pantalla redondea a 2 decimales: 0.125 se ve como 0.13.
        pantalla = {**A.valores_de_pantalla(base), 'patrocinio': 0.13}
        resultado = A.calcular_cambio(base, base, {}, pantalla)
        self.assertEqual((resultado['cambios'], resultado['ajustes']), ([], {}))

    def test_los_decimales_se_toman_exactos(self):
        r = self.cambio(comision_base=6.55, existente=33.33)
        self.assertEqual(r['ajustes']['comision.puntosPorDolarNeto'], 6.55)
        self.assertEqual(r['ajustes']['comision.factorClienteExistente'], 0.3333)
        self.assertEqual(RV.comision_directa(10000, r['candidato']), 655)

    # --- La escalera ---------------------------------------------------------------------------------------------

    def test_la_escalera_se_cambia_por_filas(self):
        r = self.cambio(esc2_desde=10000, esc2_tasa=7, esc2_tope=600)
        self.assertEqual(r['problemas'], [])
        self.assertEqual(r['ajustes']['comision.escalones'][1],
                         {'desdeVentasNetasCentavos': 1000000, 'puntosPorDolarNeto': 7, 'topeAlMesPuntos': 60000})
        self.assertEqual([c['campo'] for c in r['cambios']], ['Escalón 2'])
        self.assertIn('desde $9,000.00 vendidos · gana 6.5 %', r['cambios'][0]['antes'])
        self.assertIn('desde $10,000.00 vendidos · gana 7 %', r['cambios'][0]['despues'])

    def test_se_puede_agregar_un_cuarto_escalon_y_quitar_uno(self):
        r = self.cambio(esc4_desde=30000, esc4_tasa=8.5, esc4_tope=1200)
        self.assertEqual(r['problemas'], [])
        self.assertEqual(len(r['ajustes']['comision.escalones']), 4)
        self.assertEqual(RV.puntos_por_dolar_de_escalon(3000000, RV.seccion(r['candidato'])['comision']), 8.5)
        sin_el_ultimo = self.cambio(esc3_desde=0, esc3_tasa=0, esc3_tope=0)
        self.assertEqual(len(sin_el_ultimo['ajustes']['comision.escalones']), 2)
        self.assertEqual(sin_el_ultimo['cambios'][0]['despues'], 'sin usar')

    def test_un_escalon_sin_tope_usa_el_del_escalon_base(self):
        r = self.cambio(esc1_tope=0)
        self.assertEqual(r['problemas'], [])
        self.assertIsNone(r['ajustes']['comision.escalones'][0]['topeAlMesPuntos'])
        self.assertEqual(RV.tope_al_mes_del_vendedor(300000, r['candidato']), 20000)

    def test_un_escalon_a_medias_no_se_guarda(self):
        for cambios in ({'esc4_desde': 5000}, {'esc4_tasa': 5}, {'esc4_tope': 100}, {'esc2_tasa': 0}):
            with self.subTest(cambios):
                r = self.cambio(**cambios)
                self.assertTrue(r['problemas_de_pantalla'], cambios)
                self.assertIn('o deja todo en 0 para no usarlo', r['problemas'][0])

    # --- Límites duros --------------------------------------------------------------------------------------------

    def test_los_valores_de_fabrica_pasan_todas_las_validaciones(self):
        self.assertEqual(A.problemas_de_las_cifras(self.base), [])

    def test_cada_limite_duro_dice_en_palabras_sencillas_que_corregir(self):
        casos = {
            'comision en cero': ({'comision_base': 0},
                                 'Comisión base (% de la venta neta): tiene que ser mayor que cero'),
            'comision mayor que 100': ({'comision_base': 101}, 'no puede pasar de 100 %'),
            'comision sobre el techo': ({'comision_base': 9}, 'no puede ser mayor que el techo de costo por venta'),
            'escalon sobre el techo': ({'esc3_tasa': 9.5},
                                       'Escalón 3: paga 9.5 % y el techo de costo por venta es 8.75 %'),
            'patrocinio mayor que la base': ({'patrocinio': 5}, 'no puede ser mayor que la comisión base'),
            'la venta cuesta mas que el techo': ({'patrocinio': 4, 'comision_base': 4},
                                                'una sola venta podría costar hasta'),
            'techo sobre la ganancia': ({'techo': 40}, 'no puede ser mayor que la ganancia que se supone'),
            'techo en cero': ({'techo': 0}, 'tiene que ser mayor que cero'),
            'freno sobre el techo': ({'freno': 9}, 'no puede ser mayor que el techo por venta'),
            'freno en cero': ({'freno': 0}, 'tiene que ser mayor que cero'),
            'directos de mas': ({'directos': 6}, 'no puede pasar de 5 vendedores'),
            'directos en cero': ({'directos': 0}, 'no puede ser menos de 1 vendedor'),
            'dias del escalon en cero': ({'dias_escalon': 0}, 'no puede ser menos de 1 día'),
            'dias del escalon de mas': ({'dias_escalon': 366}, 'no puede pasar de 365 días'),
            'retencion de mas': ({'retencion_dias': 400}, 'no puede pasar de 365 días'),
            'retencion negativa': ({'retencion_dias': -1}, 'poder canjear: no puede ser negativo'),
            'meses de mas': ({'vinculo_meses': 61}, 'no puede pasar de 60 meses'),
            'primeras ventas esperan menos': ({'primeras_dias': 10}, 'no pueden esperar menos días que las demás'),
            'horas del codigo en cero': ({'vigencia_horas': 0}, 'no puede ser menos de 1 hora'),
            'horas del codigo de mas': ({'vigencia_horas': 721}, 'no puede pasar de 720 horas'),
            'canjes al mes en cero': ({'canjes_mes': 0}, 'no puede ser menos de 1 canje'),
            'tope base en cero': ({'tope_base': 0}, 'Tope del mes en el escalón base: tiene que ser mayor que cero'),
            'tope base de mas': ({'tope_base': 10001}, 'no puede pasar de $10,000.00'),
            'venta minima negativa': ({'compra_minima': -1}, 'Venta mínima que da comisión: no puede ser negativo'),
            'recompra de mas': ({'recompra': 150}, 'no puede pasar de 100 %'),
            'existente negativo': ({'existente': -5}, 'no puede ser negativo'),
            'tope de escalon negativo': ({'esc1_tope': -5}, 'Escalón 1: ninguna cifra puede ser negativa'),
            'multiplo de mas': ({'patrocinio_multiplo': 11}, 'no puede pasar de 10 veces'),
            'umbral de escalon que no sube': ({'esc2_desde': 3000},
                                              'Escalón 2: tiene que empezar en una venta mayor que la del'),
            'escalon que no paga mas': ({'esc2_tasa': 5},
                                        'Escalón 2: tiene que pagar un porcentaje mayor que el escalón anterior'),
            'tope de escalon que baja': ({'esc2_tope': 100},
                                         'Escalón 2: su tope del mes no puede ser menor que el del escalón anterior'),
        }
        for nombre, (cambios, texto) in casos.items():
            with self.subTest(nombre):
                r = self.cambio(**cambios)
                self.assertTrue(r['problemas'], f'{nombre}: tenía que dar un problema')
                self.assertIn(texto, ' | '.join(r['problemas']), nombre)

    def test_una_cifra_que_falta_en_puntos_json_se_dice_y_no_se_rellena(self):
        base = copy.deepcopy(self.base)
        base['vendedores']['comision']['puntosPorDolarNeto'] = None
        problemas = A.problemas_de_las_cifras(base)
        self.assertIn('Falta una cifra: comisión base (% de la venta neta).', problemas)
        # Y la pantalla la muestra en 0, pero no la cuenta como un cambio mientras nadie la toque.
        self.assertEqual(A.calcular_cambio(base, base, {}, A.valores_de_pantalla(base))['cambios'], [])

    def test_sin_cuantos_puntos_vale_un_dolar_no_se_convierte_nada(self):
        base = copy.deepcopy(self.base)
        base['canje']['puntosPorDolar'] = None
        with self.assertRaises(R.FaltaConfigurar):
            A.valores_de_pantalla(base)
        with self.assertRaises(R.FaltaConfigurar):
            A.calcular_cambio(base, base, {}, {})
        self.assertEqual(len(A.problemas_de_las_cifras(base)), 1)

    def test_la_escalera_de_fabrica_cabe_en_la_pantalla_y_mas_no(self):
        self.assertLessEqual(len(RV.seccion(self.base)['comision']['escalones']), A.MAX_ESCALONES)
        base = copy.deepcopy(self.base)
        base['vendedores']['comision']['escalones'] = [
            {'desdeVentasNetasCentavos': 1000 * (n + 1), 'puntosPorDolarNeto': 5 + n / 10}
            for n in range(A.MAX_ESCALONES + 1)]
        with self.assertRaises(R.FaltaConfigurar):
            A.valores_de_pantalla(base)

    def test_las_cifras_ajustables_no_incluyen_los_interruptores_legales(self):
        rutas = {campo.ruta_texto for campo in A.CAMPOS} | {A.RUTA_ESCALONES}
        for prohibida in ('canje.externosHabilitado', 'canje.efectivoHabilitado', 'bloquearComprasDentroDeLaColmena',
                          'techos.pesoDelPuntoDeVendedor', 'techos.margenBrutoSupuestoPorcentaje'):
            self.assertNotIn(prohibida, rutas)

    # --- Lo que cuesta ------------------------------------------------------------------------------------------

    def test_el_costo_con_las_cifras_de_fabrica(self):
        costo = A.costo_del_programa(self.base)
        # (tasa + patrocinio) × 0.7 + puntos del cliente (1.07 % de la venta neta): 8 % → (8 + 0.8) × 0.7 + 1.07
        self.assertAlmostEqual(costo['cliente'], 1.07)
        self.assertAlmostEqual(costo['peor'], 7.23)
        self.assertEqual([round(c, 2) for c in costo['por_escalon']], [4.43, 5.13, 6.18, 7.23])
        self.assertAlmostEqual(costo['equilibrio'], 7.23 / 35 * 100)
        self.assertEqual((costo['margen'], costo['techo'], costo['supera_el_techo']), (35.0, 8.75, False))

    def test_el_costo_sube_cuando_suben_las_comisiones_y_avisa_si_pasa_el_techo(self):
        r = self.cambio(esc3_tasa=8.5)
        costo = A.costo_del_programa(r['candidato'])
        self.assertAlmostEqual(costo['peor'], (8.5 + 0.8) * 0.7 + 1.07)
        self.assertFalse(costo['supera_el_techo'])
        reglas = copy.deepcopy(self.base)
        reglas['vendedores']['techos']['totalPorVentaPorcentajeDelNeto'] = 7
        self.assertTrue(A.costo_del_programa(reglas)['supera_el_techo'])

    def test_sin_margen_supuesto_no_hay_punto_de_equilibrio_y_sin_cifras_no_hay_costo(self):
        reglas = copy.deepcopy(self.base)
        del reglas['vendedores']['techos']['margenBrutoSupuestoPorcentaje']
        costo = A.costo_del_programa(reglas)
        self.assertIsNone(costo['equilibrio'])
        self.assertIsNone(costo['margen'])
        reglas['acumulacion']['puntosPorDolar'] = None
        self.assertIsNone(A.costo_del_programa(reglas), 'Sin los puntos del cliente no se inventa un costo')

    def test_volver_a_la_fabrica_dice_lo_que_cambia(self):
        r = self.cambio(comision_base=4.5, esc1_tasa=5.5)
        cambios = A.cambios_contra_fabrica(self.base, r['candidato'])
        self.assertEqual({c['campo'] for c in cambios}, {'Comisión base (% de la venta neta)', 'Escalón 1'})
        self.assertEqual(A.cambios_contra_fabrica(self.base, self.base), [])
