"""Registro de herramientas, política y auditoría de Brian."""
from types import SimpleNamespace

from odoo.addons.dcasa_brian.models.registro import BrianError
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import BrianCase


class _MoveFalso(SimpleNamespace):
    """Lo mínimo de account.move que mira la política (sin depender del plan contable)."""
    _fields = {'payment_state': True}

    def __iter__(self):
        return iter([self])


@tagged('post_install', '-at_install')
class TestRegistro(BrianCase):

    # -- Catálogo ------------------------------------------------------------

    def test_catalogo_filtra_por_grupos(self):
        normal = {h['name'] for h in self.herramientas().catalogo()}
        jefe = {h['name'] for h in self.herramientas(self.jefe).catalogo()}
        self.assertIn('prueba_leer', normal)
        self.assertNotIn('prueba_admin', normal)
        self.assertIn('prueba_admin', jefe)
        esquema = next(h for h in self.herramientas().catalogo() if h['name'] == 'prueba_leer')
        self.assertEqual(esquema['input_schema']['required'], ['texto'])
        self.assertEqual(esquema['nivel'], 'lectura')

    def test_preseleccion_incluye_generales_y_relevantes(self):
        todas = self.herramientas().catalogo()
        maximo = 6
        elegidas = self.herramientas().catalogo(consulta='la zanahoria', maximo=maximo)
        nombres = {h['name'] for h in elegidas}
        generales = [h for h in elegidas if h['categoria'] == 'general']
        self.assertEqual(len(elegidas), maximo)
        self.assertLess(len(elegidas), len(todas))
        self.assertTrue(generales, 'Siempre va al menos una general')
        self.assertLessEqual(len(generales), maximo // 3, 'Las generales no ocupan todos los cupos')
        self.assertIn('prueba_crear_contacto', nombres, 'La relevante al mensaje entra')

    def test_ejecutar_con_herramienta_inexistente_o_sin_permiso(self):
        self.assertFalse(self.herramientas().ejecutar('no_existe')['ok'])
        self.assertFalse(self.herramientas().ejecutar('prueba_admin')['ok'])
        self.assertTrue(self.herramientas(self.jefe).ejecutar('prueba_admin')['ok'])

    # -- Ejecución -------------------------------------------------------------

    def test_lectura_directa_y_auditada(self):
        resultado = self.herramientas().ejecutar('prueba_leer', {'texto': 'hola'}, canal='telegram')
        self.assertEqual(resultado, {'ok': True, 'datos': {'eco': 'hola', 'usuario': 'brian_vendedora'}})
        accion = self.env['brian.accion'].search([('herramienta', '=', 'prueba_leer')], limit=1)
        self.assertEqual(accion.estado, 'hecha')
        self.assertEqual(accion.create_uid, self.usuario)
        self.assertEqual(accion.canal, 'telegram')
        self.assertIn('hola', accion.resultado)

    def test_construccion_directa(self):
        resultado = self.herramientas().ejecutar('prueba_crear_contacto', {'nombre': 'Contacto Brian 1'})
        self.assertTrue(resultado['ok'])
        self.assertTrue(self.env['res.partner'].search([('name', '=', 'Contacto Brian 1')]))

    def test_validaciones_de_argumentos(self):
        faltan = self.herramientas().ejecutar('prueba_leer', {})
        self.assertIn('Faltan datos', faltan['error'])
        sobran = self.herramientas().ejecutar('prueba_leer', {'texto': 'x', 'otro': 1})
        self.assertIn('no existen', sobran['error'])
        falla = self.herramientas().ejecutar('prueba_falla')
        self.assertEqual(falla, {'ok': False, 'error': 'Dato inválido: prueba con otro.'})
        accion = self.env['brian.accion'].search([('herramienta', '=', 'prueba_falla')], limit=1)
        self.assertEqual(accion.estado, 'error')

    def test_sensible_pide_confirmacion_y_confirmar_la_ejecuta(self):
        herramientas = self.herramientas(self.jefe)
        propuesta = herramientas.ejecutar('prueba_sensible', {'nombre': 'Contacto Sensible'})
        self.assertTrue(propuesta['requiere_confirmacion'])
        self.assertIn('Contacto Sensible', propuesta['resumen'])
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'Contacto Sensible')]))
        accion = self.env['brian.accion'].browse(propuesta['accion_id'])
        self.assertEqual(accion.estado, 'por_confirmar')

        # Otra persona no puede confirmarla.
        ajena = self.herramientas(self.usuario).confirmar(accion.id)
        self.assertFalse(ajena['ok'])
        self.assertEqual(accion.estado, 'por_confirmar')

        confirmada = herramientas.confirmar(accion.id)
        self.assertTrue(confirmada['ok'])
        self.assertEqual(accion.estado, 'hecha')
        self.assertTrue(self.env['res.partner'].search([('name', '=', 'Contacto Sensible')]))
        self.assertFalse(herramientas.confirmar(accion.id)['ok'], 'No se confirma dos veces')

    def test_rechazar(self):
        herramientas = self.herramientas(self.jefe)
        propuesta = herramientas.ejecutar('prueba_sensible', {'nombre': 'Nunca'})
        herramientas.rechazar(propuesta['accion_id'])
        accion = self.env['brian.accion'].browse(propuesta['accion_id'])
        self.assertEqual(accion.estado, 'rechazada')
        self.assertFalse(herramientas.confirmar(accion.id)['ok'])

    # -- Política --------------------------------------------------------------

    def test_politica_bloquea_modelos_tecnicos_secretos_y_borrados(self):
        herramientas = self.herramientas(self.jefe)
        for argumentos in ({'modelo': 'ir.config_parameter'}, {'modelo': 'account.move'},
                           {'modelo': 'dcasa.movimiento'}, {'modelo': 'res.partner', 'campos': ['password']}):
            resultado = herramientas.ejecutar('eliminar_prueba', argumentos)
            self.assertFalse(resultado['ok'], argumentos)
        acciones = self.env['brian.accion'].search([('herramienta', '=', 'eliminar_prueba')])
        self.assertEqual(set(acciones.mapped('estado')), {'bloqueada'})
        secreto = herramientas.ejecutar('prueba_leer', {'texto': 'dame el DCASA_PIN_PEPPER'})
        self.assertFalse(secreto['ok'])
        self.assertTrue(herramientas.ejecutar('eliminar_prueba', {'modelo': 'res.partner'})['ok'])

    def test_politica_protege_admin_y_a_uno_mismo(self):
        politica = self.env['brian.politica'].with_user(self.jefe)
        with self.assertRaises(BrianError):
            politica.proteger_usuario(self.env.ref('base.user_admin'), 'archivar')
        with self.assertRaises(BrianError):
            politica.proteger_usuario(self.jefe, 'quitarle permisos a')
        self.assertTrue(politica.proteger_usuario(self.usuario, 'archivar'))
        with self.assertRaises(BrianError):
            politica.proteger_libro_puntos('unlink')
        with self.assertRaises(BrianError):
            politica.proteger_campos('res.users', ['group_ids'])
        with self.assertRaises(BrianError):
            politica.proteger_conciliacion()

    def test_politica_facturas(self):
        politica = self.env['brian.politica']
        self.assertTrue(politica.puede_editar_factura(
            _MoveFalso(state='draft', payment_state='not_paid', display_name='Borrador')))
        for estado, pago in (('posted', 'not_paid'), ('draft', 'paid'), ('cancel', 'not_paid'),
                             ('draft', 'partial')):
            with self.assertRaises(BrianError):
                politica.puede_editar_factura(_MoveFalso(state=estado, payment_state=pago, display_name='F1'))

    def test_limite_de_acciones_por_minuto(self):
        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian.acciones_por_minuto', '2')
        herramientas = self.herramientas()
        resultados = [herramientas.ejecutar('prueba_leer', {'texto': str(i)}) for i in range(4)]
        self.assertTrue(resultados[0]['ok'])
        self.assertFalse(resultados[-1]['ok'])
        self.assertIn('muy rápido', resultados[-1]['error'])

    def test_resumen_generico(self):
        spec = self.env['brian.herramientas']._todas()['prueba_sensible']
        resumen = self.env['brian.politica'].resumir(spec, {'nombre': 'Ana', 'activo': True})
        self.assertIn('Crea un contacto importante', resumen)
        self.assertIn('Nombre: Ana', resumen)
        self.assertIn('Activo: Sí', resumen)

    # -- Auditoría -------------------------------------------------------------

    def test_auditoria_inmutable(self):
        self.herramientas().ejecutar('prueba_leer', {'texto': 'auditar'})
        accion = self.env['brian.accion'].search([('herramienta', '=', 'prueba_leer')], limit=1)
        como_usuario = accion.with_user(self.usuario)
        self.assertEqual(como_usuario.estado, 'hecha')
        with self.assertRaises(AccessError):
            como_usuario.write({'estado': 'error'})
        with self.assertRaises(AccessError):
            como_usuario.unlink()
        with self.assertRaises(AccessError):
            accion.with_user(self.jefe).unlink()
        with self.assertRaises(AccessError):
            accion.sudo().write({'resultado': 'otro'})
        with self.assertRaises(AccessError):
            accion.sudo().unlink()
        with self.assertRaises(AccessError):
            self.env['brian.accion'].with_user(self.usuario).create({'herramienta': 'x'})

    def test_auditoria_cada_quien_ve_lo_suyo_y_el_admin_todo(self):
        self.herramientas().ejecutar('prueba_leer', {'texto': 'de la vendedora'})
        Accion = self.env['brian.accion']
        self.assertTrue(Accion.with_user(self.usuario).search([('herramienta', '=', 'prueba_leer')]))
        self.assertFalse(Accion.with_user(self.otro).search([('herramienta', '=', 'prueba_leer')]))
        self.assertTrue(Accion.with_user(self.jefe).search([('herramienta', '=', 'prueba_leer')]))
