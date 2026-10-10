"""La API de la pantalla «Conversaciones» (docs/JUAN_PANEL.md): lista, hilo, no leídos, respuestas y ficha."""
import logging
import os
import time
from datetime import timedelta
from unittest.mock import MagicMock, patch

import requests

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.service.model import call_kw
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from .common import JuanCase, respuesta_http

PIN = '482913'
_logger = logging.getLogger(__name__)


class PanelCase(JuanCase):

    def setUp(self):
        super().setUp()
        self.panel = self.Conversacion.with_user(self.vendedora)
        self.ahora = fields.Datetime.now()

    def cliente(self, n, texto=None, **kw):
        """Una conversación de un cliente distinto; la ``n`` mayor es la más reciente."""
        kw.setdefault('ts', self.ahora - timedelta(minutes=100 - n))
        kw.setdefault('nombre', f'Zzcliente {n}')
        return self.conversacion(texto or f'Mensaje {n}', id_externo=f'507612{n:05d}', **kw)

    def ids(self, resultado):
        return [c['id'] for c in resultado['conversaciones']]


@tagged('post_install', '-at_install')
class TestPermisosDelPanel(PanelCase):

    def test_solo_el_equipo_de_ventas_usa_la_api_del_panel_tambien_por_rpc(self):
        conv = self.cliente(1)
        llamadas = [
            ('lista', [{}]), ('hilo', [conv.id]), ('ficha', [conv.id]), ('marcar_leida', [[conv.id]]),
            ('enviar_respuesta', [conv.id, 'Hola']), ('tomar', [conv.id]), ('devolver', [conv.id]),
            ('cerrar', [conv.id]), ('asignar', [conv.id, self.vendedora.id]), ('poner_etiquetas', [conv.id, []]),
            ('cancelar_seguimiento', [conv.id]),
            ('agregar_nota', [conv.id, 'Una nota']),
        ]
        for usuario in (self.interno, self.portal):
            for metodo, args in llamadas:
                with self.subTest(usuario=usuario.login, metodo=metodo), self.assertRaises(AccessError):
                    call_kw(self.env(user=usuario)['dcasa.conversacion'], metodo, list(args), {})
        self.assertEqual((conv.estado, conv.asignada_a), ('bot', self.env['res.users']))
        self.assertFalse(conv.mensaje_ids.filtered(lambda m: m.tipo != 'mensaje'))

    def test_lo_interno_de_la_pantalla_es_privado_por_rpc(self):
        conv = self.cliente(1)
        for usuario in (self.vendedora, self.gerente, self.interno, self.portal):
            for metodo, args in (('_tomar', [[conv.id], usuario.id]), ('_aviso', [[conv.id], 'x']),
                                 ('_devolver', [[conv.id], usuario.id]), ('_cerrar', [[conv.id], usuario.id]),
                                 ('_notificar_panel', [[conv.id], 'estado']), ('_resumen_panel', [[conv.id]]),
                                 ('_para_panel', [conv.id])):
                with self.subTest(usuario=usuario.login, metodo=metodo), self.assertRaises(AccessError):
                    call_kw(self.env(user=usuario)['dcasa.conversacion'], metodo, list(args), {})
        with self.assertRaises(AccessError):
            call_kw(self.env(user=self.vendedora)['dcasa.mensaje'], '_crear_interno', [conv.id, 'aviso', 'x'], {})

    def test_una_conversacion_que_no_existe_es_un_error_claro(self):
        for malo in (999999999, 0, -1, 'abc', None, True, 1.5):
            with self.subTest(malo=malo), self.assertRaises(UserError):
                self.panel.hilo(malo)


