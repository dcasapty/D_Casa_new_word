"""Quién puede qué: todo el equipo cotiza y agrega un lugar que falta; solo Gerencia y los administradores cambian la
tarifa, la aprueban, editan o archivan lugares e importan. Probado como lo haría alguien por RPC (los mismos métodos
públicos, con su usuario)."""
from lxml import etree

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import EnviosComun


@tagged('post_install', '-at_install')
class TestPermisos(EnviosComun):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.importar()

    def test_la_vendedora_no_cambia_la_tarifa(self):
        tarifa = self.tarifa.with_user(self.vendedora)
        self.assertEqual(tarifa.minimo, 10, 'la lee (para cotizar)')
        for accion in (lambda: tarifa.write({'minimo': 1}), lambda: tarifa.write({'aprobada': True}),
                       tarifa.action_aprobar, tarifa.action_subir_5, tarifa.action_bajar_5,
                       tarifa.action_cargar_archivo, lambda: tarifa.write({'cargo_ids': [(0, 0, {'name': 'X'})]}),
                       lambda: self.env['dcasa.envio.cargo'].with_user(self.vendedora).create(
                           {'tarifa_id': tarifa.id, 'name': 'Propina', 'monto': 5, 'activo': True}),
                       lambda: tarifa.cargo_ids[:1].write({'monto': 99, 'activo': True}),
                       tarifa.cargo_ids[:1].unlink,
                       self.env['dcasa.envio.tarifa'].with_user(self.vendedora).action_abrir):
            with self.subTest(accion=accion), self.assertRaises(AccessError):
                accion()
        self.assertEqual(self.tarifa.minimo, 10)
        self.assertFalse(self.tarifa.aprobada)
        self.assertFalse(self.tarifa.cargo_ids.filtered('activo'))

    def test_gerencia_aprueba_con_su_nombre_y_no_se_puede_falsear(self):
        tarifa = self.tarifa.with_user(self.gerencia)
        tarifa.write({'aprobada': True, 'aprobada_por': self.vendedora.id, 'aprobada_el': '2020-01-01 00:00:00'})
        self.assertTrue(tarifa.aprobada)
        self.assertEqual(tarifa.aprobada_por, self.gerencia, 'quién aprobó lo pone el servidor')
        self.assertNotEqual(str(tarifa.aprobada_el)[:4], '2020')
        tarifa.write({'aprobada_por': self.vendedora.id})
        self.assertEqual(tarifa.aprobada_por, self.gerencia)
        tarifa.action_subir_5()
        self.assertEqual(tarifa.ajuste_pct, 5)
        self.assertFalse(tarifa.aprobada, 'un cambio de precios la devuelve a revisión')
        self.assertFalse(tarifa.aprobada_por)
        tarifa.action_aprobar()
        tarifa.write({'nota': 'Solo una nota'})
        self.assertTrue(tarifa.aprobada, 'una nota no cambia precios')
        tarifa.cargo_ids.filtered(lambda c: c.codigo == 'peaje').write({'monto': 2, 'activo': True})
        self.assertFalse(tarifa.aprobada, 'un cargo nuevo también la devuelve a revisión')
        tarifa.action_aprobar()
        tarifa.action_quitar_aprobacion()
        self.assertFalse(tarifa.aprobada)

    def test_la_tarifa_es_una_sola_y_no_se_borra(self):
        with self.assertRaises(UserError):
            self.env['dcasa.envio.tarifa'].with_user(self.gerencia).create({'name': 'Otra'})
        with self.assertRaises(UserError):
            self.tarifa.with_user(self.gerencia).unlink()
        with self.assertRaises(ValidationError):
            self.tarifa.with_user(self.gerencia).write({'ancla_b_km': 5})
        with self.assertRaises(ValidationError):
            self.tarifa.with_user(self.gerencia).write({'ajuste_pct': -95})
        for _vez in range(70):
            self.tarifa.with_user(self.gerencia).action_subir_5()
        self.assertEqual(self.tarifa.ajuste_pct, 300, 'el ajuste se queda en +300 %')

    def test_la_vendedora_agrega_un_lugar_y_queda_su_nombre(self):
        Lugar = self.env['dcasa.envio.lugar'].with_user(self.vendedora)
        lugar = Lugar.create({'name': '  Casa   Azul ', 'alias': 'La azul\n\nCasa del árbol', 'tipo': 'edificio',
                              'dist': 'Arraiján', 'corr': 'Vista Inventada', 'km': 18.04, 'peaje': True})
        self.assertEqual((lugar.name, lugar.origen, lugar.agregado, lugar.agregado_por, lugar.cat, lugar.prov),
                         ('Casa Azul', 'mano', True, self.vendedora, 'edificio o PH', 'Panamá Oeste'))
        self.assertEqual((lugar.km, lugar.fuente_km, lugar.estado, lugar.alias), (18.0, 'a mano (Google Maps)', 'ok',
                                                                                  'La azul\nCasa del árbol'))
        self.assertTrue(lugar.agregado_el)
        with self.assertRaisesRegex(ValidationError, 'ya está en la lista'):
            Lugar.create({'name': 'casa azul', 'tipo': 'edificio', 'dist': 'Arraiján', 'km': 3})
        for valores, error in (
                ({'name': 'X', 'tipo': 'corregimiento', 'dist': 'Arraiján', 'km': 3}, ValidationError),
                ({'name': 'X', 'tipo': 'barrio', 'dist': 'Arraiján'}, ValidationError),
                ({'name': 'X', 'tipo': 'barrio', 'dist': 'Arraiján', 'km': -1}, ValidationError),
                ({'name': '', 'tipo': 'barrio', 'dist': 'Arraiján', 'km': 2}, ValidationError),
                ({'name': 'X', 'tipo': 'barrio', 'dist': 'Arraiján', 'km': 2, 'origen': 'archivo'}, UserError),
                ({'name': 'X', 'tipo': 'barrio', 'dist': 'Arraiján', 'km': 2, 'agregado_por': self.gerencia.id},
                 UserError),
                ({'name': 'X', 'tipo': 'barrio', 'dist': 'Arraiján', 'km': 2, 'estado': 'fuera'}, UserError)):
            with self.subTest(valores=valores), self.assertRaises(error):
                Lugar.create(valores)

    def test_la_vendedora_no_edita_ni_archiva_lugares(self):
        villa = self.lugar('Villa Prueba').with_user(self.vendedora)
        propio = self.env['dcasa.envio.lugar'].with_user(self.vendedora).create(
            {'name': 'Lo mío', 'tipo': 'barrio', 'dist': 'La Chorrera', 'km': 1})
        for registro in (villa, propio):
            with self.assertRaises(AccessError):
                registro.write({'km': 99})
            with self.assertRaises(AccessError):
                registro.write({'active': False})
            with self.assertRaises(AccessError):
                registro.unlink()
            with self.assertRaises(AccessError):
                registro.action_volver_al_archivo()
        self.assertEqual(self.lugar('Villa Prueba').km, 1.2)

    def test_gerencia_edita_y_archiva_pero_no_toca_lo_del_sistema(self):
        villa = self.lugar('Villa Prueba').with_user(self.gerencia)
        villa.write({'km': 1.4, 'peaje': True})
        self.assertEqual((villa.km, villa.editado_por), (1.4, self.gerencia))
        villa.write({'active': False})
        self.assertFalse(villa.active)
        for campo, valor in (('origen', 'mano'), ('llave', 'x'), ('agregado_por', self.vendedora.id),
                             ('editado_el', False), ('secuencia', 99)):
            with self.subTest(campo=campo), self.assertRaises(UserError):
                villa.write({campo: valor})
        with self.assertRaises(AccessError):
            villa.unlink()
        # La marca de «cargando el archivo» no se puede mandar por RPC (un contexto JSON no trae su valor).
        falsa = villa.with_context(dcasa_envios_importando=True)
        with self.assertRaises(UserError):
            falsa.write({'agregado_por': self.vendedora.id})
        with self.assertRaises(UserError):
            falsa.env['dcasa.envio.lugar'].create({'name': 'Falso', 'tipo': 'barrio', 'dist': 'La Chorrera', 'km': 2,
                                                   'origen': 'archivo', 'llave': 'x'})
        corregimiento = self.env['dcasa.envio.lugar'].with_user(self.gerencia).create(
            {'name': 'Corregimiento Nuevo', 'tipo': 'corregimiento', 'dist': 'Distrito Lejano', 'km': 80,
             'estado': 'revisar'})
        self.assertEqual((corregimiento.origen, corregimiento.prov, corregimiento.estado),
                         ('mano', 'Provincia Lejana', 'revisar'))

    def test_el_portal_no_cotiza(self):
        for llamada in (lambda: self.env['dcasa.envio.lugar'].with_user(self.portal).buscar_para_cotizar('villa'),
                        lambda: self.env['dcasa.envio.lugar'].with_user(self.portal).datos_de_la_calculadora(),
                        lambda: self.env['dcasa.envio.tarifa'].with_user(self.portal).cotizar_km(10),
                        lambda: self.env['dcasa.envio.tarifa'].with_user(self.portal).cotizar_lugar(
                            self.lugar('Villa Prueba').id)):
            with self.subTest(llamada=llamada), self.assertRaises(AccessError):
                llamada()
        self.assertTrue(self.env['dcasa.envio.lugar'].with_user(self.portal).sudo().buscar_para_cotizar('villa')
                        ['total'], 'con sudo (como lo llamará la web) sí')

    def test_la_lista_no_le_ofrece_editar_a_quien_no_es_gerencia(self):
        def raiz(usuario, tipo):
            arch = self.env['dcasa.envio.lugar'].with_user(usuario).get_view(view_type=tipo)['arch']
            return etree.fromstring(arch)
        for tipo in ('list', 'form'):
            vendedora, gerencia = raiz(self.vendedora, tipo), raiz(self.gerencia, tipo)
            with self.subTest(tipo=tipo):
                self.assertEqual([vendedora.get(a) for a in ('create', 'edit', 'delete')], ['0', '0', '0'])
                self.assertIsNone(gerencia.get('create'))

    def test_lo_que_agrega_el_equipo_queda_por_revisar_hasta_que_gerencia_lo_revisa(self):
        """Revisión adversarial del 2026-11-12 (I7): Juan no le da a un cliente el precio de un lugar que agregó alguien
        del equipo (km medidos por ella) hasta que Gerencia lo revise."""
        Lugar = self.env['dcasa.envio.lugar']
        propio = Lugar.with_user(self.vendedora).create(
            {'name': 'Residencial Por Revisar', 'tipo': 'barrio', 'dist': 'Colón', 'corr': 'Barrio Simulado', 'km': 1})
        self.assertEqual((propio.revisado, propio.revisado_por, propio.revisado_el), (False, self.env['res.users'],
                                                                                       False))
        self.assertIn(propio, Lugar.search([('revisado', '=', False)]), 'sale en el filtro «Por revisar»')
        self.assertTrue(propio.with_user(self.vendedora).precio_envio_txt, 'la calculadora lo sigue usando')
        de_gerencia = Lugar.with_user(self.gerencia).create(
            {'name': 'Residencial De Gerencia', 'tipo': 'barrio', 'dist': 'Colón', 'km': 2})
        self.assertEqual((de_gerencia.revisado, de_gerencia.revisado_por), (True, self.gerencia))
        self.assertTrue(self.lugar('Villa Prueba').revisado, 'los del archivo nacen revisados')
        # La vendedora no lo marca revisado ni le cambia los km o la provincia; nadie escribe la marca a mano.
        for accion in (propio.with_user(self.vendedora).action_marcar_revisado,
                       lambda: propio.with_user(self.vendedora).write({'km': 30}),
                       lambda: propio.with_user(self.vendedora).write({'prov': 'Panamá'})):
            with self.subTest(accion=accion), self.assertRaises(AccessError):
                accion()
        for campo, valor in (('revisado', True), ('revisado_por', self.gerencia.id), ('revisado_el', False)):
            with self.subTest(campo=campo), self.assertRaises(UserError):
                propio.with_user(self.gerencia).write({campo: valor})
        propio.with_user(self.gerencia).action_marcar_revisado()
        self.assertEqual((propio.revisado, propio.revisado_por), (True, self.gerencia))
        self.assertTrue(propio.revisado_el)

    def test_la_ficha_tiene_el_boton_y_la_lista_el_filtro(self):
        ficha = etree.fromstring(self.env['dcasa.envio.lugar'].with_user(self.gerencia).get_view(
            view_type='form')['arch'])
        boton = ficha.xpath("//button[@name='action_marcar_revisado']")
        self.assertTrue(boton)
        self.assertEqual(boton[0].get('invisible'), 'revisado')
        buscar = etree.fromstring(self.env['dcasa.envio.lugar'].get_view(view_type='search')['arch'])
        self.assertEqual(buscar.xpath("//filter[@name='por_revisar']")[0].get('domain'), "[('revisado', '=', False)]")
        # La vendedora no ve el botón (grupos de Gerencia y administradores).
        de_la_vendedora = etree.fromstring(self.env['dcasa.envio.lugar'].with_user(self.vendedora).get_view(
            view_type='form')['arch'])
        self.assertFalse(de_la_vendedora.xpath("//button[@name='action_marcar_revisado']"))

    def _migracion(self, version):
        import importlib.util

        from odoo.tools.misc import file_path
        spec = importlib.util.spec_from_file_location(
            f'mig_revisado_{version}', file_path(f'dcasa_envios/migrations/{version}/post-migrate.py'))
        migracion = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migracion)
        return migracion

    def test_al_actualizar_todo_lo_agregado_a_mano_queda_por_revisar(self):
        """Segunda vuelta (M-6): el rol de HOY no dice quién lo agregó ni si se revisó; Gerencia los revisa una vez."""
        Lugar = self.env['dcasa.envio.lugar']
        propio = Lugar.with_user(self.vendedora).create({'name': 'Viejo Del Equipo', 'tipo': 'barrio',
                                                        'dist': 'La Chorrera', 'km': 3})
        de_gerencia = Lugar.with_user(self.gerencia).create({'name': 'Viejo De Gerencia', 'tipo': 'barrio',
                                                            'dist': 'La Chorrera', 'km': 4})
        self.env.flush_all()
        self.env.cr.execute('UPDATE dcasa_envio_lugar SET revisado = TRUE, revisado_por = NULL')  # la columna nueva
        Lugar.invalidate_model()
        self._migracion('19.0.1.2.0').migrate(self.env.cr, '19.0.1.1.0')
        Lugar.invalidate_model()
        self.assertEqual((propio.revisado, de_gerencia.revisado), (False, False))
        self.assertTrue(self.lugar('Villa Prueba').revisado, 'los de la tabla cargada, revisados')
        # Donde ya corrió la de antes: lo que Gerencia revisó con el botón se queda revisado; lo demás, por revisar.
        de_gerencia.with_user(self.gerencia).action_marcar_revisado()
        self.env.flush_all()
        self.env.cr.execute('UPDATE dcasa_envio_lugar SET revisado = TRUE WHERE id = %s', [propio.id])
        Lugar.invalidate_model()
        self._migracion('19.0.1.3.0').migrate(self.env.cr, '19.0.1.2.0')
        Lugar.invalidate_model()
        self.assertEqual((propio.revisado, de_gerencia.revisado), (False, True))
        self.assertTrue(self.lugar('Villa Prueba').revisado)
