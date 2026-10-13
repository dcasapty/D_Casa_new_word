"""Asignar el código de barras desde la referencia: sin pisar, sin repetir, revisable y reversible."""
from unittest.mock import patch

from odoo.addons.dcasa_barras.models.asignacion import planear_codigos
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .comun import BarrasCommon


@tagged('post_install', '-at_install')
class TestPlan(BarrasCommon):
    """El plan, sin base de datos."""

    def decidir(self, productos, usados=()):
        filas = [{'id': i, 'default_code': ref, 'barcode': codigo} for i, (ref, codigo) in enumerate(productos, 1)]
        plan = planear_codigos(filas, usados)
        return [plan[i][0] for i in range(1, len(filas) + 1)]

    def test_cada_caso(self):
        self.assertEqual(self.decidir([
            ('A-1', False),           # se asigna
            ('B-1', '123'),           # ya tiene: no se pisa
            (False, False),           # sin referencia
            ('  ', False),            # referencia en blanco
            ('Ñandú', False),         # caracteres que un lector no escribe
            ('con espacio', False),   # el espacio tampoco
            ('R-1', False), ('r-1', False),    # repetida (sin mirar mayúsculas): ninguna se asigna
            ('U-1', False),           # ya es el código de otro producto
        ], usados=['u-1', '123']),
            ['asignar', 'ya_tiene', 'sin_referencia', 'sin_referencia', 'caracteres', 'caracteres',
             'repetida', 'repetida', 'usada'])

    def test_el_codigo_es_la_referencia_sin_espacios_de_los_lados(self):
        plan = planear_codigos([{'id': 1, 'default_code': '  ZZT-CAMA-1 ', 'barcode': False}])
        self.assertEqual(plan[1], ('asignar', 'ZZT-CAMA-1'))

    def test_las_variantes_con_su_propia_referencia_quedan_distintas(self):
        decision = planear_codigos([{'id': i, 'default_code': f'CAMA-{t}', 'barcode': False}
                                    for i, t in enumerate(('TWIN', 'FULL', 'QUEEN', 'KING'), 1)])
        self.assertEqual({d for d, _c in decision.values()}, {'asignar'})
        self.assertEqual(len({c for _d, c in decision.values()}), 4)