@tagged('post_install', '-at_install')
class TestLista(PanelCase):

    def test_las_mas_recientes_primero_y_de_a_poco(self):
        convs = [self.cliente(n) for n in range(1, 6)]
        pagina1 = self.panel.lista(limite=2)
        self.assertEqual(self.ids(pagina1), [convs[4].id, convs[3].id])
        self.assertEqual((pagina1['total'], pagina1['hay_mas']), (5, True))
        pagina3 = self.panel.lista(offset=4, limite=2)
        self.assertEqual(self.ids(pagina3), [convs[0].id])
        self.assertFalse(pagina3['hay_mas'])

    def test_una_fila_trae_lo_que_la_pantalla_pinta(self):
        conv = self.cliente(1, 'Quiero una cama')
        etiqueta = self.env['dcasa.conversacion.etiqueta'].create({'name': 'Zzfila', 'color': 3})
        conv.etiqueta_ids = etiqueta
        conv.asignada_a = self.gerente
        fila = self.panel.lista()['conversaciones'][0]
        self.assertEqual(fila['id'], conv.id)
        self.assertEqual((fila['nombre'], fila['iniciales']), ('Zzcliente 1', 'Z1'))
        self.assertEqual((fila['canal'], fila['canal_nombre']), ('whatsapp_qr', 'WhatsApp (QR)'))
        self.assertEqual((fila['estado'], fila['bot_atiende'], fila['necesita_atencion']), ('bot', True, False))
        self.assertEqual(fila['ultimo_mensaje'], {'texto': 'Quiero una cama', 'autor': 'cliente'})
        self.assertEqual(fila['etiquetas'], [{'id': etiqueta.id, 'nombre': 'Zzfila', 'color': 3}])
        self.assertEqual(fila['asignada_a'], {'id': self.gerente.id, 'nombre': 'Gerente Prueba'})
        self.assertEqual(fila['sin_leer'], 1)
        self.assertRegex(fila['ultima_actividad'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')
        self.assertEqual(fila['foto'], f"/web/image/res.partner/{conv.partner_id.id}/avatar_128")
        self.assertIsNone(fila['pausada_hasta'])

    def test_una_conversacion_con_una_vendedora_que_espera_respuesta_necesita_atencion(self):
        conv = self.cliente(1)
        self.assertFalse(self.panel.lista()['conversaciones'][0]['necesita_atencion'])
        conv.with_user(self.vendedora).action_atender()
        self.registrar('¿Me contestas?', id_externo=conv.id_externo)
        fila = self.panel.lista()['conversaciones'][0]
        self.assertEqual((fila['estado'], fila['bot_atiende'], fila['necesita_atencion']), ('humano', False, True))
        self.assertTrue(fila['pausada_hasta'])

    def test_filtros(self):
        a, b, c = self.cliente(1), self.cliente(2, canal='telegram'), self.cliente(3)
        etiqueta = self.env['dcasa.conversacion.etiqueta'].create({'name': 'Zzfiltro'})
        a.etiqueta_ids = etiqueta
        b.write({'estado': 'humano', 'asignada_a': self.vendedora.id})
        b.write({'ultimo_mensaje_autor': 'cliente'})
        c.estado = 'cerrada'
        c.oportunidad_id = self.env['crm.lead'].create({'name': 'Zzoportunidad'})

        def con(**filtros):
            return set(self.ids(self.panel.lista(filtros)))

        self.assertEqual(con(), {a.id, b.id, c.id})
        self.assertEqual(con(canal='telegram'), {b.id})
        self.assertEqual(con(estado='bot'), {a.id})
        self.assertEqual(con(estado='humano'), {b.id})
        self.assertEqual(con(estado='cerrada'), {c.id})
        self.assertEqual(con(estado='necesita_atencion'), {b.id})
        self.assertEqual(con(etiqueta_id=etiqueta.id), {a.id})
        self.assertEqual(con(asignada_a_mi=True), {b.id})
        self.assertEqual(con(con_oportunidad=True), {c.id})
        self.assertEqual(con(canal='whatsapp_qr', estado='cerrada'), {c.id})
        self.assertEqual(con(canal='telegram', estado='cerrada'), set(), 'Los filtros se suman')
        self.assertEqual(con(asignada_a_mi=False, etiqueta_id=None, canal=''), {a.id, b.id, c.id})

    def test_filtros_invalidos(self):
        for filtros in ({'nada': 1}, {'canal': 'fax'}, {'estado': 'dormida'}, {'etiqueta_id': 'x'},
                        {'etiqueta_id': True}, 'canal=telegram', ['canal']):
            with self.subTest(filtros=filtros), self.assertRaises(UserError):
                self.panel.lista(filtros)

    def test_limite_y_desplazamiento_validos(self):
        for kw in ({'limite': 0}, {'limite': 101}, {'limite': True}, {'limite': '30'}, {'limite': 2.5},
                   {'offset': -1}, {'offset': '0'}, {'offset': None}):
            with self.subTest(**kw), self.assertRaises(UserError):
                self.panel.lista(**kw)
        self.assertEqual(self.panel.lista(limite=100)['conversaciones'], [])

    def test_busqueda_por_nombre_celular_y_texto(self):
        a = self.cliente(1, 'Busco un sofá azul', nombre='Marisol Zzbusca')
        b = self.cliente(2, 'Hola', nombre='Otra Persona')
        self.Mensaje._crear_interno(b, 'nota', 'Es amiga de la hija de doña Zzcarmela', self.vendedora)
        self.assertEqual(self.ids(self.panel.lista({'busqueda': 'zzbusca'})), [a.id], 'Por nombre, sin mayúsculas')
        self.assertEqual(self.ids(self.panel.lista({'busqueda': 'sofá azul'})), [a.id], 'Por lo que dijo')
        self.assertEqual(self.ids(self.panel.lista({'busqueda': 'zzcarmela'})), [b.id], 'También en las notas')
        self.assertEqual(self.ids(self.panel.lista({'busqueda': '50761200002'})), [b.id], 'Por celular')
        self.assertEqual(self.ids(self.panel.lista({'busqueda': '61200002'})), [b.id], 'Por celular, parcial')
        self.assertEqual(self.panel.lista({'busqueda': 'zzninguna'})['total'], 0)
        self.assertEqual(self.panel.lista({'busqueda': '   '})['total'], 2, 'Una búsqueda vacía no filtra')

    def test_la_busqueda_no_se_deja_enganar(self):
        self.cliente(1)
        for texto in ("'; DROP TABLE dcasa_conversacion; --", '%', '_', '\\', 'x' * 5000):
            with self.subTest(texto=texto[:20]):
                self.panel.lista({'busqueda': texto})
        self.assertEqual(self.panel.lista()['total'], 1)


@tagged('post_install', '-at_install')
class TestNoLeidos(PanelCase):

    def setUp(self):
        super().setUp()
        self.conv = self.cliente(1, 'Hola')
        self.otra = self.Conversacion.with_user(self.gerente)

    def sin_leer(self, quien=None, conv=None):
        panel = self.panel if quien is None else quien
        lista = panel.lista()
        fila = next(c for c in lista['conversaciones'] if c['id'] == (conv or self.conv).id)
        return fila['sin_leer'], lista['sin_leer_total']

    def test_cada_mensaje_del_cliente_es_uno_sin_leer(self):
        self.registrar('Otra cosa', id_externo=self.conv.id_externo)
        self.assertEqual(self.sin_leer(), (2, 1))

    def test_lo_que_dicen_el_asistente_las_vendedoras_y_el_sistema_no_cuenta(self):
        self.registrar('Te ayudo', id_externo=self.conv.id_externo, autor='bot')
        self.registrar('Soy Ana', id_externo=self.conv.id_externo, autor='vendedora')
        self.Mensaje._crear_interno(self.conv, 'nota', 'Nota', self.vendedora)
        self.Mensaje._crear_interno(self.conv, 'aviso', 'Aviso')
        self.assertEqual(self.sin_leer()[0], 1)

    def test_marcar_leida_limpia_el_conteo_solo_para_quien_la_marca(self):
        self.assertEqual(self.panel.marcar_leida(self.conv.id), {'marcadas': [self.conv.id]})
        self.assertEqual(self.sin_leer(), (0, 0))
        self.assertEqual(self.sin_leer(self.otra), (1, 1), 'Cada persona lleva su propia lectura')

    def test_un_mensaje_nuevo_vuelve_a_marcarla_sin_leer(self):
        self.panel.marcar_leida([self.conv.id])
        self.registrar('¿Sigues ahí?', id_externo=self.conv.id_externo)
        self.assertEqual(self.sin_leer(), (1, 1))

    def test_marcar_dos_veces_no_duplica_ni_retrocede(self):
        self.panel.marcar_leida(self.conv.id)
        self.panel.marcar_leida(self.conv.id)
        marcas = self.env['dcasa.conversacion.lectura'].sudo().search([('conversacion_id', '=', self.conv.id)])
        self.assertEqual(len(marcas), 1)
        ultimo = marcas.ultimo_leido_id
        self.assertEqual(ultimo, max(self.conv.mensaje_ids.ids))

    def test_el_filtro_sin_leer(self):
        otra = self.cliente(2)
        self.panel.marcar_leida(self.conv.id)
        self.assertEqual(self.ids(self.panel.lista({'sin_leer': True})), [otra.id])
        self.assertEqual(self.ids(self.otra.lista({'sin_leer': True})), [otra.id, self.conv.id])
        self.panel.marcar_leida([otra.id])
        self.assertEqual(self.panel.lista({'sin_leer': True})['total'], 0)

    def test_contestar_desde_el_panel_la_marca_como_leida(self):
        self.panel.enviar_respuesta(self.conv.id, 'Hola, claro que sí')
        self.assertEqual(self.sin_leer(), (0, 0))

    def test_marcar_varias_y_entradas_invalidas(self):
        otra = self.cliente(2)
        self.assertEqual(set(self.panel.marcar_leida([self.conv.id, otra.id])['marcadas']), {self.conv.id, otra.id})
        self.assertEqual(self.panel.marcar_leida([])['marcadas'], [])
        self.assertEqual(self.panel.marcar_leida([999999999])['marcadas'], [], 'Lo que no existe se ignora')
        for malo in ('1', None, [True], ['1'], list(range(1, 102)), {'a': 1}):
            with self.subTest(malo=malo), self.assertRaises(UserError):
                self.panel.marcar_leida(malo)

    def test_borrar_la_conversacion_borra_su_lectura(self):
        self.panel.marcar_leida(self.conv.id)
        self.conv.sudo().unlink()
        self.assertFalse(self.env['dcasa.conversacion.lectura'].sudo().search([('conversacion_id', '=', self.conv.id)]))


@tagged('post_install', '-at_install')
class TestHilo(PanelCase):

    def setUp(self):
        super().setUp()
        self.conv = self.cliente(1, 'Mensaje 0')
        for n in range(1, 7):
            self.registrar(f'Mensaje {n}', id_externo=self.conv.id_externo, ts=self.ahora - timedelta(minutes=60 - n))

    def textos(self, resultado):
        return [m['texto'] for m in resultado['mensajes']]

    def test_el_ultimo_tramo_y_luego_los_anteriores(self):
        tramo = self.panel.hilo(self.conv.id, limite=3)
        self.assertEqual(self.textos(tramo), ['Mensaje 4', 'Mensaje 5', 'Mensaje 6'], 'Del más viejo al más nuevo')
        self.assertTrue(tramo['hay_mas'])
        anterior = self.panel.hilo(self.conv.id, antes_de_id=tramo['primer_id'], limite=3)
        self.assertEqual(self.textos(anterior), ['Mensaje 1', 'Mensaje 2', 'Mensaje 3'])
        self.assertTrue(anterior['hay_mas'])
        primero = self.panel.hilo(self.conv.id, antes_de_id=anterior['primer_id'], limite=3)
        self.assertEqual(self.textos(primero), ['Mensaje 0'])
        self.assertFalse(primero['hay_mas'])

    def test_justo_al_limite_no_dice_que_hay_mas(self):
        self.assertFalse(self.panel.hilo(self.conv.id, limite=7)['hay_mas'])
        self.assertTrue(self.panel.hilo(self.conv.id, limite=6)['hay_mas'])

    def test_trae_la_cabecera_de_la_conversacion(self):
        tramo = self.panel.hilo(self.conv.id)
        self.assertEqual(tramo['conversacion']['id'], self.conv.id)
        self.assertEqual(tramo['conversacion']['sin_leer'], 7)

    def test_cada_mensaje_trae_lo_que_la_pantalla_pinta(self):
        self.panel.tomar(self.conv.id)
        nota = self.panel.agregar_nota(self.conv.id, 'Ojo con este cliente')['mensaje']
        self.assertEqual((nota['tipo'], nota['autor'], nota['direccion']), ('nota', 'vendedora', 'interna'))
        self.assertEqual(nota['usuario'], {'id': self.vendedora.id, 'nombre': 'Vendedora Prueba'})
        tramo = self.panel.hilo(self.conv.id, limite=100)
        tipos = [m['tipo'] for m in tramo['mensajes']]
        self.assertEqual(tipos.count('aviso'), 1)
        self.assertEqual(tipos.count('nota'), 1)
        primero = tramo['mensajes'][0]
        self.assertEqual(set(primero), {'id', 'tipo', 'autor', 'direccion', 'texto', 'ts', 'usuario', 'estado_envio',
                                        'error', 'origen', 'adjuntos', 'adjuntos_fallidos', 'menciones',
                                        'programado_para'})
        self.assertEqual((primero['tipo'], primero['autor'], primero['usuario']), ('mensaje', 'cliente', None))

    def test_los_adjuntos_traen_miniatura_si_son_imagen_y_la_marca_de_sensible(self):
        mensaje = self.conv.mensaje_ids[:1]
        foto = self.env['ir.attachment'].create({
            'name': 'foto.jpg', 'raw': b'\xff\xd8\xff\xe0', 'mimetype': 'image/jpeg', 'res_model': 'dcasa.mensaje',
            'res_id': mensaje.id, 'dcasa_sensible': True})
        pdf = self.env['ir.attachment'].create({
            'name': 'cotizacion.pdf', 'raw': b'%PDF-1.4', 'mimetype': 'application/pdf',
            'res_model': 'dcasa.mensaje', 'res_id': mensaje.id})
        mensaje.with_context(dcasa_mensaje_sistema=True).sudo().adjunto_ids = [Command.set([foto.id, pdf.id])]
        adjuntos = {a['nombre']: a for a in self.panel.hilo(self.conv.id, limite=100)['mensajes'][0]['adjuntos']}
        self.assertEqual(adjuntos['foto.jpg']['tipo'], 'imagen')
        self.assertTrue(adjuntos['foto.jpg']['sensible'])
        self.assertEqual(adjuntos['foto.jpg']['miniatura'], f'/web/image/{foto.id}?width=360&height=360')
        self.assertEqual(adjuntos['foto.jpg']['url'], f'/web/content/{foto.id}?download=true')
        self.assertEqual((adjuntos['cotizacion.pdf']['tipo'], adjuntos['cotizacion.pdf']['sensible']),
                         ('documento', False))
        self.assertIsNone(adjuntos['cotizacion.pdf']['miniatura'], 'Un documento no tiene miniatura')

    def test_argumentos_invalidos(self):
        for kw in ({'limite': 0}, {'limite': 101}, {'limite': True}, {'antes_de_id': 0}, {'antes_de_id': 'x'},
                   {'antes_de_id': True}):
            with self.subTest(**kw), self.assertRaises(UserError):
                self.panel.hilo(self.conv.id, **kw)


@tagged('post_install', '-at_install')
class TestEnviarRespuesta(PanelCase):

    def setUp(self):
        super().setUp()
        self.worker = self.configurar_worker()
        self.conv = self.cliente(1)

    def adjunto(self, usuario=None, **valores):
        base = {'name': 'foto.jpg', 'raw': b'\xff\xd8\xff\xe0', 'mimetype': 'image/jpeg',
                'res_model': 'dcasa.conversacion', 'res_id': 0}
        return self.env['ir.attachment'].with_user(usuario or self.vendedora).create({**base, **valores})

    def test_sale_por_el_worker_y_toma_la_conversacion(self):
        resultado = self.panel.enviar_respuesta(self.conv.id, '  Claro que sí, Karen  ')
        self.assertTrue(resultado['enviado'])
        self.assertEqual(resultado['mensaje']['texto'], 'Claro que sí, Karen')
        self.assertEqual((resultado['mensaje']['autor'], resultado['mensaje']['estado_envio']),
                         ('vendedora', 'enviado'))
        self.assertEqual(resultado['mensaje']['usuario']['id'], self.vendedora.id)
        self.assertEqual((self.conv.estado, self.conv.asignada_a), ('humano', self.vendedora))
        self.assertEqual(resultado['conversacion']['estado'], 'humano')
        (envio,) = [c for c in self.worker.call_args_list if c.args[1].endswith('/odoo/enviar')]
        self.assertEqual(envio.kwargs['json']['texto'], 'Claro que sí, Karen')

    def test_con_el_worker_caido_queda_por_enviar_y_no_se_pierde(self):
        self.worker.side_effect = requests.ConnectionError('sin red')
        resultado = self.panel.enviar_respuesta(self.conv.id, 'Te escribo ahora')
        self.assertFalse(resultado['enviado'])
        self.assertEqual(resultado['mensaje']['estado_envio'], 'por_enviar')
        self.worker.side_effect = None
        self.worker.return_value = respuesta_http({'ok': True, 'id_mensaje': 'wamid.worker.9'})
        pendiente = self.Mensaje.browse(resultado['mensaje']['id'])
        pendiente.with_context(dcasa_mensaje_sistema=True).sudo().ultimo_intento = self.ahora - timedelta(minutes=10)
        self.Mensaje._cron_reintentar_envios()
        self.assertEqual(self.Mensaje.browse(resultado['mensaje']['id']).estado_envio, 'enviado')

    def test_con_un_adjunto_propio(self):
        foto = self.adjunto()
        resultado = self.panel.enviar_respuesta(self.conv.id, None, [foto.id])
        (adjunto,) = resultado['mensaje']['adjuntos']
        self.assertEqual((adjunto['nombre'], adjunto['tipo']), ('foto.jpg', 'imagen'))
        self.assertEqual((foto.res_model, foto.public), ('dcasa.mensaje', False))
        (envio,) = [c for c in self.worker.call_args_list if c.args[1].endswith('/odoo/enviar')]
        self.assertEqual(len(envio.kwargs['json']['adjuntos']), 1)
        self.assertNotIn('texto', envio.kwargs['json'])

    def test_no_se_envia_nada_vacio_ni_demasiado(self):
        for kw in ({'texto': ''}, {'texto': '   '}, {'texto': None}, {'texto': 5}, {'texto': 'x' * 4001}):
            with self.subTest(**kw), self.assertRaises(UserError):
                self.panel.enviar_respuesta(self.conv.id, **kw)
        self.assertFalse(self.conv.mensaje_ids.filtered(lambda m: m.autor == 'vendedora'))

    def test_adjuntos_que_no_se_pueden_usar(self):
        ajeno = self.adjunto(usuario=self.gerente)
        de_otro_modelo = self.adjunto(res_model='res.partner', res_id=self.conv.partner_id.id)
        de_otra_conversacion = self.adjunto(res_id=self.cliente(2).id)
        enorme = self.adjunto(raw=b'x' * (10 * 1024 * 1024 + 1))
        casos = {'de otra persona': [ajeno.id], 'de otro modelo': [de_otro_modelo.id],
                 'de otra conversación': [de_otra_conversacion.id], 'enorme': [enorme.id],
                 'inexistente': [999999999], 'demasiados': [self.adjunto().id for _ in range(6)],
                 'basura': ['1'], 'no es lista': 7}
        for nombre, ids in casos.items():
            with self.subTest(nombre), self.assertRaises(UserError):
                self.panel.enviar_respuesta(self.conv.id, 'Mira', ids)
        self.assertFalse(self.conv.mensaje_ids.filtered(lambda m: m.autor == 'vendedora'))

    def test_el_mismo_camino_que_el_boton(self):
        self.worker.side_effect = [respuesta_http({'ok': True, 'id_mensaje': 'wamid.worker.a'}),
                                   respuesta_http({'ok': True, 'id_mensaje': 'wamid.worker.b'})]
        self.conv.borrador = 'Desde el formulario'
        self.conv.with_user(self.vendedora).action_enviar()
        self.panel.enviar_respuesta(self.conv.id, 'Desde el panel')
        mios = self.conv.mensaje_ids.filtered(lambda m: m.autor == 'vendedora')
        self.assertEqual(len(mios), 2)
        self.assertEqual(set(mios.mapped('estado_envio')), {'enviado'})
        self.assertEqual(set(mios.mapped('origen')), {'odoo'})


@tagged('post_install', '-at_install')
class TestMensajesProgramados(PanelCase):
    """Un mensaje se deja escrito para más tarde: no sale ni toma la conversación hasta su hora, y se puede cancelar."""

    def setUp(self):
        super().setUp()
        self.worker = self.configurar_worker()
        self.conv = self.cliente(1)

    def a_las(self, **delta):
        """Una hora futura como la manda el navegador: ISO en UTC con «Z»."""
        return (fields.Datetime.now() + timedelta(**delta)).isoformat() + 'Z'

    def programar(self, texto='Te escribo mañana', usuario=None, **delta):
        panel = self.panel if usuario is None else self.Conversacion.with_user(usuario)
        return panel.enviar_respuesta(self.conv.id, texto, None, self.a_las(**(delta or {'hours': 3})))

    def envios(self):
        return [c for c in self.worker.call_args_list if c.args[1].endswith('/odoo/enviar')]

    def vencer(self, mensaje):
        """Hace que su hora ya haya llegado."""
        mensaje.with_context(dcasa_mensaje_sistema=True).sudo().programado_para = fields.Datetime.now() - timedelta(
            minutes=1)

    def test_queda_programado_y_no_toca_la_conversacion(self):
        r = self.programar()
        self.assertEqual((r['enviado'], r['programado']), (False, True))
        self.assertEqual(r['mensaje']['estado_envio'], 'programado')
        self.assertTrue(r['mensaje']['programado_para'])
        self.assertEqual((self.conv.estado, self.conv.asignada_a), ('bot', self.env['res.users']),
                         'El asistente sigue atendiendo hasta que el mensaje salga')
        self.assertFalse(self.envios(), 'No sale nada antes de su hora')

    def test_la_hora_tiene_que_ser_futura_y_no_muy_lejana(self):
        pasada = (fields.Datetime.now() - timedelta(hours=1)).isoformat() + 'Z'
        casos = {'pasada': pasada, 'en medio minuto': self.a_las(seconds=30), 'a los 31 días': self.a_las(days=31),
                 'basura': 'mañana', 'número': 5}
        for nombre, hora in casos.items():
            with self.subTest(nombre), self.assertRaises(UserError):
                self.panel.enviar_respuesta(self.conv.id, 'Hola', None, hora)
        self.assertFalse(self.conv.mensaje_ids.filtered(lambda m: m.autor == 'vendedora'))

    def test_con_zona_horaria_se_convierte_a_utc(self):
        futura = fields.Datetime.now() + timedelta(hours=5)
        r = self.panel.enviar_respuesta(self.conv.id, 'Hola', None, futura.isoformat() + '-05:00')
        esperada = (futura + timedelta(hours=5)).replace(second=0, microsecond=0)
        self.assertEqual(self.Mensaje.browse(r['mensaje']['id']).programado_para, esperada)

    def test_nada_vacio_tampoco_programado(self):
        with self.assertRaises(UserError):
            self.panel.enviar_respuesta(self.conv.id, '  ', None, self.a_las(hours=2))

    def test_antes_de_su_hora_el_revisor_no_lo_manda(self):
        r = self.programar()
        self.assertEqual(self.Mensaje._cron_enviar_programados(), 0)
        self.assertEqual(self.Mensaje.browse(r['mensaje']['id']).estado_envio, 'programado')
        self.assertFalse(self.envios())

    def mios(self):
        return self.conv.mensaje_ids.filtered(lambda m: m.autor == 'vendedora' and m.tipo == 'mensaje')

    def test_a_su_hora_sale_por_el_canal_al_final_del_hilo_toma_la_conversacion_y_deja_aviso(self):
        r = self.programar('Ya está listo tu pedido')
        programado = self.Mensaje.browse(r['mensaje']['id'])
        self.recibir_del_cliente('¿Y mi pedido?')
        self.vencer(programado)
        self.worker.return_value = respuesta_http({'ok': True, 'id_mensaje': 'wamid.worker.prog'})
        self.assertEqual(self.Mensaje._cron_enviar_programados(), 1)
        self.assertFalse(programado.exists(), 'El programado se vuelve un mensaje normal, nuevo')
        (enviado,) = self.mios()
        self.assertEqual((enviado.estado_envio, enviado.texto, enviado.usuario_id),
                         ('enviado', 'Ya está listo tu pedido', self.vendedora))
        self.assertFalse(enviado.programado_para)
        self.assertGreater(enviado.id, max(self.conv.mensaje_ids.filtered(lambda m: m.autor == 'cliente').ids),
                           'Sale después de lo último que dijo el cliente, no donde se escribió')
        self.assertEqual((self.conv.estado, self.conv.asignada_a), ('humano', self.vendedora))
        (envio,) = self.envios()
        self.assertEqual(envio.kwargs['json']['texto'], 'Ya está listo tu pedido')
        avisos = self.conv.mensaje_ids.filtered(lambda m: m.tipo == 'aviso').mapped('texto')
        self.assertTrue(any('dejó programado' in (a or '') for a in avisos))
        self.assertEqual(self.Mensaje._cron_enviar_programados(), 0, 'No se manda dos veces')

    def recibir_del_cliente(self, texto):
        """El cliente de ``self.conv`` escribe (cliente(1) usa este celular)."""
        self.registrar(texto, id_externo='50761200001', ts=fields.Datetime.now())

    def test_el_mantenimiento_general_tambien_lo_despacha(self):
        mensaje = self.Mensaje.browse(self.programar()['mensaje']['id'])
        self.vencer(mensaje)
        self.Conversacion._cron_mantenimiento()
        (enviado,) = self.mios()
        self.assertEqual(enviado.estado_envio, 'enviado')

    def test_con_el_worker_caido_al_llegar_la_hora_queda_por_enviar_y_se_reintenta(self):
        mensaje = self.Mensaje.browse(self.programar()['mensaje']['id'])
        self.vencer(mensaje)
        self.worker.side_effect = requests.ConnectionError('sin red')
        self.Mensaje._cron_enviar_programados()
        (pendiente,) = self.mios()
        self.assertEqual(pendiente.estado_envio, 'por_enviar')

    def test_conserva_los_adjuntos(self):
        foto = self.env['ir.attachment'].with_user(self.vendedora).create({
            'name': 'foto.jpg', 'raw': b'\xff\xd8\xff\xe0', 'mimetype': 'image/jpeg',
            'res_model': 'dcasa.conversacion', 'res_id': 0})
        r = self.panel.enviar_respuesta(self.conv.id, None, [foto.id], self.a_las(hours=1))
        (adjunto,) = r['mensaje']['adjuntos']
        self.assertEqual(adjunto['nombre'], 'foto.jpg')
        self.vencer(self.Mensaje.browse(r['mensaje']['id']))
        self.Mensaje._cron_enviar_programados()
        (envio,) = self.envios()
        self.assertEqual(len(envio.kwargs['json']['adjuntos']), 1)
        (enviado,) = self.mios()
        self.assertEqual(enviado.adjunto_ids, foto, 'El archivo no se perdió al cambiar de mensaje')
        self.assertEqual(foto.res_id, enviado.id)

    def test_el_eco_de_otro_mensaje_igual_no_lo_confunde_con_uno_programado(self):
        mensaje = self.Mensaje.browse(self.programar('Gracias por tu compra')['mensaje']['id'])
        otro = self.conv._adoptar_mensaje_de_odoo({
            'direccion': 'saliente', 'autor': 'vendedora', 'texto': 'Gracias por tu compra', 'id_mensaje': 'wamid.x'})
        self.assertFalse(otro)
        self.assertEqual(mensaje.estado_envio, 'programado')

    def test_quien_lo_programo_lo_cancela_y_se_va_con_sus_archivos(self):
        r = self.programar()
        mensaje = self.Mensaje.browse(r['mensaje']['id'])
        resultado = self.panel.cancelar_programado(mensaje.id)
        self.assertTrue(resultado['cancelado'])
        self.assertFalse(mensaje.exists())
        avisos = self.conv.mensaje_ids.filtered(lambda m: m.tipo == 'aviso').mapped('texto')
        self.assertTrue(any('canceló un mensaje' in (a or '') for a in avisos))
        self.assertEqual(self.Mensaje._cron_enviar_programados(), 0)

    def test_otra_vendedora_no_puede_cancelarlo_pero_gerencia_si(self):
        otra = new_test_user(self.env, login='juan_otra2', name='Otra Vendedora',
                             groups='base.group_user,sales_team.group_sale_salesman')
        mensaje = self.Mensaje.browse(self.programar()['mensaje']['id'])
        with self.assertRaises(AccessError):
            self.Conversacion.with_user(otra).cancelar_programado(mensaje.id)
        self.assertTrue(mensaje.exists())
        self.Conversacion.with_user(self.gerente).cancelar_programado(mensaje.id)
        self.assertFalse(mensaje.exists())

    def test_no_se_cancela_lo_que_ya_salio_ni_lo_inexistente(self):
        enviado = self.Mensaje.browse(self.panel.enviar_respuesta(self.conv.id, 'Hola')['mensaje']['id'])
        for malo in (enviado.id, 999999999, 0, 'x', None):
            with self.subTest(malo=malo), self.assertRaises(UserError):
                self.panel.cancelar_programado(malo)
        self.assertTrue(enviado.exists())

    def test_los_demas_no_pueden_cancelar_por_rpc(self):
        mensaje = self.Mensaje.browse(self.programar()['mensaje']['id'])
        for usuario in (self.interno, self.portal):
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                call_kw(self.env(user=usuario)['dcasa.conversacion'], 'cancelar_programado', [mensaje.id], {})
        self.assertTrue(mensaje.exists())

    def test_se_ve_en_el_hilo_como_programado(self):
        self.programar('Para mañana')
        hilo = self.panel.hilo(self.conv.id)
        self.assertFalse([m for m in hilo['mensajes'] if m['estado_envio'] == 'programado'],
                         'Lo programado no se mezcla con el hilo: se ve aparte')
        (prog,) = hilo['programados']
        self.assertEqual(prog['texto'], 'Para mañana')
        self.assertTrue(prog['programado_para'])
        self.assertIn('Programado', self.conv.chat_html)


@tagged('post_install', '-at_install')
class TestAccionesDelPanel(PanelCase):

    def setUp(self):
        super().setUp()
        self.worker = self.configurar_worker()
        self.conv = self.cliente(1)

    def test_tomar_con_minutos(self):
        resumen = self.panel.tomar(self.conv.id, 30)
        self.assertEqual((resumen['estado'], resumen['bot_atiende']), ('humano', False))
        self.assertAlmostEqual((self.conv.pausada_hasta - fields.Datetime.now()).total_seconds(), 30 * 60, delta=60)
        self.assertEqual(self.conv.asignada_a, self.vendedora)

    def test_tomar_sin_minutos_usa_los_ajustes_y_cero_es_hasta_que_la_devuelvan(self):
        self.panel.tomar(self.conv.id)
        self.assertAlmostEqual((self.conv.pausada_hasta - fields.Datetime.now()).total_seconds(), 120 * 60, delta=60)
        self.panel.tomar(self.conv.id, 0)
        self.assertFalse(self.conv.pausada_hasta)
        self.assertFalse(self.conv._controla_bot())

    def test_tomar_con_minutos_invalidos(self):
        for malo in (-1, True, '30', 1.5, 7 * 24 * 60 + 1):
            with self.subTest(malo=malo), self.assertRaises(UserError):
                self.panel.tomar(self.conv.id, malo)
        self.assertEqual(self.conv.estado, 'bot')

    def test_devolver_cerrar_y_tomar_cuentan_igual_que_los_botones(self):
        self.panel.tomar(self.conv.id)
        resumen = self.panel.devolver(self.conv.id, 'Ya quedó la visita')
        self.assertEqual((resumen['estado'], resumen['bot_atiende'], resumen['nota_para_el_bot']),
                         ('bot', True, 'Ya quedó la visita'))
        resumen = self.panel.cerrar(self.conv.id)
        self.assertEqual((resumen['estado'], resumen['bot_atiende']), ('cerrada', False))
        self.assertFalse(self.conv.nota_para_el_bot)

    def test_asignar(self):
        resumen = self.panel.asignar(self.conv.id, self.gerente.id)
        self.assertEqual(resumen['asignada_a'], {'id': self.gerente.id, 'nombre': 'Gerente Prueba'})
        self.assertIn('Vendedora Prueba asignó la conversación a Gerente Prueba.',
                      self.conv.mensaje_ids.filtered(lambda m: m.tipo == 'aviso').mapped('texto'))
        self.assertIsNone(self.panel.asignar(self.conv.id, None)['asignada_a'])
        self.assertFalse(self.conv.asignada_a)

    def test_asignar_solo_a_gente_de_ventas(self):
        for usuario_id in (self.interno.id, self.portal.id, self.juan.id, 999999999, True, 'x'):
            with self.subTest(usuario_id=usuario_id), self.assertRaises(UserError):
                self.panel.asignar(self.conv.id, usuario_id)
        self.assertFalse(self.conv.asignada_a)

    def test_cancelar_el_seguimiento_programado(self):
        self.conv._oportunidad('Quiere una cama queen', interes='cama queen')
        self.registrar('¿Te muestro opciones?', id_externo=self.conv.id_externo, autor='bot',
                       ts=self.ahora - timedelta(minutes=5))
        self.assertTrue(self.conv.seguimiento_proximo)
        resumen = self.panel.cancelar_seguimiento(self.conv.id)
        self.assertFalse(self.conv.seguimiento_proximo)
        self.assertEqual(self.conv.seguimientos_enviados, 2, 'Ya no recibe ninguno más')
        self.assertIn('Vendedora Prueba canceló el seguimiento programado.',
                      self.conv.mensaje_ids.filtered(lambda m: m.tipo == 'aviso').mapped('texto'))
        self.assertEqual(resumen['id'], self.conv.id)
        with self.assertRaises(UserError):
            self.panel.cancelar_seguimiento(self.conv.id)    # ya no hay nada que cancelar

    def test_no_se_cancela_un_seguimiento_que_ya_esta_en_camino(self):
        self.conv._oportunidad('Quiere una cama queen', interes='cama queen')
        self.registrar('¿Te muestro opciones?', id_externo=self.conv.id_externo, autor='bot',
                       ts=self.ahora - timedelta(minutes=5))
        self.conv.write({'seguimiento_pedido_en': self.ahora, 'seguimiento_numero_pedido': 1,
                         'seguimiento_proximo': False})
        with self.assertRaises(UserError):
            self.panel.cancelar_seguimiento(self.conv.id)

    def test_agregar_nota(self):
        resultado = self.panel.agregar_nota(self.conv.id, '  Prefiere que le escriban en la tarde  ')
        nota = self.Mensaje.browse(resultado['mensaje']['id'])
        self.assertEqual((nota.tipo, nota.direccion, nota.autor, nota.usuario_id),
                         ('nota', 'interna', 'vendedora', self.vendedora))
        self.assertEqual(nota.texto, 'Prefiere que le escriban en la tarde')
        self.assertIn('Prefiere que le escriban en la tarde', ' '.join(self.conv.partner_id.message_ids.mapped('body')))
        self.assertEqual([c for c in self.worker.call_args_list if '/odoo/enviar' in c.args[1]], [], 'No sale al canal')

    def test_agregar_nota_invalida(self):
        for malo in ('', '   ', None, 5, 'x' * 1001):
            with self.subTest(largo=len(malo) if isinstance(malo, str) else malo), self.assertRaises(UserError):
                self.panel.agregar_nota(self.conv.id, malo)

    def test_marcar_sensible_desde_la_pantalla(self):
        mensaje = self.conv.mensaje_ids[:1]
        foto = self.env['ir.attachment'].create({
            'name': 'comprobante.jpg', 'raw': b'\xff\xd8\xff\xe0', 'mimetype': 'image/jpeg',
            'res_model': 'dcasa.mensaje', 'res_id': mensaje.id})
        mensaje.with_context(dcasa_mensaje_sistema=True).sudo().adjunto_ids = [Command.set(foto.ids)]
        resultado = self.Mensaje.with_user(self.vendedora).marcar_sensible([foto.id])
        self.assertEqual(resultado, {'marcados': [foto.id], 'sensible': True})
        self.assertTrue(foto.dcasa_sensible)
        self.assertTrue(mensaje.tiene_sensible)
        self.Mensaje.with_user(self.vendedora).marcar_sensible([foto.id], False)
        self.assertFalse(foto.dcasa_sensible)
        self.assertFalse(mensaje.tiene_sensible)

    def test_marcar_sensible_no_toca_adjuntos_de_otras_cosas(self):
        ajeno = self.env['ir.attachment'].create({
            'name': 'contrato.pdf', 'raw': b'%PDF', 'mimetype': 'application/pdf', 'res_model': 'res.partner',
            'res_id': self.conv.partner_id.id})
        self.assertEqual(self.Mensaje.with_user(self.vendedora).marcar_sensible([ajeno.id])['marcados'], [])
        self.assertFalse(ajeno.dcasa_sensible)
        for malo in ('1', None, [True], list(range(30))):
            with self.subTest(malo=malo), self.assertRaises(UserError):
                self.Mensaje.with_user(self.vendedora).marcar_sensible(malo)
        for usuario in (self.interno, self.portal):
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                self.Mensaje.with_user(usuario).marcar_sensible([ajeno.id])


@tagged('post_install', '-at_install')
class TestFicha(PanelCase):

    def setUp(self):
        super().setUp()
        self.conv = self.cliente(1, 'Quiero una cama queen', nombre='Karen Pérez', celular='6123-4567')

    def ficha(self):
        return self.panel.ficha(self.conv.id)

    def test_lo_basico_del_cliente(self):
        ficha = self.ficha()
        self.assertEqual(ficha['cliente']['nombre'], 'Karen Pérez')
        self.assertEqual(ficha['cliente']['canal'], 'whatsapp_qr')
        self.assertFalse(ficha['cliente']['no_contactar'])
        self.assertEqual(ficha['conversacion']['id'], self.conv.id)
        self.assertEqual(ficha['socio'], {'es_socio': False, 'puntos': None})
        self.assertEqual((ficha['oportunidades'], ficha['compras'], ficha['notas']), ([], [], []))
        self.assertEqual(ficha['seguimiento']['maximo'], 2)

    def test_socio_con_sus_puntos_en_solo_lectura(self):
        partner = self.conv.partner_id
        partner._dcasa_asegurar_ficha()
        partner._dcasa_guardar_pin(PIN)
        self.env['dcasa.movimiento']._asentar(partner, 'ajuste', 1500, 'sistema', motivo='Saldo de prueba')
        ficha = self.ficha()
        self.assertEqual(ficha['socio'], {'es_socio': True, 'puntos': 1500})
        self.assertNotIn('pin', str(ficha).lower())

    def test_no_es_socio_si_no_reclamo_su_ficha_aunque_tenga_puntos(self):
        self.env['dcasa.movimiento']._asentar(self.conv.partner_id, 'ajuste', 300, 'sistema', motivo='Prueba')
        self.assertEqual(self.ficha()['socio'], {'es_socio': False, 'puntos': None})

    def test_oportunidades_abiertas_y_compras_del_cliente(self):
        lead = self.env['crm.lead'].create({
            'name': 'Cama queen', 'type': 'opportunity', 'partner_id': self.conv.partner_id.id,
            'expected_revenue': 350})
        self.env['crm.lead'].create({'name': 'De otra persona', 'type': 'opportunity'})
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.conv.partner_id.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'name': 'Cama', 'quantity': 1, 'price_unit': 349.99})]})
        factura.action_post()
        ficha = self.ficha()
        self.assertEqual([o['id'] for o in ficha['oportunidades']], [lead.id])
        self.assertEqual(ficha['oportunidades'][0]['ingreso_esperado'], 350.0)
        (compra,) = ficha['compras']
        self.assertEqual((compra['id'], compra['pagada']), (factura.id, False))
        self.assertEqual(compra['total'], factura.amount_total)
        self.assertEqual(ficha['bot_sabe']['oportunidad_abierta'], 'Cama queen')

    def test_las_notas_internas_van_en_la_ficha(self):
        self.panel.agregar_nota(self.conv.id, 'Pidió que no la llamen')
        self.assertEqual([n['texto'] for n in self.ficha()['notas']], ['Pidió que no la llamen'])

    def test_lo_que_sabe_el_bot_de_esta_persona(self):
        etiqueta = self.env['dcasa.conversacion.etiqueta'].create({'name': 'Zzsabe'})
        self.conv.etiqueta_ids = etiqueta
        Acciones = self.env['brian.accion'].sudo().with_context(brian_accion_sistema=True)
        for herramienta, argumentos in (('juan_buscar_productos', '{"consulta": "cama queen"}'),
                                        ('juan_ver_producto', '{"codigo": "ZZ-CAMA"}'),
                                        ('juan_buscar_productos', '{"consulta": "Cama Queen"}'),
                                        ('juan_horario_y_tienda', '{}')):
            Acciones.create({'herramienta': herramienta, 'argumentos': argumentos, 'estado': 'hecha',
                             'dcasa_conversacion_id': self.conv.id})
        Acciones.create({'herramienta': 'juan_buscar_productos', 'argumentos': '{"consulta": "de otra conversación"}',
                         'estado': 'hecha', 'dcasa_conversacion_id': self.cliente(2).id})
        sabe = self.ficha()['bot_sabe']
        self.assertEqual(sorted(p.lower() for p in sabe['productos_preguntados']), ['cama queen', 'zz-cama'])
        self.assertEqual(sabe['nombre'], 'Karen')
        self.assertEqual(sabe['etiquetas'], ['Zzsabe'])
        self.assertFalse(sabe['es_socio'])
        self.assertTrue(sabe['ultima_vez_que_hablo'])
        self.assertFalse(sabe['seguimiento_pendiente'])

    def test_sin_nombre_real_el_bot_no_sabe_el_nombre(self):
        anonima = self.conversacion('Hola', id_externo='50761230888')
        self.assertIsNone(self.panel.ficha(anonima.id)['bot_sabe']['nombre'])

    def test_no_se_cuela_nada_de_otros_clientes_ni_costos(self):
        otra = self.cliente(2, nombre='Otra Zzpersona')
        self.panel.agregar_nota(otra.id, 'Secreto de la otra')
        crudo = str(self.ficha())
        self.assertNotIn('Zzpersona', crudo)
        self.assertNotIn('Secreto de la otra', crudo)


