"""Quinta revisión adversarial, parte E y menor 2: valores raros por todas las entradas (``create``, ``copy``,
``load``/importar, ``write`` y el asistente de ajuste) en versiones, reparto, ajustes y liquidaciones. Por RPC cualquiera
manda lo que quiera: lo que no es un número, un texto que no es una fecha, una opción que no existe, un 1.8e308.

Cada entrada tiene que terminar en un mensaje claro y traducible (``UserError``, ``ValidationError``, ``AccessError`` o
una restricción de la base, que el RPC de Odoo traduce) o en un valor válido; nunca en un error de Python sin traducir
(``ValueError``, ``TypeError``, ``OverflowError``, ``InvalidOperation``). Antes de esta revisión fallaban así: un
«Rige desde» con texto, número o lista; una opción de «La tarifa se anota» que no existe; las fechas de una
liquidación («abc», un número) y el año 1; y lo que le toca a una persona del reparto con 1.797e308.

Cifras y personas de PRUEBA."""
# ruff: noqa: E501, B023
from decimal import Decimal

from psycopg2 import IntegrityError

from odoo import Command
from odoo.addons.dcasa_comision_web.tests.test_comision import ComisionReloj
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

RAROS = [('nan', float('nan')), ('inf', float('inf')), ('-inf', float('-inf')), ('texto nan', 'nan'), ('texto inf', 'inf'),
         ('texto -inf', '-inf'), ('1e30', 1e30), ('texto 1e30', '1e30'), ('texto 1e400', '1e400'),
         ('entero 10**30', 10 ** 30), ('entero -10**30', -10 ** 30), ('entero 10**400', 10 ** 400), ('float 1e300', 1e300),
         ('float 1e308', 1.7976931348623157e308), ('float -1e308', -1.7976931348623157e308), ('texto abc', 'abc'),
         ('texto coma', '5,5'), ('texto vacio', ''), ('espacios', ' 5 '), ('bool True', True), ('lista', [1]),
         ('dict', {'a': 1}), ('None', None), ('Decimal nan', Decimal('NaN')), ('Decimal 1e30', Decimal('1e30')),
         ('negativo', -5.0), ('minusculo', 1e-30), ('limite', 21474836.47), ('sobre el limite', 21474836.48),
         ('cien', 100.0), ('mas de cien', 100.01), ('arabe', '٣'), ('texto guion bajo', '1_000')]


