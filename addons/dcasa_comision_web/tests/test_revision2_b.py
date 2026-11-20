"""Segunda revision adversarial, parte B: escala, errores en los ganchos, permisos y exportacion,
migracion, codigo VEN, carritos del equipo, fechas extremas. Cifras y personas de PRUEBA."""
# ruff: noqa: E501, UP031, B007, B023, F841, PLW0108, RUF012  (pruebas de la segunda revision: se conservan tal como se escribieron)
import importlib.util
from pathlib import Path
from unittest.mock import patch

from odoo import Command
from odoo.addons.dcasa_socios.tests.common import SociosCommon
from odoo.addons.website_sale.tests.common import MockRequest
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from .test_comision import ComisionReloj
from .test_endurecimiento import Liquida
from .test_vendedoras import VendedoraCommon

MIGRACION = (Path(__file__).resolve().parents[2] / 'dcasa_base' / 'migrations' / '19.0.1.10.0' / 'post-migrate.py')


@tagged('post_install', '-at_install')
class TestRevision2Escala(ComisionReloj):

    def test_revision2_10_poner_al_dia_revisa_todas_las_ventas_con_comision_desde_siempre_y_cuesta_lo_mismo_si_nada_cambio(self):
        """HALLAZGO (importante, escala): armar y aprobar una liquidacion llaman ``_poner_al_dia``, que recompone TODAS
        las ventas con comision cobradas desde la primera version, aunque nada haya cambiado en ellas. Con N ventas
        son N recomposiciones (cada una lee la factura, las lineas, las notas y el libro) dentro de UNA peticion, con un
        candado por venta retenido hasta el final. Se mide: consultas por venta ya al dia."""
        self.version(10.0)
        for i in range(30):
            self.venta_web()
        Venta = self.env['dcasa.web.venta']
        self.env.flush_all()
        antes = self.env.cr.sql_log_count
        revisadas = Venta._poner_al_dia()
        gastadas = self.env.cr.sql_log_count - antes
        self.assertEqual(revisadas, 30)
        por_venta = gastadas / 30.0
        _ = por_venta
        self.assertLessEqual(por_venta, 4.0,
                             'ventas ya al dia: %.1f consultas por venta (x miles de ventas, en cada Armar y cada '
                             'Aprobar)' % por_venta)