@tagged('post_install', '-at_install')
class TestRendimientoDeLaBandeja(PanelCase):

    def consultas(self, funcion):
        """Cuántas consultas SQL hace ``funcion`` (con la caché vacía, y ya calentado el registro)."""
        consultas = None
        for _ in range(3):   # las primeras pasadas calientan cachés del registro (reglas, grupos…); cuenta la última
            self.env.flush_all()
            self.env.invalidate_all()
            antes = self.env.cr.sql_log_count
            funcion()
            self.env.flush_all()
            consultas = self.env.cr.sql_log_count - antes
        return consultas

    def test_la_lista_hace_las_mismas_consultas_con_3_o_con_30_filas(self):
        etiquetas = self.env['dcasa.conversacion.etiqueta'].create([{'name': f'Zzrend{i}'} for i in range(4)])
        for n in range(1, 31):
            conv = self.cliente(n)
            conv.write({'asignada_a': (self.vendedora, self.gerente)[n % 2].id,
                        'etiqueta_ids': [Command.set(etiquetas[: n % 4].ids)]})
        self.panel.lista(limite=3)   # calienta cachés del registro
        con_3 = self.consultas(lambda: self.panel.lista(limite=3))
        con_30 = self.consultas(lambda: self.panel.lista(limite=30))
        self.assertEqual(con_3, con_30, 'Las consultas no dependen de cuántas filas se piden')
        self.assertLessEqual(con_30, 25)

    def test_el_hilo_hace_las_mismas_consultas_con_3_o_con_40_mensajes(self):
        conv = self.cliente(1)
        for n in range(2, 41):
            self.registrar(f'Mensaje {n}', id_externo=conv.id_externo, autor='cliente' if n % 2 else 'bot',
                           ts=self.ahora - timedelta(minutes=90 - n))
        for mensaje in conv.mensaje_ids.sorted('id')[-20:]:
            adjunto = self.env['ir.attachment'].create({
                'name': f'f{mensaje.id}.jpg', 'raw': b'\xff\xd8\xff\xe0', 'mimetype': 'image/jpeg',
                'res_model': 'dcasa.mensaje', 'res_id': mensaje.id})
            mensaje.with_context(dcasa_mensaje_sistema=True).sudo().adjunto_ids = [Command.set(adjunto.ids)]
        self.panel.hilo(conv.id, limite=3)
        con_3 = self.consultas(lambda: self.panel.hilo(conv.id, limite=3))
        con_40 = self.consultas(lambda: self.panel.hilo(conv.id, limite=40))
        self.assertEqual(con_3, con_40)

    def test_la_busqueda_mira_el_texto_de_los_mensajes_una_sola_vez(self):
        """Antes la bandeja contaba y luego pedía la página: el subselect sobre TODOS los mensajes corría dos veces."""
        for n in range(1, 6):
            self.cliente(n, nombre=f'Zzbusca {n}')
        consultas = []
        real = self.env.cr.execute

        def espia(query, *args, **kwargs):
            consultas.append(str(getattr(query, 'code', query)).lower())
            return real(query, *args, **kwargs)

        with patch.object(self.env.cr, 'execute', side_effect=espia):
            pagina = self.panel.lista({'busqueda': 'zzbusca'}, offset=0, limite=2)
        sobre_texto = [q for q in consultas if 'dcasa_mensaje' in q and 'ilike' in q and 'texto' in q]
        self.assertEqual(len(sobre_texto), 1, sobre_texto)
        self.assertEqual((pagina['total'], len(pagina['conversaciones']), pagina['hay_mas']), (5, 2, True))

    def test_buscar_pagina_a_pagina_da_lo_mismo_que_todo_junto(self):
        for n in range(1, 8):
            self.cliente(n, nombre=f'Zzpagina {n}')
        todo = self.panel.lista({'busqueda': 'zzpagina'}, limite=100)
        self.assertEqual(todo['total'], 7)
        vistos = []
        for offset in (0, 3, 6):
            parte = self.panel.lista({'busqueda': 'zzpagina'}, offset=offset, limite=3)
            self.assertEqual(parte['total'], 7)
            self.assertEqual(parte['hay_mas'], offset + len(parte['conversaciones']) < 7)
            vistos += [c['id'] for c in parte['conversaciones']]
        self.assertEqual(vistos, [c['id'] for c in todo['conversaciones']])
        self.assertEqual(self.panel.lista({'busqueda': 'zzpagina'}, offset=50, limite=3)['conversaciones'], [])

    def test_los_indices_de_los_mensajes_son_los_que_se_usan(self):
        """12 índices en la tabla que más crece: 5 repetidos o sobre columnas de 2 a 5 valores (no sirven)."""
        self.env.cr.execute("SELECT indexdef FROM pg_indexes WHERE tablename = 'dcasa_mensaje'")
        definiciones = [fila[0].lower() for fila in self.env.cr.fetchall()]
        columnas = ['conversacion_id', 'id_mensaje', 'canal', 'tipo', 'autor', 'estado_envio']
        for columna in columnas:
            sueltos = [d for d in definiciones if f'({columna})' in d and 'where' not in d]
            self.assertFalse(sueltos, f'Índice suelto sobre {columna}: {sueltos}')
        self.assertTrue(any('(conversacion_id, id)' in d for d in definiciones), definiciones)
        self.assertTrue(any('unique' in d and 'conversacion_id, id_mensaje' in d for d in definiciones), definiciones)
        # El que busca lo pendiente es PARCIAL: solo guarda lo que espera salir o falló.
        self.assertTrue(any('(estado_envio)' in d and "'por_enviar'" in d for d in definiciones), definiciones)
        if self.env.registry.has_trigram:
            self.assertTrue(any('gin' in d and 'texto' in d and 'trgm' in d for d in definiciones), definiciones)

    def test_el_hilo_y_los_pendientes_leen_por_indice(self):
        self.cliente(1)
        self.env.cr.execute('ANALYZE dcasa_mensaje')
        # Con tan pocas filas el planificador prefiere recorrer: se prueba que el índice PUEDE usarse.
        self.env.cr.execute('SET LOCAL enable_seqscan = off')
        consultas = {
            'hilo': 'SELECT id FROM dcasa_mensaje WHERE conversacion_id = 1 AND id < 999999 ORDER BY id DESC LIMIT 51',
            'por enviar': "SELECT id FROM dcasa_mensaje WHERE estado_envio = 'por_enviar' ORDER BY id LIMIT 50",
            'programados': ("SELECT id FROM dcasa_mensaje WHERE estado_envio = 'programado' "
                            "AND programado_para <= NOW() ORDER BY programado_para LIMIT 50"),
        }
        for nombre, consulta in consultas.items():
            self.env.cr.execute('EXPLAIN ' + consulta)
            plan = '\n'.join(fila[0] for fila in self.env.cr.fetchall())
            self.assertIn('Index', plan, f'{nombre}: {plan}')
        if self.env.registry.has_trigram:
            self.env.cr.execute("EXPLAIN SELECT conversacion_id FROM dcasa_mensaje WHERE texto ILIKE '%zzbusca%'")
            plan = '\n'.join(fila[0] for fila in self.env.cr.fetchall())
            self.assertIn('Index', plan, plan)

    def test_con_5000_conversaciones_la_lista_sale_en_menos_de_un_cuarto_de_segundo_y_usa_el_indice(self):
        self.env.cr.execute("""
            INSERT INTO dcasa_conversacion
                   (canal, id_externo, estado, name, inicio, ultima_actividad, ultimo_mensaje_texto,
                    ultimo_mensaje_autor, ultimo_cliente_msg_id, create_date, write_date, create_uid, write_uid)
            SELECT 'whatsapp_qr', 'zzcarga' || g, CASE WHEN g % 10 = 0 THEN 'humano' ELSE 'bot' END,
                   'Zzcarga ' || g, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC' - (g || ' minutes')::interval,
                   'Hola ' || g, 'cliente', 0, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC', 1, 1
              FROM generate_series(1, 5000) g""")
        self.env.cr.execute("""
            INSERT INTO dcasa_mensaje
                   (conversacion_id, id_mensaje, tipo, direccion, autor, texto, ts, origen, estado_envio, canal,
                    intentos, adjuntos_fallidos, create_date, write_date, create_uid, write_uid)
            SELECT c.id, 'zzcarga.' || c.id, 'mensaje', 'entrante', 'cliente', c.ultimo_mensaje_texto,
                   c.ultima_actividad, 'canal', 'recibido', 'whatsapp_qr', 0, 0, c.create_date, c.write_date, 1, 1
              FROM dcasa_conversacion c WHERE c.id_externo LIKE 'zzcarga%'""")
        self.env.cr.execute("""
            UPDATE dcasa_conversacion c SET ultimo_cliente_msg_id = m.id
              FROM dcasa_mensaje m WHERE m.conversacion_id = c.id AND c.id_externo LIKE 'zzcarga%'""")
        self.env.cr.execute('ANALYZE dcasa_conversacion')
        self.env.cr.execute('ANALYZE dcasa_mensaje')
        self.env.invalidate_all()
        self.panel.lista()   # calienta
        tiempos = []
        for filtros in ({}, {'estado': 'humano'}, {'sin_leer': True}, {'busqueda': 'zzcarga4999'}):
            minimo = None
            for _ in range(3):
                self.env.invalidate_all()
                t0 = time.perf_counter()
                resultado = self.panel.lista(filtros)
                dt = time.perf_counter() - t0
                minimo = dt if minimo is None else min(minimo, dt)
            tiempos.append((filtros, round(minimo, 3)))
            # Medido: ~0,03 s. Con 0,25 s se nota un índice perdido o una consulta de más, sin falsas alarmas.
            self.assertLess(minimo, 0.25, f'{filtros} tardó {minimo:.2f} s')
            self.assertTrue(resultado['conversaciones'])
        _logger.info('Bandeja con 5.000 conversaciones (mejor de 3, segundos): %s', tiempos)
        self.assertEqual(self.panel.lista()['total'], 5000)
        self.assertEqual(len(self.panel.lista(limite=30)['conversaciones']), 30)
        self.env.cr.execute("""
            EXPLAIN SELECT id FROM dcasa_conversacion ORDER BY ultima_actividad DESC NULLS LAST, id DESC LIMIT 30""")
        plan = '\n'.join(fila[0] for fila in self.env.cr.fetchall())
        self.assertIn('Index', plan, plan)
        self.assertNotIn('Sort', plan, 'Sin ordenar toda la tabla: ' + plan)