@tagged('post_install', '-at_install')
class TestValoresRaros(ComisionReloj):

    def intentar(self, funcion):
        """``'BLOQ'`` (mensaje claro o restricción de la base), ``'PASO'`` (se guardó) o ``'ERR'`` (error de Python sin
        traducir, lo que no puede pasar)."""
        try:
            with self.env.cr.savepoint(), mute_logger('odoo.sql_db'):
                funcion()
        except (UserError, AccessError, ValidationError, IntegrityError):
            return 'BLOQ'
        except Exception:  # noqa: BLE001
            return 'ERR'
        return 'PASO'

    def sin_traducir(self, entradas):
        """Los nombres de las entradas cuyo error de Python no se tradujo."""
        return [nombre for nombre, funcion in entradas if self.intentar(funcion) == 'ERR']

    def reparto(self):
        return [Command.create({'empleado_id': self.ana.id, 'porcentaje': 60.0}),
                Command.create({'empleado_id': self.beto.id, 'porcentaje': 40.0})]

    def test_version_create_campo_por_campo(self):
        Reglas = self.env['dcasa.web.reglas'].with_user(self.u_nomina)

        def crear(campo, valor):
            return lambda: Reglas.create({'company_id': self.company.id, 'reparto_ids': self.reparto(),
                                          **({'porcentaje': 10.0} if campo != 'porcentaje' else {}), campo: valor})
        entradas = [(f'{campo}={nombre}', crear(campo, valor)) for campo in ('porcentaje', 'tarifa_fija', 'tope_ajuste')
                    for nombre, valor in RAROS]
        self.assertFalse(self.sin_traducir(entradas))

    def test_el_porcentaje_de_cada_persona_del_reparto(self):
        Reglas = self.env['dcasa.web.reglas'].with_user(self.u_nomina)

        def crear(valor):
            return lambda: Reglas.create({'company_id': self.company.id, 'porcentaje': 10.0, 'reparto_ids': [
                Command.create({'empleado_id': self.ana.id, 'porcentaje': valor}),
                Command.create({'empleado_id': self.beto.id, 'porcentaje': 40.0})]})
        self.assertFalse(self.sin_traducir([(f'reparto={nombre}', crear(valor)) for nombre, valor in RAROS]))

    def test_un_reparto_de_1_8e308_se_rechaza_con_un_mensaje_claro(self):
        """Menor 2: ``OverflowError`` al redondear (``reglas.py``, ``DcasaWebReparto.create``)."""
        for valor in (1.7976931348623157e308, -1.7976931348623157e308, 1e300):
            with self.subTest(valor=valor), self.assertRaisesRegex(ValidationError, 'más de 0 y hasta 100'):
                self.env['dcasa.web.reglas'].with_user(self.u_nomina).create({
                    'company_id': self.company.id, 'porcentaje': 10.0, 'reparto_ids': [
                        Command.create({'empleado_id': self.ana.id, 'porcentaje': valor}),
                        Command.create({'empleado_id': self.beto.id, 'porcentaje': 40.0})]})

    def test_el_monto_de_un_ajuste(self):
        self.version(10.0)
        Ajuste = self.env['dcasa.web.ajuste'].with_user(self.u_nomina)

        def anotar(valor):
            def f():
                Ajuste.create({'empleado_id': self.ana.id, 'monto': valor, 'motivo': 'prueba'}).action_anotar()
            return f

        def cambiar_y_anotar(valor):
            def f():
                ajuste = Ajuste.create({'empleado_id': self.ana.id, 'monto': 5.0, 'motivo': 'prueba'})
                ajuste.write({'monto': valor})
                ajuste.action_anotar()
            return f
        entradas = [(f'create {nombre}', anotar(valor)) for nombre, valor in RAROS]
        entradas += [(f'write {nombre}', cambiar_y_anotar(valor)) for nombre, valor in RAROS]
        self.assertFalse(self.sin_traducir(entradas))

    def test_un_tope_viejo_de_1e30_ya_guardado_no_rompe_los_ajustes_ni_la_pantalla(self):
        """Una base con un tope enorme guardado ANTES de la cuarta revisión (se escribe con SQL, sin validaciones)."""
        version = self.version(10.0)
        for valor in ('1e30', '99999999999999999999.99'):
            with self.subTest(tope=valor):
                self.env.cr.execute('UPDATE dcasa_web_reglas SET tope_ajuste = %s::numeric WHERE id = %s', [valor, version.id])
                version.invalidate_recordset()
                ajuste = self.env['dcasa.web.ajuste'].with_user(self.u_nomina).create({
                    'empleado_id': self.ana.id, 'monto': 5.0, 'motivo': 'prueba'})
                ajuste.action_anotar()
                self.assertTrue(version.ejemplo_html)
                version.with_user(self.u_nomina).read(['tope_ajuste', 'ejemplo_html', 'estado', 'display_name'])
                self.env['dcasa.web.reglas'].with_user(self.u_nomina).action_nueva_version()

    def test_importar_con_load_y_copy(self):
        self.version(10.0)
        Reglas = self.env['dcasa.web.reglas'].with_user(self.u_nomina)

        def importar(valor):
            def f():
                resultado = Reglas.load(['company_id/.id', 'porcentaje', 'tarifa_fija'], [[str(self.company.id), '10', valor]])
                if resultado.get('messages'):
                    raise UserError(str(resultado['messages'])[:80])
            return f
        vigente = self.env['dcasa.web.reglas']._vigente(self.company)
        entradas = [(f'load tarifa={valor}', importar(valor)) for valor in ('abc', '1e30', 'nan', '50')]
        entradas += [('copy con tope 1e30', lambda: vigente.with_user(self.u_nomina).copy({'tope_ajuste': 1e30})),
                     ('copy simple', lambda: vigente.with_user(self.u_nomina).copy())]
        self.assertFalse(self.sin_traducir(entradas))

    # --- menor 2: fechas y opciones ------------------------------------------------------------------------------

    def test_un_rige_desde_que_no_es_fecha_se_rechaza_con_un_mensaje_claro(self):
        for nombre, valor in (('texto', 'abc'), ('entero', 12345), ('float', 1e30), ('lista', [1]), ('booleano', True),
                              ('dict', {'a': 1})):
            with self.subTest(rige_desde=nombre), self.assertRaisesRegex(UserError, 'no es una fecha válida'):
                self.env['dcasa.web.reglas'].with_user(self.u_nomina).create({
                    'company_id': self.company.id, 'porcentaje': 10.0, 'rige_desde': valor, 'reparto_ids': self.reparto()})

    def test_los_extremos_de_rige_desde_siguen_como_antes(self):
        """El año 0001 es un día que ya pasó (mensaje claro); el 9999 se guarda (no frena nada, se puede anular)."""
        with self.assertRaisesRegex(UserError, 'ya pasó'):
            self.version(10.0, rige_desde='0001-01-01 00:00:00')
        lejana = self.version(10.0, rige_desde='9999-12-31 00:00:00')
        self.assertEqual(lejana.estado, 'programada')

    def test_una_opcion_que_no_existe_se_rechaza_con_un_mensaje_claro(self):
        for campo in ('tarifa_periodo', 'base_itbms', 'base_envio', 'base_descuentos', 'base_devoluciones', 'base_pasarela'):
            for valor in ('cada siglo', 5, [1]):
                with self.subTest(campo=campo, valor=valor), self.assertRaisesRegex(UserError, 'no es una de las opciones'):
                    self.env['dcasa.web.reglas'].with_user(self.u_nomina).create({
                        'company_id': self.company.id, 'porcentaje': 10.0, campo: valor, 'reparto_ids': self.reparto()})
        quincenal = self.version(10.0, tarifa_periodo='quincenal')
        self.assertEqual(quincenal.tarifa_periodo, 'quincenal', 'y una opción válida se guarda')

    def test_las_fechas_de_una_liquidacion_que_no_son_fecha_se_rechazan_con_un_mensaje_claro(self):
        Liquidacion = self.env['dcasa.web.liquidacion'].with_user(self.u_nomina)

        class FallaConKeyError:
            """Se comporta igual en cualquier Python: ``valor[:10]`` falla con KeyError (un dict da TypeError en 3.11 y
            KeyError en 3.12+; CI y la imagen usan 3.12, esta máquina 3.11)."""
            def __getitem__(self, _clave):
                raise KeyError('no se puede recortar')

        class FallaConIndexError:
            def __getitem__(self, _clave):
                raise IndexError('no se puede recortar')

        for campo in ('fecha_desde', 'fecha_hasta'):
            for nombre, valor in (('texto', 'abc'), ('entero', 12345), ('lista', [1]), ('dict', {'a': 1}), ('mes 13', '2030-13-01'),
                                  ('KeyError', FallaConKeyError()), ('IndexError', FallaConIndexError())):
                with self.subTest(campo=campo, valor=nombre), self.assertRaisesRegex(UserError, 'no es una fecha válida'):
                    Liquidacion.create({'fecha_desde': '2030-03-01', 'fecha_hasta': '2030-03-31', campo: valor})
        borrador = Liquidacion.create({'fecha_desde': '2030-03-01', 'fecha_hasta': '2030-03-31'})
        with self.assertRaisesRegex(UserError, 'no es una fecha válida'):
            borrador.write({'fecha_desde': 'abc'})
        borrador.write({'fecha_desde': '2030-03-05'})
        self.assertEqual(str(borrador.fecha_desde), '2030-03-05')

    def test_el_periodo_de_una_liquidacion_desde_el_anio_1_se_arma_sin_error_de_python(self):
        """``0001-01-01`` es una fecha válida pero restarle un día desbordaba (``OverflowError``) al armar."""
        self.version(10.0)
        self.venta_web()
        liquidacion = self.env['dcasa.web.liquidacion'].with_user(self.u_nomina).create({
            'fecha_desde': '0001-01-01', 'fecha_hasta': '2030-03-31'})
        liquidacion.action_armar()
        self.assertEqual(sum(liquidacion.linea_ids.mapped('centavos')), 10000)
        self.assertFalse(liquidacion.avisos, 'no hay nada anotado antes del año 1')
