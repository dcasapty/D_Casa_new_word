"""Ola 3 · búsqueda en el conocimiento por SIGNIFICADO (opcional, apagada por defecto).

El Worker calcula los vectores (Workers AI); Odoo solo los guarda y los compara. Aquí el Worker es falso: cada texto
se convierte en un vector según de qué tema habla, así se prueba la lógica sin red ni IA. Lo que NO se puede probar
aquí (cuánto se parecen de verdad dos frases reales en bge-m3) queda anotado en docs/PENDIENTES_DUENA.md.
"""
import json
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import BaseCase, tagged

from ..models import conocimiento as K
from ..models import conocimiento_texto as C
from .common import URL_WORKER, JuanCase, respuesta_http

TEMA_RETIRO = 17     # «nos llevamos lo usado»
TEMA_PAGOS = 301
TEMA_OTRO = 900


def vector_del_tema(*temas, ruido=0.0):
    vector = [0.0] * C.DIMENSIONES_VECTOR
    for tema in temas:
        vector[tema] = 1.0
    if ruido:
        vector[TEMA_OTRO] = ruido
    return vector


def vector_de(texto):
    """El «significado» falso de un texto: de qué tema habla (por palabras que solo usan estas pruebas)."""
    minus = texto.lower()
    temas = [t for t, claves in ((TEMA_RETIRO, ('zzretiro', 'sacan', 'recogen')), (TEMA_PAGOS, ('zzpago', 'yappy')))
             if any(c in minus for c in claves)]
    return vector_del_tema(*(temas or [TEMA_OTRO]))


@tagged('post_install', '-at_install')
class TestVectoresPuros(BaseCase):

    def test_coseno(self):
        a, b = vector_del_tema(1), vector_del_tema(2)
        self.assertAlmostEqual(C.coseno(a, a), 1.0)
        self.assertEqual(C.coseno(a, b), 0.0)
        self.assertAlmostEqual(C.coseno(vector_del_tema(1, 2), a), 0.7071, places=3)
        self.assertEqual(C.coseno([0.0, 0.0], [1.0, 2.0]), 0.0, 'Un vector nulo no se parece a nada')
        self.assertEqual(C.coseno([1.0], [1.0, 2.0]), 0.0, 'Si no miden lo mismo no se comparan')

    def test_huella_del_texto(self):
        self.assertEqual(C.huella('hola'), C.huella('hola'))
        self.assertNotEqual(C.huella('hola'), C.huella('hola '))
        self.assertEqual(len(C.huella('')), 40)

    def test_vector_valido(self):
        self.assertTrue(C.vector_valido(vector_del_tema(1)))
        for malo in (None, 'x', [], [1.0] * 3, [float('nan')] + [0.0] * 1023, [float('inf')] + [0.0] * 1023,
                     ['a'] + [0.0] * 1023, [True] + [0.0] * 1023, (0.0,) * 1024):
            self.assertFalse(C.vector_valido(malo), repr(malo)[:40])


