"""La revisión adversarial de la etapa 2 (2026-11-06): una prueba por hallazgo. Todas fallaron sobre el código de
antes (commit 49e5f87) y pasan con el arreglo. Datos inventados (ZZCM, @example.com); Resend es el falso de
``comun.py``."""
from datetime import timedelta
from unittest.mock import patch

from odoo import SUPERUSER_ID, api, fields, sql_db
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tools import SQL

from ..models import envio as ENVIO
from ..models import reglas as R
from ..models import resend_campanas as RC
from .comun import CamilaComun


class Revision2Comun(CamilaComun):

    def enviar(self, campana, usuario=None):
        return self.Camila.with_user(usuario or self.marketing).enviar(campana['id'], campana['huella'])

    def panel(self, campana_id):
        return self.Camila.with_user(self.marketing).panel(campana_id)['campana']

    def campana(self, datos):
        return self.env['dcasa.camila.campana'].browse(datos['id'])


# ----------------------------------------------------------------------
# 1 (ALTA). Dos campañas distintas no salen a la vez
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestTurnoDeEnvio(Revision2Comun):

    def _libre_desde_otra_conexion(self):
        """¿Otra conexión (otro trabajador de Odoo) puede tomar el turno de envío ahora?"""
        cr = sql_db.db_connect(self.env.cr.dbname).cursor()
        try:
            cr.execute(SQL('SELECT pg_try_advisory_lock(%s)', ENVIO.LLAVE_ENVIO))
            libre = cr.fetchone()[0]
            if libre:
                cr.execute(SQL('SELECT pg_advisory_unlock(%s)', ENVIO.LLAVE_ENVIO))
            return libre
        finally:
            cr.rollback()
            cr.close()

    def test_el_turno_aguanta_la_confirmacion_a_mitad_de_peticion(self):
        """A toma el turno, confirma «aprobada» (COMMIT a mitad de la petición) y sigue enviando: B, en otro
        trabajador y con su «foto» de antes, NO puede tomarlo. Antes el candado era de transacción y se soltaba con
        el primer COMMIT."""
        base = sql_db.db_connect(self.env.cr.dbname)
        cr0 = base.cursor()
        env0 = api.Environment(cr0, SUPERUSER_ID, {})
        a = env0['dcasa.camila.campana'].create({'name': 'ZZCM turno A'})
        b = env0['dcasa.camila.campana'].create({'name': 'ZZCM turno B'})
        cr0.commit()
        cr1, cr2 = base.cursor(), base.cursor()
        try:
            env1 = api.Environment(cr1, SUPERUSER_ID, {})
            env2 = api.Environment(cr2, SUPERUSER_ID, {})
            env2['dcasa.camila']._bloquear(b.id)   # B empieza su petición (su foto de la base)
            camila1 = env1['dcasa.camila']
            campana_a = camila1._bloquear(a.id)
            camila1._tomar_turno_de_envio(campana_a)
            ahora = fields.Datetime.now()
            campana_a.write({'estado': 'aprobada', 'enviando_desde': ahora, 'aprobada_en': ahora})
            cr1.commit()   # como transaccion.confirmar: A sigue hablando con Resend
            with self.assertRaisesRegex(UserError, 'Otra campaña se está enviando'):
                env2['dcasa.camila']._tomar_turno_de_envio(env2['dcasa.camila.campana'].browse(b.id))
            camila1._soltar_turno_de_envio()
        finally:
            for cr in (cr1, cr2):
                cr.rollback()
                cr.execute('SELECT pg_advisory_unlock_all()')
                cr.close()
            cr0.execute('DELETE FROM dcasa_camila_campana WHERE id IN %s', [(a.id, b.id)])
            cr0.commit()
            cr0.close()

    def test_el_turno_se_suelta_aunque_no_salga(self):
        self.permiso(self.ana)
        campana = self.armar()['campana']
        with self.assertRaisesRegex(UserError, 'clave de campañas'):
            self.enviar(campana)
        self.con_clave()
        self.assertTrue(self.enviar(campana)['ok'])
        self.assertTrue(self._libre_desde_otra_conexion(), 'El candado de sesión quedó tomado en la conexión')

    def test_otra_campana_tomando_el_turno_no_deja_enviar(self):
        self.con_clave()
        self.permiso(self.ana)
        campana = self.armar()['campana']
        cr = sql_db.db_connect(self.env.cr.dbname).cursor()
        try:
            cr.execute(SQL('SELECT pg_try_advisory_lock(%s)', ENVIO.LLAVE_ENVIO))
            self.assertTrue(cr.fetchone()[0])
            with self.assertRaisesRegex(UserError, 'Otra campaña se está enviando'):
                self.enviar(campana)
        finally:
            cr.execute('SELECT pg_advisory_unlock_all()')
            cr.rollback()
            cr.close()
        self.assertFalse(self.resend.llamadas, 'Ni siquiera habló con Resend')

    def test_el_segmento_se_limpia_por_tandas(self):
        """Muchos contactos que sobran no alargan una vuelta más allá de la ventana de «enviándose»: salen por
        tandas y se pide volver a tocar «Enviar»."""
        self.con_clave()
        self.permiso(self.ana)
        segmento = self.Camila._segmento(self.Camila._cliente())
        for i in range(3):
            self.resend.contacto(f'viejo{i}.zzcm@example.com', segmentos=[segmento])
        campana = self.armar()['campana']
        with patch.object(ENVIO, 'MAX_SACAR_AL_ENVIAR', 2):
            primera = self.enviar(campana)
            self.assertFalse(primera['ok'])
            self.assertIn('por sacar', primera['mensaje'])
            self.assertFalse(self.resend.broadcasts)
            segunda = self.enviar(self.panel(campana['id']))
        self.assertTrue(segunda['ok'], segunda)
        (broadcast,) = self.resend.broadcasts.values()
        self.assertEqual(broadcast['enviado_a'], ['ana.zzcm@example.com'])


