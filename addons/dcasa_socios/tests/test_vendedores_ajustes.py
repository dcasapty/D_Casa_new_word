"""Ajustes › Programa de vendedores: Gerencia cambia las cifras desde una pantalla y los cambios solo rigen hacia
adelante. Se prueba con las cifras REALES de puntos.json (la capa de ajustes va encima de ellas), sin parches."""
import json
import os
import re
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import mute_logger

from ..models import reglas as R
from ..models import reglas_ajustes as A
from ..models import reglas_vendedores as RV
from .common import SociosCommon

LOGGER_REGLAS = 'odoo.addons.dcasa_socios.models.vend_reglas'
PIN = '482915'


class AjustesCommon(SociosCommon):
    """Un negocio con las reglas de fábrica, una vendedora (Ana), Gerencia, un administrador y una vendedora de caja."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gerencia = new_test_user(cls.env, login='ajustes_gerencia', name='Marcial Gerencia',
                                     groups='base.group_user,dcasa_base.group_gerencia')
        cls.admin = new_test_user(cls.env, login='ajustes_admin', name='Admin Sistema', groups='base.group_system')
        cls.caja = new_test_user(cls.env, login='ajustes_caja', name='Caja Vendedora',
                                 groups='base.group_user,sales_team.group_sale_salesman')
        cls.Reglas = cls.env['dcasa.vend.reglas']

    def setUp(self):
        super().setUp()
        # El freno de todo el programa depende de lo vendido en la tienda en 30 días (en una base de pruebas casi vacía
        # se pasaría con una sola venta): aquí se mide lo que Gerencia ajusta, no ese freno.
        freno = patch.object(type(self.env['dcasa.vend.comision']), '_datos_del_freno_global',
                             return_value=(0, 10**12))
        freno.start()
        self.addCleanup(freno.stop)
        self.ana = self.vendedor('Ana Vendedora', '8-111-111', '6100-0001')
        self._clientes = 0

    # --- ayudas -------------------------------------------------------------------------------------------------

    def cliente_nuevo(self):
        self._clientes += 1
        return self.env['res.partner'].create({'name': f'Cliente {self._clientes}',
                                               'phone': f'6200-{self._clientes:04d}'})

    def vender(self, vendedor, precio=100.0):
        """Una venta a un cliente nuevo con el código del vendedor, ya pagada. Devuelve su comisión directa."""
        factura = self.factura(partner=self.cliente_nuevo(), precio=precio, vendedor=vendedor)
        return factura.dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'directa')

    def abrir(self, usuario=None, **cambios):
        """La pantalla como la abre el navegador (valores de ``default_get``), más lo que la persona cambió."""
        Ajustes = self.env['dcasa.vend.ajustes'].with_user(usuario or self.gerencia)
        valores = Ajustes.default_get(list(A.CLAVES_DE_PANTALLA_ODOO))
        valores.update({f'dcasa_vend_{clave}': valor for clave, valor in cambios.items()})
        return Ajustes.create(valores)

    def guardar(self, usuario=None, motivo=None, **cambios):
        """Abre la pantalla, cambia cosas y pulsa Guardar. Devuelve la versión nueva (vacía si nada cambió)."""
        pantalla = self.abrir(usuario, **cambios)
        if motivo:
            pantalla.dcasa_vend_motivo = motivo
        antes = self.Reglas.search([])
        pantalla.execute()
        return self.Reglas.search([]) - antes

    def versiones(self):
        return self.Reglas.search([], order='numero')

    def vigentes(self):
        return RV.seccion(self.Reglas._vigentes())

    @contextmanager
    def en(self, momento):
        """Por dentro, el reloj del servidor marca ``momento``."""
        with patch.object(fields.Datetime, 'now', return_value=momento):
            yield


@tagged('post_install', '-at_install')
class TestVersionesDeReglas(AjustesCommon):
    """El modelo de versiones: fecha de vigencia, historial que no se edita ni se borra, filas dañadas."""

    def test_sin_ajustes_rige_puntos_json_tal_cual(self):
        self.assertFalse(self.versiones())
        self.assertEqual(self.Reglas._vigentes(), R.cargar_reglas())
        self.assertEqual(self.Reglas._numero_vigente(), 0)

    def test_cada_version_se_numera_y_guarda_quien_cuando_y_por_que(self):
        v1 = self.Reglas._registrar('ajuste', {'comision.puntosPorDolarNeto': 4.5},
                                    [{'campo': 'Comisión base', 'antes': '4 %', 'despues': '4.5 %'}],
                                    '  subimos la base  ', R.cargar_reglas())
        v2 = self.Reglas._registrar('ajuste', {}, [], None, R.cargar_reglas())
        self.assertEqual((v1.numero, v2.numero), (1, 2))
        self.assertEqual((v1.motivo, v2.motivo, v1.tipo, v1.fabrica_version), ('subimos la base', False, 'ajuste', 5))
        self.assertEqual(v1.autor, self.env.user.name)
        self.assertLessEqual(abs((v1.vigente_desde - fields.Datetime.now()).total_seconds()), 5)
        self.assertEqual(json.loads(v1.ajustes), {'comision.puntosPorDolarNeto': 4.5})
        self.assertIn('4.5 %', v1.cambios_html)
        self.assertEqual(v1.resumen, 'Comisión base')

    def test_la_version_vigente_depende_de_la_fecha(self):
        ahora = fields.Datetime.now()
        base = {'tipo': 'ajuste', 'autor': 'x'}
        v1 = self.Reglas.sudo().create({**base, 'ajustes': '{"comision.puntosPorDolarNeto": 4.5}'})
        v2 = self.Reglas.sudo().create({**base, 'ajustes': '{"comision.puntosPorDolarNeto": 4.8}',
                                        'vigente_desde': ahora + timedelta(days=10)})
        self.assertEqual(self.vigentes()['comision']['puntosPorDolarNeto'], 4.5, 'La v2 todavía no empieza')
        self.assertEqual(RV.ajuste_aplicado(self.Reglas._vigentes()), v1.numero)
        a_los_10_dias = ahora + timedelta(days=10, seconds=1)
        self.assertEqual(RV.seccion(self.Reglas._vigentes(a_los_10_dias))['comision']['puntosPorDolarNeto'], 4.8)
        self.assertEqual(RV.ajuste_aplicado(self.Reglas._vigentes(a_los_10_dias)), v2.numero)
        antes_de_todo = ahora - timedelta(days=1)
        self.assertEqual(RV.seccion(self.Reglas._vigentes(antes_de_todo))['comision']['puntosPorDolarNeto'], 4)
        self.assertEqual(self.versiones().mapped('rige_ahora'), [True, False])

    def test_los_cambios_solo_rigen_hacia_adelante(self):
        ahora = fields.Datetime.now()
        with self.assertRaisesRegex(UserError, 'solo rige hacia adelante'):
            self.Reglas.sudo().create({'tipo': 'ajuste', 'autor': 'x', 'ajustes': '{}',
                                       'vigente_desde': ahora - timedelta(days=1)})
        self.Reglas.sudo().create({'tipo': 'ajuste', 'autor': 'x', 'ajustes': '{}',
                                   'vigente_desde': ahora + timedelta(days=5)})
        with self.assertRaisesRegex(UserError, 'cambio programado'):
            self.Reglas.sudo().create({'tipo': 'ajuste', 'autor': 'x', 'ajustes': '{}'})
        self.assertEqual(len(self.versiones()), 1)

    def test_el_historial_no_se_edita_ni_se_borra_ni_con_permisos_de_sistema(self):
        v = self.Reglas._registrar('ajuste', {}, [], None, R.cargar_reglas())
        for contexto in (self.env, self.env(su=True)):
            with self.assertRaisesRegex(UserError, 'no se edita'):
                v.with_env(contexto).write({'motivo': 'otro'})
            with self.assertRaisesRegex(UserError, 'no se borra'):
                v.with_env(contexto).unlink()
        self.assertEqual(self.versiones(), v)

    def test_el_numero_de_version_es_unico(self):
        v = self.Reglas._registrar('ajuste', {}, [], None, R.cargar_reglas())
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError), self.cr.savepoint():
            self.cr.execute(
                "INSERT INTO dcasa_vend_reglas (numero, vigente_desde, tipo, autor) VALUES (%s, now(), 'ajuste', 'x')",
                [v.numero])

    def test_una_fila_danada_no_rompe_nada_y_rige_la_anterior(self):
        buena = self.Reglas._registrar('ajuste', {'comision.puntosPorDolarNeto': 4.5}, [], None, R.cargar_reglas())
        danada = self.Reglas._registrar('ajuste', {'comision.puntosPorDolarNeto': 4.8}, [], None, R.cargar_reglas())
        self.cr.execute('UPDATE dcasa_vend_reglas SET ajustes = %s WHERE id = %s', ['{esto no es json', danada.id])
        self.Reglas.invalidate_model()
        with self.assertLogs(LOGGER_REGLAS, 'ERROR') as registro:
            reglas = self.Reglas._vigentes()
        self.assertEqual(RV.seccion(reglas)['comision']['puntosPorDolarNeto'], 4.5)
        self.assertEqual(RV.ajuste_aplicado(reglas), buena.numero)
        self.assertIn('dañadas', registro.output[0])

    def test_una_fila_manipulada_no_enciende_el_canje_de_externos_ni_el_efectivo(self):
        manipulada = {'canje.externosHabilitado': True, 'canje.efectivoHabilitado': True,
                      'comision.puntosPorDolarNeto': 4.5}
        self.Reglas._registrar('ajuste', manipulada, [], None, R.cargar_reglas())
        v = self.vigentes()
        self.assertEqual(v['comision']['puntosPorDolarNeto'], 4.5)
        self.assertIs(v['canje']['externosHabilitado'], False)
        self.assertIs(v['canje']['efectivoHabilitado'], False)

    def test_si_leer_los_ajustes_falla_rige_la_fabrica_y_se_dice(self):
        self.Reglas._registrar('ajuste', {'comision.puntosPorDolarNeto': 4.5}, [], None, R.cargar_reglas())
        with patch.object(A, 'reglas_efectivas', side_effect=RuntimeError('algo se rompió')), \
                self.assertLogs(LOGGER_REGLAS, 'ERROR'):
            reglas = self.Reglas._vigentes()
        self.assertEqual(reglas, R.cargar_reglas())


@tagged('post_install', '-at_install')
class TestLaPantallaDeGerencia(AjustesCommon):

    def test_la_pantalla_abre_con_lo_que_rige(self):
        pantalla = self.abrir()
        self.assertEqual((pantalla.dcasa_vend_comision_base, pantalla.dcasa_vend_compra_minima,
                          pantalla.dcasa_vend_tope_base), (4.0, 20.0, 200.0))
        self.assertEqual((pantalla.dcasa_vend_esc2_desde, pantalla.dcasa_vend_esc2_tasa, pantalla.dcasa_vend_esc2_tope),
                         (9000.0, 6.5, 500.0))
        self.assertTrue(pantalla.dcasa_vend_programa)
        self.assertTrue(pantalla.dcasa_vend_cargado)
        self.assertEqual(pantalla.dcasa_vend_version_vista, 0)
        self.assertIn('Rigen los valores de fábrica', pantalla.dcasa_vend_estado)
        self.assertIn('versión 5', pantalla.dcasa_vend_estado)

    def test_los_interruptores_legales_se_ven_apagados(self):
        pantalla = self.abrir()
        self.assertEqual((pantalla.dcasa_vend_externos, pantalla.dcasa_vend_efectivo), (False, False))
        for nombre in ('dcasa_vend_externos', 'dcasa_vend_efectivo'):
            self.assertTrue(pantalla._fields[nombre].readonly, f'{nombre} es de solo lectura')

    def test_guardar_un_cambio_crea_una_version_con_su_historial(self):
        version = self.guardar(comision_base=4.5, motivo='Subimos la base para la temporada')
        self.assertEqual(len(version), 1)
        self.assertEqual((version.numero, version.tipo, version.autor), (1, 'ajuste', 'Marcial Gerencia'))
        self.assertEqual(version.motivo, 'Subimos la base para la temporada')
        self.assertEqual(json.loads(version.cambios), [{
            'campo': 'Comisión base (% de la venta neta)', 'ruta': 'comision.puntosPorDolarNeto',
            'antes': '4 %', 'despues': '4.5 %'}])
        self.assertEqual(json.loads(version.ajustes), {'comision.puntosPorDolarNeto': 4.5})
        self.assertEqual(self.vigentes()['comision']['puntosPorDolarNeto'], 4.5)
        self.assertEqual(version.fabrica_version, 5)
        # Lo demás sigue siendo de fábrica.
        self.assertEqual(self.vigentes()['comision']['escalones'],
                         RV.seccion(R.cargar_reglas())['comision']['escalones'])
        # La pantalla, vuelta a abrir, muestra la versión que rige y quién la hizo.
        otra = self.abrir()
        self.assertEqual((otra.dcasa_vend_comision_base, otra.dcasa_vend_version_vista), (4.5, 1))
        self.assertIn('versión 1', otra.dcasa_vend_estado)
        self.assertIn('Marcial Gerencia', otra.dcasa_vend_estado)

    def test_los_cambios_se_acumulan_y_dejan_dos_versiones(self):
        self.guardar(comision_base=4.5)
        self.guardar(vinculo_meses=6, motivo='Menos meses')
        self.assertEqual(self.versiones().mapped('numero'), [1, 2])
        self.assertEqual(json.loads(self.versiones()[1].ajustes),
                         {'comision.puntosPorDolarNeto': 4.5, 'vinculacion.meses': 6})
        self.assertEqual(json.loads(self.versiones()[1].cambios)[0]['antes'], '12 meses')
        v = self.vigentes()
        self.assertEqual((v['comision']['puntosPorDolarNeto'], v['vinculacion']['meses']), (4.5, 6))

    def test_sin_cambios_no_se_crea_ninguna_version(self):
        self.assertFalse(self.guardar())
        self.assertFalse(self.versiones())
        self.guardar(comision_base=4.5)
        self.assertFalse(self.guardar(), 'Guardar otra vez lo mismo no es un cambio')
        self.assertEqual(len(self.versiones()), 1)

    def test_un_cambio_nunca_altera_lo_ya_acreditado(self):
        antes = self.vender(self.ana)
        self.assertEqual((antes.puntos, antes.reglas_ajuste), (400, 0))
        saldo_antes = self.ana.dcasa_vend_saldo
        asiento = self.env['dcasa.vend.movimiento'].search([('comision_id', '=', antes.id)])
        disponible_desde = asiento.disponible_desde
        self.guardar(comision_base=4.5, retencion_dias=10)
        self.guardar(comision_base=4.2)
        self.env.invalidate_all()
        self.assertEqual((antes.puntos, antes.reglas_ajuste, antes.reglas_version), (400, 0, 5))
        self.assertEqual(self.ana.dcasa_vend_saldo, saldo_antes, 'El saldo del vendedor no se mueve con un cambio')
        self.assertEqual(asiento.disponible_desde, disponible_desde, 'La ventana de devoluciones tampoco')
        self.assertEqual(self.env['dcasa.vend.movimiento'].search_count([('partner_id', '=', self.ana.id)]), 1)

    def test_lo_que_se_paga_desde_el_cambio_usa_las_cifras_nuevas(self):
        self.vender(self.ana)
        self.guardar(comision_base=4.5)
        despues = self.vender(self.ana)
        self.assertEqual((despues.puntos, despues.reglas_ajuste), (450, 1))
        self.guardar(comision_base=4.2)
        ultima = self.vender(self.ana)
        self.assertEqual((ultima.puntos, ultima.reglas_ajuste), (420, 2))
        self.assertEqual(self.ana.dcasa_vend_saldo, 400 + 450 + 420)

    def test_la_comision_usa_la_version_vigente_cuando_la_venta_se_paga(self):
        sin_pagar = self.factura(partner=self.cliente_nuevo(), vendedor=self.ana, pagar=False)
        self.guardar(comision_base=4.5)
        self.pagar(sin_pagar)
        comision = sin_pagar.dcasa_vend_comision_ids
        self.assertEqual((comision.puntos, comision.reglas_ajuste), (450, 1))

    def test_la_escalera_nueva_manda_en_la_proxima_venta(self):
        primera = self.vender(self.ana)                                  # $100 vendidos: sigue en la base
        self.assertEqual(primera.puntos, 400)
        self.guardar(esc1_desde=100)                                     # el escalón 1 empieza en $100
        segunda = self.vender(self.ana)
        self.assertEqual(segunda.puntos, 500, 'Ya vendió $100: gana 5 %, el escalón 1')
        self.assertEqual(primera.puntos, 400)

    def test_el_patrocinio_y_sus_requisitos_se_ajustan(self):
        juan = self.vendedor('Juan Directo', '8-222-222', '6100-0002', patrocinador=self.ana)
        self.vender(self.ana)                                            # Ana vendió a 1 cliente en el mes
        sin_patrocinio = self.vender(juan)
        self.assertEqual(self.comisiones(self.ana, 'patrocinio').resultado, 'patrocinador-sin-ventas',
                         'La fábrica pide 2 clientes distintos al patrocinador')
        self.guardar(ventas_propias=1)
        self.vender(juan)
        patrocinio = self.comisiones(self.ana, 'patrocinio').filtered(lambda c: c.puntos)
        self.assertEqual((len(patrocinio), patrocinio.puntos, patrocinio.resultado), (1, 80, 'pagada'))
        self.assertEqual(sin_patrocinio.puntos, 400)

    def test_apagar_el_programa_no_acredita_y_la_venta_se_cobra_igual(self):
        self.guardar(programa=False)
        factura = self.factura(partner=self.cliente_nuevo(), vendedor=self.ana)
        self.assertEqual(factura.payment_state, 'paid')
        self.assertFalse(factura.dcasa_vend_comision_ids)
        self.guardar(programa=True)
        self.assertEqual(self.vender(self.ana).puntos, 400)

    def test_la_vigencia_del_codigo_y_los_canjes_leen_lo_que_rige(self):
        premio = self.env['dcasa.premio'].create({'name': 'Cama box Twin', 'tipo': 'producto', 'puntos': 3000,
                                                  'costo': 14.0, 'para_vendedores': True})
        elena = self.vendedor('Elena Empleada', '8-555-555', '6100-0055', tipo='empleado')
        self.env['dcasa.vend.movimiento']._asentar(
            elena, 'ajuste', 9000, 'prueba', motivo='Saldo', disponible_desde=fields.Datetime.now() - timedelta(days=1))
        self.guardar(vigencia_horas=48, canjes_mes=1)
        canje = self.env['dcasa.vend.canje']._pedir(elena, premio)
        horas = (canje.expira_en - canje.solicitado_en).total_seconds() / 3600
        self.assertEqual(horas, 48)
        otro = self.env['dcasa.premio'].create({'name': 'Cama box Full', 'tipo': 'producto', 'puntos': 4000,
                                                'costo': 20.0, 'para_vendedores': True})
        with self.assertRaisesRegex(UserError, 'máximo de 1 canjes'):
            self.env['dcasa.vend.canje']._pedir(elena, otro)
        self.guardar(canjes_mes=2, canje_minimo=50)
        with self.assertRaisesRegex(UserError, 'canje mínimo es de 5,000 puntos'):
            self.env['dcasa.vend.canje']._pedir(elena, otro)

    def test_el_canje_de_externos_sigue_apagado_aunque_haya_ajustes(self):
        premio = self.env['dcasa.premio'].create({'name': 'Cama box Twin', 'tipo': 'producto', 'puntos': 3000,
                                                  'costo': 14.0, 'para_vendedores': True})
        self.env['dcasa.vend.movimiento']._asentar(
            self.ana, 'ajuste', 9000, 'prueba', motivo='Saldo',
            disponible_desde=fields.Datetime.now() - timedelta(days=1))
        self.guardar(canjes_mes=2)
        with self.assertRaisesRegex(UserError, 'externos todavía no está habilitado'):
            self.env['dcasa.vend.canje']._pedir(self.ana, premio)

    def test_el_cupo_de_directos_lo_manda_lo_que_rige(self):
        self.guardar(directos=1)
        self.vendedor('Juan Directo', '8-222-222', '6100-0002', patrocinador=self.ana)
        with self.assertRaisesRegex(UserError, 'ya tiene 1 vendedores patrocinados'):
            self.vendedor('Luis Directo', '8-333-333', '6100-0003', patrocinador=self.ana)

    def test_un_cliente_ya_ligado_conserva_el_plazo_con_que_se_ligo(self):
        """Cambiar los meses del vínculo vale para los clientes que se liguen después, no recorta los que ya estaban."""
        cliente = self.cliente_nuevo()
        factura = self.factura(partner=cliente, vendedor=self.ana)           # liga al cliente por 12 meses (fábrica)
        ligado_en = cliente.dcasa_vendedor_ligado_en
        self.assertEqual(cliente.dcasa_vendedor_ligado_id, self.ana)
        with self.en(ligado_en + timedelta(days=1)):
            self.guardar(vinculo_meses=6)
        siguiente = self.env['account.move'].new({'partner_id': cliente.id})
        Comision = self.env['dcasa.vend.comision']
        with self.en(ligado_en + timedelta(days=200)):                       # pasaron 6 meses, no 12
            self.assertEqual(Comision._vendedor_de_la_factura(siguiente), (self.ana, 'vinculo'),
                             'Se ligó cuando eran 12 meses')
        # Un cliente que se liga DESPUÉS del cambio sí queda por 6 meses.
        cliente.sudo().write({'dcasa_vendedor_ligado_en': ligado_en + timedelta(days=2)})
        with self.en(ligado_en + timedelta(days=2 + 185)):
            self.assertEqual(Comision._vendedor_de_la_factura(siguiente), (self.env['res.partner'], False))
        with self.en(ligado_en + timedelta(days=2 + 170)):
            self.assertEqual(Comision._vendedor_de_la_factura(siguiente)[0], self.ana)
        self.assertTrue(factura.dcasa_vend_comision_ids)

    # --- Validaciones ----------------------------------------------------------------------------------------------

    def test_lo_que_no_cumple_los_limites_no_se_guarda_y_dice_que_corregir(self):
        casos = {
            'comision_base': (9, 'no puede ser mayor que el techo de costo por venta'),
            'techo': (40, 'no puede ser mayor que la ganancia que se supone'),
            'esc3_tasa': (9.5, 'Escalón 3: paga 9.5 %'),
            'patrocinio': (5, 'no puede ser mayor que la comisión base'),
            'directos': (6, 'no puede pasar de 5 vendedores'),
            'vigencia_horas': (0, 'no puede ser menos de 1 hora'),
            'esc2_desde': (3000, 'Escalón 2: tiene que empezar en una venta mayor'),
            'retencion_dias': (-1, 'no puede ser negativo'),
        }
        for campo, (valor, texto) in casos.items():
            with self.subTest(campo):
                with self.assertRaisesRegex(UserError, re.escape(texto)) as contexto:
                    self.guardar(**{campo: valor})
                self.assertIn('No se guardó nada', str(contexto.exception))
        self.assertFalse(self.versiones(), 'Ningún intento fallido deja una versión')
        self.assertEqual(self.vigentes(), RV.seccion(R.cargar_reglas()))

    def test_un_escalon_a_medias_no_se_guarda(self):
        with self.assertRaisesRegex(UserError, 'Escalón 4: llena cuánto hay que vender'):
            self.guardar(esc4_desde=5000)
        self.assertFalse(self.versiones())

    def test_todos_los_problemas_se_dicen_juntos(self):
        with self.assertRaises(UserError) as contexto:
            self.guardar(comision_base=9, directos=6)
        mensaje = str(contexto.exception)
        self.assertIn('techo', mensaje)
        self.assertIn('no puede pasar de 5 vendedores', mensaje)

    def test_los_interruptores_legales_no_se_encienden_desde_ajustes(self):
        version = self.guardar(comision_base=4.5, externos=True, efectivo=True)
        self.assertEqual(json.loads(version.ajustes), {'comision.puntosPorDolarNeto': 4.5})
        v = self.vigentes()
        self.assertEqual((v['canje']['externosHabilitado'], v['canje']['efectivoHabilitado']), (False, False))
        # Y solo con los dos «encendidos» en la pantalla tampoco se crea nada.
        self.assertFalse(self.guardar(externos=True, efectivo=True))

    def test_si_otra_persona_cambia_las_reglas_mientras_tanto_no_se_pisa_su_cambio(self):
        pantalla = self.abrir(comision_base=4.2)
        self.guardar(comision_base=4.5)                                     # otra persona guardó antes
        with self.assertRaisesRegex(UserError, 'Alguien cambió las reglas'):
            pantalla.execute()
        self.assertEqual(self.versiones().mapped('numero'), [1])
        self.assertEqual(self.vigentes()['comision']['puntosPorDolarNeto'], 4.5)

    def test_una_pantalla_que_no_cargo_las_cifras_no_guarda_nada(self):
        pantalla = self.env['dcasa.vend.ajustes'].with_user(self.gerencia).create(
            {'dcasa_vend_comision_base': 9, 'dcasa_vend_cargado': False})
        with self.assertRaisesRegex(UserError, 'no cargó las cifras'):
            pantalla.execute()
        self.assertFalse(self.versiones())

    def test_el_resumen_dice_el_costo_lo_que_cambia_y_lo_que_no_deja_guardar(self):
        sin_tocar = self.abrir().dcasa_vend_resumen
        self.assertIn('hasta 7.23 % de la venta neta', sin_tocar)
        self.assertIn('20.7 %', sin_tocar)
        self.assertIn('Cada 100 puntos valen $1', sin_tocar)
        self.assertIn('Todavía no cambiaste nada', sin_tocar)
        cambiado = self.abrir(comision_base=4.5).dcasa_vend_resumen
        self.assertIn('Vas a cambiar', cambiado)
        self.assertIn('Comisión base (% de la venta neta)', cambiado)
        self.assertIn('4 %', cambiado)
        malo = self.abrir(comision_base=9).dcasa_vend_resumen
        self.assertIn('Esto no se puede guardar todavía', malo)
        self.assertIn('techo', malo)
        caro = self.abrir(esc3_tasa=8.5).dcasa_vend_resumen
        self.assertIn('hasta 7.58 %', caro)

    # --- Volver a los valores de fábrica ----------------------------------------------------------------------------

    def test_volver_a_la_fabrica_crea_una_version_igual_al_json_y_no_borra_el_historial(self):
        self.guardar(comision_base=4.5, esc1_tasa=5.25)
        self.guardar(vinculo_meses=6)
        antes = self.versiones()
        pantalla = self.abrir()
        pantalla.dcasa_vend_motivo = 'Nos arrepentimos'
        pantalla.action_dcasa_vend_fabrica()
        nueva = self.versiones() - antes
        self.assertEqual((nueva.numero, nueva.tipo, nueva.motivo, nueva.ajustes),
                         (3, 'fabrica', 'Nos arrepentimos', '{}'))
        self.assertEqual(self.versiones()[:2], antes, 'Las versiones anteriores siguen ahí, intactas')
        self.assertEqual(self.vigentes(), RV.seccion(R.cargar_reglas()), 'Las reglas efectivas son las del JSON')
        self.assertEqual(RV.ajuste_aplicado(self.Reglas._vigentes()), 3)
        campos = {c['campo'] for c in json.loads(nueva.cambios)}
        self.assertEqual(campos, {'Comisión base (% de la venta neta)', 'Escalón 1',
                                  'Meses que el cliente queda ligado a su vendedor'})
        self.assertEqual(nueva.resumen, 'Volvieron los valores de fábrica')
        self.assertIn('Son los valores de fábrica', self.abrir().dcasa_vend_estado)
        # Y lo ya pagado no se mueve.
        self.assertEqual(self.vender(self.ana).puntos, 400)

    def test_si_ya_estan_los_valores_de_fabrica_no_hay_nada_que_devolver(self):
        with self.assertRaisesRegex(UserError, 'Ya están los valores de fábrica'):
            self.abrir().action_dcasa_vend_fabrica()
        self.assertFalse(self.versiones())

    def test_volver_a_la_fabrica_no_pisa_un_cambio_ajeno(self):
        pantalla = self.abrir()
        self.guardar(comision_base=4.5)
        with self.assertRaisesRegex(UserError, 'Alguien cambió las reglas'):
            pantalla.action_dcasa_vend_fabrica()

    def test_si_puntos_json_cambia_despues_del_ajuste_la_pantalla_avisa(self):
        self.guardar(comision_base=4.5)
        reglas = R.cargar_reglas()
        reglas['version'] = 6
        with patch('odoo.addons.dcasa_socios.models.reglas.cargar_reglas', return_value=reglas):
            self.assertIn('cambiaron a la versión 6', self.abrir().dcasa_vend_estado)

    # --- Un fallo de las reglas no rompe una venta -------------------------------------------------------------------

    def test_si_las_reglas_fallan_la_venta_se_cobra_igual(self):
        self.guardar(comision_base=4.5)
        with patch.object(type(self.Reglas), '_vigentes', side_effect=RuntimeError('fallo de reglas')), \
                self.assertLogs('odoo.addons.dcasa_socios.models.account_move_vend', 'ERROR'):
            factura = self.factura(partner=self.cliente_nuevo(), vendedor=self.ana)
        self.assertEqual(factura.payment_state, 'paid', 'El cobro nunca se frena por el programa')
        self.assertFalse(factura.dcasa_vend_comision_ids)

    def test_si_la_lectura_de_ajustes_falla_la_venta_se_cobra_y_se_paga_con_la_fabrica(self):
        self.guardar(comision_base=4.5)
        with patch.object(A, 'reglas_efectivas', side_effect=RuntimeError('fallo')), \
                self.assertLogs(LOGGER_REGLAS, 'ERROR'):
            factura = self.factura(partner=self.cliente_nuevo(), vendedor=self.ana)
        self.assertEqual(factura.payment_state, 'paid')
        self.assertEqual(factura.dcasa_vend_comision_ids.puntos, 400)

    def test_una_fila_danada_no_frena_la_venta(self):
        v = self.guardar(comision_base=4.5)
        self.cr.execute('UPDATE dcasa_vend_reglas SET ajustes = %s WHERE id = %s', ['[1, 2', v.id])
        self.Reglas.invalidate_model()
        with self.assertLogs(LOGGER_REGLAS, 'ERROR'):
            factura = self.factura(partner=self.cliente_nuevo(), vendedor=self.ana)
        self.assertEqual((factura.payment_state, factura.dcasa_vend_comision_ids.puntos), ('paid', 400))

    def test_el_panel_y_la_comision_leen_lo_mismo(self):
        self.guardar(comision_base=4.5)
        nivel = self.ana._dcasa_vend_resumen_panel()['nivel']
        self.assertEqual(nivel['puntos_por_dolar'], 4.5)
        self.assertEqual(self.vender(self.ana).puntos, 450)

    def test_el_panel_sigue_a_los_ajustes(self):
        self.guardar(comision_base=4.5, esc1_desde=100, esc1_tasa=5.5, directos=2)
        panel = self.ana._dcasa_vend_resumen_panel()
        self.assertEqual((panel['nivel']['puntos_por_dolar'], panel['tope_directos'], panel['programa_activo']),
                         (4.5, 2, True))
        self.assertEqual(panel['nivel']['siguiente'], {'puntos_por_dolar': 5.5, 'falta_centavos': 10000})
        self.guardar(programa=False)
        self.assertFalse(self.ana._dcasa_vend_resumen_panel()['programa_activo'])


@tagged('post_install', '-at_install')
class TestPermisosDeAjustes(AjustesCommon):
    """Solo Gerencia y los administradores ven y cambian las reglas; una vendedora no."""

    def test_una_vendedora_no_abre_ni_cambia_los_ajustes(self):
        Ajustes = self.env['dcasa.vend.ajustes'].with_user(self.caja)
        with self.assertRaises(AccessError):
            Ajustes.default_get(list(A.CLAVES_DE_PANTALLA_ODOO))
        with self.assertRaises(AccessError):
            Ajustes.create({'dcasa_vend_comision_base': 9, 'dcasa_vend_cargado': True})
        self.assertFalse(self.versiones())

    def test_los_metodos_del_servidor_exigen_el_grupo_antes_de_tocar_nada(self):
        Reglas = self.Reglas.with_user(self.caja)
        pantalla = A.valores_de_pantalla(R.cargar_reglas())
        with self.assertRaises(AccessError):
            Reglas._guardar_desde_pantalla({**pantalla, 'comision_base': 4.5})
        with self.assertRaises(AccessError):
            Reglas._volver_a_fabrica()
        with self.assertRaises(AccessError):
            self.env['dcasa.vend.ajustes'].with_user(self.caja).action_dcasa_vend_historial()
        self.assertFalse(self.versiones())

    def test_una_vendedora_no_lee_el_historial(self):
        self.Reglas._registrar('ajuste', {}, [], None, R.cargar_reglas())
        with self.assertRaises(AccessError):
            self.Reglas.with_user(self.caja).search([])
        with self.assertRaises(AccessError):
            self.env['dcasa.vend.ajustes.mixin'].with_user(self.caja)._dcasa_vend_valores_iniciales()

    def test_un_usuario_interno_sin_rol_tampoco(self):
        sin_rol = new_test_user(self.env, login='ajustes_sin_rol', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.env['dcasa.vend.ajustes'].with_user(sin_rol).default_get(['dcasa_vend_comision_base'])

    def test_gerencia_lee_el_historial_pero_no_lo_edita_ni_lo_borra(self):
        version = self.Reglas._registrar('ajuste', {}, [], None, R.cargar_reglas())
        Historial = self.Reglas.with_user(self.gerencia)
        self.assertEqual(Historial.search([]), version)
        self.assertEqual(Historial.browse(version.id).nombre, 'Versión 1')
        with self.assertRaisesRegex(UserError, 'no se edita'):
            Historial.browse(version.id).write({'motivo': 'x'})
        with self.assertRaisesRegex(UserError, 'no se borra'):
            Historial.browse(version.id).unlink()
        with self.assertRaises(AccessError):
            Historial.create({'tipo': 'ajuste', 'autor': 'x', 'ajustes': '{}'})

    def test_los_administradores_tambien_cambian_las_reglas(self):
        version = self.guardar(usuario=self.admin, comision_base=4.5)
        self.assertEqual(version.autor, 'Admin Sistema')
        self.assertEqual(self.env['dcasa.vend.reglas'].with_user(self.admin).search([]), version)

    @staticmethod
    def valores_de_ajustes(Ajustes):
        """Lo que el navegador manda de este bloque al guardar (no los demás ajustes de Odoo)."""
        valores = Ajustes.default_get(list(A.CLAVES_DE_PANTALLA_ODOO))
        return {campo: valor for campo, valor in valores.items() if campo.startswith('dcasa_vend_')}

    def test_los_menus_son_de_gerencia_y_administradores(self):
        menus = [self.env.ref('dcasa_socios.menu_dcasa_vend_ajustes'),
                 self.env.ref('dcasa_socios.menu_dcasa_vend_reglas')]
        gerencia = set(self.env['ir.ui.menu'].with_user(self.gerencia)._visible_menu_ids())
        caja = set(self.env['ir.ui.menu'].with_user(self.caja)._visible_menu_ids())
        for menu in menus:
            with self.subTest(menu.name):
                self.assertIn(menu.id, gerencia)
                self.assertNotIn(menu.id, caja)
                self.assertTrue(menu.action)
        self.assertEqual(menus[1].complete_name, 'Socios/Historial de reglas')

    def test_el_bloque_dentro_de_ajustes_es_de_administradores(self):
        Ajustes = self.env['res.config.settings']
        pantalla = A.CLAVES_DE_PANTALLA_ODOO
        valores = Ajustes.with_user(self.admin).default_get(list(pantalla))      # un administrador del sistema
        self.assertEqual(valores['dcasa_vend_comision_base'], 4.0)
        self.assertTrue(valores['dcasa_vend_cargado'])
        # Gerencia no entra a Ajustes de Odoo (ahí hay mucho más que las reglas de vendedores).
        with self.assertRaises(AccessError):
            Ajustes.with_user(self.gerencia).default_get(list(pantalla))
        with self.assertRaises(AccessError):
            Ajustes.with_user(self.caja).create({})

    def test_guardar_desde_ajustes_de_odoo_crea_la_misma_version(self):
        # Se crea el registro de Ajustes con todos los permisos (sus campos de otras apps escriben en la empresa y el
        # sitio) y se guarda como administrador: lo que se prueba es este bloque.
        Ajustes = self.env['res.config.settings']
        valores = self.valores_de_ajustes(Ajustes.with_user(self.admin))
        sin_cambios = Ajustes.create(valores)
        sin_cambios.with_user(self.admin).set_values()
        self.assertFalse(self.versiones(), 'Guardar otros ajustes de Odoo no toca las reglas de vendedores')
        cambiado = Ajustes.create({**valores, 'dcasa_vend_comision_base': 4.5, 'dcasa_vend_motivo': 'Desde Ajustes'})
        cambiado.with_user(self.admin).set_values()
        version = self.versiones()
        self.assertEqual((version.numero, version.motivo, version.autor), (1, 'Desde Ajustes', 'Admin Sistema'))
        self.assertEqual(self.vigentes()['comision']['puntosPorDolarNeto'], 4.5)

    def test_guardar_otros_ajustes_de_odoo_sin_cargar_las_cifras_no_las_toca(self):
        Ajustes = self.env['res.config.settings']
        Ajustes.create({'dcasa_vend_comision_base': 9, 'dcasa_vend_cargado': False}).with_user(self.admin).set_values()
        self.assertFalse(self.versiones())

    def test_ajustes_de_odoo_valida_igual_que_la_pantalla_de_gerencia(self):
        Ajustes = self.env['res.config.settings']
        valores = self.valores_de_ajustes(Ajustes.with_user(self.admin))
        with self.assertRaisesRegex(UserError, 'No se guardó nada'):
            Ajustes.create({**valores, 'dcasa_vend_comision_base': 9}).with_user(self.admin).set_values()
        self.assertFalse(self.versiones())


@tagged('post_install', '-at_install')
class TestPantallasYVistas(AjustesCommon):
    """Los campos, las dos vistas, los menús y el historial están completos y dicen lo mismo."""

    def campos_de(self, xmlid):
        arch = self.env.ref(xmlid).arch_db
        return set(re.findall(r'<field name="(dcasa_vend_[a-z0-9_]+)"', arch))

    def test_cada_cifra_ajustable_tiene_su_campo_en_las_dos_pantallas(self):
        for modelo in ('dcasa.vend.ajustes', 'res.config.settings'):
            for campo in A.CAMPOS:
                with self.subTest(f'{modelo} {campo.clave}'):
                    odoo = self.env[modelo]._fields[campo.campo_odoo]
                    self.assertEqual(odoo.string, campo.etiqueta)
                    self.assertEqual(odoo.type, {'si_no': 'boolean', 'entero': 'integer'}.get(campo.tipo, 'float'))
            for clave in A.CLAVES_DE_ESCALONES:
                self.assertIn(f'dcasa_vend_{clave}', self.env[modelo]._fields)

    def test_las_dos_vistas_muestran_las_mismas_cifras_y_todas_las_cifras(self):
        gerencia = self.campos_de('dcasa_socios.view_dcasa_vend_ajustes_form')
        en_ajustes = self.campos_de('dcasa_socios.res_config_settings_view_form_dcasa_vendedores')
        self.assertEqual(gerencia, en_ajustes)
        esperadas = {f'dcasa_vend_{clave}' for clave in A.CLAVES_DE_PANTALLA} | {
            'dcasa_vend_externos', 'dcasa_vend_efectivo', 'dcasa_vend_motivo', 'dcasa_vend_estado',
            'dcasa_vend_resumen', 'dcasa_vend_cargado', 'dcasa_vend_version_vista'}
        self.assertEqual(gerencia, esperadas)

    def test_la_pantalla_de_gerencia_se_arma_para_gerencia_y_el_bloque_para_administradores(self):
        vista = self.env['dcasa.vend.ajustes'].with_user(self.gerencia).get_views([(False, 'form')])
        self.assertIn('dcasa_vend_comision_base', vista['views']['form']['arch'])
        for bloque in ('Programa', 'Comisión y escalera', 'Patrocinio', 'Retención', 'Límites de seguridad', 'Canjes'):
            self.assertIn(f'title="{bloque}', vista['views']['form']['arch'])
        ajustes = self.env['res.config.settings'].with_user(self.admin).get_views([(False, 'form')])
        self.assertIn('Programa de vendedores', ajustes['views']['form']['arch'])

    def test_los_interruptores_legales_dicen_que_estan_apagados_hasta_el_dictamen(self):
        arch = self.env.ref('dcasa_socios.view_dcasa_vend_ajustes_form').arch_db
        self.assertEqual(arch.count('Apagado hasta el dictamen del abogado y la contadora.'), 2)

    def test_el_historial_se_ve_en_lista_y_formulario(self):
        version = self.Reglas._registrar(
            'ajuste', {}, [{'campo': 'Comisión base', 'antes': '4 %', 'despues': '4.5 %'}], 'Por la temporada',
            R.cargar_reglas())
        historial = self.env['dcasa.vend.reglas'].with_user(self.gerencia)
        for tipo in ('list', 'form', 'search'):
            self.assertTrue(historial.get_views([(False, tipo)])['views'][tipo]['arch'])
        accion = self.env.ref('dcasa_socios.action_dcasa_vend_reglas')
        self.assertEqual((accion.res_model, accion.view_mode), ('dcasa.vend.reglas', 'list,form'))
        self.assertEqual(version.with_user(self.gerencia).nombre, 'Versión 1')
        arch = historial.get_views([(False, 'list')])['views']['list']['arch']
        self.assertIn('create="false"', arch)
        self.assertIn('edit="false"', arch)
        self.assertIn('delete="false"', arch)

    def test_la_comision_dice_con_que_ajuste_se_pago(self):
        self.guardar(comision_base=4.5)
        comision = self.vender(self.ana)
        arch = self.env['dcasa.vend.comision'].get_views([(False, 'form')])['views']['form']['arch']
        self.assertIn('reglas_ajuste', arch)
        self.assertEqual(comision.reglas_ajuste, 1)

    def test_los_botones_de_la_pantalla_abren_el_historial(self):
        accion = self.abrir().action_dcasa_vend_historial()
        self.assertEqual(accion['res_model'], 'dcasa.vend.reglas')
        self.assertEqual(self.abrir().cancel()['res_model'], 'dcasa.vend.ajustes')


@tagged('post_install', '-at_install')
class TestAjustesEnLaWeb(HttpCase):
    """Lo que ve el vendedor (los términos y su panel) tiene que coincidir con lo que se le paga."""

    def setUp(self):
        super().setUp()
        patcher = patch.dict(os.environ, {'DCASA_PIN_PEPPER': 'pimienta-de-prueba'})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.env = self.env(context=dict(self.env.context, tracking_disable=True))
        self.Reglas = self.env['dcasa.vend.reglas']
        self.ana = self.env['res.partner'].create({'name': 'Ana Vendedora', 'vat': '8-111-111', 'phone': '6100-0001'})
        self.ana._dcasa_afiliar_vendedor('externo', autor='prueba', acepto_terminos=True)
        self.ana._dcasa_guardar_pin(PIN)
        self.authenticate(None, None)

    def texto(self, url):
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', self.url_open(url).text))

    def csrf(self):
        return re.search(r'csrf_token: "([^"]+)"', self.url_open('/vendedores/terminos').text).group(1)

    def entrar(self):
        return self.url_open('/socios/entrar', data={'celular': '6100-0001', 'pin': PIN, 'csrf_token': self.csrf()})

    def ajustar(self, ajustes, cambios=None):
        return self.Reglas._registrar('ajuste', ajustes, cambios or [], None, R.cargar_reglas())

    def test_los_terminos_ensenan_las_cifras_de_fabrica_y_despues_las_ajustadas(self):
        antes = self.texto('/vendedores/terminos')
        self.assertIn('Ganas 4 puntos por cada dólar', antes)
        self.assertIn('Reglas del programa, versión 5', antes)
        self.assertNotIn('ajustes de Gerencia', antes)
        self.ajustar({'comision.puntosPorDolarNeto': 4.5, 'vinculacion.meses': 6, 'retencion.dias': 15,
                      'techos.frenoGlobalPorcentajeDeLaVentaNeta': 2.5, 'canje.vigenciaDelCodigoHoras': 48,
                      'comision.escalones': [{'desdeVentasNetasCentavos': 150000, 'puntosPorDolarNeto': 5.25,
                                              'topeAlMesPuntos': 25000}],
                      'patrocinio.topeDeDirectos': 4})
        despues = self.texto('/vendedores/terminos')
        self.assertIn('Ganas 4.5 puntos por cada dólar', despues)
        self.assertIn('Desde $1,500.00 vendidos: 5.25 puntos por cada dólar', despues)
        self.assertNotIn('$18,000.00', despues, 'Los escalones de fábrica ya no se enseñan')
        self.assertIn('ligado a ti por 6 meses', despues)
        self.assertIn('se liberan a los 15 días', despues)
        self.assertIn('no pasan del 2.5%', despues)
        self.assertIn('en 48 horas', despues)
        self.assertIn('hasta 4)', despues)
        self.assertRegex(despues, r'Reglas del programa, versión 5 · con los ajustes de Gerencia número 1, vigentes '
                                  r'desde el \d\d/\d\d/\d{4}')

    def test_los_terminos_avisan_si_gerencia_apago_el_programa(self):
        self.assertNotIn('todavía no está encendido', self.texto('/vendedores/terminos'))
        self.ajustar({'programaActivo': False})
        self.assertIn('El programa de vendedores todavía no está encendido', self.texto('/vendedores/terminos'))

    def test_el_panel_del_vendedor_ensena_la_tasa_y_el_tope_que_rigen(self):
        self.entrar()
        self.assertIn('Ganas por cada $1 vendido 4 puntos', self.texto('/socios/vendedor'))
        self.ajustar({'comision.puntosPorDolarNeto': 4.5, 'techos.porVendedorAlMesPuntos': 25000})
        panel = self.texto('/socios/vendedor')
        self.assertIn('Ganas por cada $1 vendido 4.5 puntos', panel)
        self.assertIn('Puedes ganar este mes hasta 25,000 puntos', panel)
