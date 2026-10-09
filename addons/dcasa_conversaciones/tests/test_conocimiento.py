"""Base de conocimiento, preguntas sin respuesta, lecciones aprendidas y proveedor de IA elegible desde Odoo."""
import json
import re
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.dcasa_socios.models import reglas as R
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import BaseCase, tagged

from ..models import conocimiento_texto as C
from ..models.reglas_clientes import redactar
from .common import JuanCase


@tagged('post_install', '-at_install')
class TestTextoDelConocimiento(BaseCase):
    """Búsqueda por palabras y agrupación de preguntas parecidas (funciones puras)."""

    def test_palabras_significativas(self):
        self.assertEqual(C.tokens('¿Cuál es el horario de la tienda?'), ['horario', 'tienda'])
        self.assertEqual(C.tokens('Hola, quiero saber si tienen colchones'), ['colchon'])
        self.assertEqual(C.tokens('???'), [])
        self.assertEqual(C.tokens('cama king 2026'), ['cama', 'king', '2026'])

    def test_puntua_titulo_y_etiquetas_mas_que_el_contenido(self):
        en_titulo = C.puntuar('horario', 'Horario y WhatsApp', '', 'x')
        en_contenido = C.puntuar('horario', 'Tienda', '', 'El horario es de lunes a domingo')
        self.assertGreater(en_contenido, 0)
        self.assertGreater(en_titulo, en_contenido)
        self.assertGreater(C.puntuar('horario', 'Tienda', 'horario, abren', ''), en_contenido)

    def test_no_distingue_acentos_mayusculas_ni_plural(self):
        self.assertGreater(C.puntuar('GARANTÍAS de colchones', 'Garantía', '', 'Aplica a todos los colchon'), 0)

    def test_hace_falta_la_mitad_de_las_palabras(self):
        self.assertGreater(C.puntuar('garantía colchones', 'Garantía', '', ''), 0)             # 1 de 2
        self.assertEqual(C.puntuar('garantía colchones sofás', 'Garantía', '', ''), 0)         # 1 de 3
        self.assertEqual(C.puntuar('helicóptero', 'Garantía', 'cambios', 'texto'), 0)
        self.assertEqual(C.puntuar('', 'Garantía', '', ''), 0)

    def test_agrupa_preguntas_iguales_o_muy_parecidas(self):
        self.assertTrue(C.son_parecidas('¿Tienen garantía en los colchones?', 'garantia de colchones'))
        self.assertTrue(C.son_parecidas('¿Hacen instalación?', 'hacen instalacion'))
        self.assertFalse(C.son_parecidas('¿Tienen garantía en los colchones?', '¿Instalan los muebles?'))
        self.assertFalse(C.son_parecidas('¿cuánto dura la garantía?', 'garantía'))
        self.assertEqual(C.clave('¿Tienen garantía en los colchones?'), C.clave('colchones, garantía'))