@tagged('post_install', '-at_install')
class TestRefrescar(PanelCase):
    """Un aviso en vivo se atiende con UNA llamada: la lista y, si hay una conversación abierta, su hilo."""

    def test_trae_la_lista_y_el_hilo_igual_que_las_dos_llamadas_de_antes(self):
        conv = self.cliente(1)
        self.cliente(2)
        r = self.panel.refrescar({}, 30, conv.id, 50)
        self.assertEqual(r['lista'], self.panel.lista({}, 0, 30))
        self.assertEqual(r['hilo'], self.panel.hilo(conv.id, None, 50))

    def test_sin_conversacion_abierta_solo_la_lista(self):
        self.cliente(1)
        r = self.panel.refrescar({'estado': 'bot'})
        self.assertEqual(r['lista'], self.panel.lista({'estado': 'bot'}))
        self.assertIsNone(r['hilo'])

    def test_respeta_los_filtros_los_permisos_y_la_validacion_de_cada_parte(self):
        conv = self.cliente(1)
        with self.assertRaises(UserError):
            self.panel.refrescar({'inventado': True})
        with self.assertRaises(UserError):
            self.panel.refrescar({}, 30, 99999999)
        with self.assertRaises(UserError):
            self.panel.refrescar({}, 0, conv.id)
        for usuario in (self.interno, self.portal):
            with self.assertRaises(AccessError):
                call_kw(self.env(user=usuario)['dcasa.conversacion'], 'refrescar', [], {})