# ----------------------------------------------------------------------
# 2-6 (MEDIA). El registro del tope por cliente
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestRegistroDelTope(Revision2Comun):

    def enviada_de_la_etapa1(self, dias):
        return self.env['dcasa.camila.campana'].sudo().create({
            'name': 'ZZCM etapa 1', 'estado': 'enviada', 'enviada_en': fields.Datetime.now() - timedelta(days=dias),
            'destinatarios': 2, 'resend_broadcast_id': 'bc-etapa1'})

    def test_una_campana_de_la_etapa1_sin_registro_cuenta_para_el_tope(self):
        self.con_clave()
        self.permiso(self.ana)
        self.resend.broadcasts['bc-etapa1'] = {'status': 'sent', 'segment_id': 'x'}
        etapa1 = self.enviada_de_la_etapa1(2)
        datos = self.armar()['campana']
        self.assertEqual(datos['publico']['total'], 0, 'Salió una hace 2 días y no se sabe a quién: a nadie')
        self.assertEqual({f['motivo'] for f in datos['publico']['fuera']}, {'reciente'})
        with self.assertRaisesRegex(UserError, 'Nadie de este público puede recibirla ahora'):
            self.enviar(datos)
        etapa1.write({'enviada_en': fields.Datetime.now() - timedelta(days=20)})
        self.assertEqual(self.panel(datos['id'])['publico']['total'], 1, 'Pasados los 15 días, ya no cuenta')

    def test_la_migracion_registra_las_enviadas_de_la_etapa1(self):
        self.permiso(self.ana, self.beto)
        reciente = self.enviada_de_la_etapa1(4)
        vieja = self.enviada_de_la_etapa1(30)
        self.Camila._registrar_enviadas_sin_registro()
        self.assertEqual(sorted(reciente.destinatario_ids.mapped('correo')),
                         ['ana.zzcm@example.com', 'beto.zzcm@example.com'])
        self.assertEqual(set(reciente.destinatario_ids.mapped('enviada_en')), {reciente.enviada_en})
        self.assertFalse(vieja.destinatario_ids, 'Fuera de los 15 días no hace falta')
        self.Camila._registrar_enviadas_sin_registro()   # dos veces no duplica
        self.assertEqual(len(reciente.destinatario_ids), 2)
        self.assertEqual(self.Camila._correos_recientes(), {'ana.zzcm@example.com', 'beto.zzcm@example.com'})

    def test_cancelada_en_resend_despues_de_salir_no_suelta_el_registro(self):
        self.con_clave()
        self.permiso(self.ana)
        datos = self.armar()['campana']
        original = RC.ClienteCampanas.enviar_broadcast

        def enviar_y_cortar(cliente, broadcast_id):
            original(cliente, broadcast_id)
            raise RC.ErrorResend('Resend no respondió (ReadTimeout).', temporal=True)

        with patch.object(RC.ClienteCampanas, 'enviar_broadcast', enviar_y_cortar):
            self.assertFalse(self.enviar(datos)['ok'])
        campana = self.campana(datos)
        self.assertTrue(campana.envio_intentado)
        (broadcast,) = self.resend.broadcasts.values()
        broadcast['status'] = 'canceled'   # la cancelaron en Resend cuando ya había salido a una parte
        self.assertFalse(self.enviar(datos)['ok'])
        self.assertIn('ana.zzcm@example.com', self.Camila._correos_recientes(), 'A Ana le llegó: cuenta')

    def test_send_con_error_pero_salio_queda_registrada(self):
        self.con_clave()
        self.permiso(self.ana)
        datos = self.armar()['campana']
        pendiente = {}

        def enviar_con_error(cliente, broadcast_id):
            pendiente['id'] = broadcast_id   # Resend lo aceptó y lo procesa, pero contestó 500
            raise RC.ErrorResend('Resend respondió 500: Internal error', estado=500, temporal=True)

        with patch.object(RC.ClienteCampanas, 'enviar_broadcast', enviar_con_error):
            self.assertFalse(self.enviar(datos)['ok'])
        campana = self.campana(datos)
        self.assertEqual(campana.destinatario_ids.mapped('correo'), ['ana.zzcm@example.com'],
                         'Se llamó a «send»: el registro se queda (el estado de Resend puede tardar)')
        broadcast = self.resend.broadcasts[pendiente['id']]
        broadcast.update(status='sent', enviado_a=['ana.zzcm@example.com'])
        resultado = self.enviar(datos)
        self.assertTrue(resultado['ok'])
        self.assertEqual((campana.estado, campana.destinatarios), ('enviada', 1), resultado)
        self.assertIn('ana.zzcm@example.com', self.Camila._correos_recientes())

    def test_ya_salio_sin_registro_registra_lo_que_habia_en_el_segmento(self):
        self.con_clave()
        self.permiso(self.ana, self.beto)
        datos = self.armar()['campana']
        self.resend.fallar.append(('POST', r'/send$', 503, 'Unavailable'))
        self.assertFalse(self.enviar(datos)['ok'])
        self.resend.fallar.clear()
        campana = self.campana(datos)
        campana.destinatario_ids.unlink()   # p. ej. una campaña aprobada antes de este arreglo
        (broadcast,) = self.resend.broadcasts.values()
        broadcast['status'] = 'sent'
        self.assertTrue(self.enviar(datos)['ok'])
        self.assertEqual(sorted(campana.destinatario_ids.mapped('correo')),
                         ['ana.zzcm@example.com', 'beto.zzcm@example.com'])
        self.assertEqual(campana.destinatarios, 2)

    def test_sin_llamar_a_send_el_registro_se_suelta(self):
        self.con_clave()
        self.permiso(self.ana)
        datos = self.armar()['campana']
        self.resend.fallar.append(('POST', r'/broadcasts$', 503, 'Unavailable'))
        self.assertFalse(self.enviar(datos)['ok'])
        campana = self.campana(datos)
        self.assertFalse(campana.envio_intentado)
        self.assertFalse(campana.destinatario_ids)
        self.assertEqual(campana.estado, 'borrador')

    def test_todavia_saliendo_mira_todas_las_que_tienen_broadcast(self):
        self.con_clave()
        self.permiso(self.ana)
        x = self.armar()['campana']   # la de id más bajo
        hace_un_dia = fields.Datetime.now() - timedelta(days=1)
        for i in range(3):
            y = self.armar()['campana']
            self.resend.broadcasts[f'bc-y{i}'] = {'status': 'sent', 'segment_id': 'x'}
            self.campana(y).sudo().write({'estado': 'enviada', 'enviada_en': hace_un_dia,
                                          'resend_broadcast_id': f'bc-y{i}'})
            self.env['dcasa.camila.destinatario'].sudo().create({   # salieron a otra persona
                'campana_id': y['id'], 'correo': f'otro{i}.zzcm@example.com', 'enviada_en': hace_un_dia})
        self.resend.estado_al_enviar = 'queued'
        self.assertTrue(self.enviar(self.panel(x['id']))['ok'])   # X sale después y sigue «queued»
        self.permiso(self.beto)
        z = self.armar()['campana']
        self.resend.estado_al_enviar = 'sent'
        resultado = self.enviar(z)
        self.assertFalse(resultado['ok'], 'X sigue «queued» en Resend: Z no debía tocar el segmento')
        self.assertIn('todavía está saliendo', resultado['mensaje'])

    def test_un_borrador_borrado_en_resend_no_traba_nada(self):
        self.con_clave()
        self.permiso(self.ana)
        trabada = self.armar()['campana']
        self.resend.fallar.append(('POST', r'/send$', 503, 'Unavailable'))
        self.assertFalse(self.enviar(trabada)['ok'])
        self.resend.fallar.clear()
        campana = self.campana(trabada)
        self.resend.broadcasts.pop(campana.resend_broadcast_id)   # alguien lo borró en el panel de Resend
        self.permiso(self.beto)
        otra = self.armar()['campana']
        resultado = self.enviar(otra)
        self.assertTrue(resultado['ok'], resultado)
        # El reintento de la trabada: sin broadcast (vuelve a armarlo) y sin soltar el registro antes de tiempo.
        resultado = self.enviar(self.panel(trabada['id']))
        self.assertTrue(resultado['ok'], resultado)
        self.assertEqual(campana.estado, 'enviada')
        self.assertIn('ana.zzcm@example.com', campana.destinatario_ids.mapped('correo'))

    def test_un_borrador_borrado_en_resend_se_puede_descartar(self):
        self.con_clave()
        self.permiso(self.ana)
        trabada = self.armar()['campana']
        self.resend.fallar.append(('POST', r'/send$', 503, 'Unavailable'))
        self.enviar(trabada)
        self.resend.fallar.clear()
        campana = self.campana(trabada)
        self.resend.broadcasts.pop(campana.resend_broadcast_id)
        self.Camila.with_user(self.gerencia).descartar(campana.id)
        self.assertEqual(campana.estado, 'cancelada')

    def test_se_registran_todos_los_que_quedaron_en_el_segmento(self):
        self.con_clave()
        self.permiso(self.ana, self.beto)
        datos = self.armar()['campana']
        original = RC.ClienteCampanas.contactos_del_segmento
        llamadas = {'n': 0}

        def listado_con_retraso(cliente, segmento_id):
            filas = original(cliente, segmento_id)
            llamadas['n'] += 1
            if llamadas['n'] == 2:   # la revisión final: Resend todavía no lista a Beto (recién agregado)
                filas = [f for f in filas if f['email'] != 'beto.zzcm@example.com']
            return filas

        with patch.object(RC.ClienteCampanas, 'contactos_del_segmento', listado_con_retraso):
            self.assertTrue(self.enviar(datos)['ok'])
        (broadcast,) = self.resend.broadcasts.values()
        self.assertEqual(set(broadcast['enviado_a']), set(self.campana(datos).destinatario_ids.mapped('correo')))