@tagged('post_install', '-at_install')
class TestBaseDeConocimiento(JuanCase):

    def entrada(self, **valores):
        return self.env['dcasa.conocimiento'].create({'titulo': 'Prueba', 'contenido': 'Texto de prueba', **valores})

    def semilla(self, xmlid):
        return self.env.ref(f'dcasa_conversaciones.{xmlid}')

    def test_semilla_con_solo_hechos_verificados(self):
        activas = self.env['dcasa.conocimiento'].search([('activo', '=', True)])
        self.assertEqual(set(activas.mapped('fuente')), {'tienda', 'socios'})
        for xmlid in ('conocimiento_garantia', 'conocimiento_compra'):
            entrada = self.semilla(xmlid)
            self.assertFalse(entrada.activo, 'Los textos provisionales nacen inactivos')
            self.assertIn('PENDIENTE DE APROBACIÓN DE LA DUEÑA', entrada.nota)
            self.assertIn('abogado', entrada.nota)

    def test_ninguna_semilla_toca_entregas_flete_financiamiento_ni_apartados(self):
        for entrada in self.env['dcasa.conocimiento'].with_context(active_test=False).search([]):
            texto = f'{entrada.titulo} {entrada.contenido_vigente} {entrada.etiquetas}'.lower()
            for prohibida in ('entrega', 'flete', 'financiamiento', 'financiar', 'apartad', 'descuento'):
                self.assertNotIn(prohibida, texto, f'«{entrada.titulo}» menciona {prohibida}')

    def test_la_garantia_provisional_no_inventa_plazos(self):
        contenido = self.semilla('conocimiento_garantia').contenido
        self.assertNotRegex(contenido, r'\d+\s*(d[ií]as|meses|a[ñn]os)')
        self.assertIn('confirma una vendedora', contenido)

    def test_dondeestamos_se_arma_con_los_datos_vivos(self):
        texto = self.semilla('conocimiento_tienda').contenido_vigente
        self.assertIn('Frente al Parque Libertadores', texto)
        self.assertIn('La Chorrera', texto)
        self.assertIn('+507 6026-1919', texto)
        self.assertIn('todos los días, de 8:00 a. m. a 5:00 p. m.', texto)
        self.ajustes.write({'horario_inicio': 9.0, 'horario_fin': 18.0})
        self.semilla('conocimiento_tienda').invalidate_recordset()
        self.assertIn('9:00 a. m. a 6:00 p. m.', self.semilla('conocimiento_tienda').contenido_vigente)

    def test_socios_sale_de_puntos_json_y_nunca_se_guarda(self):
        entrada = self.semilla('conocimiento_socios')
        self.assertFalse(entrada.contenido, 'No hay texto guardado que se pueda quedar viejo')
        self.assertEqual(entrada.contenido_vigente, '\n'.join(redactar(R.cargar_reglas())['resumen']))
        cambiadas = R.cargar_reglas()
        cambiadas['referido']['puntosAlPadrino'] = 777
        with patch.object(R, 'cargar_reglas', return_value=cambiadas):
            entrada.invalidate_recordset()
            self.assertIn('777 puntos', entrada.contenido_vigente)

    def test_buscar_devuelve_las_3_mejores_y_solo_activas(self):
        for i in range(5):
            self.entrada(titulo=f'Zzmueble {i}', contenido='Zzmueble y su cuidado', etiquetas='zzmueble')
        self.entrada(titulo='Zzmueble inactivo', contenido='zzmueble', etiquetas='zzmueble', activo=False)
        resultados = self.env['dcasa.conocimiento']._buscar('zzmueble', 3)
        self.assertEqual(len(resultados), 3)
        self.assertTrue(all(e.activo for e, _ in resultados))
        self.assertNotIn('Zzmueble inactivo', [e.titulo for e, _ in resultados])

    def test_buscar_encuentra_lo_que_pregunta_la_gente(self):
        Conocimiento = self.env['dcasa.conocimiento']
        mejor = lambda texto: (Conocimiento._buscar(texto, 3) or [(None, 0)])[0][0]   # noqa: E731
        self.assertEqual(mejor('¿Cuál es el horario de atención?'), self.semilla('conocimiento_tienda'))
        self.assertEqual(mejor('¿Dónde están?'), self.semilla('conocimiento_tienda'))
        self.assertEqual(mejor('cómo gano puntos'), self.semilla('conocimiento_socios'))
        self.assertEqual(mejor('premios del programa de socios'), self.semilla('conocimiento_socios'))

    def test_lo_inactivo_no_se_encuentra_hasta_que_la_duena_lo_activa(self):
        Conocimiento = self.env['dcasa.conocimiento']
        self.assertFalse(Conocimiento._buscar('garantía de los colchones', 3))
        self.semilla('conocimiento_garantia').with_user(self.gerente).action_activar()
        (mejor, _), *_ = Conocimiento._buscar('garantía de los colchones', 3)
        self.assertEqual(mejor, self.semilla('conocimiento_garantia'))

    def test_sin_coincidencias(self):
        self.assertEqual(self.env['dcasa.conocimiento']._buscar('helicóptero', 3), [])
        self.assertEqual(self.env['dcasa.conocimiento']._buscar('¿?', 3), [])

    def test_gerencia_edita_las_demas_solo_leen(self):
        entrada = self.entrada(titulo='De Gerencia')
        entrada.with_user(self.gerente).write({'contenido': 'Nuevo texto'})
        self.assertEqual(entrada.contenido, 'Nuevo texto')
        self.assertEqual(entrada.with_user(self.vendedora).titulo, 'De Gerencia')
        with self.assertRaises(AccessError):
            entrada.with_user(self.vendedora).write({'contenido': 'x'})
        with self.assertRaises(AccessError):
            self.env['dcasa.conocimiento'].with_user(self.vendedora).create({'titulo': 'x', 'contenido': 'y'})
        with self.assertRaises(AccessError):
            entrada.with_user(self.vendedora).action_activar()
        Conocimiento = self.env['dcasa.conocimiento'].with_user(self.gerente)
        self.assertTrue(Conocimiento.create({'titulo': 'x', 'contenido': 'y'}))

    def test_el_personal_sin_ventas_no_lo_ve(self):
        with self.assertRaises(AccessError):
            self.env['dcasa.conocimiento'].with_user(self.interno).search([])

    def test_editar_actualiza_la_ultima_revision(self):
        entrada = self.entrada(ultima_revision=fields.Date.today() - timedelta(days=90))
        entrada.contenido = 'Cambió'
        self.assertEqual(entrada.ultima_revision, fields.Date.context_today(entrada))

    def test_una_entrada_manual_necesita_contenido(self):
        with self.assertRaises(ValidationError):
            self.env['dcasa.conocimiento'].create({'titulo': 'Vacía', 'contenido': '  '})
        with self.assertRaises(ValidationError):
            self.entrada(contenido='x' * 5001)

    def test_los_cambios_quedan_en_el_historial(self):
        entrada = self.entrada()
        self.env.cr.precommit.run()   # lo creado en esta misma transacción no deja historial de cambios
        entrada.titulo = 'Otro título'
        self.env.cr.precommit.run()
        self.assertIn('Título', ' '.join(entrada.message_ids.tracking_value_ids.field_id.mapped('field_description')))


