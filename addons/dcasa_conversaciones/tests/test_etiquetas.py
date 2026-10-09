"""Etiquetas, respuestas rápidas y la herramienta ``etiquetar_conversacion`` del asistente."""
from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import JuanCase


@tagged('post_install', '-at_install')
class TestEtiquetas(JuanCase):

    def setUp(self):
        super().setUp()
        self.Etiqueta = self.env['dcasa.conversacion.etiqueta']

    def test_la_semilla_trae_etiquetas_de_clasificacion_interna(self):
        nombres = set(self.Etiqueta.search([('activa', '=', True)]).mapped('name'))
        self.assertTrue({'Pidió precio', 'Comprobante recibido'} <= nombres)

    def test_no_se_repite_ni_con_otras_mayusculas_ni_sin_acentos(self):
        self.Etiqueta.create({'name': 'Zzapartado'})
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.env.cr.savepoint():
            self.Etiqueta.create({'name': 'Zzapartado'})
        for repetida in ('zzAPARTADO', '  zzapartado '):
            with self.subTest(repetida=repetida), self.assertRaises(ValidationError):
                self.Etiqueta.create({'name': repetida})
        self.Etiqueta.create({'name': 'Zzentrega'})
        with self.assertRaises(ValidationError):
            self.Etiqueta.create({'name': 'ZZÉntrega'})

    def test_el_nombre_va_de_1_a_40_letras_y_se_limpia(self):
        with self.assertRaises(ValidationError):
            self.Etiqueta.create({'name': 'x' * 41})
        with self.assertRaises(ValidationError):
            self.Etiqueta.create({'name': '   '})
        self.assertEqual(self.Etiqueta.create({'name': '  Zzcon   espacios '}).name, 'Zzcon espacios')

    def test_el_color_va_de_0_a_11(self):
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.env.cr.savepoint():
            self.Etiqueta.create({'name': 'Zzcolor', 'color': 12})

    def test_solo_gerencia_crea_etiquetas(self):
        self.Etiqueta.with_user(self.gerente).create({'name': 'Zzgerente'})
        for usuario in (self.vendedora, self.interno):
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                self.Etiqueta.with_user(usuario).create({'name': 'Zzotra'})

    def test_la_lista_de_la_pantalla_solo_trae_las_activas_y_pide_ser_de_ventas(self):
        inactiva = self.Etiqueta.create({'name': 'Zzvieja', 'activa': False})
        lista = self.Etiqueta.with_user(self.vendedora).lista()
        self.assertNotIn(inactiva.id, [e['id'] for e in lista])
        self.assertEqual(set(lista[0]), {'id', 'nombre', 'color'})
        for usuario in (self.interno, self.portal):
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                self.Etiqueta.with_user(usuario).lista()

    def test_buscar_por_nombre_ignora_mayusculas_y_acentos_y_las_inactivas(self):
        etiqueta = self.Etiqueta.create({'name': 'Zzpidió Cotización'})
        self.assertEqual(self.Etiqueta._buscar_por_nombre('ZZPIDIO cotizacion'), etiqueta)
        etiqueta.activa = False
        self.assertFalse(self.Etiqueta._buscar_por_nombre('Zzpidió Cotización'))
        self.assertFalse(self.Etiqueta._buscar_por_nombre('   '))

    def test_poner_etiquetas_desde_la_pantalla(self):
        conv = self.conversacion(nombre='Karen')
        a, b = self.Etiqueta.create([{'name': 'Zza'}, {'name': 'Zzb'}])
        panel = self.Conversacion.with_user(self.vendedora)
        resumen = panel.poner_etiquetas(conv.id, [a.id, b.id])
        self.assertEqual({e['nombre'] for e in resumen['etiquetas']}, {'Zza', 'Zzb'})
        panel.poner_etiquetas(conv.id, [b.id])
        self.assertEqual(conv.etiqueta_ids, b)

    def test_poner_etiquetas_no_acepta_inactivas_ni_inexistentes_ni_basura(self):
        conv = self.conversacion(nombre='Karen')
        inactiva = self.Etiqueta.create({'name': 'Zzmuerta', 'activa': False})
        panel = self.Conversacion.with_user(self.vendedora)
        for malas in ([inactiva.id], [999999999], 'texto', [True], ['1'], list(range(1, 20))):
            with self.subTest(malas=malas), self.assertRaises(UserError):
                panel.poner_etiquetas(conv.id, malas)
        self.assertFalse(conv.etiqueta_ids)

    def test_una_etiqueta_inactiva_que_ya_tenia_se_conserva(self):
        conv = self.conversacion(nombre='Karen')
        vieja = self.Etiqueta.create({'name': 'Zzvieja'})
        nueva = self.Etiqueta.create({'name': 'Zznueva'})
        conv.etiqueta_ids = vieja
        vieja.activa = False
        self.Conversacion.with_user(self.vendedora).poner_etiquetas(conv.id, [nueva.id])
        self.assertEqual(conv.etiqueta_ids, vieja | nueva)

    def test_el_conteo_de_conversaciones_por_etiqueta(self):
        etiqueta = self.Etiqueta.create({'name': 'Zzconteo'})
        self.conversacion(nombre='A', id_externo='50761230001').etiqueta_ids = etiqueta
        self.conversacion(nombre='B', id_externo='50761230002').etiqueta_ids = etiqueta
        self.assertEqual(etiqueta.conversacion_count, 2)


