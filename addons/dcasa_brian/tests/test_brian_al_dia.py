"""Brian al día (2026-11-06): las pantallas propias, Sofía, clientes repetidos, el origen de una venta y Meta.

Todo de lectura salvo «Revisar ahora» de Sofía (construcción: deja propuestas, no le escribe a nadie). Nada escribe
dinero. Las de módulos que ``dcasa_brian`` no exige (Sofía, Meta) se saltan si no están instalados (en el CI, todo).
"""
import json
import os
from unittest.mock import patch

from odoo import Command
from odoo.addons.dcasa_brian.models import herramientas_pantallas
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

    def test_propuestas_de_sofia_cada_vendedora_las_suyas_y_gerencia_todas(self):
        if not self.instalado('dcasa_sofia'):
            self.skipTest('dcasa_sofia no está instalado')
        self.env['dcasa.sofia.propuesta'].sudo().search([]).unlink()
        mia = self._propuesta(self.vendedora)
        self._propuesta(self.otra, 'escribir')
        self._propuesta(self.vendedora, 'guardar_datos', datos={
            'campos': {'nombre': 'Carla Pérez', 'correo': 'carla.perez@example.com', 'cumple': ''}})
        suyas = self.datos(self.vendedora, 'propuestas_de_sofia')
        self.assertEqual(suyas['pendientes'], 2, 'la de la otra vendedora no se ve')
        self.assertIn('alcance', suyas)
        self.assertNotIn('para', suyas['propuestas'][0])
        self.assertIn(mia.partner_id.name, [p['cliente'] for p in suyas['propuestas']])
        datos = next(p for p in suyas['propuestas'] if p['que'] == 'Guardar sus datos')
        self.assertEqual(datos['dio'], ['su nombre', 'su correo'])
        self.assertNotIn('carla.perez@example.com', json.dumps(suyas, ensure_ascii=False),
                         'dice qué dato dio, no el dato')
        self.assertEqual(suyas['abrir']['accion'], self.env.ref('dcasa_sofia.accion_sofia').id)
        solo_datos = self.datos(self.vendedora, 'propuestas_de_sofia', {'grupo': 'datos'})
        self.assertEqual([p['que'] for p in solo_datos['propuestas']], ['Guardar sus datos'])
        todas = self.datos(self.gerencia, 'propuestas_de_sofia')
        self.assertEqual(todas['pendientes'], 3)
        self.assertTrue(all(p.get('para') for p in todas['propuestas']))
        self.assertEqual(self.env['brian.herramientas']._todas()['propuestas_de_sofia']['texto_externo'], True)

    def test_revisar_con_sofia_deja_propuestas_y_no_escribe(self):
        if not self.instalado('dcasa_sofia'):
            self.skipTest('dcasa_sofia no está instalado')
        mensajes_antes = self.env['dcasa.mensaje'].sudo().search_count([])
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
