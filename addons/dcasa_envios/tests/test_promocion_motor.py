"""La cuenta de la promoción de envío, sin base de datos (``motor/promocion.py``).

La promoción de noviembre con las decisiones de la dueña: más de $200 SIN ITBMS (estrictamente mayor), gratis en toda
la provincia de Panamá y en Panamá Oeste, $20 de abono en Colón y el resto, no aplica con colchón, del 1 al 30 de
noviembre de 2026 (ambos incluidos)."""
from datetime import date

from odoo.tests import BaseCase, tagged

from ..motor import promocion as P

NOVIEMBRE = {
    'nombre': 'Envío Gratis Todo Noviembre', 'desde': date(2026, 11, 1), 'hasta': date(2026, 11, 30),
    'minimo': 200.0, 'mide': 'sin_itbms', 'provincias_gratis': ['Panamá', 'Panamá Oeste'], 'distritos_gratis': [],
    'abono': 20.0, 'excluye_colchon': True,
}
HOY = date(2026, 11, 12)


def papeles(respaldo):
    """``(normal, final, ahorro, gratis, condicional, minimo, compra)`` del respaldo de un lugar."""
    return tuple(respaldo[k] for k in ('normal', 'final', 'ahorro', 'gratis', 'condicional', 'minimo', 'compra'))


def compra(sin_itbms, con_itbms=None, colchon=False):
    return {'subtotal_sin_itbms': sin_itbms,
            'subtotal_con_itbms': round(sin_itbms * 1.07, 2) if con_itbms is None else con_itbms, 'colchon': colchon}