@tagged('post_install', '-at_install')
class TestHerramientaEtiquetar(JuanCase):

    def setUp(self):
        super().setUp()
        self.conv = self.conversacion(nombre='Karen')
        self.etiqueta = self.env['dcasa.conversacion.etiqueta'].create({'name': 'Zzpidió precio'})

    def etiquetar(self, etiqueta, conv=None):
        herramientas = self.env['brian.herramientas'].with_user(self.juan).with_context(
            juan_conversacion_id=(conv or self.conv).id)
        return herramientas.ejecutar('juan_etiquetar_conversacion', {'etiqueta': etiqueta}, canal='juan')

    def test_pone_la_etiqueta_que_existe_sin_importar_mayusculas_ni_acentos(self):
        resultado = self.etiquetar('ZZPIDIO PRECIO')
        self.assertEqual(self.conv.etiqueta_ids, self.etiqueta)
        self.assertTrue(resultado['ok'])
        self.assertEqual(resultado['datos'], {'etiquetada': True, 'etiqueta': 'Zzpidió precio', 'ya_la_tenia': False})

    def test_repetirla_no_duplica(self):
        self.etiquetar('Zzpidió precio')
        resultado = self.etiquetar('Zzpidió precio')
        self.assertTrue(resultado['datos']['ya_la_tenia'])
        self.assertEqual(len(self.conv.etiqueta_ids), 1)

    def test_no_inventa_etiquetas_y_dice_cuales_existen(self):
        resultado = self.etiquetar('Cliente VIP')
        self.assertFalse(resultado['ok'])
        self.assertIn('No existe la etiqueta «Cliente VIP»', resultado['error'])
        self.assertIn('Zzpidió precio', resultado['error'])
        self.assertFalse(self.conv.etiqueta_ids)
        self.assertFalse(self.env['dcasa.conversacion.etiqueta'].search([('name', '=', 'Cliente VIP')]))

    def test_una_etiqueta_inactiva_no_se_puede_poner(self):
        self.etiqueta.activa = False
        self.assertFalse(self.etiquetar('Zzpidió precio')['ok'])
        self.assertFalse(self.conv.etiqueta_ids)

    def test_la_conversacion_sale_del_contexto_no_de_un_argumento(self):
        otra = self.conversacion(nombre='Otra', id_externo='50761239999')
        self.etiquetar('Zzpidió precio', conv=otra)
        self.assertFalse(self.conv.etiqueta_ids)
        self.assertEqual(otra.etiqueta_ids, self.etiqueta)

    def test_queda_en_la_auditoria(self):
        self.etiquetar('Zzpidió precio')
        accion = self.env['brian.accion'].search([('herramienta', '=', 'juan_etiquetar_conversacion')], limit=1)
        self.assertEqual((accion.canal, accion.estado, accion.dcasa_conversacion_id), ('juan', 'hecha', self.conv))