@tagged('post_install', '-at_install')
class TestRevision2ErroresEnLosGanchos(Liquida):
    """«Un error de la comision nunca frena un cobro»: errores raros en cada gancho; el cobro, la nota de credito, la
    vuelta a borrador, la anulacion y el borrado se completan y la transaccion queda usable."""

    def _vivir(self):
        """La transaccion sigue sirviendo despues del error (no queda «abortada»)."""
        self.env['res.partner'].create({'name': 'sigue viva rv2'})
        self.assertTrue(self.env['res.partner'].search_count([('name', '=', 'sigue viva rv2')]))

    def test_revision2_20_un_error_de_base_de_datos_dentro_del_gancho_de_pago_no_aborta_el_cobro(self):
        from psycopg2 import errors as pg
        self.version(10.0)
        factura = self.facturar(self.orden())

        def romper(self_, *a, **k):
            self.env.cr.execute('SELECT 1/0')        # error de la base, no de Python: aborta el punto de guardado

        with patch.object(type(self.env['dcasa.web.venta']), '_registrar', romper), \
                mute_logger('odoo.addons.dcasa_comision_web.models.account_move', 'odoo.sql_db'):
            self.pagar(factura)
        self.assertEqual(factura.payment_state, 'in_payment' if factura.payment_state == 'in_payment' else 'paid')
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))
        self._vivir()
        _ = pg

    def test_revision2_21_un_error_al_publicar_una_nota_no_impide_publicarla(self):
        self.version(10.0)
        factura = self.venta_web()
        with patch.object(type(self.env['dcasa.web.venta']), '_reconciliar', side_effect=RuntimeError('rv2')), \
                mute_logger('odoo.addons.dcasa_comision_web.models.account_move'):
            nota = self.nota(factura, 100.0)
        self.assertEqual(nota.state, 'posted')
        self._vivir()

    def test_revision2_22_un_error_al_anular_o_borrar_la_factura_no_impide_anularla_ni_borrarla(self):
        self.version(10.0)
        factura = self.venta_web()
        with patch.object(type(self.env['dcasa.web.venta']), '_reconciliar', side_effect=RuntimeError('rv2')), \
                mute_logger('odoo.addons.dcasa_comision_web.models.account_move'):
            factura.button_draft()
            self.assertEqual(factura.state, 'draft')
            factura.button_cancel()
            self.assertEqual(factura.state, 'cancel')
        self._vivir()

    def test_revision2_23_un_error_al_confirmar_el_pedido_no_impide_confirmarlo(self):
        orden = self.orden(confirmar=False)
        with patch.object(type(orden), '_dcasa_chat_antes_de_comprar', side_effect=RuntimeError('rv2')), \
                mute_logger('odoo.addons.dcasa_comision_web.models.sale_order'):
            orden.action_confirm()
        self.assertEqual(orden.state, 'sale')
        self._vivir()

    def test_revision2_24_el_empleado_archivado_o_una_ficha_rota_no_frena_el_cobro_ni_la_nota(self):
        self.version(10.0)
        self.ana.active = False
        factura = self.venta_web()
        self.assertEqual(self.venta(factura).estado, 'comisionada')
        nota = self.nota(factura, 200.0)
        self.assertEqual(nota.state, 'posted')
        self.assertEqual(self.centavos_de(self.ana) + self.centavos_de(self.beto), 8000)

    def centavos_de(self, empleado):
        return sum(self.libro(empleado=empleado).mapped('centavos'))

    def test_revision2_26_el_gancho_de_pago_no_se_traga_un_error_que_no_es_suyo_ni_deja_rota_la_transaccion(self):
        """HALLAZGO (menor; el hook de vendedores ya hacia lo mismo): ``cr.savepoint()`` vacia ANTES todas las
        escrituras pendientes de la peticion y eso ocurre dentro del ``try``: si una escritura ajena choca (aqui, un
        usuario con dos fichas; en la vida real, un choque de concurrencia que Odoo repetiria solo), el gancho se traga
        el error y la transaccion queda rota (el cobro falla con «InFailedSqlTransaction» y sin reintento)."""
        self.version(10.0)
        factura = self.facturar(self.orden())
        usuario = self.u_caja
        self.env['hr.employee'].create({'name': 'Ficha uno rv2', 'user_id': usuario.id})
        otra = self.env['hr.employee'].create({'name': 'Ficha dos rv2'})
        self.env.flush_all()
        otra.user_id = usuario          # pendiente: la base lo rechaza al vaciarse
        with mute_logger('odoo.addons.dcasa_comision_web.models.account_move', 'odoo.sql_db'):
            try:
                factura._invoice_paid_hook()
            except Exception:       # noqa: BLE001 — lo correcto: que el error ajeno SUBA
                return
        self.fail('el gancho de la comision se trago el error de una escritura que no era suya')

    def test_revision2_25_con_la_venta_bloqueada_por_otra_transaccion_el_gancho_espera_sin_error(self):
        """El candado de una venta es de aviso (``pg_advisory_xact_lock``): dentro de UNA transaccion no se bloquea a
        si mismo; la espera entre transacciones se prueba en el guion de concurrencia."""
        self.version(10.0)
        factura = self.venta_web()
        venta = self.venta(factura)
        self.env.cr.execute('SELECT pg_advisory_xact_lock(%s, %s)', [731_900_102, venta.id])
        venta._reconciliar()          # mismo proceso: el candado de aviso es reentrante
        self.assertEqual(self.venta(factura).estado, 'comisionada')