@tagged('post_install', '-at_install')
class TestPreguntasSinRespuesta(JuanCase):

    def setUp(self):
        super().setUp()
        self.Pregunta = self.env['dcasa.pregunta_pendiente']
        self.conv_a = self.conversacion(id_externo='50761230001')
        self.conv_b = self.conversacion(id_externo='50761230002')

    def preguntar(self, pregunta, conv=None, resumen=None):
        return self.Pregunta._registrar(pregunta, resumen, conv or self.conv_a)

    def test_registra_una_pregunta_nueva(self):
        pregunta, nueva = self.preguntar('¿Instalan los muebles?', resumen='Hablaban de una cama king')
        self.assertTrue(nueva)
        self.assertEqual((pregunta.estado, pregunta.veces), ('nueva', 1))
        self.assertEqual(pregunta.texto, '¿Instalan los muebles?')
        self.assertEqual(pregunta.resumen, 'Hablaban de una cama king')
        self.assertEqual(pregunta.conversacion_id, self.conv_a)

    def test_la_misma_pregunta_de_otra_persona_suma(self):
        primera, _ = self.preguntar('¿Instalan los muebles?')
        segunda, nueva = self.preguntar('instalan los muebles', conv=self.conv_b)
        self.assertFalse(nueva)
        self.assertEqual(primera, segunda)
        self.assertEqual(primera.veces, 2)
        self.assertEqual(primera.conversacion_ids, self.conv_a | self.conv_b)

    def test_preguntas_muy_parecidas_se_agrupan(self):
        primera, _ = self.preguntar('¿Tienen garantía en los colchones?')
        parecida, nueva = self.preguntar('Quiero saber la garantia de colchones', conv=self.conv_b)
        self.assertFalse(nueva)
        self.assertEqual(parecida, primera)

    def test_preguntas_distintas_no_se_mezclan(self):
        primera, _ = self.preguntar('¿Instalan los muebles?')
        otra, nueva = self.preguntar('¿Aceptan Yappy?', conv=self.conv_b)
        self.assertTrue(nueva)
        self.assertNotEqual(primera, otra)
        self.assertEqual(self.Pregunta.search_count([('estado', '=', 'nueva')]), 2)

    def test_el_mismo_cliente_repitiendo_no_suma(self):
        pregunta, _ = self.preguntar('¿Instalan los muebles?')
        self.preguntar('¿Instalan los muebles?')       # el modelo reintentó
        self.assertEqual(pregunta.veces, 1)
        pregunta.ultima_vez = fields.Datetime.now() - timedelta(hours=2)
        self.preguntar('¿Instalan los muebles?')       # pasó más de una hora: otra vez
        self.assertEqual(pregunta.veces, 2)

    def test_una_atendida_ya_no_agrupa(self):
        pregunta, _ = self.preguntar('¿Instalan los muebles?')
        pregunta.estado = 'atendida'
        otra, nueva = self.preguntar('¿Instalan los muebles?', conv=self.conv_b)
        self.assertTrue(nueva)
        self.assertNotEqual(otra, pregunta)

    def test_texto_largo_se_recorta(self):
        pregunta, _ = self.preguntar('¿Instalan? ' + 'x' * 900)
        self.assertEqual(len(pregunta.texto), 500)

    def test_el_boton_abre_el_formulario_con_la_pregunta(self):
        pregunta, _ = self.preguntar('¿Instalan los muebles?')
        pregunta.veces = 3
        accion = pregunta.with_user(self.gerente).action_convertir_en_conocimiento()
        self.assertEqual((accion['res_model'], accion['view_mode']), ('dcasa.conocimiento', 'form'))
        self.assertEqual(accion['context']['default_titulo'], '¿Instalan los muebles?')
        self.assertEqual(accion['context']['default_pregunta_id'], pregunta.id)
        self.assertIn('3 veces', accion['context']['default_nota'])
        self.assertEqual(pregunta.estado, 'nueva', 'No cambia nada hasta que ella guarda la respuesta')

    def test_el_ciclo_completo_la_duena_responde_y_el_bot_aprende(self):
        pregunta, _ = self.preguntar('¿Instalan los muebles?')
        self.assertFalse(self.env['dcasa.conocimiento']._buscar('instalan los muebles', 3))
        contexto = pregunta.with_user(self.gerente).action_convertir_en_conocimiento()['context']
        entrada = self.env['dcasa.conocimiento'].with_user(self.gerente).with_context(**contexto).create({
            'titulo': '¿Instalan los muebles?', 'contenido': 'Eso lo confirma una vendedora según el mueble.',
            'etiquetas': 'instalación, armado'})
        self.assertEqual(entrada.pregunta_id, pregunta)
        self.assertEqual((pregunta.estado, pregunta.conocimiento_id), ('atendida', entrada))
        (hallada, _), *_ = self.env['dcasa.conocimiento']._buscar('¿hacen la instalación de los muebles?', 3)
        self.assertEqual(hallada, entrada)

    def test_descartar_y_reabrir(self):
        pregunta, _ = self.preguntar('¿Instalan los muebles?')
        pregunta.with_user(self.gerente).action_descartar()
        self.assertEqual(pregunta.estado, 'descartada')
        pregunta.with_user(self.gerente).action_reabrir()
        self.assertEqual(pregunta.estado, 'nueva')

    def test_solo_gerencia_atiende_las_preguntas(self):
        pregunta, _ = self.preguntar('¿Instalan los muebles?')
        self.assertEqual(pregunta.with_user(self.vendedora).veces, 1)    # leer, sí
        for metodo in ('action_descartar', 'action_reabrir', 'action_convertir_en_conocimiento'):
            with self.assertRaises(AccessError):
                getattr(pregunta.with_user(self.vendedora), metodo)()
        with self.assertRaises(AccessError):
            pregunta.with_user(self.vendedora).write({'estado': 'descartada'})
        with self.assertRaises(AccessError):
            self.Pregunta.with_user(self.interno).search([])

    def test_el_menu_es_de_gerencia(self):
        menu = self.env.ref('dcasa_conversaciones.menu_dcasa_preguntas_pendientes')
        self.assertEqual(menu.name, 'Preguntas sin respuesta')
        self.assertIn(menu.id, self.env['ir.ui.menu'].with_user(self.gerente)._visible_menu_ids())
        self.assertNotIn(menu.id, self.env['ir.ui.menu'].with_user(self.vendedora)._visible_menu_ids())
        conocimiento = self.env.ref('dcasa_conversaciones.menu_dcasa_conocimiento')
        self.assertEqual(conocimiento.name, 'Conocimiento del bot')
        self.assertIn(conocimiento.id, self.env['ir.ui.menu'].with_user(self.gerente)._visible_menu_ids())

    def test_las_vistas_cargan(self):
        for modelo in ('dcasa.conocimiento', 'dcasa.pregunta_pendiente'):
            for tipo in ('list', 'form', 'search'):
                with self.subTest(modelo=modelo, tipo=tipo):
                    self.assertTrue(self.env[modelo].with_user(self.gerente).get_view(view_type=tipo)['arch'])


