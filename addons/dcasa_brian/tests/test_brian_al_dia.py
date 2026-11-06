"""Brian al día (2026-11-06): las pantallas propias, Sofía, clientes repetidos, el origen de una venta y Meta.

Todo de lectura salvo «Revisar ahora» de Sofía (construcción: deja propuestas, no le escribe a nadie). Nada escribe
dinero. Las de módulos que ``dcasa_brian`` no exige (Sofía, Meta) se saltan si no están instalados (en el CI, todo).
"""
import json
import os
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

from psycopg2.errors import LockNotAvailable

from odoo import Command, fields
from odoo.addons.dcasa_brian.models import herramientas_asistentes, herramientas_pantallas
from odoo.addons.dcasa_brian.models.conversacion import _abrir
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

NUEVAS_DE_LECTURA = ('abrir_pantalla', 'propuestas_de_sofia', 'clientes_repetidos', 'estado_de_meta')


@tagged('post_install', '-at_install')
class TestBrianAlDia(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Usuarios = cls.env['res.users'].with_context(no_reset_password=True)

        def usuario(login, *grupos):
            return Usuarios.create({'name': login.replace('_', ' ').title(), 'login': login, 'group_ids': [
                Command.set([cls.env.ref(g).id for g in ('base.group_user', *grupos)])]})

        cls.vendedora = usuario('brian_ad_vendedora', 'dcasa_base.group_vendedora')
        cls.otra = usuario('brian_ad_otra', 'dcasa_base.group_vendedora')
        cls.gerencia = usuario('brian_ad_gerencia', 'dcasa_base.group_gerencia')
        cls.jefe = usuario('brian_ad_jefe', 'dcasa_base.group_gerencia', 'base.group_system')

    def ejecutar(self, usuario, nombre, argumentos=None):
        return self.env['brian.herramientas'].with_user(usuario).ejecutar(nombre, argumentos or {})

    def datos(self, usuario, nombre, argumentos=None):
        respuesta = self.ejecutar(usuario, nombre, argumentos)
        self.assertTrue(respuesta.get('ok'), respuesta)
        return respuesta['datos']

    def instalado(self, modulo):
        return self.env['ir.module.module']._get(modulo).state == 'installed'

    # ------------------------------------------------------------------
    # Contrato
    # ------------------------------------------------------------------

    def test_las_nuevas_son_de_lectura_menos_revisar_con_sofia(self):
        todas = self.env['brian.herramientas']._todas()
        for nombre in NUEVAS_DE_LECTURA:
            self.assertEqual(todas[nombre]['nivel'], 'lectura', nombre)
        self.assertEqual(todas['revisar_con_sofia']['nivel'], 'construccion')

    def test_una_vendedora_no_ve_lo_de_gerencia(self):
        nombres = {e['name'] for e in self.env['brian.herramientas'].with_user(self.vendedora).catalogo()}
        self.assertIn('abrir_pantalla', nombres)
        self.assertIn('propuestas_de_sofia', nombres)
        for de_gerencia in ('clientes_repetidos', 'estado_de_meta'):
            self.assertNotIn(de_gerencia, nombres)
            self.assertFalse(self.ejecutar(self.vendedora, de_gerencia)['ok'])
        de_gerencia = {e['name'] for e in self.env['brian.herramientas'].with_user(self.gerencia).catalogo()}
        self.assertTrue({'clientes_repetidos', 'estado_de_meta'} <= de_gerencia)

    def test_el_prompt_conoce_a_juan_sofia_y_camila(self):
        fijo = self.env['brian.conversacion']._sistema_fijo()
        for nombre in ('Juan', 'Sofía', 'Camila', 'abrir_pantalla', 'buscar_en_guia'):
            self.assertIn(nombre, fijo)
        ayuda = self.datos(self.vendedora, 'ayuda')
        self.assertIn('Sofía', ayuda['tambien'])

    # ------------------------------------------------------------------
    # Abrir pantallas propias
    # ------------------------------------------------------------------

    def test_abrir_pantalla_da_la_accion_y_la_ruta_del_menu(self):
        datos = self.datos(self.gerencia, 'abrir_pantalla', {'pantalla': 'valor_del_inventario'})
        menu = self.env.ref('dcasa_interfaz.menu_dcasa_valor_inventario')
        self.assertEqual(datos['abrir']['accion'], menu.action.id)
        self.assertIn('Valor del inventario', datos['donde'])
        # El destino pasa el filtro del panel (solo ids de acción enteros).
        self.assertEqual(_abrir(datos)['accion'], menu.action.id)

    def test_abrir_pantalla_respeta_los_permisos_del_menu(self):
        respuesta = self.ejecutar(self.vendedora, 'abrir_pantalla', {'pantalla': 'valor_del_inventario'})
        self.assertFalse(respuesta['ok'])
        self.assertIn('No tienes permiso', respuesta['error'])
        self.assertTrue(self.ejecutar(self.vendedora, 'abrir_pantalla', {'pantalla': 'inicio'})['ok'])
        self.assertIn('Faltan datos', self.ejecutar(self.vendedora, 'abrir_pantalla', {})['error'])

    def test_abrir_pantalla_de_un_modulo_que_no_esta(self):
        with patch.dict(herramientas_pantallas.PANTALLAS, {'sofia': ('dcasa_no_instalado.menu_sofia', 'Sofía')}):
            respuesta = self.ejecutar(self.gerencia, 'abrir_pantalla', {'pantalla': 'sofia'})
        self.assertFalse(respuesta['ok'])
        self.assertIn('no está instalada', respuesta['error'])

    def test_abrir_pantalla_nunca_una_accion_de_servidor_ni_un_enlace(self):
        """Revisión adversarial (2026-11-06): solo se abren listas y pantallas propias, como en la Guía."""
        servidor = self.env['ir.actions.server'].create({
            'name': 'Brianzeta servidor', 'model_id': self.env.ref('base.model_res_partner').id, 'state': 'code',
            'code': 'pass'})
        enlace = self.env['ir.actions.act_url'].create({'name': 'Brianzeta enlace', 'url': 'https://example.com'})
        for accion in (servidor, enlace):
            menu = self.env['ir.ui.menu'].create({'name': f'Brianzeta {accion._name}',
                                                   'action': f'{accion._name},{accion.id}'})
            xmlid = f'dcasa_brian.brianzeta_menu_{accion.id}_{accion._table}'
            self.env['ir.model.data'].create({'module': 'dcasa_brian', 'name': xmlid.split('.')[1],
                                              'model': 'ir.ui.menu', 'res_id': menu.id})
            with self.subTest(accion=accion._name), \
                    patch.dict(herramientas_pantallas.PANTALLAS, {'sofia': (xmlid, 'Prueba')}):
                respuesta = self.ejecutar(self.jefe, 'abrir_pantalla', {'pantalla': 'sofia'})
                self.assertFalse(respuesta['ok'], respuesta)
                self.assertIn('no abre ninguna pantalla', respuesta['error'])

    def test_el_panel_solo_acepta_ids_de_accion_enteros(self):
        self.assertEqual(_abrir({'abrir': {'accion': 7, 'titulo': 'Sofía'}}), {'accion': 7, 'titulo': 'Sofía'})
        for malo in (True, '7', 0, -3, 'javascript:alert(1)', {'id': 7}):
            self.assertIsNone(_abrir({'abrir': {'accion': malo, 'titulo': 'x'}}), malo)
        # Un destino de siempre no cambia.
        self.assertEqual(_abrir({'abrir': {'modelo': 'res.partner', 'titulo': 'Contactos'}})['modelo'], 'res.partner')

    # ------------------------------------------------------------------
    # Sofía
    # ------------------------------------------------------------------

    def _propuesta(self, usuario, tipo='contestar', **valores):
        cliente = self.env['res.partner'].create({'name': f'Brianzeta Cliente {tipo} {usuario.login}'})
        return self.env['dcasa.sofia.propuesta'].sudo().create({
            'clave': f'brian-al-dia:{tipo}:{usuario.id}:{cliente.id}', 'tipo': tipo, 'prioridad': 3,
            'usuario_id': usuario.id, 'partner_id': cliente.id, 'titulo': f'{tipo} de prueba',
            'motivo': 'Te escribió hoy.', **valores})

    def _guarda_sus_datos_de_verdad(self):
        """Una propuesta «Guarda sus datos» hecha por Sofía de verdad: el cliente escribió su nombre, su correo y su
        cumpleaños en el chat y Sofía revisó. Su título los lleva escritos («Guarda sus datos: <nombre> · …»)."""
        ahora = fields.Datetime.now()
        cliente = self.env['res.partner'].create({'name': '🌻', 'phone': '+507 6000-9931'})
        conversacion = self.env['dcasa.conversacion'].sudo().create({
            'canal': 'whatsapp_qr', 'id_externo': '50760009931', 'partner_id': cliente.id, 'estado': 'humano',
            'ultimo_mensaje_cliente': ahora - timedelta(hours=2), 'ultimo_mensaje_autor': 'cliente',
            'ultima_actividad': ahora - timedelta(hours=2), 'asignada_a': self.vendedora.id})
        conversacion.oportunidad_id = self.env['crm.lead'].sudo().with_context(dcasa_auto=True).create({
            'name': 'WhatsApp (QR): colchón queen', 'type': 'opportunity', 'partner_id': cliente.id,
            'user_id': self.vendedora.id, 'dcasa_temperatura': '2'})
        self.env['dcasa.mensaje'].sudo().create({
            'conversacion_id': conversacion.id, 'id_mensaje': 'brian-al-dia.datos', 'tipo': 'mensaje',
            'direccion': 'entrante', 'autor': 'cliente', 'estado_envio': 'recibido', 'ts': ahora - timedelta(hours=2),
            'texto': 'Me llamo Brianzeta Carla Pérez, mi correo es carla.brianzeta@example.com y cumplo el 5 de mayo'})
        self.env['dcasa.sofia'].sudo()._analizar('manana')
        propuesta = self.env['dcasa.sofia.propuesta'].sudo().search(
            [('tipo', '=', 'guardar_datos'), ('partner_id', '=', cliente.id), ('estado', '=', 'pendiente')])
        self.assertEqual(len(propuesta), 1, 'Sofía debió proponer «Guarda sus datos»')
        self.assertIn('carla.brianzeta@example.com', propuesta.titulo, 'el título de Sofía lleva los datos')
        return propuesta

    def test_propuestas_de_sofia_cada_vendedora_las_suyas_y_gerencia_todas(self):
        if not self.instalado('dcasa_sofia'):
            self.skipTest('dcasa_sofia no está instalado')
        self.env['dcasa.sofia.propuesta'].sudo().search([]).unlink()
        mia = self._propuesta(self.vendedora)
        self._propuesta(self.otra, 'escribir')
        suyas = self.datos(self.vendedora, 'propuestas_de_sofia')
        self.assertEqual(suyas['pendientes'], 1, 'la de la otra vendedora no se ve')
        self.assertIn('alcance', suyas)
        self.assertNotIn('para', suyas['propuestas'][0])
        self.assertEqual([p['cliente'] for p in suyas['propuestas']], [mia.partner_id.name])
        self.assertEqual(suyas['abrir']['accion'], self.env.ref('dcasa_sofia.accion_sofia').id)
        todas = self.datos(self.gerencia, 'propuestas_de_sofia')
        self.assertEqual(todas['pendientes'], 2)
        self.assertTrue(all(p.get('para') for p in todas['propuestas']))
        self.assertEqual(self.env['brian.herramientas']._todas()['propuestas_de_sofia']['texto_externo'], True)

    def test_guarda_sus_datos_dice_que_dato_dio_y_nunca_el_dato(self):
        """Revisión adversarial (2026-11-06): el título de Sofía lleva el nombre, el correo y el cumpleaños; ni eso
        llega al modelo ni al registro de acciones (que no se borra)."""
        if not self.instalado('dcasa_sofia'):
            self.skipTest('dcasa_sofia no está instalado')
        self._guarda_sus_datos_de_verdad()
        respuesta = self.ejecutar(self.vendedora, 'propuestas_de_sofia', {'grupo': 'datos'})
        self.assertTrue(respuesta['ok'], respuesta)
        fila = next(p for p in respuesta['datos']['propuestas'] if p['que'] == 'Guardar sus datos')
        self.assertEqual(fila['propuesta'], 'Guarda sus datos')
        self.assertIn('su correo', fila['dio'])
        accion = self.env['brian.accion'].sudo().search([('herramienta', '=', 'propuestas_de_sofia')], limit=1)
        for texto in (json.dumps(respuesta, ensure_ascii=False), accion.resultado or ''):
            for dato in ('carla.brianzeta@example.com', 'Brianzeta Carla', 'Carla Pérez', '05/05', '5 de mayo'):
                self.assertNotIn(dato, texto)

    def test_revisar_con_sofia_deja_propuestas_y_no_escribe(self):
        if not self.instalado('dcasa_sofia'):
            self.skipTest('dcasa_sofia no está instalado')
        mensajes_antes = self.env['dcasa.mensaje'].sudo().search_count([])
        # El botón de la pantalla arma la pantalla entera: Brian llama directo a la revisión.
        with patch.object(type(self.env['dcasa.sofia']), 'analizar',
                          side_effect=AssertionError('Brian no arma la pantalla de Sofía')):
            datos = self.datos(self.vendedora, 'revisar_con_sofia')
        self.assertIn('Sofía', datos['mensaje'])
        self.assertIn('pendientes', datos)
        self.assertEqual(self.env['dcasa.mensaje'].sudo().search_count([]), mensajes_antes,
                         'revisar no le escribe a ningún cliente')
        corrida = self.env['dcasa.sofia.corrida'].sudo().search([], limit=1)
        self.assertEqual((corrida.origen, corrida.usuario_id), ('boton', self.vendedora))
        accion = self.env['brian.accion'].sudo().search([('herramienta', '=', 'revisar_con_sofia')], limit=1)
        self.assertEqual(accion.estado, 'hecha', 'queda en el registro de acciones')
        # Otra vez enseguida: no vuelve a revisar (como el botón de la pantalla).
        otra = self.datos(self.vendedora, 'revisar_con_sofia')
        self.assertIn('acaba de revisar', otra['mensaje'])
        self.assertEqual(self.env['dcasa.sofia.corrida'].sudo().search([], limit=1), corrida)

    def test_revisar_con_sofia_cuentas_del_equipo_solo_para_gerencia(self):
        """Las cuentas de la revisión (del historial, que solo ve Gerencia) no le llegan a una vendedora: ella recibe
        cuántas de las suyas dejó esa revisión."""
        if not self.instalado('dcasa_sofia'):
            self.skipTest('dcasa_sofia no está instalado')
        self._guarda_sus_datos_de_verdad()
        self.env['dcasa.sofia.corrida'].sudo().search([]).unlink()   # que el botón sí revise
        self.env['dcasa.sofia.propuesta'].sudo().search([]).unlink()
        suyo = self.datos(self.vendedora, 'revisar_con_sofia')
        self.assertNotIn('nuevas', suyo)
        self.assertNotIn('ya_no_hacian_falta', suyo)
        self.assertGreaterEqual(suyo['nuevas_para_ti'], 1, 'al menos «Guarda sus datos» es para ella')
        self.env['dcasa.sofia.corrida'].sudo().search([]).unlink()
        del_equipo = self.datos(self.gerencia, 'revisar_con_sofia')
        self.assertIn('nuevas', del_equipo)
        self.assertIn('ya_no_hacian_falta', del_equipo)

    def test_revisar_con_sofia_va_en_su_propia_transaccion(self):
        """Fuera de las pruebas, la revisión abre un cursor propio y corto (se confirma al salir): el candado de
        Sofía y las filas de sus propuestas no quedan tomadas durante todo el turno de Brian."""
        if not self.instalado('dcasa_sofia'):
            self.skipTest('dcasa_sofia no está instalado')
        usados = []

        @contextmanager
        def cursor_propio(*_args, **_kwargs):
            usados.append(True)
            yield self.env.cr   # en la prueba no se puede confirmar: el mismo cursor hace de «cursor propio»

        with patch.object(herramientas_asistentes, 'transaccion_propia', return_value=True), \
                patch.object(self.env.registry, 'cursor', cursor_propio):
            datos = self.datos(self.vendedora, 'revisar_con_sofia')
        self.assertEqual(usados, [True])
        self.assertIn('Sofía', datos['mensaje'])

    def test_revisar_con_sofia_con_una_propuesta_tomada_lo_dice(self):
        if not self.instalado('dcasa_sofia'):
            self.skipTest('dcasa_sofia no está instalado')
        with patch.object(type(self.env['dcasa.sofia']), '_analizar', side_effect=LockNotAvailable()):
            respuesta = self.ejecutar(self.vendedora, 'revisar_con_sofia')
        self.assertFalse(respuesta['ok'])
        self.assertIn('Sofía está ocupada', respuesta['error'])

    def test_sin_sofia_lo_dice(self):
        if 'dcasa.sofia.propuesta' in self.env:
            self.skipTest('Sofía está instalada')
        respuesta = self.ejecutar(self.vendedora, 'propuestas_de_sofia')
        self.assertFalse(respuesta['ok'])
        self.assertIn('no está instalada', respuesta['error'])

    # ------------------------------------------------------------------
    # Clientes repetidos
    # ------------------------------------------------------------------

    def test_clientes_repetidos_lista_los_que_comparten_un_dato_y_no_fusiona(self):
        Partner = self.env['res.partner'].with_context(dcasa_sin_duplicados=True)
        Partner.create({'name': 'Brianzeta Repetida Uno', 'email': 'repetida.brian@example.com'})
        Partner.create({'name': 'Brianzeta Repetida Dos', 'email': 'Repetida.Brian@example.com'})
        datos = self.datos(self.gerencia, 'clientes_repetidos', {'tipo': 'correo'})
        fila = next(f for f in datos['repetidos'] if f['dato'] == 'repetida.brian@example.com')
        self.assertEqual(fila['fichas'], 2)
        self.assertIn('Brianzeta Repetida Uno', fila['quienes'])
        self.assertIn('Posibles duplicados', datos['como_unirlos'])
        self.assertEqual(datos['abrir']['modelo'], 'dcasa.contacto.duplicado')
        self.assertEqual(Partner.search_count([('name', 'like', 'Brianzeta Repetida')]), 2, 'Brian no fusiona')
        self.assertFalse(self.ejecutar(self.gerencia, 'clientes_repetidos', {'tipo': 'cedula'})['ok'])

    # ------------------------------------------------------------------
    # Origen de una venta (Chatbot, Web, Vendedora)
    # ------------------------------------------------------------------

    def test_buscar_ventas_por_origen_y_ver_venta_lo_dice(self):
        producto = self.env['product.product'].create({'name': 'Brianzeta Mesa Origen', 'list_price': 100.0})
        cliente = self.env['res.partner'].create({'name': 'Brianzeta Cliente Origen'})
        lineas = [Command.create({'product_id': producto.id, 'product_uom_qty': 1})]
        de_la_tienda = self.env['sale.order'].create({'partner_id': cliente.id, 'order_line': lineas})
        de_la_web = self.env['sale.order'].create({'partner_id': cliente.id, 'order_line': lineas,
                                                   'website_id': self.env['website'].search([], limit=1).id})
        web = self.datos(self.gerencia, 'buscar_ventas', {'texto': 'Brianzeta Cliente Origen', 'origen': 'web'})
        self.assertEqual([v['numero'] for v in web['ventas']], [de_la_web.name])
        self.assertEqual(web['ventas'][0]['origen'], 'Web')
        tienda = self.datos(self.gerencia, 'buscar_ventas', {'texto': 'Brianzeta Cliente Origen',
                                                              'origen': 'vendedora'})
        self.assertEqual([v['numero'] for v in tienda['ventas']], [de_la_tienda.name])
        self.assertEqual(self.datos(self.gerencia, 'ver_venta', {'venta': de_la_web.name})['origen'], 'Web')
        self.assertFalse(self.ejecutar(self.gerencia, 'buscar_ventas', {'origen': 'tiktok'})['ok'])

    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------

    def test_estado_de_meta_nunca_muestra_la_clave(self):
        with patch.dict(os.environ, {'META_CAPI_TOKEN': 'EAAclave-secreta-de-meta-123'}):
            datos = self.datos(self.gerencia, 'estado_de_meta')
        texto = json.dumps(datos, ensure_ascii=False)
        self.assertNotIn('EAAclave-secreta-de-meta-123', texto)
        if self.instalado('dcasa_meta_eventos'):
            eventos = datos['pixel_y_ventas']
            self.assertEqual(eventos['clave_de_meta'], 'cargada')
            self.assertEqual(eventos['pixel'], 'apagado', 'de fábrica, todo apagado')
            self.assertEqual(eventos['ventas_de_la_web'], 'apagado')
        else:
            self.assertFalse(datos['pixel_y_ventas']['instalado'])
        if self.instalado('dcasa_meta_catalogo'):
            self.assertTrue(datos['catalogo']['instalado'])
            self.assertFalse(datos['catalogo']['encendido'], 'de fábrica, apagado')
        else:
            self.assertFalse(datos['catalogo']['instalado'])
        self.assertIn('no enciende ni apaga', datos['nota'])

    def test_estado_de_meta_dice_la_fecha_en_hora_de_panama(self):
        """Revisión adversarial (2026-11-06): un error de las 03:00 UTC fue a las 10 p. m. del día antes en Panamá."""
        if not self.instalado('dcasa_meta_eventos'):
            self.skipTest('dcasa_meta_eventos no está instalado')
        evento = self.env['dcasa.meta.evento'].sudo().create({
            'event_name': 'Purchase', 'event_id': 'brianzeta-fecha', 'event_time': fields.Datetime.now(),
            'estado': 'error', 'ultimo_error': 'Meta dijo que no'})
        self.env.flush_all()
        self.env.cr.execute("UPDATE dcasa_meta_evento SET create_date = '2026-11-06 03:00:00' WHERE id = %s",
                            [evento.id])
        evento.invalidate_recordset(['create_date'])
        datos = self.datos(self.gerencia, 'estado_de_meta')
        self.assertEqual(datos['pixel_y_ventas']['ultimo_error']['cuando'], '05/11/2026 22:00')