@tagged('post_install', '-at_install')
class TestBusquedaPorSignificado(JuanCase):

    def setUp(self):
        super().setUp()
        K._SIN_SIGNIFICADO_HASTA.clear()
        self.addCleanup(K._SIN_SIGNIFICADO_HASTA.clear)
        self.Conocimiento = self.env['dcasa.conocimiento']
        self.ajustes = self.env['dcasa.juan.ajustes'].obtener()
        self.worker = self.configurar_worker()
        self.worker.side_effect = self._worker_falso
        self.lotes = []
        self.retiro = self.Conocimiento.create({
            'titulo': 'Zzretiro de lo usado', 'etiquetas': 'zzretiro',
            'contenido': 'Nos llevamos lo que ya no quieras cuando entregamos lo nuevo.'})
        self.pagos = self.Conocimiento.create({
            'titulo': 'Formas de pago', 'etiquetas': 'zzpago', 'contenido': 'Aceptamos Yappy, tarjeta y efectivo.'})
        self.inactiva = self.Conocimiento.create({
            'titulo': 'Zzretiro viejo', 'contenido': 'Texto anterior sobre el zzretiro.', 'activo': False})

    # Un Worker falso: un vector por texto, según su tema. Anota cada llamada a /odoo/embeber.
    def _worker_falso(self, metodo, url, **kwargs):
        if url != f'{URL_WORKER}/odoo/embeber':
            return respuesta_http({'ok': True})
        textos = kwargs['json']['textos']
        self.lotes.append(textos)
        if getattr(self, 'respuesta_embeber', None) is not None:
            return self.respuesta_embeber
        return respuesta_http({'ok': True, 'vectores': [vector_de(t) for t in textos], 'dimensiones': 1024,
                               'modelo': '@cf/baai/bge-m3'})

    def encender(self):
        self.ajustes.busqueda_semantica = True

    def titulos(self, consulta, limite=3):
        return [e.titulo for e, _p in self.Conocimiento._buscar(consulta, limite)]

    # -- apagada: todo como antes --------------------------------------------------------------------------

    def test_viene_apagada_y_apagada_no_llama_al_worker(self):
        self.assertFalse(self.ajustes.busqueda_semantica)
        self.assertEqual(self.Conocimiento._cron_calcular_vectores(), 0)
        self.assertEqual(self.titulos('sacan el sofá viejo'), [])
        self.assertEqual(self.lotes, [])
        self.assertFalse(self.retiro.sudo().vector)

    # -- calcular las huellas ------------------------------------------------------------------------------

    def test_el_cron_calcula_las_huellas_de_las_activas_y_solo_de_las_activas(self):
        self.encender()
        activas = self.Conocimiento.search([('activo', '=', True)])
        self.assertEqual(self.Conocimiento._cron_calcular_vectores(), len(activas))
        for entrada in activas.sudo():
            self.assertEqual(entrada.vector_huella, C.huella(entrada._texto_para_vector()))
            self.assertTrue(C.vector_valido(json.loads(entrada.vector)))
        self.assertFalse(self.inactiva.sudo().vector)
        textos = [t for lote in self.lotes for t in lote]
        self.assertIn('Zzretiro de lo usado . zzretiro . Nos llevamos lo que ya no quieras cuando entregamos lo nuevo.',
                      textos)
        self.assertTrue(all(len(t) <= 1900 for t in textos))

    def test_no_recalcula_lo_que_ya_esta_al_dia_y_si_cambia_el_texto_solo_esa(self):
        self.encender()
        self.Conocimiento._cron_calcular_vectores()
        antes = len(self.lotes)
        self.assertEqual(self.Conocimiento._cron_calcular_vectores(), 0)
        self.assertEqual(len(self.lotes), antes, 'Sin cambios no se le pide nada al Worker')
        self.retiro.contenido = 'Recogemos el colchón usado al entregar el nuevo.'
        self.assertEqual(self.Conocimiento._cron_calcular_vectores(), 1)
        self.assertEqual(self.lotes[-1], [self.retiro._texto_para_vector()])

    def test_las_entradas_automaticas_se_recalculan_si_cambia_lo_que_dicen(self):
        self.encender()
        self.Conocimiento._cron_calcular_vectores()
        tienda = self.env.ref('dcasa_conversaciones.conocimiento_tienda').sudo()
        huella = tienda.vector_huella
        with patch.object(K, 'texto_tienda', return_value='Ahora abrimos más temprano.'):
            self.env.invalidate_all()      # el texto automático se arma al leerse (cada corrida real es nueva)
            self.assertEqual(self.Conocimiento._cron_calcular_vectores(), 1, 'Solo la que cambió')
        self.assertNotEqual(tienda.vector_huella, huella)

    def test_manda_las_entradas_de_a_8_y_no_mas_de_40_por_corrida(self):
        self.encender()
        for i in range(100):
            self.Conocimiento.create({'titulo': f'Tema {i}', 'contenido': f'Contenido del tema {i}'})
        self.assertEqual(self.Conocimiento._cron_calcular_vectores(), K.VECTORES_POR_CORRIDA)
        self.assertTrue(all(len(lote) <= K.LOTE_DE_VECTORES for lote in self.lotes))
        self.assertEqual(sum(len(lote) for lote in self.lotes), K.VECTORES_POR_CORRIDA)
        self.assertEqual(self.Conocimiento._cron_calcular_vectores(), K.VECTORES_POR_CORRIDA, 'La siguiente sigue')

    def test_si_el_worker_falla_no_se_guarda_nada_y_no_revienta(self):
        self.encender()
        for respuesta in (respuesta_http({'ok': False, 'error': 'Falta el binding AI'}, 503),
                          respuesta_http({'ok': True, 'vectores': [[1, 2, 3]]}),
                          respuesta_http({'ok': True, 'vectores': []}), respuesta_http({'ok': True})):
            self.respuesta_embeber = respuesta
            self.assertEqual(self.Conocimiento._cron_calcular_vectores(), 0)
        self.assertFalse(self.Conocimiento.sudo().search([('vector', '!=', False)]))

    def test_la_huella_no_se_copia_ni_se_ve_sin_ser_gerencia(self):
        self.encender()
        self.Conocimiento._cron_calcular_vectores()
        copia = self.retiro.copy()
        self.assertFalse(copia.sudo().vector)
        self.assertFalse(copia.sudo().vector_huella)
        with self.assertRaises(AccessError):
            self.retiro.with_user(self.vendedora).vector  # noqa: B018 — solo Gerencia
        self.assertTrue(self.retiro.with_user(self.gerente).vector)

    # -- buscar --------------------------------------------------------------------------------------------

    def preparar(self):
        self.encender()
        self.Conocimiento._cron_calcular_vectores()
        self.lotes.clear()

    def test_encuentra_lo_que_las_palabras_no(self):
        self.preparar()
        self.assertEqual(self.titulos('¿Se pueden llevar mi sofá viejo? sacan?'), ['Zzretiro de lo usado'])
        self.assertEqual(self.lotes, [['¿Se pueden llevar mi sofá viejo? sacan?']], 'Una sola llamada, con la pregunta')

    def test_devuelve_el_coseno_como_puntos_y_nunca_una_inactiva(self):
        self.preparar()
        (entrada, puntos), = self.Conocimiento._buscar('sacan el sofá viejo', 3)
        self.assertEqual((entrada, puntos), (self.retiro, 100))
        self.assertNotIn(self.inactiva, [e for e, _ in self.Conocimiento._buscar('zzretiro sacan', 5)])

    def test_lo_que_no_se_parece_lo_bastante_no_sale(self):
        self.preparar()
        # La pregunta habla de retiro Y de otra cosa: coseno 0.5 con la entrada (menos que el umbral de 0.6).
        with patch(f'{__name__}.vector_de', lambda t: vector_del_tema(TEMA_RETIRO, 1000, 1001)):
            self.assertEqual(self.titulos('sacan el sofá viejo'), [], '0.58 < 0.6')
        K._SIN_SIGNIFICADO_HASTA.clear()
        with patch(f'{__name__}.vector_de', lambda t: vector_del_tema(TEMA_RETIRO, 1000)):
            self.assertEqual(self.titulos('sacan el sofá viejo'), ['Zzretiro de lo usado'], '0.71 ≥ 0.6')

    def test_lo_que_encontraron_las_palabras_va_primero_y_el_significado_solo_completa(self):
        self.preparar()
        resultados = self.titulos('zzpago sacan', 3)    # «zzpago» lo encuentran las palabras; «sacan», el significado
        self.assertEqual(resultados[0], 'Formas de pago')
        self.assertIn('Zzretiro de lo usado', resultados)

    def test_si_las_palabras_llenan_los_lugares_ni_se_le_pregunta_al_worker(self):
        self.preparar()
        for i in range(3):
            self.Conocimiento.create(
                {'titulo': f'Zzcolchones {i}', 'contenido': 'zzcolchones', 'etiquetas': 'zzcolchones'})
        self.lotes.clear()
        self.assertEqual(len(self.titulos('zzcolchones', 3)), 3)
        self.assertEqual(self.lotes, [])

    def test_una_huella_vieja_no_cuenta(self):
        self.preparar()
        self.retiro.contenido = 'Ahora decimos otra cosa sobre eso.'      # el texto cambió: su huella ya no vale
        self.assertEqual(self.titulos('sacan el sofá viejo'), [])
        self.lotes.clear()
        self.Conocimiento._cron_calcular_vectores()
        self.assertEqual(self.titulos('sacan el sofá viejo'), ['Zzretiro de lo usado'])

    def test_sin_huellas_no_se_le_pregunta_al_worker(self):
        self.encender()
        self.assertEqual(self.titulos('sacan el sofá viejo'), [])
        self.assertEqual(self.lotes, [])

    def test_si_el_worker_falla_se_sigue_por_palabras_y_no_se_insiste_por_5_minutos(self):
        self.preparar()
        self.respuesta_embeber = respuesta_http({'ok': False, 'error': 'Falta el binding AI'}, 503)
        self.assertEqual(self.titulos('sacan el sofá viejo'), [])
        self.assertEqual(self.titulos('zzpago'), ['Formas de pago'], 'Las palabras siguen funcionando')
        self.assertEqual(len(self.lotes), 1)
        self.respuesta_embeber = None
        self.assertEqual(self.titulos('sacan el sofá viejo'), [], 'Pausa: no se vuelve a intentar enseguida')
        self.assertEqual(len(self.lotes), 1)
        K._SIN_SIGNIFICADO_HASTA.clear()      # pasaron los 5 minutos
        self.assertEqual(self.titulos('sacan el sofá viejo'), ['Zzretiro de lo usado'])

    def test_la_pregunta_viaja_recortada(self):
        self.preparar()
        self.titulos('sacan ' + 'x' * 1000)
        self.assertLessEqual(len(self.lotes[0][0]), 300)

    def test_la_herramienta_del_asistente_lo_usa(self):
        self.preparar()
        herramientas = self.env['brian.herramientas'].with_user(self.juan)
        resultado = herramientas.ejecutar('juan_buscar_conocimiento', {'consulta': 'sacan el sofá viejo'}, canal='juan')
        self.assertTrue(resultado.get('ok'), resultado)
        self.assertEqual([r['titulo'] for r in resultado['datos']['resultados']], ['Zzretiro de lo usado'])
        self.assertIn('Nos llevamos lo que ya no quieras', resultado['datos']['resultados'][0]['contenido'])


@tagged('post_install', '-at_install')
class TestAjusteYCron(JuanCase):

    def test_el_ajuste_existe_apagado_y_se_cambia_desde_la_pantalla_de_ajustes(self):
        Ajustes = self.env['dcasa.juan.ajustes']
        self.assertFalse(Ajustes._fields['busqueda_semantica'].default(Ajustes))
        vista = self.env.ref('dcasa_conversaciones.view_dcasa_juan_ajustes_form')
        self.assertIn('busqueda_semantica', vista.arch)

    def test_el_cron_corre_cada_hora(self):
        cron = self.env.ref('dcasa_conversaciones.ir_cron_calcular_vectores')
        self.assertEqual((cron.interval_number, cron.interval_type), (1, 'hours'))
        self.assertEqual(cron.model_id.model, 'dcasa.conocimiento')
        self.assertIn('_cron_calcular_vectores', cron.code)
