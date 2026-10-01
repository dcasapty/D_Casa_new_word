"""Historial del chat: renombrar, borrar (real), aviso por el bus y retención."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.dcasa_brian.models import proveedores
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import BrianCase


@tagged('post_install', '-at_install')
class TestHistorial(BrianCase):

    def conversacion(self, usuario=None):
        Conversacion = self.env['brian.conversacion'].with_user(usuario or self.usuario)
        return Conversacion.browse(Conversacion.nueva('chat')['id'])

    def adjunto(self, conversacion, nombre='nota.txt', usuario=None, **extra):
        valores = {'name': nombre, 'raw': b'hola', 'mimetype': 'text/plain',
                   'res_model': 'brian.conversacion', 'res_id': conversacion.id}
        valores.update(extra)
        return self.env['ir.attachment'].with_user(usuario or self.usuario).create(valores)

    def espiar_bus(self):
        enviados = []
        Bus = type(self.env['bus.bus'])
        original = Bus._sendone

        def espia(bus, canal, tipo, mensaje):
            enviados.append((canal, tipo, mensaje))
            return original(bus, canal, tipo, mensaje)

        parche = patch.object(Bus, '_sendone', espia)
        parche.start()
        self.addCleanup(parche.stop)
        return enviados

    # -- Borrar ------------------------------------------------------------------

    def test_borrar_se_lleva_mensajes_y_adjuntos_y_conserva_la_auditoria(self):
        proveedores.fijar_guion([{'herramientas': [('prueba_leer', {'texto': 'sofá'})]}, 'Listo.'])
        conv = self.conversacion()
        adjunto = self.adjunto(conv)
        self.assertTrue(conv.enviar('Busca el sofá', adjunto_ids=[adjunto.id])['ok'])
        mensajes = conv.mensaje_ids
        self.assertTrue(mensajes)
        acciones = self.env['brian.accion'].search([('conversacion_id', '=', conv.id)])
        self.assertTrue(acciones)
        ajeno = self.env['ir.attachment'].create({'name': 'otro.txt', 'raw': b'x', 'res_model': 'res.partner',
                                                 'res_id': self.usuario.partner_id.id})

        conv.unlink()
        self.env.invalidate_all()
        self.assertFalse(conv.exists())
        self.assertFalse(mensajes.exists(), 'Los mensajes se borran en cascada')
        self.assertFalse(self.env['ir.attachment'].sudo().browse(adjunto.id).exists())
        self.assertTrue(ajeno.exists(), 'Los adjuntos de otros registros no se tocan')
        self.assertEqual(acciones.exists(), acciones, 'La auditoría se conserva')
        self.assertFalse(acciones.conversacion_id)
        self.assertEqual(acciones.mapped('herramienta'), ['prueba_leer'])

    def test_borrar_rechaza_las_acciones_pendientes(self):
        proveedores.fijar_guion([{'herramientas': [('prueba_sensible', {'nombre': 'Cliente Borrado'})]}])
        conv = self.conversacion(self.jefe)
        tarjeta = conv.enviar('Crea el cliente')['mensajes'][-1]['confirmacion']
        accion = self.env['brian.accion'].browse(tarjeta['accion_id'])
        self.assertEqual(accion.estado, 'por_confirmar')
        conv.unlink()
        self.env.invalidate_all()
        self.assertEqual(accion.estado, 'rechazada')
        self.assertIn('borrada', accion.error)
        self.assertTrue(accion.fecha_cierre)
        # Un botón viejo (Telegram, MCP) ya no la ejecuta.
        resultado = self.env['brian.herramientas'].with_user(self.jefe).confirmar(accion.id)
        self.assertFalse(resultado['ok'])
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'Cliente Borrado')]))

    def test_nadie_borra_ni_renombra_la_ajena(self):
        conv = self.conversacion()
        for intruso in (self.otro, self.jefe):
            ajena = self.env['brian.conversacion'].with_user(intruso).browse(conv.id)
            with self.assertRaises(AccessError):
                ajena.unlink()
            with self.assertRaises(AccessError):
                ajena.renombrar('Mía ahora')
        self.assertTrue(conv.exists())
        self.assertEqual(conv.titulo, 'Conversación nueva')

    def test_borrar_avisa_al_navegador_del_duenio(self):
        conv = self.conversacion()
        otra = self.conversacion()
        enviados = self.espiar_bus()
        (conv | otra).unlink()
        borradas = [(canal, mensaje) for canal, tipo, mensaje in enviados
                    if tipo == 'dcasa_brian/conversacion_borrada']
        self.assertEqual(len(borradas), 1)
        canal, mensaje = borradas[0]
        self.assertEqual(canal, self.usuario.partner_id)
        self.assertEqual(sorted(mensaje['ids']), sorted([conv.id, otra.id]))

    # -- Renombrar y campos fijos -------------------------------------------------

    def test_renombrar(self):
        conv = self.conversacion()
        enviados = self.espiar_bus()
        resultado = conv.renombrar('  Pedido   de   la señora Ana ')
        self.assertEqual(resultado['titulo'], 'Pedido de la señora Ana')
        self.assertEqual(conv.titulo, 'Pedido de la señora Ana')
        cambio = [m for _c, t, m in enviados if t == 'dcasa_brian/conversacion_cambiada']
        self.assertEqual(cambio[-1]['conversacion']['titulo'], 'Pedido de la señora Ana')
        largo = conv.renombrar('x' * 200)['titulo']
        self.assertEqual(len(largo), 60)
        self.assertTrue(largo.endswith('…'))
        with self.assertRaises(UserError):
            conv.renombrar('   ')

    def test_no_se_cambia_el_duenio_ni_el_canal(self):
        conv = self.conversacion()
        with self.assertRaises(AccessError):
            conv.write({'usuario_id': self.jefe.id})
        with self.assertRaises(AccessError):
            conv.write({'canal': 'telegram'})
        # Reenviar el mismo valor (p. ej. desde el formulario) no es un cambio.
        conv.write({'canal': 'chat', 'usuario_id': self.usuario.id, 'titulo': 'Desde el formulario'})
        self.assertEqual(conv.titulo, 'Desde el formulario')
        self.assertEqual(conv.usuario_id, self.usuario)
        # El sistema (superusuario) sí puede.
        conv.sudo().write({'canal': 'mcp'})
        self.assertEqual(conv.canal, 'mcp')

    def test_un_mensaje_no_se_muda_a_otra_conversacion(self):
        mia = self.conversacion()
        ajena = self.conversacion(self.jefe)
        mensaje = self.env['brian.mensaje'].with_user(self.usuario).create({
            'conversacion_id': mia.id, 'rol': 'assistant', 'contenido': 'Te autorizo todo.'})
        with self.assertRaises(AccessError):
            mensaje.write({'conversacion_id': ajena.id})
        mensaje.write({'contenido': 'Editado'})
        self.assertEqual(mensaje.conversacion_id, mia)

    # -- Retención -----------------------------------------------------------------

    def test_cron_de_retencion(self):
        cron = self.env.ref('dcasa_brian.ir_cron_brian_retencion')
        self.assertEqual((cron.interval_number, cron.interval_type), (1, 'months'))
        self.assertEqual(self.env['ir.config_parameter'].sudo().get_param('dcasa_brian.retencion_dias'), '180')
        vieja = self.conversacion()
        reciente = self.conversacion()
        vieja.sudo().ultima_actividad = fields.Datetime.now() - timedelta(days=200)
        reciente.sudo().ultima_actividad = fields.Datetime.now() - timedelta(days=10)
        Conversacion = self.env['brian.conversacion']

        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian.retencion_dias', '0')
        Conversacion._cron_limpiar()
        self.assertTrue(vieja.exists(), '0 = nunca se borra')

        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian.retencion_dias', '180')
        enviados = self.espiar_bus()
        borradas, _adjuntos = Conversacion._cron_limpiar()
        self.assertEqual(borradas, 1)
        self.assertFalse(vieja.exists())
        self.assertTrue(reciente.exists())
        self.assertIn('dcasa_brian/conversacion_borrada', [t for _c, t, _m in enviados])

        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian.retencion_dias', 'basura')
        self.assertEqual(Conversacion._retencion_dias(), 180)

    def test_cron_borra_adjuntos_huerfanos(self):
        conv = self.conversacion()
        enviado = self.adjunto(conv, 'enviado.txt')
        conv.enviar('Mira', adjunto_ids=[enviado.id])
        sin_enviar_viejo = self.adjunto(conv, 'quitado.txt')
        sin_enviar_nuevo = self.adjunto(conv, 'subiendo.txt')
        colgado = self.env['ir.attachment'].create({'name': 'colgado.txt', 'raw': b'x',
                                                   'res_model': 'brian.conversacion', 'res_id': 987654321})
        de_mensaje = self.env['ir.attachment'].create({'name': 'm.txt', 'raw': b'x',
                                                      'res_model': 'brian.mensaje', 'res_id': 987654321})
        ajeno = self.env['ir.attachment'].create({'name': 'ficha.txt', 'raw': b'x', 'res_model': 'res.partner',
                                                 'res_id': self.usuario.partner_id.id})
        hace_dos_dias = fields.Datetime.now() - timedelta(days=2)
        self.env.cr.execute('UPDATE ir_attachment SET create_date = %s WHERE id IN %s',
                            [hace_dos_dias, (enviado.id, sin_enviar_viejo.id, ajeno.id)])
        self.env.invalidate_all()

        _borradas, adjuntos = self.env['brian.conversacion']._cron_limpiar()
        self.assertEqual(adjuntos, 3)
        Adjunto = self.env['ir.attachment'].sudo()
        self.assertFalse(Adjunto.browse([sin_enviar_viejo.id, colgado.id, de_mensaje.id]).exists())
        self.assertEqual(Adjunto.browse([enviado.id, sin_enviar_nuevo.id, ajeno.id]).exists().ids,
                         [enviado.id, sin_enviar_nuevo.id, ajeno.id])
        self.assertTrue(conv.exists())