@tagged('post_install', '-at_install')
class TestLeccionesAprendidas(JuanCase):

    def test_van_en_config_como_lista(self):
        self.ajustes.lecciones_aprendidas = (
            'Cuando pregunten por Yappy, di que una vendedora lo confirma\n\n  Siempre saluda por el nombre  \n')
        self.assertEqual(self.ajustes.como_json()['lecciones'], [
            'Cuando pregunten por Yappy, di que una vendedora lo confirma', 'Siempre saluda por el nombre'])

    def test_vacias_por_defecto(self):
        self.assertEqual(self.ajustes.como_json()['lecciones'], [])

    def test_maximo_20_lineas(self):
        self.ajustes.lecciones_aprendidas = '\n'.join(f'Lección {i}' for i in range(20))
        self.assertEqual(len(self.ajustes.como_json()['lecciones']), 20)
        with self.assertRaises(ValidationError):
            self.ajustes.lecciones_aprendidas = '\n'.join(f'Lección {i}' for i in range(21))

    def test_las_lineas_en_blanco_no_cuentan_para_el_maximo(self):
        self.ajustes.lecciones_aprendidas = '\n\n'.join(f'Lección {i}' for i in range(20))

    def test_cada_leccion_es_corta(self):
        with self.assertRaises(ValidationError):
            self.ajustes.lecciones_aprendidas = 'x' * 301

    def test_solo_gerencia_las_edita(self):
        self.ajustes.with_user(self.gerente).lecciones_aprendidas = 'Una lección'
        with self.assertRaises(AccessError):
            self.ajustes.with_user(self.vendedora).lecciones_aprendidas = 'Otra'