@tagged('post_install', '-at_install')
class TestPromocionDeEnvio(BaseCase):

    def aplicar(self, precio=15.0, prov='Panamá', dist='San Miguelito', fecha=HOY, datos='sin', promocion=None):
        return P.aplicar(promocion or NOVIEMBRE, precio, prov, dist, fecha, None if datos == 'sin' else datos)

    # --- Fechas ---------------------------------------------------------------------------------------------------
    def test_dentro_y_fuera_de_las_fechas_ambos_dias_incluidos(self):
        for fecha, vale in ((date(2026, 10, 31), False), (date(2026, 11, 1), True), (date(2026, 11, 30), True),
                            (date(2026, 12, 1), False)):
            with self.subTest(fecha=fecha):
                resultado = self.aplicar(fecha=fecha, datos=compra(300))
                self.assertEqual(resultado['hay_promocion'], vale)
                self.assertEqual(resultado['aplica'], vale)
                self.assertEqual(resultado['precio_final'], 0.0 if vale else 15.0)
                if not vale:
                    self.assertEqual(resultado['motivo'], P.SIN_PROMOCION)
                    self.assertEqual(resultado['frase'], '', 'sin promoción vigente no se dice nada de promoción')

    def test_sin_promocion_queda_el_precio_normal(self):
        resultado = P.aplicar(None, 15.0, 'Panamá', 'San Miguelito', HOY, compra(500))
        self.assertEqual((resultado['hay_promocion'], resultado['aplica'], resultado['precio_final'],
                          resultado['ahorro'], resultado['frase']), (False, False, 15.0, 0.0, ''))
        self.assertEqual(papeles(P.respaldo(resultado)), (15.0, None, None, False, False, None, None))

    # --- El mínimo: estrictamente mayor, con o sin ITBMS -----------------------------------------------------------
    def test_en_el_limite_de_200_no_aplica_y_un_centavo_mas_si(self):
        en_el_limite = self.aplicar(datos=compra(200.0))
        self.assertFalse(en_el_limite['aplica'])
        self.assertEqual(en_el_limite['motivo'], P.MONTO)
        self.assertEqual(en_el_limite['precio_final'], 15.0)
        self.assertIn('es para compras de más de $200 sin ITBMS', en_el_limite['frase'])
        self.assertIn('tu cotización suma $200 sin ITBMS', en_el_limite['frase'])
        self.assertNotIn('gratis', en_el_limite['frase'].lower())
        un_centavo_mas = self.aplicar(datos=compra(200.01))
        self.assertTrue(un_centavo_mas['aplica'])
        self.assertEqual(un_centavo_mas['motivo'], P.GRATIS)

    def test_se_mide_sin_itbms_aunque_con_itbms_pase_del_minimo(self):
        # $190 + 7 % = $203.30: con ITBMS pasaría, pero la dueña dijo «sin ITBMS».
        resultado = self.aplicar(datos=compra(190.0, 203.30))
        self.assertFalse(resultado['aplica'])
        self.assertEqual(resultado['compra_medida'], 190.0)
        self.assertEqual(resultado['mide'], 'sin_itbms')

    def test_si_gerencia_elige_con_itbms_se_mide_con_itbms(self):
        con_itbms = dict(NOVIEMBRE, mide='con_itbms')
        resultado = self.aplicar(datos=compra(190.0, 203.30), promocion=con_itbms)
        self.assertTrue(resultado['aplica'])
        self.assertEqual(resultado['compra_medida'], 203.30)
        self.assertIn('pasa de $200 con ITBMS', resultado['frase'])

    def test_el_dinero_se_cuenta_en_centavos(self):
        # 0.1 + 0.2 en punto flotante es 0.30000000000000004: en centavos es 0.30, y 200.004 es 200.00 (no pasa).
        self.assertFalse(self.aplicar(datos=compra(200.004))['aplica'])
        self.assertTrue(self.aplicar(datos=compra(200.005))['aplica'])
        resultado = self.aplicar(precio=0.1 + 0.2, prov='Colón', dist='Colón', datos=compra(300))
        self.assertEqual(resultado['precio_normal'], 0.3)
        self.assertEqual(resultado['precio_final'], 0.0)

    # --- Colchón ---------------------------------------------------------------------------------------------------
    def test_con_colchon_no_aplica(self):
        resultado = self.aplicar(datos=compra(900.0, colchon=True))
        self.assertFalse(resultado['aplica'])
        self.assertEqual(resultado['motivo'], P.COLCHON)
        self.assertEqual(resultado['precio_final'], 15.0)
        self.assertIn('no aplica cuando la compra lleva colchón', resultado['frase'])
        self.assertFalse(resultado['menciona_gratis'])

    def test_si_la_promocion_no_excluye_el_colchon_aplica_igual(self):
        resultado = self.aplicar(datos=compra(900.0, colchon=True), promocion=dict(NOVIEMBRE, excluye_colchon=False))
        self.assertTrue(resultado['aplica'])

    # --- Zonas: gratis o abono -------------------------------------------------------------------------------------
    def test_gratis_en_toda_la_provincia_de_panama_y_en_panama_oeste(self):
        for prov, dist in (('Panamá', 'Panamá'), ('Panamá', 'Chepo'), ('Panamá', 'San Miguelito'),
                           ('Panamá Oeste', 'La Chorrera'), ('PANAMA OESTE', 'Arraiján'), ('panama', 'Taboga')):
            with self.subTest(prov=prov, dist=dist):
                resultado = self.aplicar(precio=35.0, prov=prov, dist=dist, datos=compra(250.0))
                self.assertEqual((resultado['motivo'], resultado['precio_final'], resultado['ahorro']),
                                 (P.GRATIS, 0.0, 35.0))
                self.assertEqual(resultado['frase'], "Con la promoción de noviembre, como tu compra pasa de $200 sin "
                                                     "ITBMS, D'CASA te regala el envío: te sale gratis (te ahorras "
                                                     "$35). La promoción es hasta el 30 de noviembre; después, el "
                                                     "envío vuelve a su precio normal.")
                self.assertEqual(papeles(P.respaldo(resultado)), (35.0, 0.0, 35.0, True, False, 200.0, None))

    def test_abono_de_20_en_colon_y_el_resto(self):
        for prov in ('Colón', 'Coclé', 'Provincia Lejana'):
            with self.subTest(prov=prov):
                resultado = self.aplicar(precio=90.0, prov=prov, dist='Algún distrito', datos=compra(450.0))
                self.assertEqual((resultado['motivo'], resultado['precio_final'], resultado['ahorro']),
                                 (P.ABONO, 70.0, 20.0))
                self.assertEqual(resultado['frase'], "Con la promoción de noviembre, como tu compra pasa de $200 sin "
                                                     "ITBMS, D'CASA te abona $20 del envío: te queda en $70. La "
                                                     "promoción es hasta el 30 de noviembre; después, el envío vuelve "
                                                     "a su precio normal.")
                self.assertFalse(resultado['menciona_gratis'], 'en una zona con abono no se dice «gratis»')
                # Lo abonado ($20) es un ahorro, nunca el costo (revisión adversarial I1).
                self.assertEqual(papeles(P.respaldo(resultado)), (90.0, 70.0, 20.0, False, False, 200.0, None))

    def test_el_abono_nunca_deja_el_envio_en_negativo(self):
        resultado = self.aplicar(precio=12.5, prov='Colón', dist='Colón', datos=compra(450.0))
        self.assertEqual((resultado['motivo'], resultado['precio_final'], resultado['ahorro']), (P.GRATIS, 0.0, 12.5))
        self.assertIn('te sale gratis (te ahorras $12.50)', resultado['frase'])
        self.assertTrue(resultado['menciona_gratis'])

    def test_distritos_gratis_ademas_de_las_provincias(self):
        promocion = dict(NOVIEMBRE, provincias_gratis=['Panamá'], distritos_gratis=['Arraiján'])
        self.assertEqual(self.aplicar(precio=35.0, prov='Panamá Oeste', dist='Arraiján', datos=compra(300),
                                      promocion=promocion)['motivo'], P.GRATIS)
        self.assertEqual(self.aplicar(precio=35.0, prov='Panamá Oeste', dist='La Chorrera', datos=compra(300),
                                      promocion=promocion)['motivo'], P.ABONO)

    def test_sin_abono_fuera_de_las_zonas_gratis_no_hay_beneficio(self):
        resultado = self.aplicar(prov='Colón', dist='Colón', datos=compra(300), promocion=dict(NOVIEMBRE, abono=0))
        self.assertEqual((resultado['motivo'], resultado['aplica'], resultado['precio_final'], resultado['frase']),
                         (P.ZONA_SIN_BENEFICIO, False, 15.0, ''))

    def test_un_envio_que_se_cotiza_aparte_no_tiene_promocion_que_calcular(self):
        resultado = self.aplicar(precio=None, datos=compra(300))
        self.assertEqual((resultado['motivo'], resultado['aplica'], resultado['precio_final']),
                         (P.SIN_PRECIO, False, None))
        self.assertEqual(papeles(P.respaldo(resultado)), (None, None, None, False, False, None, None))

    def test_un_envio_en_cero_o_negativo_nunca_da_te_ahorras_0_ni_montos_negativos(self):
        """Revisión adversarial (M7): con $0 o menos no hay nada que rebajar ni que decir."""
        for precio in (0.0, -50.0, 0.004):
            for datos in (compra(300), None):
                with self.subTest(precio=precio, compra=datos):
                    resultado = self.aplicar(precio=precio, datos=datos)
                    self.assertEqual((resultado['motivo'], resultado['aplica'], resultado['ahorro'],
                                      resultado['precio_normal'], resultado['frase']),
                                     (P.SIN_PRECIO, False, 0.0, None, ''))
                    self.assertEqual(papeles(P.respaldo(resultado))[:4], (None, None, None, False))
                    self.assertEqual(P.con_el_precio_normal(resultado, 'Villa Prueba'), '')

    def test_el_respaldo_de_cada_lugar_lleva_sus_nombres_su_desglose_y_el_minimo_o_la_compra(self):
        """Revisión adversarial (I1, I2, M1): cada cifra con su papel y su lugar, para la guardia del Worker."""
        chica = self.aplicar(precio=45.0, datos=compra(90.0))
        lugar = P.respaldo(chica, nombres=('Costa Inventada', '', 'Costa Inventada', 'Panamá'),
                           cargos=[{'nombre': 'tarifa', 'monto': 40}, {'nombre': 'peaje', 'monto': 5}],
                           lleva_itbms=True)
        self.assertEqual(lugar['nombres'], ['Costa Inventada', 'Panamá'], 'sin vacíos ni repetidos')
        self.assertEqual(papeles(lugar), (45.0, None, None, False, False, 200.0, 90.0),
                         'la frase dice el mínimo y lo que suma la cotización')
        self.assertEqual(lugar['cargos'], [{'nombre': 'tarifa', 'monto': 40.0}, {'nombre': 'peaje', 'monto': 5.0}])
        self.assertTrue(lugar['lleva_itbms'])
        colchon = self.aplicar(precio=45.0, datos=compra(900.0, colchon=True))
        self.assertEqual(papeles(P.respaldo(colchon)), (45.0, None, None, False, False, None, None))

    def test_m7_nunca_una_cifra_negativa_de_la_compra(self):
        """Segunda vuelta (M-7): una compra en negativo (más rebaja que productos) no dice «tu cotización suma $-50»."""
        resultado = self.aplicar(datos=compra(-50.0))
        self.assertEqual((resultado['motivo'], resultado['compra_medida']), (P.MONTO, 0.0))
        self.assertEqual(resultado['frase'], 'La promoción de noviembre es para compras de más de $200 sin ITBMS, así '
                                             'que el envío va a su precio normal.')
        self.assertNotIn('-', resultado['frase'])
        self.assertIsNone(P.respaldo(resultado)['compra'])

    def test_lo_prometido_con_los_terminos_guardados(self):
        """Segunda vuelta (I-1, I-2): lo sumado se revisa con sus términos guardados, no con la promoción de hoy."""
        sumado = self.aplicar(precio=90.0, prov='Colón', dist='Colón', datos=compra(300.0))
        terminos = P.terminos(NOVIEMBRE, sumado, date(2026, 11, 28), promocion_id=7)
        self.assertEqual(terminos, {
            'promocion_id': 7, 'nombre': 'Envío Gratis Todo Noviembre', 'desde': '2026-11-01', 'hasta': '2026-11-30',
            'minimo': 200.0, 'mide': 'sin_itbms', 'zona': 'abono', 'abono': 20.0, 'excluye_colchon': True,
            'sumada_el': '2026-11-28'})
        # Sin mirar la fecha (eso lo decide quien llama: la cotización no venció) y con la compra de ahora.
        ahora = P.con_lo_prometido(terminos, 90.0, compra(250.0))
        self.assertEqual((ahora['aplica'], ahora['ahorro'], ahora['precio_final']), (True, 20.0, 70.0))
        self.assertEqual(P.con_lo_prometido(terminos, 90.0, compra(150.0))['motivo'], P.MONTO)
        self.assertEqual(P.con_lo_prometido(terminos, 90.0, compra(300.0, colchon=True))['motivo'], P.COLCHON)
        self.assertEqual(P.con_lo_prometido(terminos, 0.0, compra(300.0))['motivo'], P.SIN_PRECIO)
        self.assertEqual(P.recordar(terminos, ahora),
                         "Tu cotización ya tiene la promoción de noviembre, así que D'CASA te abona $20 del envío: te "
                         'queda en $70.')
        self.assertEqual(P.recordar(terminos, P.con_lo_prometido(terminos, 90.0, compra(150.0))), '')

    # --- Sin cotización todavía: las condiciones ------------------------------------------------------------------
    def test_sin_compra_dice_las_condiciones_y_no_dice_que_aplica(self):
        gratis = self.aplicar(precio=15.0)
        self.assertEqual((gratis['motivo'], gratis['aplica'], gratis['condicional'], gratis['precio_final'],
                          gratis['precio_si_aplica']), (P.SIN_COMPRA, False, True, None, 0.0))
        self.assertEqual(gratis['frase'], "Con la promoción de noviembre, en compras de más de $200 sin ITBMS, D'CASA "
                                          "te regala el envío: te sale gratis (te ahorras $15). La promoción es hasta "
                                          "el 30 de noviembre; después, el envío vuelve a su precio normal. No aplica "
                                          "si la compra lleva colchón.")
        self.assertEqual(papeles(P.respaldo(gratis)), (15.0, 0.0, 15.0, True, True, 200.0, None))
        abono = self.aplicar(precio=90.0, prov='Colón', dist='Colón')
        self.assertEqual(abono['frase'], "Con la promoción de noviembre, en compras de más de $200 sin ITBMS, D'CASA "
                                         "te abona $20 del envío: te queda en $70. La promoción es hasta el 30 de "
                                         "noviembre; después, el envío vuelve a su precio normal. No aplica si la "
                                         "compra lleva colchón.")
        self.assertEqual(papeles(P.respaldo(abono)), (90.0, 70.0, 20.0, False, True, 200.0, None),
                         'sin compra: lo que quedaría y lo que se abonaría, con la condición')

    def test_la_frase_completa_dice_el_precio_normal_lo_que_resta_dcasa_y_hasta_cuando(self):
        """Pedido de la dueña (2026-11-12): que no se lea como si no se le restara nada al envío."""
        abono = self.aplicar(precio=105.0, prov='Colón', dist='Colón', datos=compra(450.0))
        self.assertEqual(P.con_el_precio_normal(abono, 'Sabanitas (Colón)'),
                         "El envío a Sabanitas (Colón) cuesta normalmente $105. Con la promoción de noviembre, como "
                         "tu compra pasa de $200 sin ITBMS, D'CASA te abona $20 del envío: te queda en $85. La "
                         "promoción es hasta el 30 de noviembre; después, el envío vuelve a su precio normal.")
        con_cargos = P.con_el_precio_normal(abono, 'Sabanitas (Colón)', 'Tarifa $100 + peaje $5.')
        self.assertTrue(con_cargos.startswith('El envío a Sabanitas (Colón) cuesta normalmente $105. Tarifa $100 + '
                                              'peaje $5. Con la promoción de noviembre'))
        for sin_beneficio in (self.aplicar(datos=compra(90.0)), self.aplicar(datos=compra(900.0, colchon=True)),
                              self.aplicar(fecha=date(2026, 12, 1))):
            with self.subTest(motivo=sin_beneficio['motivo']):
                self.assertEqual(P.con_el_precio_normal(sin_beneficio, 'Villa Lucre'), '', 'sin beneficio, nada')
        dos_meses = dict(NOVIEMBRE, hasta=date(2026, 12, 5))
        self.assertIn('Con la promoción de envío, ', self.aplicar(promocion=dos_meses)['frase'])
        self.assertIn('La promoción es hasta el 5 de diciembre;', self.aplicar(promocion=dos_meses)['frase'])

    def test_fechas_de_varios_meses_y_varios_anos(self):
        self.assertEqual(P.fecha_texto(date(2026, 11, 25), date(2026, 12, 2)), 'del 25 de noviembre al 2 de diciembre')
        self.assertEqual(P.fecha_texto(date(2026, 12, 26), date(2027, 1, 5)),
                         'del 26 de diciembre de 2026 al 5 de enero de 2027')
