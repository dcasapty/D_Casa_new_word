"""Las reglas por versión: nacen vacías, solo rigen hacia adelante, no se editan, el reparto suma 100 %, el ejemplo de
la pantalla se mueve con los interruptores y el módulo no trae ninguna cifra."""
import re
from datetime import timedelta
from pathlib import Path

from psycopg2 import IntegrityError

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import ComisionCommon

MODULO = Path(__file__).resolve().parent.parent


@tagged('post_install', '-at_install')
class TestReglas(ComisionCommon):

    def test_el_modulo_nace_sin_versiones_sin_porcentaje_y_sin_tarifa(self):
        self.assertEqual(self.env['dcasa.web.reglas'].search_count([]), 0)
        self.assertEqual(self.env['dcasa.web.reparto'].search_count([]), 0)
        self.assertEqual(self.env['dcasa.web.movimiento'].search_count([]), 0)
        self.assertEqual(self.env['dcasa.web.venta'].search_count([]), 0)

    def test_ningun_archivo_de_datos_trae_reglas_ni_cifras(self):
        """Los datos que instala el módulo no crean ninguna versión, ningún porcentaje y ninguna tarifa."""
        for archivo in (MODULO / 'data').glob('*.xml'):
            texto = archivo.read_text()
            for prohibido in ('dcasa.web.reglas', 'dcasa.web.reparto', 'name="porcentaje"', 'name="tarifa_fija"'):
                self.assertNotIn(prohibido, texto, f'{archivo.name} trae {prohibido}')
        # Y el código no escribe cifras de fábrica: ningún valor por defecto de porcentaje ni de tarifa.
        por_defecto = self.env['dcasa.web.reglas'].default_get(['porcentaje', 'tarifa_fija'])
        self.assertFalse(por_defecto.get('porcentaje'))
        self.assertFalse(por_defecto.get('tarifa_fija'))

    def test_los_valores_de_fabrica_de_los_interruptores_son_los_recomendados(self):
        valores = self.env['dcasa.web.reglas'].default_get(
            ['base_itbms', 'base_envio', 'base_descuentos', 'base_devoluciones', 'base_pasarela', 'tarifa_periodo'])
        self.assertEqual(valores, {'base_itbms': 'sin', 'base_envio': 'sin', 'base_descuentos': 'despues',
                                   'base_devoluciones': 'resta', 'base_pasarela': 'no_resta',
                                   'tarifa_periodo': 'mensual'})

    def test_una_version_se_guarda_numerada_con_su_autor(self):
        v1 = self.version(10.0)
        v2 = self.env['dcasa.web.reglas'].with_user(self.u_nomina).create({
            'company_id': self.company.id, 'porcentaje': 5.0, 'rige_desde': fields.Datetime.now() + timedelta(days=1),
            'reparto_ids': [Command.create({'empleado_id': self.ana.id, 'porcentaje': 100.0})]})
        self.assertEqual((v1.numero, v2.numero), (1, 2))
        self.assertEqual(v2.autor, self.u_nomina.name)
        self.assertEqual((v1.estado, v2.estado), ('vigente', 'programada'))

    def test_solo_rige_hacia_adelante(self):
        with self.assertRaisesRegex(UserError, 'fecha que ya pasó'):
            self.version(10.0, rige_desde=fields.Datetime.now() - timedelta(days=1))
        futura = self.version(10.0, rige_desde=fields.Datetime.now() + timedelta(days=10))
        self.assertEqual(self.env['dcasa.web.reglas']._vigente(self.company), self.env['dcasa.web.reglas'])
        self.assertEqual(futura.estado, 'programada')
        # Una versión más cercana que otra ya programada se puede guardar (no traba el módulo): rige primero.
        cercana = self.version(8.0, rige_desde=fields.Datetime.now() + timedelta(days=5))
        self.assertEqual(self.env['dcasa.web.reglas']._vigente(
            self.company, fields.Datetime.now() + timedelta(days=6)), cercana)
        self.assertEqual(self.env['dcasa.web.reglas']._vigente(
            self.company, fields.Datetime.now() + timedelta(days=11)), futura)

    def test_la_version_vigente_es_la_mas_reciente_que_ya_empezo(self):
        v1 = self.version(10.0)
        Reglas = self.env['dcasa.web.reglas']
        self.assertEqual(Reglas._vigente(self.company), v1)
        v2 = self.version(12.0, rige_desde=fields.Datetime.now() + timedelta(days=3))
        self.assertEqual(Reglas._vigente(self.company), v1, 'la nueva todavía no empieza')
        self.assertEqual(Reglas._vigente(self.company, fields.Datetime.now() + timedelta(days=4)), v2)
        self.assertEqual(Reglas._primera(self.company), v1)

    def test_una_version_no_se_edita_ni_se_borra_ni_con_sudo(self):
        version = self.version(10.0)
        for usuario in (self.env, self.env(user=self.u_nomina), self.env(user=self.u_gerencia)):
            with self.subTest(usuario=usuario.user.login):
                registro = version.with_env(usuario)
                self.rechaza(lambda registro=registro: registro.write({'porcentaje': 99}))
                self.rechaza(lambda registro=registro: registro.unlink())
        with self.assertRaisesRegex(UserError, 'no se edita'):
            version.sudo().write({'porcentaje': 99})
        with self.assertRaisesRegex(UserError, 'no se borra'):
            version.sudo().unlink()
        self.assertEqual(version.porcentaje, 10.0)

    def test_el_reparto_de_una_version_ya_guardada_no_se_toca(self):
        version = self.version(10.0)
        renglon = version.reparto_ids[0]
        with self.assertRaisesRegex(UserError, 'no se edita'):
            renglon.sudo().write({'porcentaje': 1})
        with self.assertRaisesRegex(UserError, 'no se borra'):
            renglon.sudo().unlink()
        with self.assertRaisesRegex(UserError, 'no se agrega'):
            self.env['dcasa.web.reparto'].sudo().create({'reglas_id': version.id, 'empleado_id': self.ana.id,
                                                         'porcentaje': 5})

    def test_el_reparto_tiene_que_sumar_cien(self):
        with self.assertRaisesRegex(ValidationError, 'sumar 100'):
            self.version(10.0, reparto=[(self.ana, 60.0), (self.beto, 39.99)])
        with self.assertRaisesRegex(ValidationError, 'sumar 100'):
            self.version(10.0, reparto=[(self.ana, 50.0), (self.beto, 50.0), (self.empleado_nomina, 0.01)])
        self.assertEqual(len(self.version(10.0, reparto=[(self.ana, 33.33), (self.beto, 33.33),
                                                         (self.empleado_nomina, 33.34)]).reparto_ids), 3)

    def test_con_porcentaje_o_tarifa_hace_falta_el_reparto(self):
        with self.assertRaisesRegex(ValidationError, 'quiénes reciben'):
            self.version(10.0, reparto=[])
        with self.assertRaisesRegex(ValidationError, 'quiénes reciben'):
            self.version(0.0, tarifa=50.0, reparto=[])

    def test_una_pausa_no_necesita_reparto(self):
        pausa = self.version(0.0, reparto=[])
        self.assertEqual((pausa.porcentaje, pausa.tarifa_fija), (0.0, 0.0))

    def test_cada_persona_sale_una_vez_y_es_de_nomina(self):
        with self.assertRaisesRegex(ValidationError, 'una sola vez'):
            self.version(10.0, reparto=[(self.ana, 50.0), (self.ana, 50.0)])
        fuera = self._empleado('Fuera de nómina', 1000, '2029-01-01', dcasa_en_planilla=False)
        with self.assertRaisesRegex(ValidationError, 'no está en Nómina'):
            self.version(10.0, reparto=[(fuera, 100.0)])

    def test_el_porcentaje_y_la_tarifa_tienen_limites(self):
        with self.assertRaisesRegex(ValidationError, 'de 0 a 100'):
            self.version(101.0)
        with self.assertRaisesRegex(ValidationError, 'de 0 a 100'):
            self.version(-1.0)
        with self.assertRaisesRegex(ValidationError, 'negativa'):
            self.version(0.0, tarifa=-5.0)

    def test_el_porcentaje_de_cada_persona_es_mas_de_cero(self):
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.version(10.0, reparto=[(self.ana, 100.0), (self.beto, 0.0)])

    def test_nueva_version_abre_el_formulario_con_lo_que_rige_hoy(self):
        self.version(7.5, tarifa=20.0, base_itbms='con')
        accion = self.env['dcasa.web.reglas'].action_nueva_version()
        contexto = accion['context']
        self.assertEqual((contexto['default_porcentaje'], contexto['default_tarifa_fija']), (7.5, 20.0))
        self.assertEqual(contexto['default_base_itbms'], 'con')
        self.assertEqual(len(contexto['default_reparto_ids']), 2)

    def test_quienes_reciben_es_la_lista_de_la_version_vigente(self):
        vacia = self.env['dcasa.web.reparto']._accion_quienes_reciben()
        self.assertEqual(self.env['dcasa.web.reparto'].search(vacia['domain']), self.env['dcasa.web.reparto'])
        version = self.version(10.0)
        accion = self.env['dcasa.web.reparto']._accion_quienes_reciben()
        self.assertEqual(self.env['dcasa.web.reparto'].search(accion['domain']), version.reparto_ids)

    # ------------------------------------------------------------------ el ejemplo con números de mentira

    def ejemplo(self, **opciones):
        valores = {'porcentaje': opciones.pop('porcentaje', 0.0), **opciones}
        return self.env['dcasa.web.reglas'].new(valores).ejemplo_html

    def test_el_ejemplo_dice_que_es_de_mentira_y_la_base_recomendada(self):
        html = str(self.ejemplo())
        self.assertIn('números de mentira', html)
        self.assertIn('$700.00', html, '1,000 − 100 de premio − 200 devueltos')
        self.assertIn('Escribe el porcentaje', html)

    def test_el_ejemplo_se_mueve_con_cada_interruptor(self):
        def base(**opciones):
            return re.search(r'La base de este ejemplo es <strong>(\$[\d,.]+)</strong>',
                             str(self.ejemplo(**opciones))).group(1)
        self.assertEqual(base(), '$700.00')
        self.assertEqual(base(base_itbms='con'), '$772.00', '+90 de ITBMS −18 del devuelto')
        self.assertEqual(base(base_envio='con'), '$750.00')
        self.assertEqual(base(base_descuentos='antes'), '$777.78', 'precio de lista; lo devuelto también a lista')
        self.assertEqual(base(base_devoluciones='no_resta'), '$900.00')
        self.assertEqual(base(base_pasarela='resta'), '$670.00')

    def test_el_ejemplo_dice_que_entra_y_que_no_entra(self):
        html = str(self.ejemplo(base_envio='con'))
        self.assertRegex(html, r'Cobro de envío</td><td class="text-end">\+\$50.00</td><td><strong>Entra</strong>')
        self.assertRegex(str(self.ejemplo()), r'Cobro de envío</td><td class="text-end">\+\$50.00</td>'
                         r'<td><strong>No entra</strong>')

    def test_con_porcentaje_el_ejemplo_dice_cuanto_seria_la_comision(self):
        html = str(self.ejemplo(porcentaje=10.0))
        self.assertIn('Con tu porcentaje (10 %)', html)
        self.assertIn('$70.00', html)
