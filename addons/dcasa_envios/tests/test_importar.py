"""«Cargar lugares y tarifa desde el archivo»: idempotente, respeta lo de Odoo y la tarifa vuelve a revisión."""
import base64

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from ..models.lugar import PARAMETRO_VERSION
from .common import EnviosComun, fixture


@tagged('post_install', '-at_install')
class TestImportar(EnviosComun):

    def test_cargar_el_html_crea_los_lugares_y_la_tarifa(self):
        asistente = self.importar()
        Lugar = self.env['dcasa.envio.lugar']
        self.assertEqual(Lugar.search_count([('origen', '=', 'archivo')]), 39)
        self.assertIn('Nuevos: 39', asistente.resumen)
        self.assertEqual(asistente.estado, 'hecho')
        self.assertFalse(asistente.archivo, 'el archivo no se queda guardado en el asistente')
        villa = self.lugar('Villa Prueba')
        self.assertEqual((villa.tipo, villa.corr, villa.dist, villa.prov, villa.km, villa.km_medido),
                         ('barrio', 'Barrio Prueba', 'La Chorrera', 'Panamá Oeste', 1.2, True))
        self.assertTrue(villa.llave)
        finca = self.lugar('Finca Agregada')
        self.assertTrue(finca.agregado, 'los agregados a mano del archivo se marcan')
        self.assertEqual(finca.alias, 'La finca')
        sin_camino = self.lugar('Monte Sin Camino')
        self.assertEqual((sin_camino.km_medido, sin_camino.estado), (False, 'sin_carretera'))
        inversiones = self.lugar('Inversiones Ensayo')
        self.assertEqual(inversiones.alias.splitlines(), ['INVERSIONES ENSAYO, S. A.', 'Ensayo Inversiones'])
        tarifa = self.tarifa
        self.assertEqual((tarifa.minimo, tarifa.ancla_a_km, tarifa.ancla_a_precio, tarifa.ancla_b_km,
                          tarifa.ancla_b_precio, tarifa.ancla_b_nombre, tarifa.paso, tarifa.modo, tarifa.max_km),
                         (10, 10, 20, 100, 110, 'Pueblo Prueba', '5', 'arriba', 300))
        self.assertEqual(tarifa.cargo_ids.mapped('codigo'), ['viatico', 'honorarios', 'peaje'])
        self.assertFalse(tarifa.aprobada, 'el «aprobada» del archivo no cuenta: se aprueba en Odoo')
        self.assertEqual((tarifa.version_archivo, str(tarifa.fecha_archivo)), (1, '2026-11-06'))
        self.assertEqual(tarifa.cargada_por, self.gerencia)
        self.assertIn('queda en revisión', asistente.resumen.lower())
        self.assertTrue(tarifa.message_ids.filtered(lambda m: 'Nuevos: 39' in (m.body or '')),
                        'el resumen queda en el historial de la tarifa')

    def test_volver_a_cargar_no_duplica(self):
        self.importar()
        ids = set(self.env['dcasa.envio.lugar'].search([]).ids)
        version = self.env['ir.config_parameter'].sudo().get_param(PARAMETRO_VERSION)
        otra = self.importar()
        self.assertEqual(set(self.env['dcasa.envio.lugar'].search([]).ids), ids)
        self.assertIn('Nuevos: 0', otra.resumen)
        self.assertIn('Actualizados: 0', otra.resumen)
        self.assertIn('Sin cambios: 39', otra.resumen)
        self.assertIn('igual a la de Odoo', otra.resumen)
        self.assertEqual(len(self.tarifa.cargo_ids), 3)
        self.assertNotEqual(self.env['ir.config_parameter'].sudo().get_param(PARAMETRO_VERSION), version)

    def test_el_json_da_lo_mismo_que_el_html(self):
        self.importar(formato='json', nombre='envios.json')
        self.assertEqual(self.env['dcasa.envio.lugar'].search_count([]), 39)
        otra = self.importar(formato='html')
        self.assertIn('Sin cambios: 39', otra.resumen)

    def test_lo_que_cambia_en_el_archivo_se_actualiza_y_lo_que_falta_se_archiva(self):
        self.importar()
        villa, loma, primero = self.lugar('Villa Prueba'), self.lugar('Loma Dudosa'), self.lugar('Barrio Prueba')
        self.assertEqual(primero.secuencia, 1)
        datos = fixture()
        nuevo = dict(datos['lugares'][14], nombre='Villa Nueva Prueba', km=2.4, lat=8.9013, lon=-79.8013)
        datos['lugares'] = [nuevo] + [lugar for lugar in datos['lugares'] if lugar['nombre'] != 'Loma Dudosa']
        next(lugar for lugar in datos['lugares'] if lugar['nombre'] == 'Villa Prueba')['km'] = 1.7
        resumen = self.importar(datos).resumen
        self.assertIn('Nuevos: 1', resumen)
        self.assertIn('Actualizados: 1', resumen)
        self.assertIn('Archivados porque ya no vienen en el archivo: 1', resumen)
        self.assertEqual(villa.km, 1.7)
        self.assertFalse(loma.active, 'archivado, no borrado')
        self.assertEqual(self.lugar('Villa Nueva Prueba').secuencia, 1)
        self.assertEqual(primero.secuencia, 2, 'el orden del archivo se corre (desempata la búsqueda)')
        regreso = self.importar().resumen
        self.assertTrue(loma.active, 'si vuelve al archivo, vuelve a la lista')
        self.assertIn('Archivados porque ya no vienen en el archivo: 1', regreso)
        self.assertFalse(self.lugar('Villa Nueva Prueba').active)

    def test_dos_lugares_con_el_mismo_nombre_se_distinguen_por_su_ubicacion(self):
        self.importar()
        duplicados = self.lugar('El Duplicado').sorted('km')
        self.assertEqual(duplicados.mapped('km'), [13.0, 14.0])
        datos = fixture()
        uno, otro = [i for i, lugar in enumerate(datos['lugares']) if lugar['nombre'] == 'El Duplicado']
        datos['lugares'][uno], datos['lugares'][otro] = datos['lugares'][otro], datos['lugares'][uno]
        datos['lugares'][otro]['km'] = 13.5          # el que estaba en 13 km, ahora mide 13.5
        resumen = self.importar(datos).resumen
        self.assertIn('Nuevos: 0', resumen)
        self.assertIn('Actualizados: 1', resumen)
        self.assertEqual(self.lugar('El Duplicado').sorted('km').mapped('km'), [13.5, 14.0])
        self.assertEqual(set(self.lugar('El Duplicado').ids), set(duplicados.ids))

    def test_respeta_lo_agregado_y_lo_cambiado_en_odoo(self):
        self.importar()
        Lugar = self.env['dcasa.envio.lugar']
        propio = Lugar.with_user(self.vendedora).create({'name': 'Casa de la Vendedora', 'tipo': 'barrio',
                                                         'dist': 'La Chorrera', 'km': 4.2})
        villa, isla = self.lugar('Villa Prueba'), self.lugar('Isla Inventada')
        villa.with_user(self.gerencia).write({'km': 1.9})
        isla.with_user(self.gerencia).write({'active': False})
        self.assertEqual((villa.editado_por, isla.editado_por), (self.gerencia, self.gerencia))
        datos = fixture()
        datos['lugares'] = [lugar for lugar in datos['lugares'] if lugar['nombre'] != 'Villa Prueba']
        resumen = self.importar(datos).resumen
        self.assertTrue(propio.exists() and propio.active)
        self.assertEqual((propio.origen, propio.agregado_por), ('mano', self.vendedora))
        self.assertEqual(villa.km, 1.9, 'lo que Gerencia corrigió en Odoo se respeta')
        self.assertTrue(villa.active, 'tampoco se archiva aunque ya no venga en el archivo')
        self.assertFalse(isla.active, 'lo archivado por Gerencia sigue archivado')
        self.assertIn('se respetó lo de Odoo): 2', resumen)
        self.assertIn('agregados en Odoo por el equipo (no se tocan): 1', resumen)
        villa.with_user(self.gerencia).action_volver_al_archivo()
        self.assertFalse(villa.editado_el)
        self.importar()
        self.assertEqual(villa.km, 1.2, 'sin la marca, el archivo vuelve a mandar')

    def test_la_tarifa_aprobada_vuelve_a_revision_solo_si_cambia(self):
        self.importar()
        tarifa = self.tarifa
        tarifa.with_user(self.gerencia).action_aprobar()
        self.assertTrue(tarifa.aprobada)
        igual = self.importar()
        self.assertTrue(tarifa.aprobada, 'el mismo archivo no le quita la aprobación')
        self.assertIn('sigue aprobada', igual.resumen)
        datos = fixture()
        datos['ajustes']['minimo'] = 12
        datos['ajustes']['extras'][2].update(monto=3, activo=True)
        datos['ajustes']['extras'].append({'id': 'x3', 'nombre': 'Subir escaleras', 'como': 'viaje', 'monto': 4,
                                           'desde': 0, 'ajusta': False, 'activo': False})
        self.importar(datos)
        self.assertFalse(tarifa.aprobada)
        self.assertFalse(tarifa.aprobada_por)
        self.assertEqual(tarifa.minimo, 12)
        self.assertEqual(tarifa.cargo_ids.mapped('codigo'), ['viatico', 'honorarios', 'peaje', 'x3'])
        self.assertTrue(tarifa.cargo_ids.filtered(lambda c: c.codigo == 'peaje').activo)
        self.assertTrue(tarifa.message_ids.filtered(lambda m: 'vuelve a revisión' in (m.body or '')))
        datos['ajustes']['extras'].pop()
        self.importar(datos)
        self.assertEqual(tarifa.cargo_ids.mapped('codigo'), ['viatico', 'honorarios', 'peaje'])

    def test_cargar_solo_los_lugares_no_toca_la_tarifa(self):
        self.importar()
        tarifa = self.tarifa
        tarifa.with_user(self.gerencia).write({'minimo': 11})
        datos = fixture()
        datos['ajustes']['minimo'] = 99
        self.importar(datos, tarifa=False)
        self.assertEqual(tarifa.minimo, 11)

    def test_un_archivo_que_no_sirve_no_cambia_nada(self):
        self.importar()
        malos = [
            ('<html><body>Otro archivo</body></html>', 'No encontré la lista de lugares'),
            ('{"lugares": "no"}', 'no tiene la forma esperada'),
        ]
        for contenido, mensaje in malos:
            asistente = self.env['dcasa.envio.importar'].with_user(self.gerencia).create(
                {'archivo': base64.b64encode(contenido.encode())})
            with self.subTest(contenido=contenido), self.assertRaisesRegex(UserError, mensaje):
                asistente.action_cargar()
        datos = fixture()
        datos['ajustes']['anclaB']['km'] = 5
        datos['lugares'][14]['km'] = 99
        with self.assertRaises(UserError):
            self.importar(datos)
        self.assertEqual(self.lugar('Villa Prueba').km, 1.2, 'la tarifa mala frena todo antes de tocar los lugares')
        with self.assertRaisesRegex(UserError, 'Elige el archivo'):
            self.env['dcasa.envio.importar'].with_user(self.gerencia).create({}).action_cargar()

    def test_solo_gerencia_carga_el_archivo(self):
        with self.assertRaises(AccessError):
            self.importar(usuario=self.vendedora)
        self.assertFalse(self.env['dcasa.envio.lugar'].search_count([]))
