"""Quinta revisión adversarial, bloqueante 1 y menores 4 y 5: la regla «una versión guardada no se edita ni se borra»
vive en el SERVIDOR (RPC ``write``, ``unlink``, ``copy``, ``web_save``, los comandos del reparto y el otro modelo del
reparto), con los 5 roles, y no la abre el ``edit="1"`` de la sublista «Quiénes reciben» de la pantalla.

El bloqueante: desde la pantalla no se podía guardar ninguna versión con porcentaje o tarifa, porque no se podía agregar
a nadie a «Quiénes reciben» (nadie tiene permiso de escribir en el reparto, así que Odoo marcaba la sublista como no
editable). El arreglo es solo de pantalla (``edit="1"``): la prueba de Chrome está en ``test_revision5_navegador``; aquí
se comprueba que el servidor sigue negando todo lo demás.

Cifras y personas de PRUEBA."""
# ruff: noqa: E501, B023
from datetime import timedelta

from lxml import etree

from odoo import Command, fields
from odoo.addons.dcasa_comision_web.models.reglas import CLAVE_CREANDO
from odoo.addons.dcasa_comision_web.tests.test_comision import ComisionReloj
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestVersionGuardadaNoSeEditaPorServidor(ComisionReloj):

    def roles(self):
        return {'caja': self.u_caja, 'vendedora': self.u_vendedora, 'nomina': self.u_nomina,
                'gerencia': self.u_gerencia, 'tecnico': self.u_tecnico}

    def bloqueada(self, funcion):
        """Verdadero si la operación la rechaza Odoo con un mensaje (UserError, AccessError o ValidationError)."""
        try:
            with self.env.cr.savepoint():
                funcion()
        except (UserError, AccessError, ValidationError):
            return True
        return False

    def versiones(self):
        """A rige hoy; B quedó tapada por C (se guardó antes pero rige después); C programada; D anulada."""
        A = self.version(10.0)
        B = self.version(5.0, rige_desde=fields.Datetime.now() + timedelta(days=6))
        C = self.version(7.0, rige_desde=fields.Datetime.now() + timedelta(days=3))
        D = self.version(9.0, rige_desde=fields.Datetime.now() + timedelta(days=20))
        D.motivo_anulacion = 'puesta mal'
        D.with_user(self.u_nomina).action_anular()
        return A, B, C, D

    def test_ninguna_version_guardada_se_edita_por_rpc(self):
        A, B, C, D = self.versiones()
        self.assertEqual((A.estado, B.estado, C.estado, D.estado), ('vigente', 'tapada', 'programada', 'anulada'))
        otra_empresa = self.env['res.company'].create({'name': 'Otra empresa de prueba'})
        campos = {'porcentaje': 50.0, 'tarifa_fija': 100.0, 'tope_ajuste': 10.0,
                  'rige_desde': fields.Datetime.now() + timedelta(days=30),
                  'base_itbms': 'con', 'base_envio': 'con', 'base_descuentos': 'antes', 'base_devoluciones': 'no_resta',
                  'base_pasarela': 'resta', 'tarifa_periodo': 'semanal', 'motivo': 'otro motivo', 'numero': 99,
                  'autor': 'otro', 'anulada': True, 'anulada_por': self.u_nomina.id, 'company_id': otra_empresa.id}
        pasaron = []
        for rol, usuario in self.roles().items():
            for version in (A, B, C, D):
                for campo, valor in campos.items():
                    if not self.bloqueada(lambda: version.with_user(usuario).write({campo: valor})):
                        pasaron.append((rol, version.estado, campo))
                # la mezcla del motivo (que sí se permite solo) con otro campo tampoco pasa
                if not self.bloqueada(lambda: version.with_user(usuario).write({'motivo_anulacion': 'x', 'porcentaje': 50.0})):
                    pasaron.append((rol, version.estado, 'motivo + porcentaje'))
        self.assertFalse(pasaron, pasaron[:5])

    def test_el_motivo_de_anulacion_solo_se_escribe_en_programadas_o_tapadas(self):
        A, B, C, D = self.versiones()
        for rol, usuario in self.roles().items():
            for version in (A, D):
                with self.subTest(rol=rol, estado=version.estado):
                    self.assertTrue(self.bloqueada(lambda: version.with_user(usuario).write({'motivo_anulacion': 'cambiado'})))
        self.assertTrue(self.bloqueada(lambda: (A | B | C).with_user(self.u_nomina).write({'motivo_anulacion': 'x'})),
                        'con una vigente entre ellas, no')
        for version in (B, C):
            version.with_user(self.u_nomina).write({'motivo_anulacion': 'puesta mal'})

    def test_unlink_no_borra_nada_y_copy_no_hereda_lo_anulado(self):
        A, B, C, D = self.versiones()
        for rol, usuario in self.roles().items():
            for version in (A, B, C, D):
                with self.subTest(rol=rol, estado=version.estado):
                    self.assertTrue(self.bloqueada(lambda: version.with_user(usuario).unlink()))
                    version.invalidate_recordset()
                    self.assertTrue(version.exists())
        # copy: o lo rechaza el servidor (sin reparto no pasa la validación) o crea una versión NUEVA que no nace anulada
        for version in (A, D):
            for extra in ({}, {'anulada': True, 'numero': 1, 'autor': 'otro', 'anulada_por': self.u_nomina.id},
                          {'reparto_ids': [Command.create({'empleado_id': self.ana.id, 'porcentaje': 100.0})]}):
                try:
                    with self.env.cr.savepoint():
                        copia = version.with_user(self.u_nomina).with_context(default_anulada=True).copy(dict(extra))
                        self.assertFalse(copia.anulada)
                        self.assertNotEqual(copia.numero, version.numero)
                except (UserError, ValidationError):
                    pass

    def test_los_comandos_del_reparto_y_el_otro_modelo_no_editan_una_version_guardada(self):
        A, B, C, D = self.versiones()
        pasaron = []
        for rol, usuario in self.roles().items():
            for original in (A, B, C, D):
                # Un entorno limpio: ``create`` ya no deja la llave interna del reparto en el contexto de lo que devuelve
                # (menor 5), así que lo que se prueba es lo que ve de verdad quien llama.
                version = self.env['dcasa.web.reglas'].browse(original.id)
                linea = self.env['dcasa.web.reparto'].browse(original.reparto_ids[:1].id)
                Reparto = self.env['dcasa.web.reparto'].with_user(usuario)
                intentos = {
                    'write reparto_ids update': lambda: version.with_user(usuario).write({'reparto_ids': [Command.update(linea.id, {'porcentaje': 99.0})]}),
                    'write reparto_ids create': lambda: version.with_user(usuario).write({'reparto_ids': [Command.create({'empleado_id': self.ana.id, 'porcentaje': 10.0})]}),
                    'write reparto_ids delete': lambda: version.with_user(usuario).write({'reparto_ids': [Command.delete(linea.id)]}),
                    'write reparto_ids unlink': lambda: version.with_user(usuario).write({'reparto_ids': [Command.unlink(linea.id)]}),
                    'write reparto_ids clear': lambda: version.with_user(usuario).write({'reparto_ids': [Command.clear()]}),
                    'write reparto_ids set': lambda: version.with_user(usuario).write({'reparto_ids': [Command.set([])]}),
                    'reparto.write': lambda: linea.with_user(usuario).write({'porcentaje': 99.0}),
                    'reparto.write empleado': lambda: linea.with_user(usuario).write({'empleado_id': self.empleado_nomina.id}),
                    'reparto.write reglas_id': lambda: linea.with_user(usuario).write({'reglas_id': B.id}),
                    'reparto.write usuario_ids': lambda: linea.with_user(usuario).write({'usuario_ids': [Command.set(usuario.ids)]}),
                    'reparto.unlink': lambda: linea.with_user(usuario).unlink(),
                    'reparto.create': lambda: Reparto.create({'reglas_id': version.id, 'empleado_id': self.empleado_nomina.id, 'porcentaje': 5.0}),
                    'reparto.create con la llave del contexto como True': lambda: Reparto.with_context(**{CLAVE_CREANDO: True}).create({'reglas_id': version.id, 'empleado_id': self.empleado_nomina.id, 'porcentaje': 5.0}),
                    'SUDO reparto.write porcentaje': lambda: linea.with_user(usuario).sudo().write({'porcentaje': 99.0}),
                    'SUDO reparto.write usuario_ids': lambda: linea.with_user(usuario).sudo().write({'usuario_ids': [Command.set(usuario.ids)]}),
                    'SUDO reparto.unlink': lambda: linea.with_user(usuario).sudo().unlink(),
                    'SUDO reglas.write porcentaje': lambda: version.with_user(usuario).sudo().write({'porcentaje': 99.0}),
                    'SUDO reglas.unlink': lambda: version.with_user(usuario).sudo().unlink(),
                    'SUDO reglas.write con el contexto de anular como True': lambda: version.with_user(usuario).sudo().with_context(dcasa_comision_web_anulando_version=True).write({'anulada': True}),
                }
                pasaron += [(rol, original.estado, nombre) for nombre, f in intentos.items() if not self.bloqueada(f)]
        self.assertFalse(pasaron, pasaron[:5])

    def test_web_save_de_una_version_guardada_no_cambia_nada(self):
        A, B, C, D = self.versiones()
        for rol, usuario in self.roles().items():
            for version in (A, B, C):
                with self.subTest(rol=rol, estado=version.estado):
                    self.assertTrue(self.bloqueada(lambda: version.with_user(usuario).web_save({'porcentaje': 50.0}, {'porcentaje': {}})))

    def test_el_libro_y_las_ventas_siguen_sin_editarse(self):
        self.version(10.0)
        venta = self.venta(self.venta_web())
        fila = self.libro(venta=venta)[:1]
        for rol, usuario in self.roles().items():
            for nombre, f in (('libro write', lambda: fila.with_user(usuario).write({'centavos': 1})),
                              ('libro unlink', lambda: fila.with_user(usuario).unlink()),
                              ('libro sudo write', lambda: fila.with_user(usuario).sudo().write({'centavos': 1})),
                              ('libro sudo unlink', lambda: fila.with_user(usuario).sudo().unlink()),
                              ('venta write', lambda: venta.with_user(usuario).write({'productos_centavos': 1})),
                              ('venta unlink', lambda: venta.with_user(usuario).unlink())):
                with self.subTest(rol=rol, que=nombre):
                    self.assertTrue(self.bloqueada(f))

    # --- lo que sí se guarda: el flujo de «Nueva versión» tal como lo manda el navegador ----------------------------

    def test_el_flujo_del_formulario_nueva_version_se_guarda_con_su_reparto(self):
        """«Nueva versión» (precargada con lo que rige) → ``web_save`` con el reparto como lo manda el cliente web, que es
        lo que ahora sí se puede armar desde la pantalla (bloqueante 1)."""
        A = self.version(10.0)
        Reglas = self.env['dcasa.web.reglas'].with_user(self.u_nomina)
        contexto = Reglas.action_nueva_version()['context']
        precargado = Reglas.with_context(**contexto).default_get(['porcentaje', 'reparto_ids'])
        self.assertEqual(precargado['porcentaje'], 10.0)
        self.assertEqual(len([c for c in precargado['reparto_ids'] if c[0] == 0]), 2, 'la pantalla trae a las personas de hoy ya escritas')
        vals = {'porcentaje': 12.0, 'tarifa_fija': 0.0, 'tope_ajuste': 0.0, 'tarifa_periodo': 'mensual',
                'base_itbms': 'sin', 'base_envio': 'sin', 'base_descuentos': 'despues', 'base_devoluciones': 'resta',
                'base_pasarela': 'no_resta', 'motivo': 'subimos el porcentaje',
                'reparto_ids': [[0, 'virtual_1', {'sequence': 10, 'empleado_id': self.ana.id, 'porcentaje': 70.0}],
                                [0, 'virtual_2', {'sequence': 20, 'empleado_id': self.beto.id, 'porcentaje': 30.0}]]}
        Reglas.web_save(vals, {'porcentaje': {}, 'reparto_ids': {'fields': {'empleado_id': {'fields': {'display_name': {}}},
                                                                           'porcentaje': {}}}, 'estado': {}, 'numero': {}})
        nueva = Reglas.search([('porcentaje', '=', 12.0)])
        self.assertEqual(len(nueva), 1)
        self.assertEqual(sorted(nueva.reparto_ids.mapped('porcentaje')), [30.0, 70.0])
        self.assertEqual(nueva.estado, 'vigente')
        self.assertEqual(A.porcentaje, 10.0, 'la versión vieja queda como estaba')

    # --- pantalla ------------------------------------------------------------------------------------------------

    def test_la_sublista_de_quienes_reciben_es_editable_solo_en_la_pantalla_y_nadie_escribe_el_reparto(self):
        """El ``edit="1"`` es la pantalla: nadie tiene permiso de escribir en el reparto (a propósito), y por eso Odoo
        marcaba la sublista como no editable y no se podía agregar a nadie. En una versión guardada el campo es de solo
        lectura (``readonly="id"``)."""
        for usuario in (self.u_nomina, self.u_gerencia):
            self.assertFalse(self.env['dcasa.web.reparto'].with_user(usuario).has_access('write'),
                             'nadie escribe un reparto por permiso: el servidor lo niega siempre')
            self.assertFalse(self.env['dcasa.web.reparto'].with_user(usuario).has_access('unlink'))
            vista = self.env['dcasa.web.reglas'].with_user(usuario).get_views([[False, 'form']])
            arch = etree.fromstring(vista['views']['form']['arch'])
            campo = arch.xpath("//field[@name='reparto_ids']")[0]
            self.assertEqual(campo.get('readonly'), 'id', 'una versión guardada no se edita')
            sublista = campo.xpath('./list')[0]
            self.assertEqual(sublista.get('edit'), '1', 'sin esto Odoo la marca no editable y no se puede agregar a nadie')
            self.assertEqual(sublista.get('editable'), 'bottom')

    def test_el_formulario_de_una_version_no_se_duplica(self):
        """Menor 4: «Duplicar» daba el error «Elige quiénes reciben…» (el reparto no se copia)."""
        vista = self.env['dcasa.web.reglas'].with_user(self.u_nomina).get_views([[False, 'form']])
        self.assertEqual(etree.fromstring(vista['views']['form']['arch']).get('duplicate'), '0')

    def test_lo_que_devuelve_create_no_trae_la_llave_interna_del_reparto(self):
        """Menor 5: ``create`` devolvía las versiones con la llave interna del reparto en su contexto."""
        version = self.version(10.0)
        self.assertNotIn(CLAVE_CREANDO, version.env.context)
        self.assertNotIn(CLAVE_CREANDO, version.reparto_ids.env.context)
        for linea in version.reparto_ids:
            self.assertTrue(self.bloqueada(lambda linea=linea: linea.sudo().write({'usuario_ids': [Command.set(self.u_nomina.ids)]})))
        self.assertEqual(sorted(version.reparto_ids.mapped('porcentaje')), [40.0, 60.0], 'y el reparto sigue completo')