@tagged('post_install', '-at_install')
class TestRevision2PermisosYExportar(VendedoraCommon, Liquida):

    def _usuarios(self):
        portal = new_test_user(self.env, login='rv2_portal', groups='base.group_portal')
        marketing = new_test_user(self.env, login='rv2_marketing',
                                  groups='base.group_user,dcasa_marketing.group_marketing')
        return {'vendedora': self.u_vendedora, 'caja': self.u_caja, 'tecnico': self.u_tecnico,
                'portal': portal, 'marketing': marketing}

    def test_revision2_30_nadie_sin_nomina_lee_ni_una_tabla_de_la_comision(self):
        self.version(10.0)
        self.venta_web()
        liq = self.liquidar()
        modelos = ('dcasa.web.reglas', 'dcasa.web.reparto', 'dcasa.web.venta', 'dcasa.web.movimiento',
                   'dcasa.web.liquidacion', 'dcasa.web.liquidacion.linea', 'dcasa.web.ajuste', 'dcasa.web.candado')
        for nombre, usuario in self._usuarios().items():
            for modelo in modelos:
                with self.subTest(usuario=nombre, modelo=modelo):
                    self.rechaza(lambda: self.env[modelo].with_user(usuario).search_count([]))
        for modelo in modelos[:-1]:      # el candado no lo lee nadie, ni Nomina
            with self.subTest(usuario='nomina', modelo=modelo):
                self.env[modelo].with_user(self.u_nomina).search_count([])
        self.rechaza(lambda: self.env['dcasa.web.candado'].with_user(self.u_nomina).search_count([]))
        _ = liq

    def test_revision2_31_el_receptor_ve_el_libro_de_todos_pero_no_puede_escribir_en_el_(self):
        """«Un empleado receptor»: con rol de Nomina ve todo (diseño); no puede escribir ni crear en el libro."""
        self.version(10.0)
        self.venta_web()
        libro = self.env['dcasa.web.movimiento'].with_user(self.u_ana)
        self.assertEqual(len(libro.search([])), 2, 've las filas de los dos (Nomina ve todo)')
        self.rechaza(lambda: libro.search([])[:1].write({'centavos': 1}))
        self.rechaza(lambda: libro.search([])[:1].unlink())
        self.rechaza(lambda: libro.create({'empleado_id': self.ana.id, 'company_id': self.company.id, 'tipo': 'ajuste',
                                           'concepto': 'comision', 'centavos': 100000, 'autor': 'x', 'motivo': 'x',
                                           'mes': '2030-03-01'}))

    def test_revision2_32_gerencia_no_baja_el_libro_ni_las_liquidaciones_ni_las_reglas_por_exportar(self):
        self.version(10.0)
        self.venta_web()
        self.liquidar()
        for modelo, campos in (('dcasa.web.movimiento', ['empleado_id/name', 'centavos']),
                               ('dcasa.web.liquidacion', ['name', 'total']),
                               ('dcasa.web.liquidacion.linea', ['empleado_id/name', 'centavos']),
                               ('dcasa.web.reglas', ['porcentaje']), ('dcasa.web.reparto', ['empleado_id/name']),
                               ('dcasa.web.venta', ['factura', 'comision']), ('hr.employee', ['name', 'wage'])):
            with self.subTest(modelo=modelo):
                self.rechaza(lambda: self.env[modelo].with_user(self.u_gerencia).search([]).export_data(campos))

    def test_revision2_33_gerencia_no_baja_empleados_ni_comision_siguiendo_relaciones_de_una_factura_o_pedido(self):
        # La vendedora del pedido tiene ficha de empleado (con salario): si no hay datos, la relacion no se recorre.
        factura = self.facturar(self.orden(vendedora=self.u_vendedora, creado_por=self.u_vendedora), '2030-03-04')
        pedido = factura.line_ids.sale_line_ids.order_id
        for modelo, registro, campos in (
                ('sale.order', pedido, ['name', 'user_id/employee_ids/name']),
                ('sale.order', pedido, ['name', 'dcasa_creada_por_id/employee_ids/wage']),
                ('account.move', factura, ['name', 'invoice_user_id/employee_ids/name']),
                ('account.move', factura, ['name', 'invoice_user_id/employee_id/wage'])):
            with self.subTest(campos=campos):
                self.rechaza(lambda: self.env[modelo].with_user(self.u_gerencia).browse(registro.id).export_data(campos))

    def test_revision2_34_los_textos_de_motivo_y_referencia_no_se_pintan_como_html(self):
        """XSS: ``motivo``, ``referencia_pago`` y ``avisos`` son Char/Text (la vista los escapa); el unico Html es el
        ejemplo, hecho solo con numeros y palabras fijas."""
        campos = self.env['dcasa.web.reglas']._fields['ejemplo_html'], self.env['dcasa.web.movimiento']._fields['motivo']
        self.assertEqual(campos[1].type, 'char')
        for modelo in ('dcasa.web.movimiento', 'dcasa.web.liquidacion', 'dcasa.web.ajuste', 'dcasa.web.reglas'):
            for campo in self.env[modelo]._fields.values():
                if campo.type == 'html' and campo.name != 'ejemplo_html':
                    self.fail('%s.%s es Html' % (modelo, campo.name))
        v = self.version(10.0, motivo='<script>alert(1)</script>')
        self.assertNotIn('<script>', v.ejemplo_html)


