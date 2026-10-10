"""Ronda 8 (auditoría del 2026-10-10): topes de tamaño, texto de clientes y adjuntos que siguen contando."""
import time

from odoo.addons.dcasa_brian.models import herramientas_comun as c
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
