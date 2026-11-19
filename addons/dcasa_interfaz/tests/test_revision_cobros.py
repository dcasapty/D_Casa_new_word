"""Revisión independiente (2026-11-19): ataques a ``dcasa.tablero.cobros_del_periodo``.

Permisos de cada rol (con entrada buena y mala), pagos que NO son cobros a clientes, el reloj real de Panamá (sin
parchear ``_ahora_en_panama``), entradas raras, número de consultas con muchos diarios y el contrato que Brian lee.
"""
from datetime import date, datetime
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .test_inicio_por_rol import crear_usuario
from .test_por_dia import PorDiaCommon


@tagged('post_install', '-at_install')
class TestRevisionCobrosDelPeriodo(PorDiaCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.efectivo = cls.env['account.journal'].create({'name': 'Efectivo revision', 'type': 'cash', 'code': 'EFRW'})
        cls.hoy_fijo = date(2025, 7, 10)

    def con_reloj(self, hoy=None):
        """El reloj de Panamá fijo a mediodía de ``hoy`` (para el método público)."""
        from datetime import time

        from .test_por_dia import en_panama
        ahora = en_panama(hoy or self.hoy_fijo, time(12, 0))
        return patch.object(self.env.registry['dcasa.tablero'], '_ahora_en_panama', lambda _self: ahora)

    def cobro(self, monto, dia, diario=None, **extra):
        pago = self.env['account.payment'].create({
            'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': self.cliente.id, 'amount': monto,
            'date': dia, 'journal_id': (diario or self.banco).id, **extra})
        pago.action_post()
        return pago

    @staticmethod
    def anular_pago(pago):
        """Un pago cancelado (de publicado a borrador y de ahí a cancelado, como lo hace Odoo)."""
        pago.action_draft()
        pago.action_cancel()
        return pago

    # ------------------------------------------------------------------ permisos

    def _usuarios_sin_gerencia(self):
        contable = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Contable revision', 'login': 'rev_contable', 'password': 'rev_contable',
            'group_ids': [Command.set([self.env.ref('base.group_user').id,
                                       self.env.ref('account.group_account_user').id])]})
        portal = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Portal revision', 'login': 'rev_portal2', 'password': 'rev_portal2',
            'group_ids': [Command.set([self.env.ref('base.group_portal').id])]})
        return {
            'vendedora': self.vendedora, 'otra': self.otra,
            'caja': crear_usuario(self.env, 'rev_caja', 'dcasa_base.group_caja'),
            'contable': contable,
            'interno_sin_rol': self.env['res.users'].with_context(no_reset_password=True).create({
                'name': 'Interno revision', 'login': 'rev_interno2', 'password': 'rev_interno2',
                'group_ids': [Command.set([self.env.ref('base.group_user').id])]}),
            'portal': portal, 'publico': self.env.ref('base.public_user'),
        }

    def test_ningun_rol_sin_gerencia_lee_cobros_con_entrada_buena_ni_mala(self):
        self.cobro(100.0, self.hoy_fijo)
        entradas = (('2025-07-10', 'dia'), ('2025-07-10', 'mes'), ('no es fecha', 'siglo'), (None, None),
                    ('2025-07-10', ['mes']), ('3000-01-01', 'dia'), (False, False))
        with self.con_reloj():
            for nombre, usuario in self._usuarios_sin_gerencia().items():
                Tablero = self.env['dcasa.tablero'].with_user(usuario)
                for dia, periodo in entradas:
                    with self.subTest(rol=nombre, dia=dia, periodo=periodo), self.assertRaises(AccessError):
                        Tablero.cobros_del_periodo(dia, periodo)

    def test_gerencia_sin_permiso_de_cobros_no_ve_cobros_pero_si_la_fecha_valida(self):
        """Gerencia a la que se le quita el permiso de leer pagos: el método contesta sin la tarjeta (``None``), no
        con un error ni con datos."""
        sin_pagos = self.env['dcasa.tablero'].with_user(self.gerencia)
        with self.con_reloj(), patch.object(type(self.env['account.payment']), 'has_access',
                                            lambda s, op: False if s._name == 'account.payment' else True):
            datos = sin_pagos.cobros_del_periodo('2025-07-10', 'mes')
        self.assertIsNone(datos['cobros'])

    # ------------------------------------------------------------------ qué es un cobro

    def _cobros(self, periodo='dia', dia='2025-07-10'):
        with self.con_reloj():
            return self.ger.cobros_del_periodo(dia, periodo)

    def test_los_pagos_que_no_son_de_clientes_no_cuentan_como_cobros(self):
        """«El dinero que cobró la tienda a clientes»: ni el que sale, ni el cancelado, ni un borrador, ni lo que un
        PROVEEDOR devuelve (entra a un diario, pero no es dinero cobrado a un cliente). Si cuenta, la «Caja de hoy» y la
        nueva tarjeta suman dinero que ninguna venta generó."""
        Pago = self.env['account.payment']
        base = self._cobros()['cobros']['total']
        self.cobro(100.0, self.hoy_fijo)
        cancelado = self.anular_pago(self.cobro(33.0, self.hoy_fijo))
        self.assertEqual(cancelado.state, 'canceled')
        Pago.create({'payment_type': 'outbound', 'partner_type': 'customer', 'partner_id': self.cliente.id,
                     'amount': 20.0, 'date': self.hoy_fijo, 'journal_id': self.efectivo.id}).action_post()
        Pago.create({'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': self.cliente.id,
                     'amount': 15.0, 'date': self.hoy_fijo, 'journal_id': self.efectivo.id})   # borrador
        self.assertEqual(self._cobros()['cobros']['total'], base + 100.0, 'hasta aquí, solo el cobro bueno')
        # Un proveedor devuelve dinero (entra a un diario, pero no es una venta).
        proveedor = self.env['res.partner'].create({'name': 'Proveedor revision'})
        Pago.create({'payment_type': 'inbound', 'partner_type': 'supplier', 'partner_id': proveedor.id,
                     'amount': 40.0, 'date': self.hoy_fijo, 'journal_id': self.efectivo.id}).action_post()
        self.assertEqual(self._cobros()['cobros']['total'], base + 100.0,
                         'un reembolso de proveedor (payment_type inbound, partner_type supplier) no es un cobro')

    def test_las_dos_cajas_cuentan_igual_con_pagos_raros(self):
        """Lo que cuenta la nueva tarjeta es EXACTAMENTE lo que cuenta ``_cobrado`` (la «Caja de hoy»)."""
        Pago = self.env['account.payment']
        self.cobro(100.0, self.hoy_fijo)
        self.cobro(30.0, self.hoy_fijo, self.efectivo)
        self.anular_pago(self.cobro(7.0, self.hoy_fijo))
        Pago.create({'payment_type': 'outbound', 'partner_type': 'customer', 'partner_id': self.cliente.id,
                     'amount': 20.0, 'date': self.hoy_fijo, 'journal_id': self.efectivo.id}).action_post()
        proveedor = self.env['res.partner'].create({'name': 'Proveedor revision 2'})
        Pago.create({'payment_type': 'inbound', 'partner_type': 'supplier', 'partner_id': proveedor.id,
                     'amount': 40.0, 'date': self.hoy_fijo, 'journal_id': self.efectivo.id}).action_post()
        for periodo, desde in (('dia', self.hoy_fijo), ('mes', date(2025, 7, 1))):
            with self.subTest(periodo=periodo):
                nueva = self._cobros(periodo)['cobros']['total']
                self.assertEqual(nueva, round(self.ger._cobrado(desde, self.hoy_fijo), 2))

    # ------------------------------------------------------------------ el reloj de Panamá (el de verdad)

    def _con_utc(self, ahora_utc):
        """Congela ``fields.Datetime.now`` (lo que usa ``_ahora_en_panama``), no el método."""
        return patch.object(fields.Datetime, 'now', staticmethod(lambda: ahora_utc))

    def test_el_dia_de_hoy_cambia_a_medianoche_de_panama_no_de_utc(self):
        """04:59:59 UTC del 20 son las 23:59:59 del 19 en Panamá (UTC−5, sin horario de verano): el 20 todavía no
        llega. Un segundo después (05:00:00 UTC) ya es el 20."""
        with self._con_utc(datetime(2026, 11, 20, 4, 59, 59)):
            self.assertEqual(self.ger.cobros_del_periodo('2026-11-19', 'dia')['titulo'],
                             'Cobrado · hoy, jueves 19 de noviembre')
            with self.assertRaises(UserError):
                self.ger.cobros_del_periodo('2026-11-20', 'dia')
            semana = self.ger.cobros_del_periodo('2026-11-19', 'semana')
            self.assertEqual((semana['desde'], semana['hasta'], semana['contado_hasta']),
                             ('2026-11-16', '2026-11-22', '2026-11-19'))
        with self._con_utc(datetime(2026, 11, 20, 5, 0, 0)):
            self.assertEqual(self.ger.cobros_del_periodo('2026-11-20', 'dia')['titulo'],
                             'Cobrado · hoy, viernes 20 de noviembre')
            with self.assertRaises(UserError):
                self.ger.cobros_del_periodo('2026-11-21', 'dia')

    def test_el_ultimo_dia_del_anio_y_el_primero(self):
        with self._con_utc(datetime(2027, 1, 1, 4, 59, 59)):    # 31 de dic. 23:59:59 en Panamá
            datos = self.ger.cobros_del_periodo('2026-12-31', 'semana')
            self.assertEqual((datos['desde'], datos['hasta'], datos['contado_hasta']),
                             ('2026-12-28', '2027-01-03', '2026-12-31'))
            self.assertTrue(datos['en_curso'])
            self.assertEqual(datos['titulo'], 'Cobrado · semana del 28 de diciembre de 2026 al 3 de enero de 2027')
        with self._con_utc(datetime(2027, 1, 1, 5, 0, 0)):      # ya es 1 de enero en Panamá
            datos = self.ger.cobros_del_periodo('2027-01-01', 'mes')
            self.assertEqual((datos['desde'], datos['contado_hasta']), ('2027-01-01', '2027-01-01'))
            self.assertEqual(datos['titulo'], 'Cobrado · mes de enero')

    def test_un_cobro_de_las_11_de_la_noche_de_panama_cuenta_ese_dia(self):
        """El pago lleva ``date`` (un día), no hora: el de las 11 p. m. del 10 es del 10 aunque en UTC ya sea el 11."""
        pago = self.cobro(55.0, self.hoy_fijo)
        self.env.cr.execute('UPDATE account_payment SET create_date = %s WHERE id = %s',
                            (datetime(2025, 7, 11, 4, 30, 0), pago.id))
        pago.invalidate_recordset()
        self.assertEqual(self._cobros('dia')['cobros']['total'], 55.0)

    # ------------------------------------------------------------------ entradas raras

    def test_entradas_raras_dan_un_error_claro_o_una_respuesta_entera(self):
        with self.con_reloj():
            for periodo in (b'dia', 1.5, True, (), ('dia',), set(), object, 'dia\n', ' dia', 'día', 'DIA', 'dia\x00',
                            'x' * 10 ** 6):
                with self.subTest(periodo=repr(periodo)[:30]), self.assertRaises(UserError):
                    self.ger.cobros_del_periodo('2025-07-10', periodo)
            for dia in (b'2025-07-10', 20250710, 1.5, True, (), [], {}, object, '', ' ', '0000-00-00', '9999-12-31',
                        '2025-7-10x', '٢٠٢٥-٠٧-١٠' + '0' * 20, '2025-07-10'[:9], '\x00', 'x' * 10 ** 6):
                with self.subTest(dia=repr(dia)[:30]):
                    try:
                        datos = self.ger.cobros_del_periodo(dia, 'dia')
                    except UserError:
                        continue
                    # Lo que se acepta tiene que ser un día de verdad dentro del rango (nunca un valor a medias).
                    self.assertIn(datos['dia'], ('2025-07-10', '2025-07-01'), datos['dia'])
            # Fecha ISO con hora y zona: cuenta el día escrito (el servidor no convierte zonas).
            for texto in ('2025-07-10T23:59:59-05:00', '2025-07-10T00:00:00Z', '2025-07-10 12:00'):
                with self.subTest(texto=texto):
                    self.assertEqual(self.ger.cobros_del_periodo(texto, 'dia')['dia'], '2025-07-10')

    def test_el_mes_sin_cobros_y_el_periodo_vacio_dan_cero_no_error(self):
        for periodo in ('dia', 'semana', 'quincena', 'mes'):
            with self.subTest(periodo=periodo):
                datos = self._cobros(periodo, '2025-03-14')
                self.assertEqual((datos['cobros']['filas'], datos['cobros']['total'], datos['cobros']['cuantos']),
                                 ([], 0.0, 0))

    # ------------------------------------------------------------------ rendimiento

    def test_pocas_consultas_aunque_haya_muchos_diarios(self):
        """Un diario más no puede costar una consulta más (nada de N+1 por forma de pago)."""
        self.cobro(10.0, self.hoy_fijo)
        self._cobros('mes')                                   # calienta cachés
        self.env.flush_all()
        antes = self.env.cr.sql_log_count
        self._cobros('mes')
        con_uno = self.env.cr.sql_log_count - antes
        for i in range(30):
            diario = self.env['account.journal'].create({'name': f'Diario masivo {i}', 'type': 'bank',
                                                         'code': f'DM{i:02d}'})
            self.cobro(5.0 + i, self.hoy_fijo, diario)
        self.env.flush_all()
        self.env.invalidate_all()
        self._cobros('mes')
        self.env.invalidate_all()
        antes = self.env.cr.sql_log_count
        datos = self._cobros('mes')
        con_treinta = self.env.cr.sql_log_count - antes
        self.assertEqual(len(datos['cobros']['filas']), 31)
        self.assertLessEqual(con_treinta - con_uno, 6,
                             f'consultas con 1 diario: {con_uno}; con 31: {con_treinta} (¿N+1 por diario?)')

    # ------------------------------------------------------------------ lo que ya existía

    def test_el_contrato_que_lee_brian_sigue_igual(self):
        """Brian lee ``cobros`` de ``por_dia`` y ``ventas_del_dia``: sigue ahí, con las mismas llaves."""
        self.cobro(100.0, self.hoy_fijo)
        with self.con_reloj():
            dia = self.ger.ventas_del_dia('2025-07-10')['cobros']
            mes = self.ger.por_dia('2025-07')['cobros']
            nuevo = self.ger.cobros_del_periodo('2025-07-10', 'dia')['cobros']
        for cobros in (dia, mes, nuevo):
            self.assertEqual(set(cobros), {'filas', 'total', 'cuantos', 'accion'})
            self.assertEqual(set(cobros['filas'][0]), {'clave', 'forma', 'monto', 'cuantos', 'accion'})
        self.assertEqual((dia['total'], nuevo['total']), (100.0, 100.0))
        self.assertEqual(mes['total'], 100.0)

    def test_el_nombre_del_diario_no_cambia_el_titulo_ni_se_escapa(self):
        """Un diario con HTML en el nombre sale tal cual (texto): escapar es de la pantalla (t-out), que no lo
        interpreta. El servidor no lo deja pasar a ninguna llave de control."""
        diario = self.env['account.journal'].create({
            'name': '<img src=x onerror=alert(1)>', 'type': 'bank', 'code': 'XSS1'})
        self.cobro(5.0, self.hoy_fijo, diario)
        fila = self._cobros('dia')['cobros']['filas'][0]
        self.assertEqual(fila['forma'], '<img src=x onerror=alert(1)>')
        self.assertIn('<img src=x onerror=alert(1)>', fila['accion']['name'])
