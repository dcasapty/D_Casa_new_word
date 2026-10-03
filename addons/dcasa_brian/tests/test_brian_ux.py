"""Brian en vivo (ronda UX): pasos por el bus, tarjeta Permitir / Rechazar con detalle exacto,
pastillas de estado por rol y estados del avatar.

Sin IA real: el proveedor 'prueba' sigue un guion. El bus se espía parchando ``bus.bus._sendone``
(los pasos salen con un cursor aparte, pero la clase del registro es la misma).
"""
import re
from datetime import timedelta
from unittest.mock import patch

from odoo import fields, models
from odoo.addons.dcasa_brian.models import pasos, proveedores
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase

from .common import BrianCase

PASOS = 'dcasa_brian/pasos'


@tagged('post_install', '-at_install')
class TestPasosPuros(TransactionCase):
    """``models/pasos.py``: funciones puras, sin Odoo."""

    def test_gerundio(self):
        self.assertEqual(pasos.gerundio('buscar'), 'buscando')
        self.assertEqual(pasos.gerundio('leer'), 'leyendo')
        self.assertEqual(pasos.gerundio('sugerir'), 'sugiriendo')
        self.assertEqual(pasos.gerundio('deshacer'), 'deshaciendo')
        self.assertIsNone(pasos.gerundio('ayuda'))
        self.assertIsNone(pasos.gerundio(''))

    def test_titulo_paso_humano(self):
        self.assertEqual(pasos.titulo_paso('buscar_productos', {'texto': '888K'}), 'Buscando productos «888K»')
        self.assertEqual(pasos.titulo_paso('crear_cotizacion', {'cliente': '6026-1919', 'lineas': 'x'}),
                         'Creando cotizacion «6026-1919»')
        self.assertEqual(pasos.titulo_paso('leer_adjunto', {'adjunto': 42}), 'Leyendo adjunto «42»')
        self.assertEqual(pasos.titulo_paso('pantalla_actual'), 'Mirando la pantalla actual')
        self.assertEqual(pasos.titulo_paso('reporte_del_dia', {}), 'Armando el reporte del día')
        self.assertEqual(pasos.titulo_paso('zzz'), 'Usando zzz')
        self.assertEqual(pasos.titulo_paso(''), 'Usando una herramienta')
        # Los argumentos largos se recortan; los booleanos y las listas no van al título.
        largo = pasos.titulo_paso('buscar_clientes', {'texto': 'x' * 100})
        self.assertLessEqual(len(largo), len('Buscando clientes «»') + pasos.MAX_ARGUMENTO)
        self.assertTrue(largo.endswith('…»'))
        self.assertEqual(pasos.titulo_paso('buscar_compras', {'texto': True, 'estado': ['a']}), 'Buscando compras')

    def test_resumen_sin_inventar(self):
        self.assertEqual(pasos.resumen_resultado({'ok': True, 'datos': {'resumen': 'Hay 3 ventas'}}), 'Hay 3 ventas')
        self.assertEqual(pasos.resumen_resultado({'ok': True, 'datos': {'productos': [1, 2, 3]}}), '3 productos')
        self.assertEqual(pasos.resumen_resultado({'ok': True, 'datos': {'productos': [1]}}), '1 producto')
        self.assertEqual(pasos.resumen_resultado({'ok': True, 'datos': {'eco': 'x'}}), 'Listo')
        self.assertEqual(pasos.resumen_resultado({'ok': False, 'error': 'No se pudo tal cosa'}), 'No se pudo tal cosa')
        self.assertEqual(pasos.resumen_resultado({'ok': False, 'requiere_confirmacion': True, 'resumen': 'x'}),
                         'Necesita tu permiso')
        self.assertEqual(pasos.resumen_resultado('basura'), '')
        self.assertLessEqual(len(pasos.resumen_resultado({'ok': False, 'error': 'e' * 500})), pasos.MAX_RESUMEN)

    def test_detalle_recortado(self):
        detalle = pasos.detalle_resultado({'ok': True, 'datos': {'lista': list(range(400))}})
        self.assertIn('[recortado]', detalle)
        self.assertLessEqual(len(detalle), pasos.MAX_DETALLE + 20)
        self.assertEqual(pasos.detalle_resultado({'ok': True, 'datos': {}}), '')
        self.assertIn('"error"', pasos.detalle_resultado({'ok': False, 'error': 'ay'}))
        self.assertIn('888K', pasos.detalle_resultado({'ok': True, 'datos': {'eco': '888K'}}))


