"""Ronda 8 (auditoría del 2026-10-10): topes de tamaño, texto de clientes y adjuntos que siguen contando."""
import time
from datetime import timedelta

from odoo import fields
from odoo.addons.dcasa_brian.models import herramientas_comun as c
from odoo.addons.dcasa_brian.models import proveedores
from odoo.addons.dcasa_brian.models.registro import MAX_ARGUMENTOS, MAX_TEXTO_ARGUMENTO, BrianError
from odoo.tests import tagged

from .common import BrianCase


@tagged('post_install', '-at_install')
class TestRonda8(BrianCase):

    def conversacion(self):
        Conversacion = self.env['brian.conversacion'].with_user(self.usuario)
        return Conversacion.browse(Conversacion.nueva('chat')['id'])

    def mensaje_de_la_persona(self, conv, texto, con_adjunto=False):
        valores = {'conversacion_id': conv.id, 'rol': 'user', 'contenido': texto}
        if con_adjunto:
            archivo = self.env['ir.attachment'].create({
                'name': 'factura.txt', 'raw': b'datos', 'mimetype': 'text/plain',
                'res_model': 'brian.conversacion', 'res_id': conv.id})
            valores['adjunto_ids'] = [(6, 0, [archivo.id])]
        return self.env['brian.mensaje'].create(valores)

    # -- Tamaño de lo que manda el modelo ---------------------------------------------------------------------------

    def test_un_dato_gigante_se_rechaza_antes_de_registrar_nada(self):
        antes = self.env['brian.accion'].search_count([])
        respuesta = self.herramientas().ejecutar('prueba_leer', {'texto': 'x' * (MAX_TEXTO_ARGUMENTO + 1)})
        self.assertFalse(respuesta['ok'])
        self.assertIn('demasiado largo', respuesta['error'])
        self.assertEqual(self.env['brian.accion'].search_count([]), antes, 'ni siquiera queda en la auditoría')
        self.assertTrue(self.herramientas().ejecutar('prueba_leer', {'texto': 'x' * MAX_TEXTO_ARGUMENTO})['ok'])

    def test_muchos_datos_chicos_que_suman_demasiado_tambien(self):
        campos = ['a' * 100] * (MAX_ARGUMENTOS // 100 + 50)
        respuesta = self.herramientas().ejecutar('eliminar_prueba', {'modelo': 'x', 'campos': campos})
        self.assertFalse(respuesta['ok'])
        self.assertIn('demasiado largos', respuesta['error'])

    def test_las_lineas_de_una_cotizacion_no_se_vuelven_lentas_con_basura(self):
        basura = 'a' + ' ' * 8000 + '!'
        inicio = time.monotonic()
        with self.assertRaises(BrianError):
            c.leer_lineas(basura)
        with self.assertRaises(BrianError):
            c.leer_lineas('SOF-001 x 1; ' + basura)
        self.assertLess(time.monotonic() - inicio, 0.5)
        self.assertEqual(c.leer_lineas('SOF-001 x 2 @ 150'), [('SOF-001', 2.0, 150.0)], 'lo normal sigue igual')

    # -- Texto escrito por clientes ---------------------------------------------------------------------------------

    def test_despues_de_leer_texto_de_clientes_lo_de_construccion_pide_visto_bueno(self):
        estado = {'texto_externo': False}
        herramientas = self.herramientas().with_context(brian_turno_estado=estado)
        self.assertTrue(herramientas.ejecutar('prueba_crear_contacto', {'nombre': 'Antes'})['ok'],
                        'sin haber leído nada ajeno, corre directo')
        self.assertTrue(herramientas.ejecutar('prueba_texto_externo')['ok'])
        self.assertTrue(estado['texto_externo'])
        respuesta = herramientas.ejecutar('prueba_crear_contacto', {'nombre': 'Despues'})
        self.assertTrue(respuesta.get('requiere_confirmacion'), respuesta)
        self.assertIn('clientes', respuesta['resumen'])
        self.assertNotIn('adjunto', respuesta['resumen'])
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'Despues')]))
        self.assertTrue(herramientas.ejecutar('prueba_leer', {'texto': 'x'})['ok'], 'leer sigue directo')
        # Y otro turno (otro estado) vuelve a empezar limpio.
        limpio = self.herramientas().with_context(brian_turno_estado={'texto_externo': False})
        self.assertTrue(limpio.ejecutar('prueba_crear_contacto', {'nombre': 'Otro turno'})['ok'])

    def test_la_herramienta_del_crm_esta_marcada_como_texto_externo(self):
        especificaciones = self.env['brian.herramientas']._todas()
        if 'oportunidades_abiertas' in especificaciones:   # vive en dcasa_conversaciones
            self.assertTrue(especificaciones['oportunidades_abiertas']['texto_externo'])
        self.assertFalse(especificaciones['prueba_leer']['texto_externo'])

    # -- Adjuntos que siguen contando -------------------------------------------------------------------------------

    def test_un_ok_sigue_despues_del_adjunto_no_quita_la_defensa(self):
        conv = self.conversacion()
        self.assertFalse(conv._turno_con_adjuntos())
        self.mensaje_de_la_persona(conv, 'Revisa esta factura', con_adjunto=True)
        self.mensaje_de_la_persona(conv, 'ok, sigue')
        self.assertTrue(conv._turno_con_adjuntos(), 'el texto del adjunto sigue a la vista del modelo')
        for i in range(8):
            self.mensaje_de_la_persona(conv, f'otra cosa {i}')
        self.assertFalse(conv._turno_con_adjuntos(), 'cuando el adjunto ya quedó lejos, vuelve a la normalidad')