@tagged('post_install', '-at_install')
class TestAsignacion(BarrasCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Se aparta todo lo demás del catálogo: la prueba solo mira lo suyo.
        otros = cls.env['product.product'].search([('id', 'not in', (cls.cama | cls.zapatera).ids)])
        otros.write({'active': False})
        cls.nuevo = cls.producto('Nuevo con referencia', 'NUE-1')
        cls.sin_ref = cls.producto('Sin referencia')
        cls.rep_a = cls.producto('Repetido A', 'REP-9')
        cls.rep_b = cls.producto('Repetido B', 'REP-9')
        cls.raro = cls.producto('Con acento', 'Ñu-1')

    def asignar(self, usuario=None):
        asignacion = self.env['dcasa.barras.asignacion'].with_user(usuario or self.gerencia).create({})
        asignacion.action_revisar()
        return asignacion

    def decisiones(self, asignacion):
        return {linea.producto_id: linea.decision for linea in asignacion.linea_ids}

    def test_revisar_no_cambia_ningun_producto_y_cuenta_todo(self):
        asignacion = self.asignar()
        self.assertEqual(self.decisiones(asignacion), {
            self.cama: 'asignar', self.nuevo: 'asignar', self.zapatera: 'ya_tiene', self.sin_ref: 'sin_referencia',
            self.rep_a: 'repetida', self.rep_b: 'repetida', self.raro: 'caracteres'})
        self.assertEqual((asignacion.n_asignar, asignacion.n_ya_tienen, asignacion.n_sin_referencia,
                          asignacion.n_repetidas, asignacion.n_otros), (2, 1, 1, 2, 1))
        self.assertFalse(self.cama.barcode or self.nuevo.barcode)
        self.assertEqual(asignacion.estado, 'borrador')

    def test_aplicar_escribe_la_referencia_y_nunca_pisa_un_codigo_existente(self):
        asignacion = self.asignar()
        asignacion.action_aplicar()
        self.assertEqual(asignacion.estado, 'aplicada')
        self.assertEqual((self.cama.barcode, self.nuevo.barcode), ('ZZT-CAMA-1', 'NUE-1'))
        self.assertEqual(self.zapatera.barcode, '7501234567890', 'el que ya tenía código sigue igual')
        self.assertFalse(self.rep_a.barcode or self.rep_b.barcode or self.sin_ref.barcode or self.raro.barcode)
        self.assertEqual(asignacion.n_asignados, 2)
        # y el lector lo encuentra por ese código
        self.assertEqual(self.Barras.buscar('NUE-1')['forma'], 'codigo_de_barras')

    def test_repetir_no_cambia_nada(self):
        self.asignar().action_aplicar()
        segunda = self.asignar()
        self.assertEqual(segunda.n_asignar, 0)
        self.assertEqual(segunda.n_ya_tienen, 3)
        with self.assertUserError():
            segunda.action_aplicar()

    def test_antes_de_escribir_se_vuelve_a_comprobar(self):
        """Entre revisar y aplicar alguien le puso un código al producto: no se pisa."""
        asignacion = self.asignar()
        self.nuevo.barcode = 'OTRO-CODIGO'
        self.producto('Otro con ese código', 'XXX-1', barcode='ZZT-CAMA-1')   # y otro ya usó el de la cama
        asignacion.action_aplicar()
        self.assertEqual(self.nuevo.barcode, 'OTRO-CODIGO')
        self.assertFalse(self.cama.barcode)
        decisiones = {linea.producto_id: linea.decision for linea in asignacion.linea_ids}
        self.assertEqual(decisiones[self.nuevo], 'ya_tiene')
        self.assertEqual(decisiones[self.cama], 'usada')

    def test_un_codigo_de_un_producto_archivado_tambien_cuenta_como_usado(self):
        archivado = self.producto('Archivado', 'VIEJO-1', barcode='NUE-1')
        archivado.action_archive()
        asignacion = self.asignar()
        self.assertEqual(self.decisiones(asignacion)[self.nuevo], 'usada')

    def test_deshacer_quita_solo_lo_que_se_asigno_y_sigue_igual(self):
        asignacion = self.asignar()
        asignacion.action_aplicar()
        self.nuevo.barcode = 'CAMBIADO-A-MANO'
        asignacion.action_deshacer()
        self.assertEqual(asignacion.estado, 'deshecha')
        self.assertFalse(self.cama.barcode, 'lo que se asignó y siguió igual se quita')
        self.assertEqual(self.nuevo.barcode, 'CAMBIADO-A-MANO', 'lo que alguien cambió después no se toca')
        self.assertEqual(self.zapatera.barcode, '7501234567890')
        with self.assertUserError():
            asignacion.action_deshacer()

    def test_no_se_puede_aplicar_ni_revisar_dos_veces(self):
        asignacion = self.asignar()
        asignacion.action_aplicar()
        with self.assertUserError():
            asignacion.action_aplicar()
        with self.assertUserError():
            asignacion.action_revisar()

    def test_un_error_de_permisos_al_escribir_el_producto_no_se_calla(self):
        """Si Odoo no deja escribir el producto, el aviso sale: no queda como un «error» silencioso en la línea."""
        asignacion = self.asignar()
        sin_permiso = AccessError("No puedes escribir productos")
        with patch.object(self.env.registry['product.product'], 'write', side_effect=sin_permiso):
            with self.assertRaises(AccessError):
                asignacion.action_aplicar()
        self.assertNotIn('error', asignacion.linea_ids.mapped('decision'))
        self.assertEqual(asignacion.estado, 'borrador')

    def test_administrar_inventario_sin_productos_no_basta(self):
        asignacion = self.asignar()
        with self.assertRaises(AccessError):
            asignacion.with_user(self.solo_inventario).action_aplicar()
        self.assertFalse(self.cama.barcode)

    def test_si_le_cambian_la_referencia_despues_de_revisar_no_se_asigna(self):
        asignacion = self.asignar()
        self.cama.default_code = 'ZZT-CAMA-OTRA'
        asignacion.action_aplicar()
        self.assertFalse(self.cama.barcode)
        self.assertEqual(self.decisiones(asignacion)[self.cama], 'error')
        self.assertEqual(self.nuevo.barcode, 'NUE-1', 'los demás sí')

    def test_si_aparece_otro_producto_con_la_misma_referencia_no_se_asigna(self):
        asignacion = self.asignar()
        self.producto('Gemelo que apareció', 'nue-1')
        asignacion.action_aplicar()
        self.assertFalse(self.nuevo.barcode)
        self.assertEqual(self.decisiones(asignacion)[self.nuevo], 'repetida')

    def test_aplicar_sin_revisar_avisa(self):
        vacia = self.env['dcasa.barras.asignacion'].with_user(self.gerencia).create({})
        with self.assertUserError():
            vacia.action_aplicar()

    def test_solo_gerencia(self):
        with self.assertRaises(AccessError):
            self.env['dcasa.barras.asignacion'].with_user(self.vendedora).create({})
        asignacion = self.asignar()
        for accion in ('action_revisar', 'action_aplicar', 'action_deshacer'):
            with self.assertRaises(AccessError, msg=accion):
                getattr(asignacion.with_user(self.vendedora), accion)()
        # la comprobación del servidor no depende de los permisos de la tabla
        with self.assertRaises(AccessError):
            asignacion.with_user(self.vendedora)._exigir_gerencia()
        # administrar Inventario sin administrar Productos tampoco basta (aunque la tabla le deje escribir)
        with self.assertRaises(AccessError):
            asignacion.with_user(self.solo_inventario)._exigir_gerencia()
        asignacion.with_user(self.gerencia)._exigir_gerencia()
        self.assertFalse(self.cama.barcode)

    def test_aplicar_y_deshacer_dejan_historial_de_etiquetas(self):
        """El historial ve también lo que escribe esta asignación, no solo el Escáner."""
        asignacion = self.asignar()
        asignacion.action_aplicar()
        Historial = self.env['dcasa.barras.etiqueta']
        filas = Historial.search([('codigo', '=', 'NUE-1')], order='id')
        self.assertEqual([(f.accion, f.motivo, f.producto_id, f.usuario_id) for f in filas],
                         [('asignada', 'Asignado desde la referencia', self.nuevo, self.gerencia)])
        asignacion.action_deshacer()
        filas = Historial.search([('codigo', '=', 'NUE-1')], order='id')
        self.assertEqual([(f.accion, f.motivo) for f in filas],
                         [('asignada', 'Asignado desde la referencia'),
                          ('retirada', 'Se deshizo la asignación desde la referencia')])
        self.assertEqual(self.como(self.gerencia).etiqueta('NUE-1')['estado'], 'retirada')
