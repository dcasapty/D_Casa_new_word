"""Cotizar: la API para la pantalla, Brian y (mañana) la web; el índice en memoria y el precio en la lista."""
from unittest.mock import patch

from odoo.addons.dcasa_brian.models import pasos
from odoo.tests import tagged

from ..models import lugar as modulo_lugar
from ..motor import buscador
from .common import EnviosComun


@tagged('post_install', '-at_install')
class TestCotizar(EnviosComun):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.importar()

    def test_cotizar_por_kilometros(self):
        Tarifa = self.env['dcasa.envio.tarifa'].with_user(self.vendedora)
        quince = Tarifa.cotizar_km(15)
        self.assertEqual((quince['con_precio'], quince['total'], quince['total_txt'], quince['km_txt']),
                         (True, 25.0, '$25', '15 km'))
        self.assertEqual(quince['desglose'], [{'texto': 'Tarifa base', 'monto': '$25'}])
        self.assertEqual(quince['tarifa'], {'configurada': True, 'aprobada': False,
                                            'aviso': 'Tarifa en revisión: estos precios todavía no se usan con '
                                                     'clientes.'})
        self.assertEqual(Tarifa.cotizar_km(0)['total'], 10.0, 'el mínimo')
        lejos = Tarifa.cotizar_km(305)
        self.assertEqual(lejos['aviso_lejos'], 'Pasa de 300 km: confirmar con Gerencia.')
        for malo in (-1, 'mucho', None, 99999):
            self.assertFalse(Tarifa.cotizar_km(malo)['con_precio'])
        self.tarifa.cargo_ids.filtered(lambda c: c.codigo == 'peaje').with_user(self.gerencia).write(
            {'monto': 3, 'activo': True})
        con_peaje = Tarifa.cotizar_km(15, peaje=True)
        self.assertEqual((con_peaje['base'], con_peaje['total']), (25.0, 28.0))
        self.assertEqual(con_peaje['extras'], [{'nombre': 'Peaje', 'monto': 3.0}])
        self.assertEqual(Tarifa.cotizar_km(15)['total'], 25.0, 'sin peaje no se cobra')

    def test_cotizar_un_lugar(self):
        Tarifa = self.env['dcasa.envio.tarifa'].with_user(self.vendedora)
        villa = self.lugar('Villa Prueba')
        for como in (villa, villa.id, villa._como_motor()):
            datos = Tarifa.cotizar_lugar(como)
            self.assertEqual((datos['total'], datos['texto_cliente']),
                             (15.0, 'Envío a Villa Prueba (Barrio Prueba, La Chorrera): $15.'))
        lejano = Tarifa.cotizar_lugar(self.lugar('Pueblo Lejano'))
        self.assertEqual((lejano['con_precio'], lejano['motivo']), (False, 'aparte'))
        self.assertFalse(Tarifa.cotizar_lugar(self.lugar('Monte Sin Camino'))['con_precio'])
        self.assertTrue(Tarifa.cotizar_lugar(self.lugar('Isla Inventada'))['con_precio'], 'con lancha sí tiene precio')

    def test_buscar_para_cotizar_da_lo_mismo_a_todos_y_lo_mismo_que_el_motor(self):
        de_vendedora = self.env['dcasa.envio.lugar'].with_user(self.vendedora).buscar_para_cotizar('vla prueba')
        de_gerencia = self.env['dcasa.envio.lugar'].with_user(self.gerencia).buscar_para_cotizar('vla prueba')
        self.assertEqual(de_vendedora, de_gerencia, 'datos puros: no dependen de quién pregunta')
        primero = de_vendedora['resultados'][0]
        self.assertEqual((primero['nombre'], primero['total_txt'], primero['id']),
                         ('Villa Prueba', '$15', self.lugar('Villa Prueba').id))
        self.assertEqual(primero['url_mapa'], 'https://www.google.com/maps/dir/?api=1&origin=8.8765881,-79.7867962'
                                              '&destination=8.9011%2C-79.8011&travelmode=driving')
        self.assertEqual(de_vendedora['total'], 2)
        vacio = self.env['dcasa.envio.lugar'].buscar_para_cotizar('pruebaxx zzz')
        self.assertEqual(vacio['total'], 0)
        self.assertIn('Villa Prueba', [s['nombre'] for s in vacio['sugerencias']])
        filtrado = self.env['dcasa.envio.lugar'].buscar_para_cotizar('prueba', tipo='corregimiento')
        self.assertEqual({r['tipo'] for r in filtrado['resultados']}, {'corregimiento'})
        de_la_zona = self.env['dcasa.envio.lugar'].buscar_para_cotizar('ensayo', distrito='Panamá Oeste')
        self.assertTrue(de_la_zona['total'])
        self.assertEqual({r['prov'] for r in de_la_zona['resultados']}, {'Panamá Oeste'})
        largo = self.env['dcasa.envio.lugar'].buscar_para_cotizar('prueba ' * 100, tipo='otra cosa', limite=10 ** 6)
        self.assertEqual(largo['texto'], ('prueba ' * 100)[:120])
        self.assertLessEqual(len(largo['resultados']), 200)
        self.assertEqual(self.env['dcasa.envio.lugar'].buscar_para_cotizar(None)['total'], 0)

    def test_al_aprobar_desaparece_el_aviso(self):
        self.tarifa.with_user(self.gerencia).action_aprobar()
        datos = self.env['dcasa.envio.lugar'].with_user(self.vendedora).buscar_para_cotizar('villa prueba')
        self.assertEqual(datos['tarifa'], {'configurada': True, 'aprobada': True, 'aviso': ''})
        pantalla = self.env['dcasa.envio.lugar'].with_user(self.vendedora).datos_de_la_calculadora()
        self.assertTrue(pantalla['tarifa']['aprobada'])
        self.assertEqual(pantalla['tarifa']['aprobada_por'], 'Gerencia Envíos')

    def test_lo_que_necesita_la_pantalla(self):
        datos = self.env['dcasa.envio.lugar'].with_user(self.vendedora).datos_de_la_calculadora()
        self.assertEqual(datos['total_lugares'], 39)
        self.assertIn('La Chorrera', datos['distritos'])
        self.assertIn('Panamá Oeste', datos['provincias'])
        self.assertEqual(datos['corregimientos']['La Chorrera'], ['Barrio Prueba', 'Cerro Ficticio', 'Los Ensayos'])
        self.assertFalse(datos['es_gerencia'])
        tarifa = datos['tarifa']
        self.assertEqual([f['texto'] for f in tarifa['regla'] if f['clase'] == 'ficha'],
                         ['$10.00 de salida', '$1.000 por km', 'mínimo $10', 'redondeado a $5 hacia arriba'])
        self.assertEqual(tarifa['tramos'][:3], [{'km_txt': 'hasta 0 km', 'precio_txt': '$10'},
                                                {'km_txt': '0.1 – 5 km', 'precio_txt': '$15'},
                                                {'km_txt': '5.1 – 10 km', 'precio_txt': '$20'}])
        self.assertIn('OpenStreetMap', datos['atribucion'])

    def test_un_lugar_nuevo_sale_en_la_busqueda_al_momento(self):
        Lugar = self.env['dcasa.envio.lugar'].with_user(self.vendedora)
        self.assertEqual(Lugar.buscar_para_cotizar('casa del mango')['total'], 0)
        nuevo = Lugar.create({'name': 'Casa del Mango', 'tipo': 'barrio', 'dist': 'La Chorrera', 'km': 3.3})
        datos = Lugar.buscar_para_cotizar('casa del mango')
        self.assertEqual(datos['resultados'][0]['id'], nuevo.id)
        self.assertIn({'texto': 'agregado a mano', 'clase': 'mano'}, datos['resultados'][0]['chips'])
        nuevo.with_user(self.gerencia).write({'active': False})
        self.assertEqual(Lugar.buscar_para_cotizar('casa del mango')['total'], 0, 'archivado ya no sale')

    def test_el_indice_se_arma_una_vez_por_version_y_vale_para_varios_procesos(self):
        Lugar = self.env['dcasa.envio.lugar']
        Lugar.buscar_para_cotizar('villa')
        clave = self.env.cr.dbname
        version, indice, _ids = modulo_lugar._INDICES[clave]
        with patch.object(buscador, 'Indice', wraps=buscador.Indice) as armar:
            Lugar.buscar_para_cotizar('villa')
            Lugar.buscar_para_cotizar('torre')
            self.assertEqual(armar.call_count, 0, 'con la misma versión se reusa el índice')
            # Otro proceso cambió los lugares: la versión de la base ya no es la de este proceso.
            modulo_lugar._INDICES[clave] = ('una-version-vieja', indice, _ids)
            Lugar.buscar_para_cotizar('villa')
            self.assertEqual(armar.call_count, 1, 'con otra versión se vuelve a armar')
            self.lugar('Villa Prueba').with_user(self.gerencia).write({'km': 1.3})
            self.assertNotEqual(Lugar._version(), version)
            Lugar.buscar_para_cotizar('villa')
            self.assertEqual(armar.call_count, 2)
        self.assertEqual(Lugar.buscar_para_cotizar('villa prueba')['resultados'][0]['km'], 1.3)

    def test_el_precio_en_la_lista_y_al_exportar(self):
        villa, lejano = self.lugar('Villa Prueba'), self.lugar('Pueblo Lejano')
        self.assertEqual((villa.precio_envio, villa.precio_envio_txt, villa.tarifa_base, villa.cotizar_aparte),
                         (15.0, '$15', 15.0, False))
        self.assertEqual((lejano.precio_envio, lejano.precio_envio_txt, lejano.cotizar_aparte),
                         (0.0, 'Cotizar aparte', True))
        # Exportar es de quien tiene el permiso «Exportar» de Odoo (los administradores; se da en la ficha del usuario).
        self.gerencia.group_ids = [(4, self.env.ref('base.group_allow_export').id)]
        filas = (villa | lejano).with_user(self.gerencia).export_data(['name', 'km', 'precio_envio',
                                                                       'precio_envio_txt'])['datas']
        self.assertEqual(filas, [['Villa Prueba', 1.2, 15.0, '$15'], ['Pueblo Lejano', 305.0, 0.0, 'Cotizar aparte']])

    def test_brian_cotiza_y_dice_si_la_tarifa_esta_en_revision(self):
        Brian = self.env['brian.herramientas'].with_user(self.vendedora)
        self.assertIn('cotizar_envio', {h['name'] for h in Brian.catalogo()})
        r = Brian.ejecutar('cotizar_envio', {'lugar': 'villa prueba'})
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['datos']['tarifa'], 'en revisión: estos precios todavía no se usan con clientes')
        self.assertEqual(r['datos']['lugares'][0]['lugar'], 'Villa Prueba')
        self.assertEqual(r['datos']['lugares'][0]['total'], '$15')
        self.assertEqual(r['datos']['lugares'][0]['texto_para_el_cliente'],
                         'Envío a Villa Prueba (Barrio Prueba, La Chorrera): $15.')
        km = Brian.ejecutar('cotizar_envio', {'km': '15', 'peaje': 'no'})
        self.assertEqual((km['datos']['total'], km['datos']['desglose']), ('$25', 'Tarifa base $25'))
        nada = Brian.ejecutar('cotizar_envio', {'lugar': 'pruebaxx zzz'})
        self.assertEqual(nada['datos']['encontrados'], 0)
        self.assertIn('Villa Prueba', nada['datos']['quisiste_decir'])
        aparte = Brian.ejecutar('cotizar_envio', {'lugar': 'pueblo lejano'})
        self.assertIn('se cotiza aparte', aparte['datos']['lugares'][0]['precio'])
        self.assertFalse(Brian.ejecutar('cotizar_envio', {})['ok'])
        self.tarifa.with_user(self.gerencia).action_aprobar()
        self.assertEqual(Brian.ejecutar('cotizar_envio', {'km': 15})['datos']['tarifa'], 'aprobada por Gerencia')
        self.assertEqual(pasos.titulo_paso('cotizar_envio', {'lugar': 'x'}), 'Calculando el precio del envío')
