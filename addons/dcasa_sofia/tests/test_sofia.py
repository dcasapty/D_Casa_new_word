"""Sofía revisa el CRM y propone; una persona aprueba (pedido de la dueña, 2026-11-05)."""
from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import fields
from odoo.addons.dcasa_conversaciones.models import crm_reglas as CRM
from odoo.addons.dcasa_conversaciones.tests.common import JuanCase
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged

AHORA = '2026-11-05 15:00:00'   # 10:00 a. m. en Panamá: dentro del horario


@tagged('post_install', '-at_install')
@freeze_time(AHORA)
class TestSofia(JuanCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora2 = new_test_user(cls.env, login='sofia_vendedora2', name='Luisa Segunda',
                                       groups='base.group_user,sales_team.group_sale_salesman')
        cls.Sofia = cls.env['dcasa.sofia']
        cls.Propuesta = cls.env['dcasa.sofia.propuesta']
        cls.producto = cls.env['product.product'].create({'name': 'Sofá de prueba Sofía', 'list_price': 300.0})

    # ------------------------------------------------------------------
    # Datos de prueba
    # ------------------------------------------------------------------

    def cliente(self, nombre, telefono, canal='whatsapp_qr', temperatura=CRM.CALIENTE, vendedora=None,
                horas_sin_escribir=5, estado='bot', autor='bot', asignada=None, correo=False, interes='sofá gris'):
        """Un cliente con su conversación y su oportunidad (como las deja Juan)."""
        ahora = fields.Datetime.now()
        partner = self.Partner.create({'name': nombre, 'phone': telefono, 'email': correo})
        ultimo = ahora - timedelta(hours=horas_sin_escribir) if horas_sin_escribir is not None else False
        conv = self.Conversacion.create({
            'canal': canal, 'id_externo': telefono.replace('+', '').replace(' ', '').replace('-', ''),
            'partner_id': partner.id, 'estado': estado, 'ultimo_mensaje_cliente': ultimo,
            'ultimo_mensaje_autor': autor, 'ultima_actividad': ultimo or ahora,
            'asignada_a': asignada.id if asignada else False})
        lead = self.env['crm.lead'].with_context(dcasa_auto=True).create({
            'name': f'WhatsApp (QR): {interes}', 'type': 'opportunity', 'partner_id': partner.id,
            'user_id': vendedora.id if vendedora else False, 'dcasa_temperatura': temperatura,
            'dcasa_temperatura_motivo': 'pidió cotización'})
        conv.oportunidad_id = lead
        conv.seguimiento_proximo = False
        return partner, conv, lead

    def propuestas(self, **dominio):
        return self.Propuesta.sudo().search(
            [('estado', '=', 'pendiente')] + [(campo, '=', valor) for campo, valor in dominio.items()])

    def analizar(self, usuario=None):
        return self.Sofia.with_user(usuario or self.gerente).analizar()

    # ------------------------------------------------------------------
    # Lo que propone
    # ------------------------------------------------------------------

    def test_al_caliente_sin_datos_le_propone_escribirle_y_pedirle_nombre_y_correo(self):
        partner, conv, lead = self.cliente('🙏', '+507 6000-3001', vendedora=self.vendedora)
        self.analizar()
        propuesta = self.propuestas(lead_id=lead.id, tipo='escribir')
        self.assertEqual(len(propuesta), 1)
        self.assertTrue(propuesta.pide_datos)
        self.assertEqual(propuesta.usuario_id, self.vendedora)
        self.assertEqual(propuesta.prioridad, 3)
        texto = self.Sofia.with_user(self.vendedora)._texto(propuesta, self.vendedora)
        self.assertTrue(texto.startswith("¡Hola! Soy Vendedora de D'CASA."), texto)
        self.assertIn('sofá gris', texto)
        self.assertIn('tu nombre y apellido y tu correo', texto)
        self.assertIn('programa Socios', texto)
        self.assertNotIn('{', texto)
        self.assertNotIn('$', texto, 'nunca cifras')
        self.assertNotIn('🙏', texto)

    def test_al_tibio_con_sus_datos_solo_le_propone_el_seguimiento(self):
        partner, conv, lead = self.cliente('Carla Méndez', '+507 6000-3002', temperatura=CRM.TIBIO,
                                           vendedora=self.vendedora2, correo='carla.mendez@example.com')
        lead.dcasa_para_cuando = 'fin de mes'
        self.analizar()
        propuesta = self.propuestas(lead_id=lead.id)
        self.assertEqual(propuesta.tipo, 'escribir')
        self.assertFalse(propuesta.pide_datos)
        self.assertEqual(propuesta.plantilla, 'seguimiento_cuando')
        self.assertEqual(propuesta.prioridad, 2)
        texto = self.Sofia._texto(propuesta, self.vendedora2)
        self.assertIn('¡Hola Carla!', texto)
        self.assertIn('fin de mes', texto)
        self.assertNotIn('correo', texto)

    def test_si_ya_le_escribieron_hoy_y_le_faltan_datos_propone_pedirlos(self):
        partner, conv, lead = self.cliente('Luz', '+507 6000-3003', vendedora=self.vendedora,
                                           correo='luz@example.com')
        self.Mensaje.create({'conversacion_id': conv.id, 'id_mensaje': 'sofia.1', 'direccion': 'saliente',
                             'autor': 'vendedora', 'tipo': 'mensaje', 'texto': 'Hola Luz',
                             'ts': fields.Datetime.now() - timedelta(hours=2), 'usuario_id': self.vendedora.id,
                             'estado_envio': 'enviado'})
        self.analizar()
        propuesta = self.propuestas(partner_id=partner.id)
        self.assertEqual(propuesta.tipo, 'pedir_datos')
        texto = self.Sofia._texto(propuesta, self.vendedora)
        self.assertIn('¡Hola Luz!', texto)
        self.assertIn('tu nombre y apellido', texto)
        self.assertNotIn('tu correo', texto)

    def test_no_se_mete_con_juan(self):
        """Ni mientras Juan conversa, ni si Juan ya tiene su seguimiento en camino, ni con quien pidió que no le
        escriban. Y revisar no cambia nada: ni conversaciones, ni oportunidades."""
        _p1, conv1, lead1 = self.cliente('🌸', '+507 6000-3004', vendedora=self.vendedora, horas_sin_escribir=0.5)
        _p2, conv2, lead2 = self.cliente('Ana Juan', '+507 6000-3005', vendedora=self.vendedora)
        conv2.seguimiento_proximo = fields.Datetime.now() + timedelta(hours=1)   # Juan está por escribirle
        p3, _conv3, lead3 = self.cliente('No Escribir', '+507 6000-3006', vendedora=self.vendedora)
        p3.dcasa_no_contactar = True
        antes = [(c.estado, c.asignada_a, c.seguimiento_proximo, c.borrador) for c in (conv1, conv2)]
        etapas = [(lead.stage_id, lead.user_id, lead.dcasa_temperatura) for lead in (lead1, lead2, lead3)]
        self.analizar()
        for lead in (lead1, lead2, lead3):
            self.assertFalse(self.propuestas(lead_id=lead.id).filtered(lambda p: p.tipo != 'sincronizar'))
        self.assertEqual(antes, [(c.estado, c.asignada_a, c.seguimiento_proximo, c.borrador) for c in (conv1, conv2)])
        self.assertEqual(etapas, [(lead.stage_id, lead.user_id, lead.dcasa_temperatura)
                                  for lead in (lead1, lead2, lead3)])
        self.assertFalse(self.Mensaje.search([('conversacion_id', 'in', (conv1 | conv2).ids)]),
                         'Sofía no le escribe a nadie por su cuenta')

    def test_si_juan_le_escribe_mas_adelante_lo_propone_y_avisa(self):
        _p, conv, lead = self.cliente('Ana Pronto', '+507 6000-3026', vendedora=self.vendedora,
                                      correo='ana.pronto@example.com')
        conv.seguimiento_proximo = fields.Datetime.now() + timedelta(days=2)
        self.analizar()
        propuesta = self.propuestas(lead_id=lead.id)
        self.assertEqual(propuesta.tipo, 'escribir')
        self.assertIn('Juan le iba a escribir solo el 07/11', propuesta.motivo)
        self.assertEqual(conv.seguimiento_proximo, fields.Datetime.now() + timedelta(days=2), 'no se toca')

    def test_pasadas_las_24_horas_de_meta_propone_llamarlo(self):
        partner, conv, lead = self.cliente('Pedro Messenger', '+507 6000-3007', canal='messenger',
                                           vendedora=self.vendedora, horas_sin_escribir=30)
        self.analizar()
        propuesta = self.propuestas(partner_id=partner.id)
        self.assertEqual(propuesta.tipo, 'llamar')
        self.assertIn('+507 6000-3007', propuesta.titulo)

    def test_contestar_a_quien_espera_a_una_persona(self):
        partner, conv, lead = self.cliente('Rosa Espera', '+507 6000-3008', vendedora=self.vendedora, estado='humano',
                                           autor='cliente', asignada=self.vendedora, horas_sin_escribir=3,
                                           correo='rosa@example.com')
        self.analizar()
        propuesta = self.propuestas(partner_id=partner.id)
        self.assertEqual(propuesta.tipo, 'contestar')
        self.assertEqual(propuesta.usuario_id, self.vendedora)
        self.assertEqual(propuesta.prioridad, 3)

    def test_recordar_la_cotizacion_que_vence(self):
        partner, conv, lead = self.cliente('Marta Cotiza', '+507 6000-3009', temperatura=CRM.FRIO,
                                           vendedora=self.vendedora, correo='marta@example.com')
        orden = self.env['sale.order'].create({
            'partner_id': partner.id, 'opportunity_id': lead.id, 'user_id': self.vendedora.id,
            'order_line': [(0, 0, {'product_id': self.producto.id, 'product_uom_qty': 1})]})
        orden.validity_date = self.env['dcasa.reparto']._hoy()
        self.analizar()
        propuesta = self.propuestas(partner_id=partner.id)
        self.assertEqual(propuesta.tipo, 'vence')
        self.assertEqual(propuesta.orden_id, orden)
        texto = self.Sofia._texto(propuesta, self.vendedora)
        self.assertIn(orden.name, texto)
        self.assertIn(orden.validity_date.strftime('%d/%m/%Y'), texto)

    # ------------------------------------------------------------------
    # «Guarda sus datos»
    # ------------------------------------------------------------------

    def mensaje(self, conv, texto, horas, autor='cliente', usuario=None):
        entrante = autor == 'cliente'
        return self.Mensaje.create({
            'conversacion_id': conv.id, 'id_mensaje': f'sofia.datos.{conv.id}.{horas}.{autor}',
            'direccion': 'entrante' if entrante else 'saliente', 'autor': autor, 'tipo': 'mensaje', 'texto': texto,
            'ts': fields.Datetime.now() - timedelta(hours=horas), 'usuario_id': usuario.id if usuario else False})

    def test_guarda_los_datos_que_contesto_cuando_se_los_pidieron(self):
        partner, conv, lead = self.cliente('🙏', '+507 6000-3061', vendedora=self.vendedora)
        self.mensaje(conv, "¡Hola! Soy Vendedora de D'CASA. ¿Me regalas tu nombre y apellido y tu correo? Si quieres, "
                           "dime también el día y el mes de tu cumpleaños.", 6, autor='vendedora',
                     usuario=self.vendedora)
        self.mensaje(conv, 'ingrid DE LA pérez\nIngrid.P@Example.com\n12/03', 5)
        fichas_antes = self.Partner.search_count([])
        self.analizar()
        propuesta = self.propuestas(partner_id=partner.id, tipo='guardar_datos')
        self.assertEqual(len(propuesta), 1)
        self.assertEqual(propuesta.datos['campos'],
                         {'nombre': 'Ingrid de la Pérez', 'correo': 'ingrid.p@example.com', 'cumple': '03-12'})
        self.assertEqual(propuesta.usuario_id, self.vendedora)
        self.assertEqual(propuesta.prioridad, 2)
        self.assertIn('Ingrid de la Pérez', propuesta.titulo)
        # La vendedora la ve con lo que escribió y lo que hoy dice su ficha.
        fila = next(f for f in self.Sofia.with_user(self.vendedora).panel()['propuestas'] if f['id'] == propuesta.id)
        self.assertEqual(fila['campos']['cumple'], '03-12')
        self.assertEqual(fila['antes']['nombre'], '🙏')
        self.assertEqual(fila['acciones'], ['guardar'])
        # Un clic: todo a su ficha, con nuestro formato, sin crear ninguna ficha nueva.
        resultado = self.Sofia.with_user(self.vendedora).aplicar(propuesta.id, 'guardar')
        self.assertEqual(resultado['resultado'], 'Guardado en su ficha.')
        self.assertEqual(partner.name, 'Ingrid de la Pérez')
        self.assertEqual(partner.email, 'ingrid.p@example.com')
        self.assertEqual(partner.dcasa_cumple, '03-12')
        self.assertEqual(propuesta.estado, 'aplicada')
        self.assertEqual(self.Partner.search_count([]), fichas_antes, 'nunca crea fichas')
        nota = partner.message_ids[0].body
        self.assertIn('Sofía guardó', nota)
        self.assertIn('🙏', nota, 'el antes queda escrito en la ficha')
        # Ya no hay nada que pedirle ni que guardar.
        with freeze_time('2026-11-05 15:05:00'):
            self.analizar()
        self.assertFalse(self.propuestas(partner_id=partner.id, tipo='guardar_datos'))
        self.assertFalse(self.propuestas(partner_id=partner.id, tipo='pedir_datos'))

    def test_si_ya_se_los_pidieron_en_el_chat_no_se_los_vuelve_a_pedir(self):
        partner, conv, lead = self.cliente('🙏', '+507 6000-3062', vendedora=self.vendedora)
        self.mensaje(conv, '¿Me regalas tu nombre y apellido y tu correo?', 30, autor='vendedora',
                     usuario=self.vendedora)
        self.analizar()
        self.assertFalse(self.propuestas(partner_id=partner.id, tipo='pedir_datos'))
        escribir = self.propuestas(lead_id=lead.id, tipo='escribir')
        self.assertTrue(escribir, 'el seguimiento sí: nadie le escribió en 24 horas')
        self.assertFalse(escribir.pide_datos, 'sin volver a pedirle sus datos')

    def test_sin_que_se_los_pidan_solo_lee_lo_que_dice_claro(self):
        p1, conv1, _l1 = self.cliente('🌸', '+507 6000-3063', temperatura=CRM.FRIO)
        self.mensaje(conv1, 'Hola, me llamo carla ruiz y mi correo es Carla.Ruiz@Example.com', 3)
        p2, conv2, _l2 = self.cliente('😊', '+507 6000-3064', temperatura=CRM.FRIO)
        self.mensaje(conv2, 'Ana Pérez', 3)   # una línea suelta: nadie le pidió su nombre
        self.mensaje(conv2, 'Lo quiero para el 15/12, cumple con lo que busco', 2)
        self.analizar()
        propuesta = self.propuestas(partner_id=p1.id, tipo='guardar_datos')
        self.assertEqual(propuesta.datos['campos'], {'nombre': 'Carla Ruiz', 'correo': 'carla.ruiz@example.com'})
        self.assertEqual(propuesta.prioridad, 1)
        self.assertFalse(self.propuestas(partner_id=p2.id, tipo='guardar_datos'))

    def test_no_pisa_lo_bueno_ni_duplica_un_correo(self):
        partner, conv, _lead = self.cliente('Pedro Gómez', '+507 6000-3065', vendedora=self.vendedora)
        otra = self.Partner.create({'name': 'Pedro Otra Ficha', 'email': 'pedro.gomez@example.com'})
        self.mensaje(conv, 'Me llamo Pedro Gómez Castillo, mi correo es pedro.gomez@example.com y cumplo el 5 de mayo',
                     3)
        self.analizar()
        propuesta = self.propuestas(partner_id=partner.id, tipo='guardar_datos')
        self.assertEqual(propuesta.datos['campos'], {'cumple': '05-05'}, 'su nombre ya sirve; el correo es de otra')
        self.assertIn(otra.name, propuesta.motivo)
        fila = next(f for f in self.Sofia.with_user(self.vendedora).panel()['propuestas'] if f['id'] == propuesta.id)
        self.assertIn('Posibles duplicados', fila['aviso'])
        # Lo que Sofía no propuso no se cuela desde la pantalla.
        with self.assertRaises(UserError):
            self.Sofia.with_user(self.vendedora).aplicar(propuesta.id, 'guardar',
                                                          campos={'correo': 'pedro.gomez@example.com'})
        self.Sofia.with_user(self.vendedora).aplicar(propuesta.id, 'guardar')
        self.assertEqual(partner.name, 'Pedro Gómez')
        self.assertFalse(partner.email)
        self.assertEqual(partner.dcasa_cumple, '05-05')
        self.assertFalse(otra.dcasa_cumple)

    def test_el_nombre_de_una_empresa_no_se_cambia(self):
        partner, conv, _lead = self.cliente('Muebles y Más S.A.', '+507 6000-3066')
        partner.is_company = True
        self.mensaje(conv, 'Me llamo Rosa Díaz, compras', 3)
        self.analizar()
        self.assertFalse(self.propuestas(partner_id=partner.id, tipo='guardar_datos'))

    def test_al_guardar_corrige_el_formato_valida_y_revisa_otra_vez(self):
        partner, conv, _lead = self.cliente('❤️', '+507 6000-3067', vendedora=self.vendedora)
        self.mensaje(conv, 'Me llamo maría ruiz, mi correo es maria.ruiz@example.com y cumplo el 29 de febrero', 3)
        self.analizar()
        propuesta = self.propuestas(partner_id=partner.id, tipo='guardar_datos')
        self.assertEqual(set(propuesta.datos['campos']), {'nombre', 'correo', 'cumple'})
        Sofia = self.Sofia.with_user(self.vendedora)
        malos = [
            {'nombre': '🙏🙏'},
            {'nombre': 'Dios te bendiga'},
            {'correo': 'maria@gmial'},
            {'correo': self.vendedora.partner_id.email or 'vendedora@dcasa.example.com'},
            {'cumple': '02-30'},
            {'cumple': '29/02'},
            {'nombre': 'x' * 200},
            {'telefono': '6000-0000'},
            {'nombre': 5},
            ['nombre'],
        ]
        self.vendedora.partner_id.email = self.vendedora.partner_id.email or 'vendedora@dcasa.example.com'
        for campos in malos:
            with self.subTest(campos=campos), self.assertRaises(UserError):
                Sofia.aplicar(propuesta.id, 'guardar', campos=campos)
        with self.assertRaises(UserError):
            Sofia.aplicar(propuesta.id, 'guardar', campos={'nombre': '', 'correo': '', 'cumple': ''})
        self.assertEqual(propuesta.estado, 'pendiente', 'un dato mal escrito no la resuelve')
        # Mientras tanto otra ficha quedó con ese correo: no se duplica (y lo demás se puede guardar sin él).
        self.Partner.create({'name': 'María Repetida', 'email': 'maria.ruiz@example.com'})
        with self.assertRaisesRegex(UserError, 'Posibles duplicados'):
            Sofia.aplicar(propuesta.id, 'guardar')
        resultado = Sofia.aplicar(propuesta.id, 'guardar', campos={
            'nombre': '  MARÍA  de los ángeles RUIZ ', 'correo': '', 'cumple': '02-29'})
        self.assertEqual(partner.name, 'María de los Ángeles Ruiz')
        self.assertFalse(partner.email)
        self.assertEqual(partner.dcasa_cumple, '02-29')
        self.assertEqual(propuesta.estado, 'aplicada')
        self.assertEqual(resultado['resultado'], 'Guardado en su ficha.')

    def test_si_alguien_ya_lo_guardo_no_lo_pisa(self):
        partner, conv, _lead = self.cliente('⭐', '+507 6000-3068', vendedora=self.vendedora)
        self.mensaje(conv, 'Me llamo Rosa Díaz y mi correo es rosa.diaz@example.com', 3)
        self.analizar()
        propuesta = self.propuestas(partner_id=partner.id, tipo='guardar_datos')
        partner.write({'email': 'rosa@example.com'})   # alguien lo escribió a mano en su ficha
        resultado = self.Sofia.with_user(self.vendedora).aplicar(propuesta.id, 'guardar')
        self.assertEqual(partner.email, 'rosa@example.com')
        self.assertEqual(partner.name, 'Rosa Díaz')
        self.assertIn('Ya tenía su correo', resultado['resultado'])
        # Y si ya tenía todo, no hace nada: «ya no hacía falta».
        p2, conv2, _l2 = self.cliente('🌙', '+507 6000-3069', vendedora=self.vendedora)
        self.mensaje(conv2, 'Me llamo Luna Vega', 3)
        with freeze_time('2026-11-05 15:05:00'):   # el botón no vuelve a revisar en el mismo minuto
            self.analizar()
        propuesta2 = self.propuestas(partner_id=p2.id, tipo='guardar_datos')
        p2.name = 'Luna Vega Castillo'
        resultado = self.Sofia.with_user(self.vendedora).aplicar(propuesta2.id, 'guardar')
        self.assertTrue(resultado.get('ya_no_hace_falta'))
        self.assertEqual(p2.name, 'Luna Vega Castillo')
        self.assertEqual(propuesta2.estado, 'vencida')

    def test_otra_vendedora_no_guarda_los_datos_de_tu_cliente(self):
        partner, conv, _lead = self.cliente('🎈', '+507 6000-3070', vendedora=self.vendedora)
        self.mensaje(conv, 'Me llamo Sara Mora', 3)
        self.analizar()
        propuesta = self.propuestas(partner_id=partner.id, tipo='guardar_datos')
        with self.assertRaises(AccessError):
            self.Sofia.with_user(self.vendedora2).aplicar(propuesta.id, 'guardar')
        self.assertEqual(partner.name, '🎈')

    def test_las_de_guardar_correo_de_antes_siguen_funcionando(self):
        partner, conv, _lead = self.cliente('Ana Correo', '+507 6000-3071', vendedora=self.vendedora)
        propuesta = self.Propuesta.sudo().create({
            'clave': f'guardar_correo:partner:{partner.id}', 'tipo': 'guardar_correo', 'prioridad': 1,
            'usuario_id': self.vendedora.id, 'partner_id': partner.id, 'conversacion_id': conv.id,
            'titulo': 'Guarda su correo', 'datos': {'correo': 'ana.correo@example.com'}})
        self.Sofia.with_user(self.vendedora).aplicar(propuesta.id, 'guardar')
        self.assertEqual(partner.email, 'ana.correo@example.com')
        self.assertEqual(propuesta.estado, 'aplicada')

    def test_repartir_y_sincronizar_solo_para_gerencia(self):
        _p1, conv1, sin_duena = self.cliente('Sin Vendedora', '+507 6000-3011')
        _p2, conv2, otra = self.cliente('Otra Vendedora', '+507 6000-3012', vendedora=self.vendedora2,
                                        asignada=self.vendedora)
        self.analizar()
        asignar = self.propuestas(lead_id=sin_duena.id, tipo='asignar')
        sincronizar = self.propuestas(lead_id=otra.id, tipo='sincronizar')
        self.assertTrue(asignar.solo_gerencia and sincronizar.solo_gerencia)
        self.assertIn(asignar.destino_id, self.vendedora | self.vendedora2)
        self.assertEqual(sincronizar.destino_id, self.vendedora)
        # La vendedora no las ve ni las puede aprobar.
        vistas = {p['id'] for p in self.Sofia.with_user(self.vendedora).panel()['propuestas']}
        self.assertFalse(vistas & {asignar.id, sincronizar.id})
        with self.assertRaises(AccessError):
            self.Sofia.with_user(self.vendedora).aplicar(asignar.id, 'asignar')
        # Gerencia sí: la oportunidad pasa a la vendedora y lo demás pendiente de ella también.
        escribir = self.propuestas(lead_id=sin_duena.id, tipo='escribir')
        self.assertFalse(escribir.usuario_id)
        resultado = self.Sofia.with_user(self.gerente).aplicar(asignar.id, 'asignar')
        self.assertIn(asignar.destino_id.name, resultado['resultado'])
        self.assertEqual(sin_duena.user_id, asignar.destino_id)
        self.assertEqual(escribir.usuario_id, asignar.destino_id)
        self.assertIn('Sofía propuso', sin_duena.message_ids[0].body)
        self.assertFalse(conv1.asignada_a, 'el chat no se toca: eso es de Juan')
        # Si alguien se adelantó, no se pisa.
        otra.user_id = self.gerente
        resultado = self.Sofia.with_user(self.gerente).aplicar(sincronizar.id, 'asignar')
        self.assertTrue(resultado.get('ya_no_hace_falta'))
        self.assertEqual(otra.user_id, self.gerente)
        self.assertEqual(sincronizar.estado, 'vencida')

    # ------------------------------------------------------------------
    # Quién ve qué
    # ------------------------------------------------------------------

    def test_cada_vendedora_ve_lo_suyo_y_gerencia_todo(self):
        _p1, _c1, mio = self.cliente('Cliente Uno', '+507 6000-3013', vendedora=self.vendedora)
        _p2, _c2, suyo = self.cliente('Cliente Dos', '+507 6000-3014', vendedora=self.vendedora2)
        self.analizar(self.vendedora)
        ver = lambda u: {p['lead_id'] for p in self.Sofia.with_user(u).panel()['propuestas']}   # noqa: E731
        self.assertIn(mio.id, ver(self.vendedora))
        self.assertNotIn(suyo.id, ver(self.vendedora))
        self.assertIn(suyo.id, ver(self.vendedora2))
        self.assertTrue({mio.id, suyo.id} <= ver(self.gerente))
        ajena = self.propuestas(lead_id=suyo.id)
        with self.assertRaises(AccessError):
            self.Sofia.with_user(self.vendedora).descartar(ajena.id)
        with self.assertRaises(AccessError):
            self.Propuesta.with_user(self.vendedora).browse(ajena.id).write({'estado': 'aplicada'})

    def test_solo_el_equipo_de_ventas(self):
        for usuario in (self.interno, self.portal):
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                self.Sofia.with_user(usuario).panel()
        with self.assertRaises(AccessError):
            self.Sofia.with_user(self.interno).analizar()

    def test_valida_lo_que_le_mandan(self):
        _p, _c, lead = self.cliente('Cliente Valida', '+507 6000-3015', vendedora=self.vendedora)
        self.analizar()
        propuesta = self.propuestas(lead_id=lead.id)
        Sofia = self.Sofia.with_user(self.vendedora)
        for malo in ('1', True, 0, None):
            with self.subTest(malo=malo), self.assertRaises(UserError):
                Sofia.aplicar(malo, 'chat')
        with self.assertRaises(UserError):
            Sofia.aplicar(propuesta.id, 'asignar')
        with self.assertRaises(UserError):
            Sofia.aplicar(propuesta.id, 'enviar', texto='x' * 5000)
        with self.assertRaises(UserError):
            Sofia.aplicar(propuesta.id, 'enviar', texto=['no es texto'])
        with self.assertRaises(UserError):
            Sofia.aplicar(propuesta.id, 'enviar', texto='   ')

    # ------------------------------------------------------------------
    # Aprobar
    # ------------------------------------------------------------------

    def test_abrir_el_chat_con_el_mensaje(self):
        _p, conv, lead = self.cliente('Cliente Chat', '+507 6000-3016', vendedora=self.vendedora)
        self.analizar()
        propuesta = self.propuestas(lead_id=lead.id)
        resultado = self.Sofia.with_user(self.vendedora).aplicar(propuesta.id, 'chat', texto='Hola, ¿seguimos?')
        accion = resultado['accion']
        self.assertEqual(accion['type'], 'ir.actions.client')
        self.assertEqual(accion['params'], {'conversacion_id': conv.id}, 'el texto no viaja en la acción')
        self.assertEqual((resultado['texto'], resultado['conversacion_id']), ('Hola, ¿seguimos?', conv.id))
        self.assertEqual((propuesta.estado, propuesta.accion), ('aplicada', 'chat'))
        self.assertEqual(propuesta.resuelta_por, self.vendedora)
        self.assertFalse(self.Mensaje.search([('conversacion_id', '=', conv.id)]), 'abrir el chat no envía nada')

    def test_enviar_ya_escribe_por_la_misma_ruta_que_el_chat(self):
        partner, conv, lead = self.cliente('🙏', '+507 6000-3017', vendedora=self.vendedora)
        self.analizar()
        propuesta = self.propuestas(lead_id=lead.id)
        texto = self.Sofia._texto(propuesta, self.vendedora)
        resultado = self.Sofia.with_user(self.vendedora).aplicar(propuesta.id, 'enviar', texto=texto)
        self.assertIn('se reintenta solo', resultado['resultado'], 'sin Worker queda por enviar')
        mensaje = self.Mensaje.search([('conversacion_id', '=', conv.id), ('tipo', '=', 'mensaje')])
        self.assertEqual((mensaje.autor, mensaje.texto, mensaje.usuario_id), ('vendedora', texto, self.vendedora))
        self.assertEqual(conv.estado, 'humano', 'como cuando una vendedora escribe: la conversación es suya')
        # Ya se le pidieron sus datos: no se le vuelven a pedir en 30 días.
        with freeze_time('2026-11-07 15:00:00'):
            self.analizar()
            self.assertFalse(self.propuestas(partner_id=partner.id).filtered('pide_datos'))

    def test_un_doble_clic_no_envia_dos_veces(self):
        _p, conv, lead = self.cliente('Doble Clic', '+507 6000-3027', vendedora=self.vendedora,
                                      correo='doble@example.com')
        self.analizar()
        propuesta = self.propuestas(lead_id=lead.id)
        Sofia = self.Sofia.with_user(self.vendedora)
        Sofia.aplicar(propuesta.id, 'enviar', texto='Hola, ¿seguimos?')
        segunda = Sofia.aplicar(propuesta.id, 'enviar', texto='Hola, ¿seguimos?')
        self.assertTrue(segunda['ya_estaba'])
        self.assertEqual(self.Mensaje.search_count([('conversacion_id', '=', conv.id), ('tipo', '=', 'mensaje')]), 1)
        with self.assertRaises(UserError):   # otra persona: ya se resolvió
            self.Sofia.with_user(self.gerente).aplicar(propuesta.id, 'enviar', texto='Hola')

    def test_al_aprobar_revisa_otra_vez(self):
        _p1, conv1, lead1 = self.cliente('Ya Le Escribieron', '+507 6000-3028', vendedora=self.vendedora,
                                         correo='ya@example.com')
        _p2, conv2, lead2 = self.cliente('Juan Va A Escribir', '+507 6000-3029', vendedora=self.vendedora,
                                         correo='juanva@example.com')
        p3, conv3, lead3 = self.cliente('Cotizacion Confirmada', '+507 6000-3030', temperatura=CRM.FRIO,
                                        vendedora=self.vendedora, correo='conf@example.com')
        orden = self.env['sale.order'].create({
            'partner_id': p3.id, 'opportunity_id': lead3.id, 'user_id': self.vendedora.id,
            'order_line': [(0, 0, {'product_id': self.producto.id, 'product_uom_qty': 1})]})
        orden.validity_date = self.env['dcasa.reparto']._hoy()
        self.analizar()
        escribir1 = self.propuestas(lead_id=lead1.id)
        escribir2 = self.propuestas(lead_id=lead2.id)
        vence = self.propuestas(partner_id=p3.id)
        self.assertEqual((escribir1.tipo, escribir2.tipo, vence.tipo), ('escribir', 'escribir', 'vence'))
        self.Mensaje.create({'conversacion_id': conv1.id, 'id_mensaje': 'sofia.4', 'direccion': 'saliente',
                             'autor': 'vendedora', 'tipo': 'mensaje', 'texto': 'Hola', 'ts': fields.Datetime.now(),
                             'usuario_id': self.vendedora.id, 'estado_envio': 'enviado'})
        conv2.seguimiento_proximo = fields.Datetime.now() + timedelta(minutes=30)
        orden.action_confirm()
        Sofia = self.Sofia.with_user(self.vendedora)
        for propuesta, motivo, conv in ((escribir1, 'ya le escribió', conv1), (escribir2, 'Juan está por', conv2),
                                        (vence, 'ya no está por vencer', conv3)):
            with self.subTest(motivo=motivo):
                antes = self.Mensaje.search_count([('conversacion_id', '=', conv.id), ('tipo', '=', 'mensaje')])
                resultado = Sofia.aplicar(propuesta.id, 'enviar', texto='Hola')
                self.assertTrue(resultado['ya_no_hace_falta'])
                self.assertIn(motivo, resultado['resultado'])
                self.assertEqual(propuesta.estado, 'vencida')
                self.assertEqual(antes, self.Mensaje.search_count([('conversacion_id', '=', conv.id),
                                                                   ('tipo', '=', 'mensaje')]))

    def test_nunca_se_cuela_un_precio_en_el_mensaje(self):
        _p, _c, lead = self.cliente('Precio Cuela', '+507 6000-3031', vendedora=self.vendedora,
                                    correo='precio@example.com', interes='sofá gris de $899')
        self.analizar()
        texto = self.Sofia._texto(self.propuestas(lead_id=lead.id), self.vendedora)
        self.assertNotIn('899', texto)
        self.assertNotIn('$', texto)
        self.assertIn('nuestros muebles', texto)

    def test_crear_tarea_no_cuenta_como_datos_pedidos(self):
        partner, _c, lead = self.cliente('🌻', '+507 6000-3032', vendedora=self.vendedora)
        self.analizar()
        propuesta = self.propuestas(lead_id=lead.id)
        self.assertTrue(propuesta.pide_datos)
        self.Sofia.with_user(self.vendedora).aplicar(propuesta.id, 'tarea')
        with freeze_time('2026-11-07 15:00:00'):
            self.Sofia.sudo()._analizar('boton')
            self.assertTrue(self.propuestas(partner_id=partner.id).filtered('pide_datos'),
                            'una tarea no le pidió nada al cliente')

    def test_contestar_a_quien_ya_compro_y_lo_descartado_no_tapa_lo_demas(self):
        partner, conv, lead = self.cliente('Ya Compró', '+507 6000-3033', vendedora=self.vendedora, estado='humano',
                                           autor='cliente', asignada=self.vendedora, horas_sin_escribir=3,
                                           correo='compro@example.com')
        lead.with_context(dcasa_auto=True).action_set_won()
        self.analizar()
        contestar = self.propuestas(partner_id=partner.id)
        self.assertEqual(contestar.tipo, 'contestar')
        self.assertFalse(contestar.lead_id, 'la oportunidad ganada no frena la respuesta')
        resultado = self.Sofia.with_user(self.vendedora).aplicar(contestar.id, 'chat')
        self.assertEqual(resultado['accion']['params'], {'conversacion_id': conv.id})
        # Descartar la cotización que vence no le quita lugar a su seguimiento.
        p2, _c2, lead2 = self.cliente('Vence Descartada', '+507 6000-3034', vendedora=self.vendedora,
                                      correo='vd@example.com')
        orden = self.env['sale.order'].create({
            'partner_id': p2.id, 'opportunity_id': lead2.id, 'user_id': self.vendedora.id,
            'order_line': [(0, 0, {'product_id': self.producto.id, 'product_uom_qty': 1})]})
        orden.validity_date = self.env['dcasa.reparto']._hoy()
        with freeze_time('2026-11-05 15:05:00'):
            self.Sofia.sudo()._analizar('boton')
        vence = self.propuestas(partner_id=p2.id)
        self.assertEqual(vence.tipo, 'vence')
        self.Sofia.with_user(self.vendedora).descartar(vence.id)
        with freeze_time('2026-11-05 15:10:00'):
            self.Sofia.sudo()._analizar('boton')
        self.assertEqual(self.propuestas(partner_id=p2.id).tipo, 'escribir')

    def test_no_envia_pasadas_las_24_horas_ni_a_quien_pidio_que_no(self):
        partner, conv, lead = self.cliente('Instagram Uno', '+507 6000-3018', canal='instagram',
                                           vendedora=self.vendedora, correo='ig@example.com')
        self.analizar()
        propuesta = self.propuestas(lead_id=lead.id)
        self.assertEqual(propuesta.tipo, 'escribir')
        conv.ultimo_mensaje_cliente = fields.Datetime.now() - timedelta(hours=30)
        fila = next(p for p in self.Sofia.with_user(self.vendedora).panel()['propuestas'] if p['id'] == propuesta.id)
        self.assertNotIn('enviar', fila['acciones'])
        self.assertIn('24 horas', fila['aviso'])
        with self.assertRaises(UserError):
            self.Sofia.with_user(self.vendedora).aplicar(propuesta.id, 'enviar', texto='Hola')
        partner.dcasa_no_contactar = True
        resultado = self.Sofia.with_user(self.vendedora).aplicar(propuesta.id, 'chat', texto='Hola')
        self.assertTrue(resultado['ya_no_hace_falta'])
        self.assertFalse(self.Mensaje.search([('conversacion_id', '=', conv.id)]))

    def test_crear_tarea(self):
        _p, _c, lead = self.cliente('Pedro Llamar', '+507 6000-3019', canal='messenger', vendedora=self.vendedora,
                                    horas_sin_escribir=30)
        self.analizar()
        propuesta = self.propuestas(lead_id=lead.id)
        self.Sofia.with_user(self.vendedora).aplicar(propuesta.id, 'tarea')
        actividad = lead.activity_ids
        self.assertEqual(len(actividad), 1)
        self.assertEqual(actividad.user_id, self.vendedora)
        self.assertEqual(actividad.activity_type_id, self.env.ref('mail.mail_activity_data_call'))

    def test_descartar_no_vuelve_en_unos_dias_y_lo_que_ya_no_hace_falta_se_va(self):
        _p1, _c1, lead1 = self.cliente('Cliente Descarta', '+507 6000-3020', vendedora=self.vendedora)
        _p2, conv2, lead2 = self.cliente('Cliente Atendido', '+507 6000-3021', vendedora=self.vendedora,
                                         correo='atendido@example.com')
        self.analizar()
        descartada = self.propuestas(lead_id=lead1.id)
        sigue = self.propuestas(lead_id=lead2.id)
        self.Sofia.with_user(self.vendedora).descartar(descartada.id)
        self.assertEqual(descartada.estado, 'descartada')
        # Una vendedora le escribió al otro: ya no hace falta.
        self.Mensaje.create({'conversacion_id': conv2.id, 'id_mensaje': 'sofia.3', 'direccion': 'saliente',
                             'autor': 'vendedora', 'tipo': 'mensaje', 'texto': 'Hola', 'ts': fields.Datetime.now(),
                             'usuario_id': self.vendedora.id, 'estado_envio': 'enviado'})
        with freeze_time('2026-11-05 16:00:00'):
            corrida = self.Sofia.sudo()._analizar('boton')
        self.assertEqual(sigue.estado, 'vencida')
        self.assertFalse(self.propuestas(lead_id=lead1.id), 'lo descartado no vuelve en 7 días')
        self.assertEqual(corrida.vencidas, 1)
        with freeze_time('2026-11-13 16:00:00'):
            self.Sofia.sudo()._analizar('boton')
            self.assertTrue(self.propuestas(lead_id=lead1.id), 'a los 8 días sí')

    def test_revisar_dos_veces_no_repite(self):
        self.cliente('Cliente Repite', '+507 6000-3022', vendedora=self.vendedora)
        self.analizar()
        cuantas = len(self.propuestas())
        corridas = self.env['dcasa.sofia.corrida'].search_count([])
        self.analizar()   # al momento: no vuelve a revisar
        self.assertEqual(self.env['dcasa.sofia.corrida'].search_count([]), corridas)
        with freeze_time('2026-11-05 15:05:00'):
            self.analizar()
        self.assertEqual(len(self.propuestas()), cuantas)
        self.assertEqual(self.env['dcasa.sofia.corrida'].search_count([]), corridas + 1)

    # ------------------------------------------------------------------
    # Mensajes, botón, ajustes
    # ------------------------------------------------------------------

    def test_las_plantillas_no_aceptan_claves_inventadas(self):
        plantilla = self.env.ref('dcasa_sofia.plantilla_pedir_datos')
        with self.assertRaises(ValidationError):
            plantilla.texto = 'Hola {nombre}, te damos {descuento}'
        plantilla.with_user(self.gerente).texto = 'Hola {nombre}, ¿me regalas {que_falta}?'
        with self.assertRaises(AccessError):
            plantilla.with_user(self.vendedora).texto = 'Hola'

    def test_el_boton_del_crm(self):
        accion = self.env['crm.lead'].with_user(self.vendedora).action_dcasa_sofia()
        self.assertEqual((accion['tag'], accion['params']), ('dcasa_sofia.panel', {'analizar': True}))
        Lead = self.env['crm.lead']
        for xmlid, tipo in (('crm.crm_case_kanban_view_leads', 'kanban'), ('crm.crm_case_tree_view_oppor', 'list')):
            arch = Lead.with_user(self.vendedora).get_view(self.env.ref(xmlid).id, tipo)['arch']
            self.assertIn('action_dcasa_sofia', arch)
            self.assertIn('Organizar con Sofía', arch)

    # ------------------------------------------------------------------
    # Cada mañana
    # ------------------------------------------------------------------

    def test_la_revision_de_la_manana_una_vez_al_dia_y_el_resumen_por_telegram(self):
        self.cliente('Cliente Mañana', '+507 6000-3023', vendedora=self.vendedora)
        self.cliente('Cliente Otra', '+507 6000-3024', vendedora=self.vendedora2)
        self.cliente('Sin Dueña Mañana', '+507 6000-3025')
        Enlace = self.env['brian.telegram.enlace'].sudo()
        for usuario, chat in ((self.vendedora, '111'), (self.gerente, '222')):
            Enlace.create({'user_id': usuario.id, 'chat_id': chat})
        enviados = []
        with patch.object(type(Enlace), '_enviar', lambda self, chat_id, texto, botones=None:
                          enviados.append((chat_id, texto)) or {'ok': True}):
            with freeze_time('2026-11-05 13:10:00'):   # 8:10 a. m.: todavía no
                self.assertFalse(self.Sofia._cron_manana())
            with freeze_time('2026-11-05 13:40:00'):   # 8:40 a. m.
                self.assertTrue(self.Sofia._cron_manana())
                self.assertFalse(self.Sofia._cron_manana(), 'una vez al día')
        corrida = self.env['dcasa.sofia.corrida'].search([], limit=1)
        self.assertEqual((corrida.origen, corrida.avisos_telegram), ('manana', 2))
        avisos = dict(enviados)
        self.assertIn('Cliente Mañana', avisos['111'])
        self.assertNotIn('Cliente Otra', avisos['111'], 'cada vendedora lo suyo')
        self.assertIn('Por vendedora', avisos['222'])
        self.assertIn('sin vendedora', avisos['222'])
        self.assertIn('CRM › Sofía', avisos['111'])

    def test_apagada_no_revisa_sola(self):
        self.ajustes.sofia_manana = False
        with freeze_time('2026-11-05 14:00:00'):
            self.assertFalse(self.Sofia._cron_manana())
        self.assertFalse(self.env['dcasa.sofia.corrida'].search_count([]))