# ----------------------------------------------------------------------
# 7-11 (BAJA)
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestRevision2Baja(Revision2Comun):

    def test_el_reintento_no_manda_precios_viejos(self):
        self.con_clave()
        self.permiso(self.ana)
        datos = self.armar()['campana']
        self.resend.fallar.append(('POST', r'/send$', 503, 'Unavailable'))
        self.assertFalse(self.enviar(datos)['ok'])
        self.resend.fallar.clear()
        campana = self.campana(datos)
        viejo = campana.resend_broadcast_id
        precio_viejo = campana.linea_ids[0].precio_texto
        campana.linea_ids[0].producto_id.list_price = 999.0
        resultado = self.Camila.with_user(self.marketing).enviar(datos['id'], datos['huella'])
        self.assertFalse(resultado['ok'])
        self.assertTrue(resultado.get('cambio'), 'Cambió el precio: se muestra la versión nueva antes de enviar')
        self.assertNotIn(viejo, self.resend.broadcasts, 'El borrador viejo se borra en Resend')
        self.assertFalse(campana.resend_broadcast_id)
        resultado = self.enviar(self.panel(datos['id']))
        self.assertTrue(resultado['ok'], resultado)
        (broadcast,) = self.resend.broadcasts.values()
        self.assertNotIn(precio_viejo, broadcast['html'])
        self.assertIn('999', broadcast['html'])

    def test_la_ia_respeta_el_tope_por_persona(self):
        datos = self.armar()['campana']
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('dcasa_brian.tope_por_persona_usd', '0.01')
        ICP.set_param('dcasa_brian.tope_mensual_usd', '10000000')
        self.env['brian.uso'].with_user(self.marketing).sudo().create({
            'modelo': 'prueba', 'tokens_entrada': 50_000_000, 'tokens_salida': 5_000_000})
        self.guion_ia(asunto='Lo nuevo para tu sala')
        resultado = self.Camila.with_user(self.marketing).escribir(datos['id'], 'asunto')
        self.assertFalse(resultado['ok'])
        self.assertIn('tu tope de gasto de IA', resultado['mensaje'])

    def test_vino_del_correo_no_se_escribe_a_mano(self):
        orden = self.env['sale.order'].with_user(self.vendedora).create(
            {'partner_id': self.beto.id, 'dcasa_camila_correo': 'DCN-0999 · Inventado'})
        self.assertFalse(orden.dcasa_camila_correo)
        orden.with_user(self.vendedora).write({'dcasa_camila_correo': 'DCN-0998 · Otro'})
        self.assertFalse(orden.dcasa_camila_correo)
        orden.with_user(self.vendedora).with_context(dcasa_camila_marcar_correo=True).write(
            {'dcasa_camila_correo': 'DCN-0997 · Con contexto'})
        self.assertFalse(orden.dcasa_camila_correo, 'Un contexto que llega por RPC tampoco sirve')
        orden.sudo().write({'dcasa_camila_correo': 'DCN-0996 · Con sudo'})
        self.assertFalse(orden.dcasa_camila_correo, 'Solo lo escribe Camila')

    def test_la_revision_de_marca_atrapa_lo_que_dejaba_pasar(self):
        frases = [
            'Quedan pocas, corre por la tuya',
            'Llévatela hoy y págala en partes',
            'Te la apartamos con abonos',
            'Págala con Tafi o Crediviva',
            'Te la llevamos a tu casa sin pagar extra',
            'Te la dejamos regalada',
            'El sofá más cómodo de Panamá',
            'Lo más top para tu sala',
            'A todos nuestros clientes les encanta',
            'Nuestros clientes dicen que es comodísimo',
            'Precios bajísimos esta quincena',
            'Black Friday en tu sala',
            'Le va a encantar a su familia',
            'No te lo pierdas antes de que vuele',
            'Te dura toda la vida',
            'Precio de locura',
            'Visita dcasaofertasya punto com',
            'Escríbenos al seis cero dos seis',
            'Hasta la mitad',
        ]
        pasan = [f for f in frases if not R.problemas(f, R.MAX_LINEA)]
        self.assertFalse(pasan)
        # Lo de siempre sigue pasando (de tú, sin cifras ni promesas).
        for buena in ('Para tu sala, cómoda y firme.', 'Te va a encantar en tu recámara.',
                      'Su tela es suave y fácil de limpiar.', R.ASUNTO_FIJO, R.ENTRADA_FIJA,
                      *R.LINEAS_FIJAS.values()):
            self.assertEqual(R.problemas(buena, R.MAX_ENTRADA), [], buena)

    def test_marketing_no_lee_quien_llego_por_el_correo(self):
        self.con_clave()
        self.permiso(self.ana)
        datos = self.armar()['campana']
        self.assertTrue(self.enviar(datos)['ok'])
        conversacion = self.env['dcasa.conversacion'].sudo().create({'canal': 'whatsapp_qr',
                                                                     'id_externo': '50760009999'})
        self.env['dcasa.camila.llegada'].sudo().create({
            'campana_id': datos['id'], 'conversacion_id': conversacion.id, 'partner_id': self.ana.id,
            'ts': fields.Datetime.now()})
        with self.assertRaises(AccessError):
            self.env['dcasa.camila.llegada'].with_user(self.marketing).search_read([], ['partner_id'])
        self.assertTrue(self.env['dcasa.camila.llegada'].with_user(self.gerencia).search_read([], ['partner_id']))
        historial = self.Camila.with_user(self.marketing).panel()['historial']
        self.assertEqual(historial[0]['chats'], 1, 'Marketing sigue viendo cuántos')