@tagged('post_install', '-at_install')
class TestEliminarConversacion(PanelCase):
    """«Eliminar conversación» (Ley 81): solo Gerencia; el bot olvida su copia ANTES de que Odoo borre la suya."""

    def setUp(self):
        super().setUp()
        self.llamadas = self.configurar_worker()
        self.llamadas.return_value = respuesta_http({'ok': True, 'mensajes': 3})
        self.gerencia = self.Conversacion.with_user(self.gerente)
        self.conv = self.cliente(1, nombre='Karen Prueba')
        self.mensaje = self.conv.mensaje_ids[:1]
        self.adjunto = self.env['ir.attachment'].create({
            'name': 'foto.txt', 'raw': b'contenido', 'res_model': 'dcasa.mensaje', 'res_id': self.mensaje.id})
        self.mensaje.adjunto_ids = [Command.link(self.adjunto.id)]

    def olvidos(self):
        return [c for c in self.llamadas.call_args_list if c.args[1].endswith('/odoo/olvidar')]

    def test_gerencia_la_elimina_con_sus_mensajes_y_archivos_y_el_bot_la_olvida(self):
        conv_id, partner, canal, externo = self.conv.id, self.conv.partner_id, self.conv.canal, self.conv.id_externo
        lead, _nueva = self.conv._oportunidad('Quiere una cama queen', interes='cama queen')
        resultado = self.gerencia.eliminar(conv_id)
        self.assertEqual(resultado, {'eliminada': True, 'conversacion_id': conv_id})
        self.assertFalse(self.Conversacion.browse(conv_id).exists())
        self.assertFalse(self.Mensaje.search([('conversacion_id', '=', conv_id)]))
        self.assertFalse(self.adjunto.exists(), 'Los archivos de la conversación se van con ella')
        (llamada,) = self.olvidos()
        self.assertEqual((llamada.args[0], llamada.kwargs['json']), ('POST', {'canal': canal, 'id_externo': externo}))
        # La oportunidad y la ficha del cliente son registros del negocio: se quedan.
        self.assertTrue(lead.exists())
        self.assertTrue(partner.exists())

    def test_las_vendedoras_no_pueden(self):
        with self.assertRaises(AccessError):
            self.panel.eliminar(self.conv.id)
        self.assertTrue(self.conv.exists())
        self.assertFalse(self.olvidos())

    def test_nadie_mas_puede_ni_por_rpc(self):
        for usuario in (self.interno, self.portal):
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                call_kw(self.env(user=usuario)['dcasa.conversacion'], 'eliminar', [self.conv.id], {})
        self.assertTrue(self.conv.exists())
        self.assertFalse(self.olvidos())

    def test_si_el_bot_no_pudo_olvidar_no_se_borra_nada(self):
        self.llamadas.return_value = respuesta_http({'ok': False, 'error': 'almacenamiento no disponible'}, 502)
        with self.assertRaises(UserError) as error:
            self.gerencia.eliminar(self.conv.id)
        self.assertIn('No se eliminó nada', str(error.exception))
        self.assertTrue(self.conv.exists())
        self.assertTrue(self.conv.mensaje_ids)
        self.assertTrue(self.adjunto.exists())

    def test_si_el_bot_no_responde_tampoco_se_borra(self):
        self.llamadas.side_effect = requests.ConnectionError('sin red')
        with self.assertRaises(UserError):
            self.gerencia.eliminar(self.conv.id)
        self.assertTrue(self.conv.exists())

    def test_sin_bot_conectado_se_borra_solo_lo_de_odoo(self):
        with patch.dict(os.environ, {'JUAN_URL': '', 'JUAN_WORKER_TOKEN': ''}):
            self.gerencia.eliminar(self.conv.id)
        self.assertFalse(self.conv.exists())
        self.assertFalse(self.olvidos())

    def test_una_conversacion_que_ya_no_existe_avisa(self):
        conv_id = self.conv.id
        self.gerencia.eliminar(conv_id)
        with self.assertRaises(UserError):
            self.gerencia.eliminar(conv_id)

    def test_pide_un_numero_entero_valido(self):
        for malo in (None, True, 'x', 0, -1, 1.5):
            with self.subTest(malo=malo), self.assertRaises(UserError):
                self.gerencia.eliminar(malo)
        self.assertTrue(self.conv.exists())