@tagged('post_install', '-at_install')
class TestProveedorDeIA(JuanCase):
    """La dueña elige el proveedor de IA desde Odoo; las claves viven solo en el Worker."""

    def test_valores_por_defecto(self):
        a = self.ajustes
        self.assertEqual((a.proveedor_ia, a.proveedor_respaldo_ia), ('anthropic', False))
        self.assertEqual((a.modelo_rapido, a.modelo_inteligente), ('claude-haiku-4-5', 'claude-sonnet-5-5'))
        self.assertEqual(a.presupuesto_ia_mensual_usd, 30)

    def test_config_trae_los_nombres_exactos(self):
        datos = self.ajustes.como_json()
        self.assertEqual(datos['proveedor_ia'], 'anthropic')
        self.assertIsNone(datos['proveedor_respaldo_ia'])
        self.assertEqual((datos['modelo_rapido'], datos['modelo_inteligente']),
                         ('claude-haiku-4-5', 'claude-sonnet-5-5'))
        self.assertEqual(set(datos['precios']), {'rapido', 'inteligente'})
        for nivel in datos['precios'].values():
            self.assertEqual(set(nivel), {'entrada', 'salida', 'cache'})
        self.assertEqual(datos['presupuesto_ia_mensual_usd'], 30)

    def test_los_precios_vacios_son_nulos_nunca_cifras_inventadas(self):
        self.assertEqual(self.ajustes.como_json()['precios'], {
            'rapido': {'entrada': None, 'salida': None, 'cache': None},
            'inteligente': {'entrada': None, 'salida': None, 'cache': None}})

    def test_los_precios_se_guardan_por_nivel(self):
        self.ajustes.write({
            'precio_rapido_entrada_usd_mtok': 1.0, 'precio_rapido_salida_usd_mtok': 5.0,
            'precio_inteligente_entrada_usd_mtok': 3.0, 'precio_inteligente_cache_usd_mtok': 0.3})
        self.assertEqual(self.ajustes.como_json()['precios'], {
            'rapido': {'entrada': 1.0, 'salida': 5.0, 'cache': None},
            'inteligente': {'entrada': 3.0, 'salida': None, 'cache': 0.3}})
        with self.assertRaises(ValidationError):
            self.ajustes.precio_rapido_salida_usd_mtok = -1

    def test_meta_con_su_modelo(self):
        self.ajustes.write({'proveedor_ia': 'meta', 'modelo_rapido': 'muse-spark-1.3',
                            'modelo_inteligente': 'muse-spark-1.3', 'proveedor_respaldo_ia': 'anthropic'})
        datos = self.ajustes.como_json()
        self.assertEqual((datos['proveedor_ia'], datos['proveedor_respaldo_ia']), ('meta', 'anthropic'))
        self.assertEqual((datos['modelo_rapido'], datos['modelo_inteligente']), ('muse-spark-1.3', 'muse-spark-1.3'))

    def test_al_cambiar_de_proveedor_los_modelos_pasan_a_los_suyos(self):
        with self.env.cr.savepoint():
            formulario = self.env['dcasa.juan.ajustes'].new({'proveedor_ia': 'anthropic'})
            formulario.proveedor_ia = 'meta'
            formulario._onchange_proveedor_ia()
            self.assertEqual((formulario.modelo_rapido, formulario.modelo_inteligente),
                             ('muse-spark-1.3', 'muse-spark-1.3'))
            formulario.proveedor_ia = 'anthropic'
            formulario._onchange_proveedor_ia()
            self.assertEqual((formulario.modelo_rapido, formulario.modelo_inteligente),
                             ('claude-haiku-4-5', 'claude-sonnet-5-5'))
            # Un modelo escrito a mano no se pisa.
            formulario.modelo_rapido = 'mi-modelo-propio'
            formulario.proveedor_ia = 'meta'
            formulario._onchange_proveedor_ia()
            self.assertEqual(formulario.modelo_rapido, 'mi-modelo-propio')

    def test_los_modelos_por_defecto_de_cada_proveedor_viajan_en_config(self):
        por_defecto = self.ajustes.como_json()['modelos_por_defecto']
        self.assertEqual(por_defecto['anthropic'], {'rapido': 'claude-haiku-4-5', 'inteligente': 'claude-sonnet-5-5'})
        self.assertEqual(por_defecto['meta'], {'rapido': 'muse-spark-1.3', 'inteligente': 'muse-spark-1.3'})
        self.assertEqual(por_defecto['openai'], {'rapido': '', 'inteligente': ''}, 'OpenAI: no se inventa un modelo')

    def test_el_respaldo_no_puede_ser_el_mismo(self):
        with self.assertRaises(ValidationError):
            self.ajustes.proveedor_respaldo_ia = 'anthropic'

    def test_hay_que_escribir_los_modelos(self):
        for valores in ({'modelo_rapido': ''}, {'modelo_inteligente': '   '}, {'modelo_rapido': 'dos palabras'}):
            with self.subTest(valores=valores), self.assertRaises(ValidationError):
                self.ajustes.write(valores)

    def test_aviso_de_los_modelos_contributor(self):
        self.assertFalse(self.ajustes.aviso_contributor)
        self.ajustes.modelo_rapido = 'muse-spark-1.3-contributor'
        self.assertTrue(self.ajustes.aviso_contributor)
        arch = self.env['dcasa.juan.ajustes'].get_view(view_type='form')['arch']
        self.assertIn('contributor', arch)
        self.assertIn('la política de privacidad del sitio debe decirlo', arch)

    def test_en_odoo_no_hay_claves_de_api(self):
        campos = self.env['dcasa.juan.ajustes']._fields
        for nombre, campo in campos.items():
            if campo.type in ('char', 'text') and nombre not in (
                    'nombre_publico', 'modelo_rapido', 'modelo_inteligente'):
                self.assertNotRegex(nombre, r'(?i)(api|clave|key|secret|token)', nombre)
        self.assertFalse([n for n in campos if re.search(r'(?i)(api_?key|clave_api|secret)', n)])
        self.assertNotIn('sk-', json.dumps(self.ajustes.como_json()))

    def test_solo_gerencia_cambia_el_proveedor(self):
        self.ajustes.with_user(self.gerente).proveedor_ia = 'meta'
        with self.assertRaises(AccessError):
            self.ajustes.with_user(self.vendedora).proveedor_ia = 'openai'