@tagged('post_install', '-at_install')
class TestRespuestasRapidas(JuanCase):

    def setUp(self):
        super().setUp()
        self.Rapida = self.env['dcasa.respuesta.rapida']
        self.conv = self.conversacion(nombre='Karen Pérez')

    def texto(self, atajo, conv=None, usuario=None):
        return self.Rapida.with_user(usuario or self.vendedora).texto_para((conv or self.conv).id, atajo)['texto']

    def test_la_semilla_trae_ubicacion_horario_y_socios(self):
        atajos = set(self.Rapida.search([]).mapped('atajo'))
        self.assertTrue({'/ubicacion', '/horario', '/socios'} <= atajos)

    def test_el_atajo_se_limpia_y_se_valida(self):
        self.assertEqual(self.Rapida.create({'atajo': ' Zzhola ', 'texto': 'Hola'}).atajo, '/zzhola')
        self.assertEqual(self.Rapida.create({'atajo': '/zz uno', 'texto': 'Hola'}).atajo, '/zz-uno')
        for malo in ('/', '/zz!', '//zz', '/' + 'a' * 31, '/ñandú'):
            with self.subTest(atajo=malo), self.assertRaises(ValidationError):
                self.Rapida.create({'atajo': malo, 'texto': 'Hola'})

    def test_el_atajo_es_unico(self):
        self.Rapida.create({'atajo': '/zzunico', 'texto': 'Uno'})
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.env.cr.savepoint():
            self.Rapida.create({'atajo': '/ZZUNICO', 'texto': 'Dos'})

    def test_el_texto_no_puede_estar_vacio_ni_pasarse(self):
        for texto in ('   ', 'x' * 1001):
            with self.subTest(largo=len(texto)), self.assertRaises(ValidationError):
                self.Rapida.create({'atajo': '/zzmalo', 'texto': texto})

    def test_solo_se_aceptan_los_datos_conocidos(self):
        with self.assertRaises(ValidationError) as error:
            self.Rapida.create({'atajo': '/zzdatos', 'texto': 'Hola {Nombre}, tu {saldo}'})
        self.assertIn('{Nombre}', str(error.exception))
        self.assertIn('{saldo}', str(error.exception))

    def test_se_llena_con_el_nombre_del_cliente(self):
        self.Rapida.create({'atajo': '/zzsaludo', 'texto': 'Hola {nombre}, ¿en qué te ayudo?'})
        self.assertEqual(self.texto('/zzsaludo'), 'Hola Karen, ¿en qué te ayudo?')
        self.assertEqual(self.texto('zzsaludo'), 'Hola Karen, ¿en qué te ayudo?', 'El «/» es opcional al pedirlo')

    def test_sin_nombre_real_no_queda_un_hola_con_coma_sola(self):
        self.Rapida.create({'atajo': '/zzsaludo', 'texto': 'Hola {nombre}, ¿en qué te ayudo?'})
        self.Rapida.create({'atajo': '/zzinicio', 'texto': '{nombre}, estamos para ayudarte.'})
        anonima = self.conversacion(id_externo='50761230777')   # su ficha se llama «WhatsApp 6123-0777»
        self.assertEqual(self.texto('/zzsaludo', conv=anonima), 'Hola, ¿en qué te ayudo?')
        self.assertEqual(self.texto('/zzinicio', conv=anonima), 'estamos para ayudarte.')

    def test_horario_y_direccion_salen_de_donde_ya_viven(self):
        self.Rapida.create({'atajo': '/zzdatos', 'texto': 'Atendemos {horario}. Estamos en {direccion}.'})
        texto = self.texto('/zzdatos')
        horario = self.ajustes.horario()
        self.assertIn('todos los días, de 8:00 a. m. a 5:00 p. m. (hora de Panamá)', texto)
        self.assertEqual(len(horario.dias), 7)
        self.env.company.sudo().street = 'Calle Zzprueba'
        self.assertIn('Calle Zzprueba', self.texto('/zzdatos'))

    def test_cambia_el_horario_y_la_respuesta_cambia_sola(self):
        self.Rapida.create({'atajo': '/zzhorario', 'texto': 'Atendemos {horario}.'})
        self.ajustes.horario_fin = 18.0
        self.assertIn('de 8:00 a. m. a 6:00 p. m.', self.texto('/zzhorario'))

    def test_lo_que_no_es_un_dato_conocido_se_deja_tal_cual(self):
        # Una llave que se coló antes de validar (p. ej. por SQL) no se rompe ni se inventa.
        respuesta = self.Rapida.create({'atajo': '/zzraro', 'texto': 'Hola'})
        self.env.cr.execute('UPDATE dcasa_respuesta_rapida SET texto = %s WHERE id = %s',
                            ['Pago {saldo}', respuesta.id])
        respuesta.invalidate_recordset()
        self.assertEqual(self.texto('/zzraro'), 'Pago {saldo}')

    def test_una_respuesta_inactiva_o_inexistente_no_se_puede_usar(self):
        respuesta = self.Rapida.create({'atajo': '/zzapagada', 'texto': 'Hola', 'activa': False})
        for atajo in ('/zzapagada', '/noexiste'):
            with self.subTest(atajo=atajo), self.assertRaises(UserError):
                self.texto(atajo)
        self.assertNotIn(respuesta.id, [r['id'] for r in self.Rapida.with_user(self.vendedora).lista()])

    def test_permisos(self):
        self.Rapida.with_user(self.gerente).create({'atajo': '/zzgerente', 'texto': 'Hola'})
        with self.assertRaises(AccessError):
            self.Rapida.with_user(self.vendedora).create({'atajo': '/zzvendedora', 'texto': 'Hola'})
        for usuario in (self.interno, self.portal):
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                self.Rapida.with_user(usuario).lista()
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                self.texto('/ubicacion', usuario=usuario)

    def test_la_lista_trae_el_texto_sin_armar(self):
        lista = {r['atajo']: r for r in self.Rapida.with_user(self.vendedora).lista()}
        self.assertIn('{nombre}', lista['/horario']['texto'])
        self.assertEqual(set(lista['/horario']), {'id', 'atajo', 'texto', 'descripcion'})

    def test_la_semilla_no_inventa_cifras_ni_politicas(self):
        for atajo in ('/ubicacion', '/horario', '/socios'):
            texto = self.Rapida.search([('atajo', '=', atajo)]).texto
            with self.subTest(atajo=atajo):
                self.assertNotRegex(texto, r'\d', 'Ninguna cifra escrita a mano')
                for prohibida in ('remate', 'garantía', 'envío', 'entrega', 'financ', 'apart'):
                    self.assertNotIn(prohibida, texto.lower())