@tagged('post_install', '-at_install')
class TestRevision2Migracion(VendedoraCommon):

    def _migrar(self):
        spec = importlib.util.spec_from_file_location('rv2_migracion', MIGRACION)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        self.env.flush_all()
        modulo.migrate(self.env.cr, '19.0.1.9.0')
        self.env.invalidate_all()

    def _foto(self, *ordenes):
        return [(o.dcasa_nacio_en_web, o.dcasa_llevada_por_vendedora, o.dcasa_venta_online) for o in ordenes]

    def test_revision2_40_la_migracion_es_idempotente_y_no_marca_mal(self):
        # Pedidos «viejos»: se crean sin marcas (como existian antes del despliegue).
        def viejo(web, **extra):
            return self.orden(web=False, vendedora=self.u_vendedora, website_id=self.website.id if web else False,
                              confirmar=False, **extra)
        otro = self.env['res.partner'].create({'name': 'Cliente migr rv2', 'phone': '+507 6555-0344',
                                               'email': 'migr.rv2@example.com'})
        con_mensaje = viejo(True)                                  # web, confirmado sin pagar, vendedora hace 10 dias
        sin_mensaje = viejo(True, cliente=otro)                    # web, sin vendedora
        tienda = viejo(False)                                      # tienda
        self.hablar(self.cliente, 'vendedora', hace_dias=10)
        con_mensaje.action_confirm()
        sin_mensaje.action_confirm()
        tienda.action_confirm()
        ya_pagado = viejo(True, cliente=self.env['res.partner'].create({
            'name': 'Cliente pagado rv2', 'phone': '+507 6555-0345', 'email': 'pagado.rv2@example.com'}))
        ya_pagado.action_confirm()
        self.pagar(self.facturar(ya_pagado, '2030-03-04'), '2030-03-04')
        self.env.cr.execute("UPDATE sale_order SET dcasa_nacio_en_web = NULL, dcasa_llevada_por_vendedora = NULL, "
                            "dcasa_venta_online = NULL WHERE id IN %s",
                            [tuple((con_mensaje | sin_mensaje | tienda | ya_pagado).ids)])
        self.env.invalidate_all()
        todas = con_mensaje | sin_mensaje | tienda | ya_pagado
        self._migrar()
        primera = self._foto(*todas)
        self.assertEqual(primera[0], (True, True, False), 'web + vendedora le escribio: nacio en la web pero es de ella')
        self.assertEqual(primera[1], (True, False, True))
        self.assertEqual(primera[2], (False, False, False))
        self.assertEqual(primera[3][0], True)
        self._migrar()
        self.assertEqual(self._foto(*todas), primera, 'segunda corrida: nada cambia')