@tagged('post_install', '-at_install')
class TestMencionesEnNotas(PanelCase):
    """Escribir @ en una nota interna avisa a la compañera (Odoo y Telegram) y, si se pide, le deja una tarea."""

    def setUp(self):
        super().setUp()
        self.conv = self.cliente(1, nombre='Karen Prueba')
        self.otra = new_test_user(self.env, login='juan_otra', name='Otra Vendedora',
                                  groups='base.group_user,sales_team.group_sale_salesman')
        self.Enlace = self.env['brian.telegram.enlace'].sudo()
        self.Enlace.create({'user_id': self.otra.id, 'chat_id': '7770001'})
        self.Enlace.create({'user_id': self.vendedora.id, 'chat_id': '7770002'})
        self.enviar = MagicMock()
        parche = patch.object(type(self.Enlace), '_enviar', self.enviar)
        parche.start()
        self.addCleanup(parche.stop)

    def chats(self):
        return [c.args[0] for c in self.enviar.call_args_list]

    def test_la_nota_guarda_a_quien_se_menciono_y_se_le_avisa_solo_a_ella(self):
        r = self.panel.agregar_nota(self.conv.id, '@Otra Vendedora ¿puedes llamarla?', [self.otra.id])
        self.assertEqual((r['mencionadas'], r['telegram'], r['tareas']), (1, 1, 0))
        self.assertEqual(r['mensaje']['menciones'], [{'id': self.otra.id, 'nombre': 'Otra Vendedora'}])
        self.assertEqual(self.chats(), ['7770001'], 'El aviso va solo a la mencionada, no a todo el equipo')
        self.assertIn('Vendedora Prueba te mencionó', self.enviar.call_args.args[1])
        self.assertIn('Karen Prueba', self.enviar.call_args.args[1])
        self.assertIn('¿puedes llamarla?', self.enviar.call_args.args[1])

    def test_le_llega_a_la_bandeja_de_odoo(self):
        self.panel.agregar_nota(self.conv.id, '@Otra Vendedora mira esto', [self.otra.id])
        mensaje = self.conv.message_ids.filtered(lambda m: 'te mencionó' in str(m.body))
        self.assertTrue(mensaje)
        self.assertIn(self.otra.partner_id, mensaje.partner_ids)

    def test_con_fecha_le_deja_una_tarea(self):
        fecha = fields.Date.context_today(self.panel) + timedelta(days=2)
        r = self.panel.agregar_nota(self.conv.id, '@Otra Vendedora llámala', [self.otra.id], str(fecha))
        self.assertEqual(r['tareas'], 1)
        (tarea,) = self.conv.activity_ids
        self.assertEqual((tarea.user_id, tarea.date_deadline), (self.otra, fecha))
        self.assertIn('Karen Prueba', tarea.summary)

    def test_una_nota_sin_menciones_no_avisa_a_nadie(self):
        r = self.panel.agregar_nota(self.conv.id, 'Solo para que quede anotado')
        self.assertEqual((r['mencionadas'], r['telegram'], r['tareas']), (0, 0, 0))
        self.assertFalse(self.chats())
        self.assertEqual(r['mensaje']['menciones'], [])

    def test_no_se_avisa_a_la_misma_autora(self):
        r = self.panel.agregar_nota(self.conv.id, '@Vendedora Prueba recuérdame', [self.vendedora.id])
        self.assertEqual(r['mencionadas'], 0)
        self.assertFalse(self.chats())

    def test_solo_se_menciona_a_gente_del_equipo_de_ventas(self):
        for malos in ([self.interno.id], [self.portal.id], [self.juan.id], [999999999], [True], ['x'], 5, [0]):
            with self.subTest(malos=malos), self.assertRaises(UserError):
                self.panel.agregar_nota(self.conv.id, 'hola', malos)
        self.assertFalse(self.conv.mensaje_ids.filtered(lambda m: m.tipo == 'nota'))

    def test_maximo_de_menciones_por_nota(self):
        with self.assertRaises(UserError):
            self.panel.agregar_nota(self.conv.id, 'hola', list(range(1, 12)))

    def test_la_fecha_de_la_tarea_se_valida_y_pide_a_alguien(self):
        hoy = fields.Date.context_today(self.panel)
        for fecha in ('ayer', '2020-01-01', str(hoy + timedelta(days=900)), 20261010):
            with self.subTest(fecha=fecha), self.assertRaises(UserError):
                self.panel.agregar_nota(self.conv.id, '@Otra Vendedora x', [self.otra.id], fecha)
        with self.assertRaises(UserError):     # una tarea sin nadie a quien dársela
            self.panel.agregar_nota(self.conv.id, 'x', None, str(hoy + timedelta(days=1)))
        self.assertFalse(self.conv.activity_ids)

    def test_un_fallo_de_telegram_no_pierde_la_nota(self):
        self.enviar.side_effect = RuntimeError('sin red')
        with mute_logger('odoo.addons.dcasa_conversaciones.models.conversacion'):
            r = self.panel.agregar_nota(self.conv.id, '@Otra Vendedora hola', [self.otra.id])
        self.assertTrue(r['mensaje']['id'])
        self.assertEqual(r['mencionadas'], 1)

    def test_la_nota_con_mencion_nunca_sale_al_cliente(self):
        worker = self.configurar_worker()
        self.panel.agregar_nota(self.conv.id, '@Otra Vendedora hola', [self.otra.id])
        self.Mensaje._cron_reintentar_envios()
        enviados = [c for c in worker.call_args_list if c.args[1].endswith('/odoo/enviar')]
        self.assertFalse(enviados)