@tagged('post_install', '-at_install')
class TestTopesDeGasto(BrianCase):
    """El freno de seguridad del gasto de IA: mensual (todos) y por persona, y límites de lo que se manda."""

    def setUp(self):
        super().setUp()
        self.Uso = self.env['brian.uso'].sudo()
        self.parametros = self.env['ir.config_parameter'].sudo()
        # Cuenta limpia: lo que haya gastado la base de pruebas no cuenta.
        self.env.cr.execute('DELETE FROM brian_uso')
        self.env.invalidate_all()

    def gastar(self, usuario, entrada=0, salida=0, modelo='claude-sonnet-5-5', cuando=None):
        fila = self.Uso.with_user(usuario).sudo().create({
            'modelo': modelo, 'tokens_entrada': entrada, 'tokens_salida': salida, 'canal': 'chat'})
        if cuando:
            self.env.cr.execute('UPDATE brian_uso SET create_date = %s WHERE id = %s', [cuando, fila.id])
            self.Uso.invalidate_model()
        return fila

    def conversacion(self, usuario=None):
        Conversacion = self.env['brian.conversacion'].with_user(usuario or self.usuario)
        return Conversacion.browse(Conversacion.nueva('chat')['id'])

    def test_los_topes_traen_valores_de_seguridad_y_cero_los_quita(self):
        self.assertEqual(self.Uso.topes(), (30.0, 10.0))
        self.parametros.set_param('dcasa_brian.tope_mensual_usd', '0')
        self.parametros.set_param('dcasa_brian.tope_por_persona_usd', '2.5')
        self.assertEqual(self.Uso.topes(), (0.0, 2.5))
        self.parametros.set_param('dcasa_brian.tope_mensual_usd', 'basura')
        self.assertEqual(self.Uso.topes()[0], 30.0, 'un valor roto no deja a Brian sin freno')

    def test_el_gasto_del_mes_usa_la_tarifa_y_un_modelo_nuevo_la_mas_cara(self):
        # 1 millón de tokens de salida de Sonnet = $10.
        self.gastar(self.usuario, salida=1_000_000)
        self.assertAlmostEqual(self.Uso.gasto_del_mes(), 10.0)
        # Un modelo que no conocemos se cuenta con la tarifa más cara: nunca queda fuera del tope.
        self.gastar(self.otro, salida=1_000_000, modelo='un-modelo-nuevo')
        self.assertAlmostEqual(self.Uso.gasto_del_mes(), 20.0)
        self.assertAlmostEqual(self.Uso.gasto_del_mes(self.otro), 10.0)
        self.assertAlmostEqual(self.Uso.gasto_del_mes(self.usuario), 10.0)

    def test_lo_del_mes_pasado_no_cuenta(self):
        self.gastar(self.usuario, salida=1_000_000, cuando=fields.Datetime.now() - timedelta(days=40))
        self.assertAlmostEqual(self.Uso.gasto_del_mes(), 0.0)

    def test_al_llegar_al_tope_de_todos_nadie_gasta_mas_y_se_dice_claro(self):
        self.parametros.set_param('dcasa_brian.tope_mensual_usd', '5')
        self.gastar(self.otro, salida=600_000)   # $6 de otra persona
        proveedores.fijar_guion(['No debería llegar al modelo'])
        resultado = self.conversacion().enviar('hola')
        self.assertFalse(resultado['ok'])
        self.assertIn('tope de gasto de IA de este mes', resultado['error'])
        self.assertIn('$5.00', resultado['error'])
        self.assertFalse(proveedores.LLAMADAS, 'ni una llamada al modelo')

    def test_al_llegar_al_tope_de_una_persona_solo_ella_se_frena(self):
        self.parametros.set_param('dcasa_brian.tope_por_persona_usd', '3')
        self.gastar(self.usuario, salida=400_000)   # $4
        proveedores.fijar_guion(['Hola, aquí estoy.'])
        frenada = self.conversacion().enviar('hola')
        self.assertFalse(frenada['ok'])
        self.assertIn('Llegaste a tu tope', frenada['error'])
        libre = self.conversacion(self.otro).enviar('hola')
        self.assertTrue(libre['ok'], libre)

    def test_cero_en_los_dos_topes_no_frena_a_nadie(self):
        self.parametros.set_param('dcasa_brian.tope_mensual_usd', '0')
        self.parametros.set_param('dcasa_brian.tope_por_persona_usd', '0')
        self.gastar(self.usuario, salida=50_000_000)
        proveedores.fijar_guion(['Sigo aquí.'])
        self.assertTrue(self.conversacion().enviar('hola')['ok'])

    def test_confirmar_una_accion_tambien_respeta_el_tope_y_la_accion_sigue_pendiente(self):
        proveedores.fijar_guion([{'herramientas': [('prueba_sensible', {'nombre': 'Cliente Tope'})]}])
        conv = self.conversacion()
        tarjeta = conv.enviar('Crea el cliente')
        accion_id = tarjeta['mensajes'][-1]['confirmacion']['accion_id']
        self.parametros.set_param('dcasa_brian.tope_por_persona_usd', '1')
        self.gastar(self.usuario, salida=300_000)
        resultado = conv.confirmar_accion(accion_id)
        self.assertFalse(resultado['ok'])
        self.assertEqual(self.env['brian.accion'].browse(accion_id).estado, 'por_confirmar')
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'Cliente Tope')]))

    def test_un_mensaje_enorme_o_con_demasiados_archivos_se_rechaza_antes_de_gastar(self):
        proveedores.fijar_guion(['No debería llegar al modelo'])
        conv = self.conversacion()
        largo = conv.enviar('a' * 8001)
        self.assertFalse(largo['ok'])
        self.assertIn('muy largo', largo['error'])
        archivos = [self.env['ir.attachment'].with_user(self.usuario).create({
            'name': f'f{i}.txt', 'raw': b'x', 'mimetype': 'text/plain',
            'res_model': 'brian.conversacion', 'res_id': conv.id}).id for i in range(6)]
        muchos = conv.enviar('mira', adjunto_ids=archivos)
        self.assertFalse(muchos['ok'])
        self.assertIn('muchos archivos', muchos['error'])
        self.assertFalse(proveedores.LLAMADAS)
        self.assertTrue(conv.enviar('a' * 8000)['ok'], 'justo en el límite sí pasa')