@tagged('post_install', '-at_install')
class TestRevision2VenYElEquipo(VendedoraCommon):
    activar_vendedores = SociosCommon.activar_vendedores
    vendedor = SociosCommon.vendedor

    def setUp(self):
        super().setUp()
        import os
        entorno = patch.dict(os.environ, {'DCASA_PIN_PEPPER': 'pimienta-de-prueba'})
        entorno.start()
        self.addCleanup(entorno.stop)
        self.activar_vendedores()
        self.codigo = self.vendedor('Vendedor VEN rv2', '8-901-777', '6100-0777')

    def comision(self, factura):
        return self.env['dcasa.vend.comision'].search([('move_id', '=', factura.id), ('tipo', '=', 'directa')])

    def test_revision2_50_online_con_codigo_ven_paga_al_vendedor_y_al_sitio_pero_no_al_bono_de_la_vendedora(self):
        self.version(10.0)
        nuevo = self.env['res.partner'].create({'name': 'Cliente VEN rv2', 'phone': '+507 6555-0351',
                                                'email': 'ven.rv2@example.com'})
        factura = self.facturar(self.orden(web=True, vendedora=self.u_vendedora, cliente=nuevo,
                                           dcasa_vendedor_id=self.codigo.id), '2030-03-05')
        self.pagar(factura, '2030-03-05')
        self.assertGreater(self.comision(factura).puntos, 0, 'paga al dueño del enlace')
        self.assertEqual(self.venta(factura).comision_centavos, 10000, 'y al sitio')
        self.assertEqual(self.bono().cobrado, 0.0, 'pero no al bono de la vendedora del pedido')

    def test_revision2_51_el_codigo_ven_anotado_a_mano_en_un_pedido_online_ya_confirmado_solo_lo_cambia_gerencia(self):
        """Poner el codigo propio en una venta online (para cobrar tambien como vendedor): solo antes de confirmar,
        o Gerencia; queda el rastro de quien lo anoto."""
        nuevo = self.env['res.partner'].create({'name': 'Cliente VEN2 rv2', 'phone': '+507 6555-0352',
                                                'email': 'ven2.rv2@example.com'})
        orden = self.orden(web=True, vendedora=self.u_vendedora, cliente=nuevo)
        with self.assertRaises(UserError):
            orden.with_user(self.u_vendedora).write({'dcasa_vendedor_id': self.codigo.id})
        orden.with_user(self.u_gerencia).write({'dcasa_vendedor_id': self.codigo.id})
        self.assertEqual(orden.dcasa_vendedor_anotado_por, self.u_gerencia)

    def _carrito_de(self, usuario):
        website = self.website.with_user(usuario)
        with MockRequest(website.env, website=website):
            return website._create_cart()

    def _cobrar(self, orden, cliente, vendedora=True):
        orden.sudo().partner_id = cliente
        orden.sudo().write({'order_line': [Command.create({'product_id': self.mueble.id, 'product_uom_qty': 1,
                                                           'price_unit': 800.0})]})
        if vendedora:
            orden.sudo().with_user(self.u_vendedora).user_id = self.u_vendedora
        orden.sudo().action_confirm()
        factura = self.facturar(orden.sudo(), '2030-03-05')
        self.pagar(factura, '2030-03-05')
        return factura

    def test_revision2_52_un_carrito_abierto_por_el_equipo_y_editado_a_un_cliente_de_mostrador_es_online_y_se_vigila(self):
        self.version(10.0)
        cliente = self.env['res.partner'].create({'name': 'Cliente mostrador rv2', 'phone': '+507 6555-0361',
                                                  'email': 'mostrador.rv2@example.com'})
        carrito = self._carrito_de(self.u_gerencia)
        factura = self._cobrar(carrito, cliente)
        venta = self.venta(factura)
        self.assertTrue(venta, 'es venta online del sitio (decision de Gerencia: cotizar en la pagina y cobrar aparte)')
        self.assertTrue(venta.creado_por_personal, 'y se ve en la vigilancia: lo abrio alguien del equipo')
        self.assertEqual(self.bono().cobrado, 0.0, 'la vendedora no recibe nada de lo online')

    def test_revision2_53_el_mismo_carrito_abierto_como_visitante_y_editado_por_el_equipo_no_deja_rastro(self):
        """LIMITE (vigilancia ciega): si el carrito lo abre una sesion anonima, ``dcasa_creada_por_id`` es el publico y
        el cambio posterior de cliente y de lineas por alguien del equipo no marca nada. Debe haber alguna senal."""
        self.version(10.0)
        cliente = self.env['res.partner'].create({'name': 'Cliente mostrador2 rv2', 'phone': '+507 6555-0362',
                                                  'email': 'mostrador2.rv2@example.com'})
        carrito = self._carrito_de(self.env.ref('base.public_user'))
        factura = self._cobrar(carrito, cliente, vendedora=False)     # lo confirma Caja o Gerencia
        venta = self.venta(factura)
        self.assertTrue(venta)
        senal = venta.creado_por_personal or venta.atendida_por_vendedora or venta.como_llego in ('andres', 'juan')
        self.assertTrue(senal, 'ninguna senal en Ventas del sitio: nada distingue esta venta de una compra normal '
                               '(como_llego=%s, atendida=%s, personal=%s)' % (
                                   venta.como_llego, venta.atendida_por_vendedora, venta.creado_por_personal))