@tagged('post_install', '-at_install')
class TestComprobanteAUnDocumento(PanelCase):
    """Un archivo del cliente (un comprobante) se adjunta con un clic al pedido o a la factura de ESE cliente."""

    def setUp(self):
        super().setUp()
        self.conv = self.cliente(1, nombre='Karen Prueba')
        self.partner = self.conv.partner_id
        self.assertTrue(self.partner, 'La conversación de WhatsApp crea la ficha del cliente')
        self.mensaje = self.conv.mensaje_ids.filtered(lambda m: m.autor == 'cliente')[:1]
        self.adjunto = self.env['ir.attachment'].create({
            'name': 'yappy.png', 'raw': b'contenido-del-comprobante', 'mimetype': 'image/png',
            'res_model': 'dcasa.mensaje', 'res_id': self.mensaje.id})
        self.mensaje.sudo().adjunto_ids = [Command.link(self.adjunto.id)]
        self.producto = self.env['product.product'].create({
            'name': 'Cama de prueba (comprobantes)', 'type': 'consu', 'list_price': 100.0,
            'taxes_id': [Command.clear()]})
        self.pedido = self.env['sale.order'].create({
            'partner_id': self.partner.id, 'user_id': self.vendedora.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})]})
        self.factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.partner.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': self.producto.id, 'quantity': 1, 'price_unit': 100.0})]})
        self.ajeno = self.env['res.partner'].create({'name': 'Otro cliente'})
        self.pedido_ajeno = self.env['sale.order'].create({
            'partner_id': self.ajeno.id, 'user_id': self.vendedora.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})]})

    def adjuntar(self, modelo, registro, usuario=None, adjunto=None):
        return (self.panel if usuario is None else self.Conversacion.with_user(usuario)).adjuntar_a_documento(
            self.conv.id, (adjunto or self.adjunto).id, modelo, registro.id)

    def test_lista_solo_los_documentos_de_ese_cliente(self):
        r = self.panel.documentos_del_cliente(self.conv.id)
        self.assertTrue(r['cliente'])
        self.assertEqual([p['id'] for p in r['pedidos']], [self.pedido.id])
        self.assertEqual([f['id'] for f in r['facturas']], [self.factura.id])
        self.assertEqual(r['pedidos'][0]['total'], 100.0)

    def test_sin_cliente_no_hay_documentos(self):
        sin = self.conversacion('hola', canal='telegram', id_externo='999')
        sin.sudo().partner_id = False
        self.assertEqual(self.panel.documentos_del_cliente(sin.id), {'cliente': False, 'pedidos': [], 'facturas': []})

    def test_adjunta_el_comprobante_al_pedido_con_nota_en_su_chatter_y_aviso_en_el_hilo(self):
        r = self.adjuntar('sale.order', self.pedido)
        self.assertEqual((r['ok'], r['ya_estaba'], r['documento']), (True, False, self.pedido.name))
        copia = self.env['ir.attachment'].search([('res_model', '=', 'sale.order'), ('res_id', '=', self.pedido.id)])
        self.assertEqual(len(copia), 1)
        self.assertEqual(copia.raw, b'contenido-del-comprobante')
        self.assertTrue(self.adjunto.exists(), 'El original se queda en la conversación')
        nota = self.pedido.message_ids.filtered(lambda m: 'adjuntó «yappy.png»' in str(m.body))
        self.assertTrue(nota)
        self.assertIn(copia, nota.attachment_ids)
        avisos = self.conv.mensaje_ids.filtered(lambda m: m.tipo == 'aviso').mapped('texto')
        self.assertTrue(any(self.pedido.name in a and 'yappy.png' in a for a in avisos))

    def test_tambien_a_una_factura_del_cliente(self):
        # El rol real «Vendedora» de D'CASA incluye Facturación (account.group_account_invoice).
        facturadora = new_test_user(self.env, login='juan_facturadora', name='Facturadora Prueba',
                                    groups='base.group_user,dcasa_base.group_vendedora')
        self.adjuntar('account.move', self.factura, usuario=facturadora)
        self.assertEqual(self.env['ir.attachment'].search_count([
            ('res_model', '=', 'account.move'), ('res_id', '=', self.factura.id), ('name', '=', 'yappy.png')]), 1)

    def test_adjuntarlo_dos_veces_no_lo_duplica(self):
        self.adjuntar('sale.order', self.pedido)
        r = self.adjuntar('sale.order', self.pedido)
        self.assertTrue(r['ya_estaba'])
        self.assertEqual(self.env['ir.attachment'].search_count([
            ('res_model', '=', 'sale.order'), ('res_id', '=', self.pedido.id)]), 1)

    def test_no_se_adjunta_al_documento_de_otro_cliente(self):
        with self.assertRaises(UserError) as error:
            self.adjuntar('sale.order', self.pedido_ajeno)
        self.assertIn('otro cliente', str(error.exception))
        self.assertFalse(self.env['ir.attachment'].search_count([('res_id', '=', self.pedido_ajeno.id),
                                                                  ('res_model', '=', 'sale.order')]))

    def test_solo_archivos_que_mando_el_cliente_en_esta_conversacion(self):
        otra = self.cliente(2, nombre='Otra Persona')
        ajeno = self.env['ir.attachment'].create({
            'name': 'ajeno.png', 'raw': b'x', 'res_model': 'dcasa.mensaje', 'res_id': otra.mensaje_ids[:1].id})
        otra.mensaje_ids[:1].sudo().adjunto_ids = [Command.link(ajeno.id)]
        with self.assertRaises(UserError):
            self.adjuntar('sale.order', self.pedido, adjunto=ajeno)       # de otra conversación
        propio = self.env['ir.attachment'].create({
            'name': 'cotizacion.pdf', 'raw': b'pdf', 'res_model': 'dcasa.mensaje', 'res_id': self.mensaje.id})
        nota = self.Mensaje._crear_interno(self.conv, 'nota', 'una nota', self.vendedora)
        nota.sudo().adjunto_ids = [Command.link(propio.id)]
        with self.assertRaises(UserError):
            self.adjuntar('sale.order', self.pedido, adjunto=propio)      # no lo mandó el cliente
        with self.assertRaises(UserError):
            self.adjuntar('sale.order', self.pedido, adjunto=self.env['ir.attachment'].browse(999999999))

    def test_sin_permiso_de_facturacion_el_mensaje_es_claro(self):
        with self.assertRaises(UserError) as error:
            self.adjuntar('account.move', self.factura, usuario=self.gerente)   # solo equipo de ventas, sin Facturación
        self.assertIn('No tienes permiso', str(error.exception))

    def test_solo_pedidos_y_facturas_de_cliente(self):
        for modelo in ('res.partner', 'ir.config_parameter', 'sale.order.line', None, 5):
            with self.subTest(modelo=modelo), self.assertRaises(UserError):
                self.panel.adjuntar_a_documento(self.conv.id, self.adjunto.id, modelo, self.pedido.id)
        compra = self.env['account.move'].create({
            'move_type': 'out_refund', 'partner_id': self.partner.id, 'invoice_date': fields.Date.today()})
        with self.assertRaises(UserError):
            self.adjuntar('account.move', compra)

    def test_pide_numeros_enteros(self):
        for malo in (None, True, 'x', 0, -3):
            with self.subTest(malo=malo), self.assertRaises(UserError):
                self.panel.adjuntar_a_documento(self.conv.id, malo, 'sale.order', self.pedido.id)
            with self.subTest(malo=malo, campo='registro'), self.assertRaises(UserError):
                self.panel.adjuntar_a_documento(self.conv.id, self.adjunto.id, 'sale.order', malo)

    def test_quien_no_puede_escribir_en_el_documento_recibe_un_mensaje_claro(self):
        ajeno_a_ella = self.env['sale.order'].create({
            'partner_id': self.partner.id, 'user_id': self.gerente.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})]})
        try:
            ajeno_a_ella.with_user(self.vendedora).check_access('write')
            self.skipTest('La vendedora puede escribir en los pedidos de otras: no hay nada que negar en este entorno')
        except AccessError:
            pass
        with self.assertRaises(UserError) as error:
            self.adjuntar('sale.order', ajeno_a_ella)
        self.assertIn('No tienes permiso', str(error.exception))

    def test_nadie_fuera_de_ventas_puede_ni_por_rpc(self):
        for usuario in (self.interno, self.portal):
            adjuntar = [self.conv.id, self.adjunto.id, 'sale.order', self.pedido.id]
            for metodo, args in (('documentos_del_cliente', [self.conv.id]), ('adjuntar_a_documento', adjuntar)):
                with self.subTest(usuario=usuario.login, metodo=metodo), self.assertRaises(AccessError):
                    call_kw(self.env(user=usuario)['dcasa.conversacion'], metodo, list(args), {})