@tagged('post_install', '-at_install')
class TestBrianEnVivo(BrianCase):

    def conversacion(self, usuario=None, canal='chat'):
        Conversacion = self.env['brian.conversacion'].with_user(usuario or self.usuario)
        return Conversacion.browse(Conversacion.nueva(canal)['id'])

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

    @staticmethod
    def eventos_pasos(enviados):
        return [(canal, mensaje) for canal, tipo, mensaje in enviados if tipo == PASOS]

    # -- Pasos en vivo -------------------------------------------------------------

    def test_pasos_en_vivo_por_el_bus(self):
        enviados = self.espiar_bus()
        proveedores.fijar_guion([
            {'texto': 'Déjame ver…', 'herramientas': [('prueba_leer', {'texto': '888K'})]},
            'Listo: 888K.',
        ])
        conv = self.conversacion()
        resultado = conv.enviar('Busca 888K')
        self.assertTrue(resultado['ok'], resultado)

        eventos = self.eventos_pasos(enviados)
        self.assertGreaterEqual(len(eventos), 5, 'pensar, herramienta (empieza y termina), pensar, cierre')
        turno = resultado['mensajes'][0]['id']
        for canal, carga in eventos:
            # Solo al navegador del dueño (su partner), y siempre la lista completa del mismo turno.
            self.assertIsInstance(canal, models.BaseModel)
            self.assertEqual(canal.id, self.usuario.partner_id.id)
            self.assertEqual(carga['conversacion_id'], conv.id)
            self.assertEqual(carga['turno'], turno)
            for paso in carga['pasos']:
                self.assertEqual(set(paso), {'id', 'tipo', 'nombre', 'titulo', 'estado', 'resumen', 'detalle',
                                             'duracion_ms'})
        estados = [carga['estado'] for _c, carga in eventos]
        self.assertEqual(estados[:-1], ['trabajando'] * (len(eventos) - 1))
        self.assertEqual(estados[-1], 'terminado')
        tamanos = [len(carga['pasos']) for _c, carga in eventos]
        self.assertEqual(tamanos, sorted(tamanos), 'La lista solo crece (idempotente para el panel)')

        primero = eventos[0][1]['pasos']
        self.assertEqual([(p['tipo'], p['titulo'], p['estado']) for p in primero],
                         [('modelo', 'Pensando…', 'en_curso')])

        final = eventos[-1][1]['pasos']
        self.assertEqual([p['titulo'] for p in final], ['Pensando…', 'Usando prueba leer «888K»', 'Pensando…'])
        self.assertEqual([p['estado'] for p in final], ['ok', 'ok', 'ok'])
        self.assertEqual([p['resumen'] for p in final], ['Va a usar 1 herramienta(s)', 'Listo', 'Respondió'])
        herramienta = final[1]
        self.assertEqual(herramienta['nombre'], 'prueba_leer')
        self.assertIn('888K', herramienta['detalle'])
        self.assertIsInstance(herramienta['duracion_ms'], int)
        self.assertGreaterEqual(herramienta['duracion_ms'], 0)
        # El paso vivo (en curso) no trae resumen todavía.
        en_curso = [p for _c, carga in eventos for p in carga['pasos'] if p['estado'] == 'en_curso']
        self.assertTrue(en_curso)
        self.assertTrue(all(p['resumen'] == '' and p['duracion_ms'] is None for p in en_curso))

    def test_paso_con_error_y_paso_por_confirmar(self):
        enviados = self.espiar_bus()
        proveedores.fijar_guion([{'herramientas': [('prueba_falla', {})]}, 'Uy.'])
        self.conversacion().enviar('Prueba el error')
        final = self.eventos_pasos(enviados)[-1][1]['pasos']
        fallido = next(p for p in final if p['nombre'] == 'prueba_falla')
        self.assertEqual(fallido['estado'], 'error')
        self.assertEqual(fallido['resumen'], 'Dato inválido: prueba con otro.')

        enviados.clear()
        proveedores.fijar_guion([{'herramientas': [('prueba_sensible', {'nombre': 'Cliente VIP'})]}])
        self.conversacion(self.jefe).enviar('Crea el cliente VIP')
        eventos = self.eventos_pasos(enviados)
        final = eventos[-1][1]['pasos']
        sensible = next(p for p in final if p['nombre'] == 'prueba_sensible')
        self.assertEqual(sensible['estado'], 'por_confirmar')
        self.assertEqual(sensible['resumen'], 'Necesita tu permiso')
        self.assertEqual(eventos[-1][1]['estado'], 'terminado')
        self.assertEqual(eventos[-1][0].id, self.jefe.partner_id.id)

    def test_sin_bus_el_turno_sigue(self):
        """Si el bus falla, Brian responde igual por el RPC (los pasos son un extra)."""
        Bus = type(self.env['bus.bus'])
        original = Bus._sendone

        def roto(bus, canal, tipo, mensaje):
            if tipo == PASOS:
                raise RuntimeError('bus caído')
            return original(bus, canal, tipo, mensaje)

        proveedores.fijar_guion([{'herramientas': [('prueba_leer', {'texto': 'a'})]}, 'Todo bien.'])
        with patch.object(Bus, '_sendone', roto):
            resultado = self.conversacion().enviar('Hola')
        self.assertTrue(resultado['ok'], resultado)
        self.assertEqual(resultado['mensajes'][-1]['texto'], 'Todo bien.')

    def test_telegram_y_mcp_no_emiten_pasos(self):
        enviados = self.espiar_bus()
        proveedores.fijar_guion([{'herramientas': [('prueba_leer', {'texto': 'a'})]}, 'Listo.'])
        self.assertTrue(self.conversacion(canal='telegram').enviar('Hola')['ok'])
        self.assertFalse(self.eventos_pasos(enviados), 'Nadie mira el panel desde Telegram')

    def test_historial_trae_titulo_resumen_y_detalle(self):
        proveedores.fijar_guion([{'herramientas': [('prueba_leer', {'texto': 'sofá'})]}, 'Listo.'])
        conv = self.conversacion()
        conv.enviar('Busca el sofá')
        historial = self.env['brian.conversacion'].with_user(self.usuario).historial(conv.id)
        herramienta = historial['mensajes'][1]['herramientas'][0]
        self.assertEqual(herramienta['titulo'], 'Usando prueba leer «sofá»')
        self.assertEqual(herramienta['resumen'], 'Listo')
        self.assertIn('sofá', herramienta['detalle'])
        self.assertIsInstance(herramienta['duracion_ms'], int)
        self.assertTrue(herramienta['ok'])

    # -- Tarjeta Permitir / Rechazar ------------------------------------------------------

    def test_tarjeta_con_detalle_exacto_permitir(self):
        proveedores.fijar_guion([{'texto': 'Te propongo crearlo.',
                                  'herramientas': [('prueba_sensible', {'nombre': 'Cliente VIP'})]}])
        conv = self.conversacion(self.jefe)
        tarjeta = conv.enviar('Crea el cliente VIP')['mensajes'][-1]['confirmacion']
        self.assertEqual(tarjeta['estado'], 'por_confirmar')
        self.assertEqual(tarjeta['nivel'], 'sensible')
        self.assertEqual(tarjeta['detalle'], [{'etiqueta': 'Nombre', 'valor': 'Cliente VIP'}])
        # El detalle sale de los argumentos registrados: los mismos que se ejecutarán.
        accion = self.env['brian.accion'].browse(tarjeta['accion_id'])
        self.assertEqual(accion.argumentos_dict(), {'nombre': 'Cliente VIP'})

        enviados = self.espiar_bus()
        proveedores.fijar_guion(['Quedó creado.'])
        permitido = conv.confirmar_accion(tarjeta['accion_id'])
        self.assertTrue(permitido['ok'], permitido)
        self.assertTrue(self.env['res.partner'].search([('name', '=', 'Cliente VIP')]))
        tarjetas = [m['confirmacion'] for m in permitido['mensajes'] if m['confirmacion']]
        self.assertEqual(tarjetas[0]['estado'], 'hecha')
        self.assertEqual(tarjetas[0]['detalle'], [{'etiqueta': 'Nombre', 'valor': 'Cliente VIP'}])
        # Confirmar también se cuenta en vivo (Brian vuelve a pensar tras la acción).
        eventos = self.eventos_pasos(enviados)
        self.assertTrue(eventos)
        self.assertEqual(eventos[-1][1]['estado'], 'terminado')
        self.assertIn('Pensando…', [p['titulo'] for p in eventos[-1][1]['pasos']])
        # Permitir vale una sola vez: no hay «siempre»; volver a pulsar no repite la acción.
        proveedores.fijar_guion(['Eso ya estaba hecho.'])
        conv.confirmar_accion(tarjeta['accion_id'])
        self.assertEqual(self.env['res.partner'].search_count([('name', '=', 'Cliente VIP')]), 1)
        self.assertIn('no se pudo', proveedores.LLAMADAS[0]['mensajes'][-1]['texto'])

    def test_tarjeta_rechazar(self):
        proveedores.fijar_guion([{'herramientas': [('prueba_sensible', {'nombre': 'No Crear'})]}])
        conv = self.conversacion(self.jefe)
        tarjeta = conv.enviar('Crea No Crear')['mensajes'][-1]['confirmacion']
        rechazo = conv.rechazar_accion(tarjeta['accion_id'])
        self.assertTrue(rechazo['ok'])
        tarjetas = [m['confirmacion'] for m in rechazo['mensajes'] if m['confirmacion']]
        self.assertEqual(tarjetas[0]['estado'], 'rechazada')
        self.assertEqual(tarjetas[0]['detalle'], [{'etiqueta': 'Nombre', 'valor': 'No Crear'}])
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'No Crear')]))
        self.assertEqual(self.env['brian.accion'].browse(tarjeta['accion_id']).estado, 'rechazada')

    def test_detalle_humano_y_sin_vacios(self):
        from odoo.addons.dcasa_brian.models.conversacion import _detalle_accion
        spec = self.env['brian.herramientas']._todas()['eliminar_prueba']
        accion = self.env['brian.accion'].with_user(self.usuario).registrar(
            spec, {'modelo': 'res.partner', 'campos': ['a', 'b'], 'vacio': '', 'nada': None, 'si': True})
        self.assertEqual(_detalle_accion(accion), [
            {'etiqueta': 'Modelo', 'valor': 'res.partner'},
            {'etiqueta': 'Campos', 'valor': 'a, b'},
            {'etiqueta': 'Si', 'valor': 'Sí'},
        ])

    # -- Pastillas de estado ----------------------------------------------------------------

    def pastillas(self, usuario):
        return {p['clave']: p for p in self.env['brian.conversacion'].with_user(usuario).estado_panel()['pastillas']}

    def test_pastillas_de_una_vendedora(self):
        pastillas = self.pastillas(self.usuario)
        self.assertEqual(list(pastillas), ['telegram', 'mcp', 'actividad'],
                         'Sin consumo (no es administradora) ni importaciones (no ve brian.importacion)')
        self.assertEqual(pastillas['telegram']['texto'], 'Telegram sin vincular')
        self.assertEqual(pastillas['telegram']['tono'], 'neutro')
        self.assertEqual(pastillas['mcp']['texto'], 'MCP sin clave')
        self.assertEqual(pastillas['actividad']['texto'], 'Sin actividad todavía')
        for pastilla in pastillas.values():
            self.assertTrue(set(pastilla) >= {'clave', 'texto', 'icono', 'tono', 'titulo'}, pastilla)
            self.assertIn(pastilla['tono'], ('ok', 'neutro', 'aviso'))

        # Vincula Telegram, crea una clave de API y conversa: las pastillas lo reflejan.
        self.env['brian.telegram.enlace'].sudo().create({'user_id': self.usuario.id, 'chat_id': '777',
                                                         'nombre': 'Ana (@ana)'})
        self.env['res.users.apikeys'].with_user(self.usuario)._generate(
            'brian', 'Claude de Ana', fields.Datetime.now() + timedelta(days=1))
        proveedores.fijar_guion(['Hola.'])
        self.conversacion().enviar('Hola')
        pastillas = self.pastillas(self.usuario)
        self.assertEqual(pastillas['telegram']['texto'], 'Telegram conectado')
        self.assertEqual(pastillas['telegram']['tono'], 'ok')
        self.assertIn('Ana (@ana)', pastillas['telegram']['titulo'])
        self.assertEqual(pastillas['mcp']['texto'], 'MCP activo')
        self.assertEqual(pastillas['mcp']['tono'], 'ok')
        self.assertRegex(pastillas['actividad']['texto'], r'^Última actividad: hoy \d\d:\d\d$')
        self.assertTrue(pastillas['actividad']['fecha'])

        # La clave vencida no cuenta.
        self.env.cr.execute('UPDATE res_users_apikeys SET expiration_date = %s WHERE user_id = %s',
                            (fields.Datetime.now() - timedelta(minutes=1), self.usuario.id))
        self.assertEqual(self.pastillas(self.usuario)['mcp']['texto'], 'MCP sin clave')

    def test_pastillas_de_la_administradora(self):
        pastillas = self.pastillas(self.jefe)
        self.assertIn('consumo', pastillas)
        self.assertEqual(pastillas['consumo']['texto'], 'IA este mes: sin uso')
        self.assertEqual(pastillas['consumo']['llamadas'], 0)
        proveedores.fijar_guion([{'herramientas': [('prueba_leer', {'texto': 'a'})]}, 'Listo.'])
        self.conversacion(self.jefe).enviar('Hola')
        consumo = self.pastillas(self.jefe)['consumo']
        # El proveedor «prueba» no tiene tarifa: se cuentan llamadas y tokens, nunca un costo inventado.
        self.assertRegex(consumo['texto'], r'^IA este mes: 2 llamadas · [\d,]+ tokens$')
        self.assertEqual(consumo['llamadas'], 2)
        self.assertEqual(consumo['costo'], 0.0)
        # Con tarifa conocida sale el costo estimado (misma tabla que consumo_de_brian).
        self.env['brian.uso'].sudo().search([]).write({'modelo': 'claude-haiku-4-5', 'tokens_entrada': 1_000_000})
        consumo = self.pastillas(self.jefe)['consumo']
        self.assertRegex(consumo['texto'], r'^IA este mes: 2 llamadas · \$\d+\.\d\d$')
        self.assertGreater(consumo['costo'], 0)

    def test_pastilla_de_importaciones_por_rol(self):
        vendedora = new_test_user(self.env, login='brian_ux_vend', name='Vendedora UX',
                                  groups='base.group_user,sales_team.group_sale_salesman')
        self.assertNotIn('importaciones', self.pastillas(vendedora), 'Sin borradores no hay pastilla')
        propia = self.env['brian.importacion'].with_user(vendedora).sudo().create({'archivo': 'lista.xlsx'})
        pastilla = self.pastillas(vendedora)['importaciones']
        self.assertEqual(pastilla['texto'], '1 importación(es) por aplicar')
        self.assertEqual(pastilla['tono'], 'aviso')
        # Otra vendedora no ve la ajena (regla de registro, sin sudo); Gerencia sí.
        otra = new_test_user(self.env, login='brian_ux_otra', name='Otra UX',
                             groups='base.group_user,sales_team.group_sale_salesman')
        self.assertNotIn('importaciones', self.pastillas(otra))
        gerencia = new_test_user(self.env, login='brian_ux_ger', name='Gerencia UX',
                                 groups='base.group_user,sales_team.group_sale_salesman,dcasa_base.group_gerencia')
        self.assertEqual(self.pastillas(gerencia)['importaciones']['texto'], '1 importación(es) por aplicar')
        propia.sudo().write({'estado': 'aplicada'})
        self.assertNotIn('importaciones', self.pastillas(gerencia))

    def test_pastillas_solo_para_el_equipo(self):
        portal = new_test_user(self.env, login='brian_ux_portal', groups='base.group_portal', name='Portal')
        with self.assertRaises(AccessError):
            self.env['brian.conversacion'].with_user(portal).estado_panel()
        self.assertNotIn('consumo', self.pastillas(self.otro), 'El consumo es solo de administradores')

    # -- Avatar: clases preparadas, sin dibujo --------------------------------------------------

    def test_clases_del_avatar_documentadas(self):
        """La ronda del avatar solo tiene que dibujar: las clases ya existen en SCSS, JS y plantilla."""
        from pathlib import Path
        raiz = Path(__file__).resolve().parent.parent / 'static' / 'src'
        scss = (raiz / 'scss' / 'brian_panel.scss').read_text()
        js = (raiz / 'js' / 'brian_panel.js').read_text()
        xml = (raiz / 'xml' / 'brian_panel.xml').read_text()
        for estado in ('esperando', 'trabajando', 'te_necesito', 'termine'):
            self.assertIn(f'.o_brian_avatar_{estado}', scss)
            self.assertIn(f'"{estado}"', js)
        self.assertIn('ESTADOS_AVATAR', js)
        self.assertIn('clasesPanel', xml)
        self.assertIn('claseAvatar', js)
        self.assertIn('data-avatar', xml)
        # La tarjeta dice Permitir / Rechazar y no existe «Siempre».
        self.assertIn('Permitir', xml)
        self.assertIn('Rechazar', xml)
        self.assertFalse(re.search(r'\bSiempre\b', xml))
        self.assertIn('o_brian_tarjeta_detalle', xml)
        self.assertIn('dcasa_brian/pasos', js)
        self.assertIn('estado_panel', js)