@tagged('post_install', '-at_install')
class TestRevision2Fechas(ComisionReloj):

    def test_revision2_60_fechas_extremas_en_la_version_dan_un_error_claro_o_se_aceptan(self):
        for texto in ('9999-12-31 23:59:59', '0001-01-01 00:00:00', '1900-01-01 00:00:00'):
            with self.subTest(rige_desde=texto):
                try:
                    with self.env.cr.savepoint():
                        self.version(10.0, rige_desde=texto)
                except UserError:
                    continue
                except OverflowError as error:
                    self.fail('error de Python sin traducir: %r' % error)

    def test_revision2_61_una_version_con_rige_desde_en_el_ano_9999_no_traba_ni_la_tarifa_ni_las_ventas(self):
        lejana = self.version(10.0, tarifa=100.0, rige_desde='9999-12-31 05:00:00')
        self.assertEqual(lejana.estado, 'programada')
        factura = self.venta_web()
        self.assertEqual(self.venta(factura).estado, 'medida', 'la primera version rige en 9999: nada cobra todavia')
        self.assertFalse(self.env['dcasa.web.movimiento']._cron_tarifa(), 'tampoco hay tarifa')
        lejana.action_anular() if False else None


@tagged('post_install', '-at_install')
class TestRevision2ChatYCuentas(VendedoraCommon):

    def test_revision2_70_un_mensaje_de_vendedora_que_nunca_llego_al_cliente_tambien_le_quita_la_venta_al_sitio(self):
        """OBSERVACION (menor): el cruce con el chat no mira si el mensaje salio (``estado_envio``). Uno «fallido» o
        «por enviar» (el Worker no respondio) cuenta igual que uno entregado."""
        self.version(10.0)
        conv = self.hablar(self.cliente, 'vendedora', hace_dias=2)
        self.env.cr.execute("UPDATE dcasa_mensaje SET estado_envio = 'fallido' WHERE conversacion_id = %s", [conv.id])
        self.env.invalidate_all()
        orden = self.orden(web=True, vendedora=self.u_vendedora)
        self.assertTrue(orden.dcasa_venta_online, 'un mensaje que nunca llego al cliente no es haberlo atendido '
                                                  '(hoy la venta se le quita al sitio)')

    def test_revision2_71_una_nota_interna_de_la_vendedora_no_cuenta_como_haber_atendido(self):
        self.version(10.0)
        conv = self.hablar(self.cliente, 'vendedora', hace_dias=2)
        self.env.cr.execute("UPDATE dcasa_mensaje SET tipo = 'nota', direccion = 'interna' WHERE conversacion_id = %s",
                            [conv.id])
        self.env.invalidate_all()
        orden = self.orden(web=True, vendedora=self.u_vendedora)
        self.assertTrue(orden.dcasa_venta_online)

    def test_revision2_80_la_base_con_cada_interruptor_y_sus_combinaciones_contra_cuentas_a_mano(self):
        """1,000 con 10 % (900) + 500 + premio de 75 + envio de 40; ITBMS 7 % sobre lo que lleva impuesto (92.75)."""
        lineas = [(self.mueble, 1000.0, 1, {'discount': 10.0}), (self.mueble, 500.0, 1, {}),
                  (self.premio, -75.0, 1, {}), (self.envio, 40.0, 1, {'is_delivery': True})]
        casos = [
            ({}, 132500),
            ({'base_envio': 'con'}, 132500 + 4000),
            ({'base_descuentos': 'antes'}, 150000),
            ({'base_itbms': 'con'}, 132500 + 9275),
            ({'base_itbms': 'con', 'base_descuentos': 'antes'}, 150000 + 10500),   # el ITBMS sobre el precio de lista
            ({'base_envio': 'con', 'base_itbms': 'con'}, 132500 + 4000 + 9275),
        ]
        for i, (opciones, esperada) in enumerate(casos):
            with self.subTest(opciones=opciones):
                self.avanzar(f'2030-03-{10 + i} 15:00:00')
                self.version(10.0, **opciones)
                factura = self.facturar(self.orden(lineas=lineas), f'2030-03-{10 + i}')
                self.pagar(factura, f'2030-03-{10 + i}')
                self.assertEqual(self.venta(factura).base_centavos, esperada)
