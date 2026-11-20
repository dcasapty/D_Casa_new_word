"""Lo que se cerró tras la revisión adversarial del 2026-11-19: el origen de una venta online no se fabrica ni se
vigila a ciegas, «quien cobra no aprueba» no se esquiva, la numeración no se repite, hay UN corte por día de cobro para
el sitio y para las vendedoras, una liquidación aprobada se cancela y un saldo se ajusta desde la pantalla, lo anulado
se reversa en el acto, las devoluciones con «antes de descuentos» restan a precio de lista y una versión puesta con la
fecha equivocada se anula.

Cifras de PRUEBA."""
import importlib.util
import os
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from psycopg2 import errors as pg_errors

from odoo import Command, fields
from odoo.addons.dcasa_socios.tests.common import SociosCommon
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, new_test_user, tagged
from odoo.tools import mute_logger
from odoo.tools.safe_eval import safe_eval

from ..models import venta as modelo_venta
from ..models.movimiento import CANDADO_LIQUIDACIONES, CANDADO_NUMERACION
from .test_comision import ComisionReloj
from .test_vendedoras import VendedoraCommon

MIGRACION = (Path(__file__).resolve().parents[2] / 'dcasa_base' / 'migrations' / '19.0.1.10.0' / 'post-migrate.py')


def todos_los_usuarios(modelo, empleados):
    """Finge que cada usuario del sistema es de quien cobra (para probar que alguien tiene que quedar libre)."""
    return set(modelo.env['res.users'].sudo().with_context(active_test=False).search([]).ids)


class Liquida(ComisionReloj):
    """Una venta de la página cobrada en marzo y una liquidación de ese mes lista para armar."""

    def liquidar(self, usuario=None, hasta='2030-03-31'):
        liq = self.env['dcasa.web.liquidacion'].with_user(usuario or self.u_nomina).create({
            'fecha_desde': '2030-03-01', 'fecha_hasta': hasta})
        liq.action_armar()
        return liq

    def vueltas(self, clave):
        """Lo que va en la fila del candado (se escribe con SQL: se lee con SQL, no de la memoria del ORM)."""
        self.env.cr.execute('SELECT vueltas FROM dcasa_web_candado WHERE clave = %s', [clave])
        return self.env.cr.fetchone()[0]


# ----------------------------------------------------------------------------------------------------------------------
# B1: quién abrió el carrito y la vigilancia de «cotizó en la página y pagó en la tienda»
# ----------------------------------------------------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestOrigenYVigilancia(ComisionReloj):

    def test_cotizar_en_la_pagina_y_pagar_en_la_tienda_cuenta_y_deja_ver_quien_abrio_el_carrito(self):
        self.version(10.0)
        publico = self.env.ref('base.public_user')
        del_equipo = self.facturar(self.orden(pago='en_tienda', creado_por=self.u_vendedora))
        self.pagar(del_equipo)
        del_visitante = self.facturar(self.orden(pago='en_tienda', creado_por=publico))
        self.pagar(del_visitante)
        propia, ajena = self.venta(del_equipo), self.venta(del_visitante)
        self.assertEqual((propia.como_llego, propia.forma_pago), ('tienda', 'en_tienda'))
        self.assertEqual(propia.comision_centavos, 10000, 'decisión de Gerencia: cotizar en la página y pagar en la '
                                                           'tienda SÍ cuenta')
        self.assertEqual(propia.creado_por_id, self.u_vendedora)
        self.assertTrue(propia.creado_por_personal)
        self.assertFalse(ajena.creado_por_personal, 'el carrito de un visitante no es del equipo')
        vigiladas = self.env['dcasa.web.venta'].with_user(self.u_nomina).search([('creado_por_personal', '=', True)])
        self.assertEqual(vigiladas, propia)

    def test_gerencia_tiene_el_reporte_de_pedidos_de_la_pagina_para_revisar(self):
        accion = self.env.ref('dcasa_comision_web.accion_pedidos_vigilados')
        llevada = self.orden()
        llevada._dcasa_escribir_marca(dcasa_llevada_por_vendedora=True)
        normal = self.orden(creado_por=self.env.ref('base.public_user'))
        tienda = self.orden(web=False)
        modelo = self.env['sale.order'].with_user(self.u_gerencia)
        dominio = safe_eval(accion.domain)
        self.assertEqual(modelo.search(dominio + [('dcasa_llevada_por_vendedora', '=', True)]), llevada)
        self.assertEqual(modelo.search(dominio + [('dcasa_creada_por_id.share', '=', False)]), llevada,
                         'el carrito que abrió alguien del equipo')
        self.assertEqual(modelo.search(dominio) & (llevada | normal | tienda), llevada | normal)
        vistas = modelo.get_views([[accion.view_ids.view_id.id, 'list'], [accion.search_view_id.id, 'search']])
        self.assertEqual(set(vistas['views']), {'list', 'search'})
        menu = self.env.ref('dcasa_comision_web.menu_pedidos_vigilados')
        for usuario, ve in ((self.u_gerencia, True), (self.u_nomina, False), (self.u_vendedora, False),
                            (self.u_caja, False), (self.u_tecnico, False)):
            with self.subTest(usuario=usuario.login):
                self.assertEqual(menu.id in self.env['ir.ui.menu'].with_user(usuario)._visible_menu_ids(), ve,
                                 'solo Gerencia ve el reporte')


@tagged('post_install', '-at_install')
class TestVigilanciaDelPuntoCiego(ComisionReloj):
    """Un carrito que abre un visitante y luego arma a mano alguien del equipo: queda señalado (segunda revisión)."""

    def otro_cliente(self):
        return self.env['res.partner'].create({'name': 'Cliente de mostrador vigilado', 'phone': '+507 6555-0391',
                                               'email': 'mostrador.vigilado@example.com'})

    def test_el_equipo_que_cambia_el_cliente_o_las_lineas_de_un_carrito_de_visitante_queda_anotado(self):
        publico = self.env.ref('base.public_user')
        for cambio in ({'partner_id': self.otro_cliente().id},
                       {'order_line': [Command.create({'product_id': self.mueble.id, 'product_uom_qty': 1})]}):
            with self.subTest(cambio=list(cambio)):
                orden = self.orden(creado_por=publico, confirmar=False)
                self.assertFalse(orden.dcasa_tocada_por_id)
                orden.with_user(self.u_gerencia).write(cambio)
                self.assertEqual(orden.dcasa_tocada_por_id, self.u_gerencia)

    def test_un_visitante_o_un_cliente_que_edita_su_carrito_no_deja_senal(self):
        orden = self.orden(creado_por=self.env.ref('base.public_user'), confirmar=False)
        portal = new_test_user(self.env, login='com_portal_vigilado', groups='base.group_portal')
        for usuario in (self.env.ref('base.public_user'), portal):
            with self.subTest(usuario=usuario.login):
                orden.with_user(usuario).sudo().write({'partner_id': orden.partner_id.id,
                                                       'order_line': [Command.create({
                                                           'product_id': self.mueble.id, 'product_uom_qty': 1})]})
        self.assertFalse(orden.dcasa_tocada_por_id)

    def test_teclear_el_precio_de_una_linea_de_un_pedido_digital_lo_senala_aunque_lo_haga_quien_abrio_el_carrito(self):
        """La tienda pone los precios sola: un precio tecleado en una línea de producto es un pedido armado a mano."""
        publico = self.env.ref('base.public_user')
        for linea, esperado in (
                ({'product_id': self.mueble.id, 'product_uom_qty': 1}, False),                      # lo normal
                ({'product_id': self.premio.id, 'product_uom_qty': 1, 'price_unit': -50.0}, False),   # un premio
                ({'product_id': self.mueble.id, 'product_uom_qty': 1, 'price_unit': 800.0}, True)):    # precio a mano
            with self.subTest(linea=linea):
                orden = self.orden(creado_por=publico, confirmar=False)
                orden.with_user(publico).sudo().write({'order_line': [Command.create(linea)]})
                self.assertEqual(bool(orden.dcasa_tocada_por_id), esperado)

    def test_un_pedido_de_mostrador_no_se_marca_aunque_lo_cambie_el_equipo(self):
        tienda = self.orden(web=False, confirmar=False)
        tienda.with_user(self.u_gerencia).write({'partner_id': self.otro_cliente().id})
        self.assertFalse(tienda.dcasa_tocada_por_id)

    def test_la_marca_de_quien_lo_cambio_no_se_escribe_ni_se_fabrica_a_mano(self):
        orden = self.orden(confirmar=False)
        with self.assertRaisesRegex(UserError, 'lo pone el sistema'):
            orden.sudo().write({'dcasa_tocada_por_id': self.u_gerencia.id})
        creada = self.env['sale.order'].with_user(self.u_gerencia).with_context(
            default_dcasa_tocada_por_id=self.u_caja.id).create({'partner_id': self.cliente.id})
        self.assertFalse(creada.dcasa_tocada_por_id)

    def test_la_venta_y_el_reporte_de_gerencia_muestran_quien_lo_cambio(self):
        self.version(10.0)
        orden = self.orden(creado_por=self.env.ref('base.public_user'), confirmar=False)
        orden.with_user(self.u_gerencia).write({'partner_id': self.otro_cliente().id})
        orden.action_confirm()
        factura = self.facturar(orden)
        self.pagar(factura)
        venta = self.venta(factura)
        self.assertEqual((venta.tocada_por_id, venta.creado_por_personal), (self.u_gerencia, True))
        self.assertFalse(venta.creado_por_id.id == self.u_gerencia.id, 'el visitante abrió el carrito')
        accion = self.env.ref('dcasa_comision_web.accion_pedidos_vigilados')
        encontrados = self.env['sale.order'].with_user(self.u_gerencia).search(
            safe_eval(accion.domain) + [('dcasa_tocada_por_id', '!=', False)])
        self.assertEqual(encontrados, orden)

    def test_la_cotizacion_de_juan_editada_por_el_equipo_tambien_queda_senalada(self):
        juan = self.env.ref('dcasa_conversaciones.user_juan')
        orden = self.orden(creado_por=juan, confirmar=False)
        self.assertFalse(self.env['dcasa.web.venta']._es_del_equipo(orden), 'Juan no es una persona del equipo')
        orden.with_user(self.u_vendedora).write({'partner_id': self.otro_cliente().id})
        self.assertTrue(self.env['dcasa.web.venta']._es_del_equipo(orden))


# ----------------------------------------------------------------------------------------------------------------------
# B2: quien cobra no aprueba lo suyo, aunque cambie su ficha
# ----------------------------------------------------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestQuienCobraNoAprueba(Liquida):

    def setUp(self):
        super().setUp()
        self.version(10.0)
        self.venta_web()
        self.avanzar('2030-04-02 15:00:00')

    def test_guardar_una_version_exige_a_alguien_que_pueda_aprobar_sin_cobrar(self):
        with patch.object(type(self.env['dcasa.web.reparto']), '_usuarios_de', todos_los_usuarios), \
                self.assertRaisesRegex(ValidationError, 'NO figure entre quienes reciben'), self.env.cr.savepoint():
            self.version(10.0)
        self.assertTrue(self.version(10.0), 'con el reparto de siempre, quien aprueba existe')

    def test_el_usuario_que_tenia_la_ficha_al_guardar_la_version_queda_fijo(self):
        reparto = self.env['dcasa.web.reglas']._vigente(self.company).reparto_ids
        self.assertIn(self.u_ana, reparto.filtered(lambda r: r.empleado_id == self.ana).usuario_ids)
        liq = self.liquidar()
        otro = new_test_user(self.env, login='com_otro_de_ana', name='Otro de Ana',
                             groups='base.group_user,dcasa_nomina.group_nomina')
        self.ana.user_id = otro                        # la ficha de Ana ahora nombra a otra persona...
        self.ana.work_contact_id = self.env['res.partner'].create({'name': 'Contacto que no es nadie'})
        for usuario in (self.u_ana, otro):             # ...y ni el de antes ni el de ahora aprueban lo de ella
            with self.subTest(usuario=usuario.login), self.assertRaisesRegex(UserError, 'figuras entre quienes cobran'):
                liq.with_user(usuario).action_aprobar()
        liq.with_user(self.u_gerencia).action_aprobar()
        self.assertEqual((liq.estado, liq.aprobada_por), ('aprobada', self.u_gerencia))

    def test_la_version_nueva_congela_los_usuarios_de_cada_receptor_otra_vez(self):
        otro = new_test_user(self.env, login='com_otro_de_ana', name='Otro de Ana',
                             groups='base.group_user,dcasa_nomina.group_nomina')
        self.ana.user_id = otro
        nueva = self.version(10.0, reparto=[(self.ana, 100.0)])
        self.assertEqual(nueva.reparto_ids.usuario_ids, otro | self.u_ana,
                         'el de ahora y el que ya estaba congelado de antes')

    def test_los_usuarios_congelados_no_se_editan_a_mano(self):
        reparto = self.env['dcasa.web.reglas']._vigente(self.company).reparto_ids
        for valores in ({'usuario_ids': [Command.clear()]}, {'porcentaje': 1.0}):
            with self.subTest(valores=valores), self.assertRaises(UserError):
                reparto.sudo().write(valores)

    def test_nadie_aprueba_con_la_llave_de_otro_ni_el_superusuario(self):
        liq = self.liquidar()
        with self.assertRaisesRegex(UserError, 'solo la aprueba una persona'):
            liq.with_user(self.env.ref('base.user_root')).action_aprobar()


# ----------------------------------------------------------------------------------------------------------------------
# B3: numeración y aprobación se serializan escribiendo una fila (un candado de aviso no sirve con REPEATABLE READ)
# ----------------------------------------------------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestCandados(Liquida):

    def test_guardar_una_version_escribe_el_candado_de_la_numeracion(self):
        antes = self.vueltas(CANDADO_NUMERACION)
        self.version(10.0)
        self.version(11.0)
        self.assertEqual(self.vueltas(CANDADO_NUMERACION), antes + 2)
        self.assertEqual(self.env['dcasa.web.reglas'].search([], order='numero').mapped('numero'), [1, 2])

    def test_aprobar_y_cancelar_escriben_el_candado_de_las_liquidaciones(self):
        self.version(10.0)
        self.venta_web()
        self.avanzar('2030-04-02 15:00:00')
        antes = self.vueltas(CANDADO_LIQUIDACIONES)
        liq = self.liquidar()
        liq.action_aprobar()
        self.assertEqual(self.vueltas(CANDADO_LIQUIDACIONES), antes + 1)
        liq.with_user(self.u_nomina).write({'motivo_cancelacion': 'Prueba'})
        liq.action_cancelar()
        self.assertEqual(self.vueltas(CANDADO_LIQUIDACIONES), antes + 2)

    def test_el_candado_no_se_toca_desde_la_interfaz(self):
        modelo = self.env['dcasa.web.candado'].with_user(self.u_nomina)
        with self.assertRaises(AccessError):
            modelo.search([])


# ----------------------------------------------------------------------------------------------------------------------
# B4: UN corte, por el día del cobro, para el sitio y para las vendedoras
# ----------------------------------------------------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestCortePorDiaDeCobro(VendedoraCommon):
    """«Rige desde» es el INICIO de ese día en Panamá. Hoy es el 4 de marzo (10:00 en Panamá)."""

    def test_lo_cobrado_el_dia_antes_sigue_siendo_de_la_vendedora_y_nunca_del_sitio(self):
        self.version(10.0)
        self.vender(web=True, pago='2030-03-03')           # el pago se registra hoy pero es del día 3
        self.assertEqual(self.bono().cobrado, 1000.0)
        self.assertFalse(self.libro(), 'el sitio no cobra lo de antes del corte')
        self.assertFalse(self.env['dcasa.web.venta'].search([]).reglas_id, 'solo medida')

    def test_lo_cobrado_el_dia_que_rige_es_del_sitio_y_de_nadie_mas(self):
        self.version(10.0)
        self.vender(web=True, pago='2030-03-04')
        self.assertEqual(self.bono().cobrado, 0.0)
        self.assertEqual(sum(self.libro().mapped('centavos')), 10000)

    def test_cobrado_horas_antes_de_guardar_la_version_el_mismo_dia_tambien_es_del_sitio(self):
        """El hueco de la revisión: las 8 de la mañana, el cobro se anota sin versión; a las 10 se guarda la primera
        versión (rige desde el inicio del día). La venta ya no es de la vendedora: tiene que ser del sitio."""
        self.avanzar('2030-03-04 13:00:00')                # 08:00 en Panamá
        factura = self.vender(web=True, pago='2030-03-04')
        self.assertFalse(self.venta(factura).reglas_id, 'sin versión: solo medida')
        self.avanzar('2030-03-04 15:00:00')
        self.version(10.0)
        self.assertTrue(self.venta(factura).reglas_id, 'la versión de hoy la alcanza')
        self.assertEqual(sum(self.libro().mapped('centavos')), 10000)
        self.assertEqual(self.bono().cobrado, 0.0, 'y la vendedora ya no la cuenta: de alguien tiene que ser')

    def test_atribuir_dos_veces_no_duplica_el_libro(self):
        self.avanzar('2030-03-04 13:00:00')
        self.vender(web=True, pago='2030-03-04')
        self.avanzar('2030-03-04 15:00:00')
        self.version(10.0)
        filas = len(self.libro())
        for _ in range(2):
            self.assertEqual(self.env['dcasa.web.venta']._atribuir_a_las_reglas(), 0)
            self.env['dcasa.web.venta']._barrido()
        self.assertEqual(len(self.libro()), filas)

    def test_lo_cobrado_antes_de_la_primera_version_no_se_atribuye_nunca_aunque_pasen_los_dias(self):
        self.vender(web=True, pago='2030-03-03')
        self.avanzar('2030-03-06 15:00:00')
        self.version(10.0)
        self.assertEqual(self.env['dcasa.web.venta']._atribuir_a_las_reglas(), 0)
        self.assertFalse(self.libro())


@tagged('post_install', '-at_install')
class TestCorteDelProgramaDeVendedores(ComisionReloj):
    """El programa de vendedores corta por el día del cobro, igual que el bono y el sitio. Desde el 2026-11-20 solo
    importa para lo que no lleva código VEN (la compra con código paga siempre)."""

    activar_vendedores = SociosCommon.activar_vendedores
    vendedor = SociosCommon.vendedor

    def setUp(self):
        super().setUp()
        entorno = patch.dict(os.environ, {'DCASA_PIN_PEPPER': 'pimienta-de-prueba'})
        entorno.start()
        self.addCleanup(entorno.stop)
        self.activar_vendedores()
        self.reglas['vendedores']['vinculacion']['meses'] = 12
        self.codigo = self.vendedor('Vendedor Corte', '8-905-678', '6100-0905')

    def comision(self, factura):
        return self.env['dcasa.vend.comision'].search([('move_id', '=', factura.id), ('tipo', '=', 'directa')])

    def comprar(self, pago, con_codigo=False):
        extra = {'dcasa_vendedor_id': self.codigo.id} if con_codigo else {}
        factura = self.facturar(self.orden(**extra), pago)
        self.pagar(factura, pago)
        return factura

    def venta(self, factura):
        return self.env['dcasa.web.venta'].search([('move_id', '=', factura.id)])

    def test_el_corte_del_programa_de_vendedores_es_el_dia_del_cobro_y_no_el_de_hoy(self):
        # El cliente queda ligado al vendedor con una compra de la tienda con su código (antes de todo).
        liga = self.facturar(self.orden(web=False, dcasa_vendedor_id=self.codigo.id), '2030-03-01')
        self.pagar(liga, '2030-03-01')
        self.assertEqual(self.cliente.dcasa_vendedor_ligado_id, self.codigo)
        self.version(10.0)                                  # rige el 4 de marzo; hoy también es 4
        antes, ese_dia = self.comprar('2030-03-03'), self.comprar('2030-03-04')
        self.assertIn(self.comision(antes).resultado, ('pagada', 'recortada'))
        self.assertTrue(self.comision(antes).puntos, 'cobrada el día 3: sigue como siempre para el vendedor')
        self.assertEqual((self.comision(ese_dia).resultado, self.comision(ese_dia).puntos), ('venta-online', 0))
        self.assertFalse(self.venta(antes).reglas_id, 'y el sitio no la cobra: un solo corte para los dos')
        self.assertTrue(self.venta(ese_dia).reglas_id)

    def test_con_codigo_ven_el_corte_no_importa_paga_el_programa_y_el_sitio(self):
        self.version(10.0)
        ese_dia = self.comprar('2030-03-04', con_codigo=True)
        self.assertEqual(self.comision(ese_dia).resultado, 'pagada')
        self.assertTrue(self.comision(ese_dia).puntos)
        self.assertTrue(self.venta(ese_dia).reglas_id)


# ----------------------------------------------------------------------------------------------------------------------
# I1: cancelar una aprobada y ajustar un saldo, por la pantalla
# ----------------------------------------------------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestPantallaDeCancelarYAjustar(Liquida):

    def setUp(self):
        super().setUp()
        self.version(10.0)
        self.venta_web()
        self.avanzar('2030-04-02 15:00:00')

    def test_una_aprobada_se_cancela_escribiendo_el_motivo_en_el_formulario(self):
        liq = self.liquidar()
        liq.action_aprobar()
        with Form(liq.with_user(self.u_nomina)) as formulario:
            formulario.motivo_cancelacion = 'Se armó con el periodo equivocado'
        self.assertEqual(liq.motivo_cancelacion, 'Se armó con el periodo equivocado')
        liq.with_user(self.u_nomina).action_cancelar()
        self.assertEqual(liq.estado, 'cancelada')
        self.assertEqual((self.saldo(self.ana), self.saldo(self.beto)), (6000, 4000), 'la plata vuelve al saldo')

    def test_lo_demas_de_una_aprobada_sigue_sin_editarse(self):
        liq = self.liquidar()
        liq.action_aprobar()
        for campo, valor in (('notas', 'cambio'), ('fecha_hasta', '2030-04-30'), ('estado', 'borrador')):
            with self.subTest(campo=campo), self.assertRaises(UserError):
                liq.with_user(self.u_nomina).write({campo: valor})

    def ajustar(self, usuario=None, **valores):
        formulario = Form(self.env['dcasa.web.ajuste'].with_user(usuario or self.u_nomina))
        formulario.empleado_id = valores.get('empleado', self.ana)
        formulario.concepto = valores.get('concepto', 'comision')
        formulario.monto = valores.get('monto', -15.0)
        formulario.motivo = valores.get('motivo', 'Se pagó de más la semana pasada')
        return formulario.save()

    def test_un_ajuste_se_anota_con_su_motivo_y_mueve_el_saldo(self):
        antes = self.saldo(self.ana)
        self.ajustar().action_anotar()
        fila = self.libro(empleado=self.ana, tipo='ajuste')
        self.assertEqual((fila.centavos, fila.concepto, fila.autor), (-1500, 'comision', self.u_nomina.login))
        self.assertIn('pagó de más', fila.motivo)
        self.assertEqual(self.saldo(self.ana), antes - 1500)
        self.assertFalse(fila.venta_id, 'un ajuste no es de una venta')

    def test_un_ajuste_sin_motivo_o_en_cero_o_de_quien_no_administra_no_se_anota(self):
        sin_motivo = self.env['dcasa.web.ajuste'].with_user(self.u_nomina).create({
            'empleado_id': self.ana.id, 'monto': 10.0, 'motivo': '   '})
        en_cero = self.env['dcasa.web.ajuste'].with_user(self.u_nomina).create({
            'empleado_id': self.ana.id, 'monto': 0.0, 'motivo': 'Nada'})
        for ajuste in (sin_motivo, en_cero):
            with self.assertRaises(UserError), self.env.cr.savepoint():
                ajuste.action_anotar()
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            self.env['dcasa.web.ajuste'].with_user(self.u_vendedora).create({
                'empleado_id': self.ana.id, 'monto': 10.0, 'motivo': 'Intento'}).action_anotar()
        self.assertFalse(self.libro(tipo='ajuste'))

    def test_el_asistente_se_abre_desde_el_libro_para_nomina_y_gerencia(self):
        accion = self.env.ref('dcasa_comision_web.accion_ajuste')
        for usuario in (self.u_nomina, self.u_gerencia):
            datos = self.env[accion.res_model].with_user(usuario).get_views([[False, 'form']])
            self.assertIn('form', datos['views'])
        lista = self.env['dcasa.web.movimiento'].with_user(self.u_nomina).get_views([[False, 'list']])
        self.assertIn('Anotar un ajuste', lista['views']['list']['arch'])


# ----------------------------------------------------------------------------------------------------------------------
# I2: lo que ya no está cobrado se reversa en el acto y antes de pagar
# ----------------------------------------------------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestReversoEnElActo(Liquida):

    def setUp(self):
        super().setUp()
        self.version(10.0)

    def anulable(self, factura):
        factura.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable').remove_move_reconcile()

    def test_volver_a_borrador_o_anular_la_factura_reversa_sin_esperar_al_barrido(self):
        for accion in ('button_draft', 'button_cancel'):
            with self.subTest(accion=accion):
                factura = self.venta_web()
                self.assertEqual(self.centavos(self.ana, self.venta(factura)), 6000)
                self.anulable(factura)
                getattr(factura, accion)()
                self.assertEqual(self.centavos(self.ana, self.venta(factura)), 0)
                self.assertEqual(self.venta(factura).estado, 'revertida')

    def test_borrar_la_factura_reversa_lo_anotado(self):
        factura = self.venta_web()
        venta = self.venta(factura)
        self.anulable(factura)
        factura.button_draft()
        factura.unlink()
        self.assertFalse(venta.move_id)
        self.assertEqual(self.centavos(self.ana, venta), 0)
        self.assertFalse(venta.cobrada)

    def test_armar_compara_con_la_verdad_y_aprobar_se_niega_si_algo_cambio(self):
        factura = self.venta_web()
        self.avanzar('2030-04-02 15:00:00')                 # se liquida marzo en abril: el reverso será de abril
        liq = self.liquidar()
        self.assertEqual(sum(liq.linea_ids.mapped('centavos')), 10000)
        self.anulable(factura)                              # el pago se revierte DESPUÉS de armar
        with self.assertRaisesRegex(UserError, 'cambió'):
            liq.with_user(self.u_gerencia).action_aprobar()
        self.assertEqual((liq.estado, self.centavos(self.ana)), ('borrador', 0), 'se reversó antes de decidir')
        liq.action_armar()
        self.assertFalse(liq.linea_ids, 'ya no hay nada que liquidar')
        self.assertIn('ya lo cubre', liq.avisos)

    def test_nunca_se_paga_mas_de_lo_que_se_debe_hoy_aunque_el_reverso_sea_posterior_al_periodo(self):
        """Una devolución se anota con la fecha de hoy, que casi siempre cae después del periodo que se liquida."""
        factura = self.venta_web()
        self.avanzar('2030-04-02 15:00:00')
        self.nota(factura, 400.0, fecha='2030-04-02')       # devuelve el 40 % ya en abril
        liq = self.liquidar()                               # marzo
        self.assertEqual(sorted(liq.linea_ids.mapped('centavos')), [2400, 3600],
                         'marzo debía 100,00 y la devolución de abril ya restó 40,00: se paga 60,00')
        self.assertEqual(sum(liq.linea_ids.mapped('centavos')), 6000)
        liq.with_user(self.u_gerencia).action_aprobar()
        self.assertEqual((self.saldo(self.ana), self.saldo(self.beto)), (0, 0), 'no queda saldo en contra')

    def test_un_pago_nuevo_posterior_al_periodo_no_se_cuela_en_la_liquidacion(self):
        self.venta_web()
        self.avanzar('2030-04-02 15:00:00')
        self.venta_web(fecha='2030-04-02')                  # otra venta, ya de abril
        liq = self.liquidar()                               # marzo
        self.assertEqual(sum(liq.linea_ids.mapped('centavos')), 10000, 'solo lo de marzo')

    def test_un_error_al_reversar_nunca_impide_volver_a_borrador(self):
        factura = self.venta_web()
        self.anulable(factura)
        with patch.object(type(self.env['dcasa.web.venta']), '_reconciliar', side_effect=RuntimeError('falla')), \
                mute_logger('odoo.addons.dcasa_comision_web.models.account_move'):
            factura.button_draft()
        self.assertEqual(factura.state, 'draft')


# ----------------------------------------------------------------------------------------------------------------------
# I3: «antes de descuentos» y devoluciones, a precio de lista y en proporción
# ----------------------------------------------------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestAntesDeDescuentosConDevoluciones(ComisionReloj):

    def vender(self, **version):
        self.version(10.0, **version)
        factura = self.facturar(self.orden(lineas=[(self.mueble, 1000.0, 1, {'discount': 10.0})]))
        self.pagar(factura)
        return factura

    def test_devolver_la_mitad_resta_la_mitad_del_precio_de_lista(self):
        factura = self.vender(base_descuentos='antes')
        self.nota(factura, 450.0)                           # la mitad de lo cobrado (900)
        venta = self.venta(factura)
        self.assertEqual((venta.base_centavos, venta.comision_centavos), (50000, 5000))

    def test_con_descuentos_despues_se_resta_lo_devuelto_tal_cual(self):
        factura = self.vender()
        self.nota(factura, 450.0)
        venta = self.venta(factura)
        self.assertEqual((venta.base_centavos, venta.comision_centavos), (45000, 4500))

    def test_la_base_con_cada_interruptor_a_mano(self):
        """Venta de 1,000 con descuento de línea 10 % (900), premio de 100, envío 50, ITBMS 7 %; nota de 200 sin ITBMS.
        Cuentas hechas a mano, en centavos: productos 90,000; descuento de línea 10,000; premio 10,000; envío 5,000."""
        lineas = [(self.mueble, 1000.0, 1, {'discount': 10.0}), (self.premio, -100.0, 1, {}),
                  (self.envio, 50.0, 1, {'is_delivery': True})]
        itbms = self.itbms.amount / 100
        esperados = [
            ({}, 90000 - 10000 - 20000),                                    # sin ITBMS, sin envío, con descuentos
            ({'base_envio': 'con'}, 90000 - 10000 + 5000 - 20000),
            # Precio de lista (100,000) y lo devuelto TAMBIÉN a precio de lista: 20,000 de lo cobrado (80,000) son la
            # cuarta parte de la venta, es decir 25,000 de la lista.
            ({'base_descuentos': 'antes'}, 100000 - 25000),
            ({'base_devoluciones': 'no_resta'}, 90000 - 10000),
            ({'base_itbms': 'con', 'base_envio': 'con'},
             90000 - 10000 + 5000 + round(80000 * itbms) - 20000 - round(20000 * itbms)),
        ]
        for i, (opciones, base) in enumerate(esperados):
            with self.subTest(opciones=opciones):
                self.avanzar(f'2030-03-{10 + i} 15:00:00')
                self.version(10.0, **opciones)
                factura = self.facturar(self.orden(lineas=lineas), f'2030-03-{10 + i}')
                self.pagar(factura, f'2030-03-{10 + i}')
                self.nota(factura, 200.0, fecha=f'2030-03-{10 + i}')
                self.assertEqual(self.venta(factura).base_centavos, base)

    def test_la_misma_venta_devuelta_dos_veces_nunca_deja_base_negativa(self):
        factura = self.vender(base_descuentos='antes')
        self.nota(factura, 450.0)
        self.nota(factura, 450.0)
        self.assertEqual((self.venta(factura).base_centavos, self.venta(factura).comision_centavos), (0, 0))


# ----------------------------------------------------------------------------------------------------------------------
# I4: una versión puesta con la fecha equivocada se anula; «rige desde» es el inicio del día
# ----------------------------------------------------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestAnularYFechas(ComisionReloj):

    def anular(self, version, motivo='Se puso el año equivocado', usuario=None):
        version = version.with_user(usuario or self.u_nomina)
        version.write({'motivo_anulacion': motivo})
        version.action_anular()

    def test_una_version_que_todavia_no_rige_se_anula_con_motivo_y_ya_no_estorba(self):
        futura = self.version(10.0, rige_desde=fields.Datetime.now() + timedelta(days=730))
        Orden = self.env['sale.order']
        self.assertEqual(futura.estado, 'programada')
        self.assertTrue(Orden._dcasa_online_desde(), 'una versión guardada ya fija desde cuándo no es de vendedoras')
        with self.assertRaisesRegex(UserError, 'motivo'):
            futura.with_user(self.u_nomina).action_anular()
        self.anular(futura)
        self.assertEqual((futura.estado, futura.anulada_por), ('anulada', self.u_nomina))
        self.assertFalse(Orden._dcasa_online_desde(), 'anulada: es como si nunca se hubiera guardado')
        self.assertFalse(self.env['dcasa.web.reglas']._primera(self.company))
        self.assertTrue(self.version(5.0), 'y el módulo ya no queda trabado')

    def test_una_version_que_ya_se_uso_para_calcular_una_venta_no_se_anula(self):
        futura = self.version(10.0, rige_desde=fields.Datetime.now() + timedelta(days=10))
        factura = self.facturar(self.orden(), '2030-03-14')
        self.pagar(factura, '2030-03-14')                    # un pago con fecha del día en que rige
        venta = self.venta(factura)
        # Tercera revisión: un pago con fecha futura ya no escoge una versión programada (se calcula con la de hoy, y
        # aquí todavía no rige ninguna). El candado de «ya se usó» se conserva por si una venta llegara a apuntar a una
        # versión que todavía no rige: se prueba apuntándola a mano.
        self.assertFalse(venta.reglas_id)
        venta.sudo().reglas_id = futura
        futura.with_user(self.u_nomina).write({'motivo_anulacion': 'Prueba'})
        with self.assertRaisesRegex(UserError, 'ya se usó'):
            futura.with_user(self.u_nomina).action_anular()

    def test_una_version_que_ya_rige_no_se_anula_y_lo_anulado_no_se_edita_ni_se_borra(self):
        vigente = self.version(10.0)
        with self.assertRaisesRegex(UserError, 'todavía no rige'):
            self.anular(vigente)
        futura = self.version(5.0, rige_desde=fields.Datetime.now() + timedelta(days=365))
        self.anular(futura)
        for hacer in (lambda: futura.sudo().write({'porcentaje': 1.0}), futura.sudo().unlink,
                      lambda: futura.with_user(self.u_nomina).action_anular()):
            with self.assertRaises(UserError), self.env.cr.savepoint():
                hacer()

    def test_solo_gerencia_y_nomina_anulan(self):
        futura = self.version(10.0, rige_desde=fields.Datetime.now() + timedelta(days=365))
        futura.sudo().write({'motivo_anulacion': 'Prueba'})
        for usuario in (self.u_vendedora, self.u_tecnico):
            with self.subTest(usuario=usuario.login):
                self.rechaza(lambda usuario=usuario: futura.with_user(usuario).action_anular())
        self.assertEqual(futura.estado, 'programada')

    def test_una_anulada_no_cuenta_para_la_que_rige_ni_para_la_numeracion_consecutiva(self):
        vigente = self.version(10.0)
        futura = self.version(20.0, rige_desde=fields.Datetime.now() + timedelta(days=10))
        self.assertEqual(self.env['dcasa.web.reglas']._vigente(self.company), vigente)
        self.anular(futura)
        self.assertEqual(self.env['dcasa.web.reglas']._vigente(self.company), vigente)
        self.assertEqual(self.version(7.0).numero, 3, 'la anulada conserva su número: no se reusa')

    def test_rige_desde_es_el_inicio_del_dia_en_panama_y_lo_de_ayer_ya_paso(self):
        self.assertTrue(self.version(10.0, rige_desde='2030-03-04 05:00:00'), 'hoy a las 00:00 en Panamá: vale')
        with self.assertRaisesRegex(UserError, 'ya pasó'), self.env.cr.savepoint():
            self.version(5.0, rige_desde='2030-03-04 04:59:00')        # 23:59 del día 3 en Panamá

    def test_la_fecha_que_trae_el_formulario_vale_todo_el_dia_aunque_se_tarde_horas(self):
        por_defecto = self.env['dcasa.web.reglas'].default_get(['rige_desde'])['rige_desde']
        self.avanzar('2030-03-05 04:30:00')                 # todavía es el día 4 en Panamá (23:30)
        self.assertTrue(self.version(10.0, rige_desde=por_defecto))
        self.avanzar('2030-03-05 05:30:00')                 # ya es el día 5
        with self.assertRaisesRegex(UserError, 'ya pasó'), self.env.cr.savepoint():
            self.version(5.0, rige_desde=por_defecto)

    def test_el_dia_de_la_primera_version_es_el_de_su_rige_desde_en_panama(self):
        self.version(10.0, rige_desde='2030-03-04 05:00:00')
        self.assertEqual(str(self.env['sale.order']._dcasa_online_desde()), '2030-03-04')


# ----------------------------------------------------------------------------------------------------------------------
# Menores
# ----------------------------------------------------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestMenoresDeLaSegundaRevision(ComisionReloj):

    def nota_con_producto(self, factura, producto, monto):
        """Una nota de crédito (como la que hace el asistente de «Nota de crédito») con una línea de ``producto``."""
        nota = self.env['account.move'].create({
            'move_type': 'out_refund', 'partner_id': factura.partner_id.id, 'invoice_date': '2030-03-04',
            'reversed_entry_id': factura.id,
            'invoice_line_ids': [Command.create({
                'product_id': producto.id, 'name': producto.name, 'quantity': 1, 'price_unit': monto,
                'tax_ids': [Command.set(producto.taxes_id.ids)]})]})
        nota.action_post()
        return nota

    def test_devolver_solo_el_envio_resta_solo_si_el_envio_cuenta(self):
        lineas = [(self.mueble, 1000.0, 1, {}), (self.envio, 50.0, 1, {'is_delivery': True})]
        self.version(10.0)
        sin = self.venta_web(lineas=lineas)
        self.nota_con_producto(sin, self.envio, 50.0)
        self.assertEqual(self.venta(sin).base_centavos, 100000, 'el envío no cuenta: devolverlo no resta comisión')
        self.avanzar('2030-03-05 15:00:00')
        self.version(10.0, base_envio='con')
        con = self.venta_web(lineas=lineas, fecha='2030-03-05')
        self.nota_con_producto(con, self.envio, 50.0)
        self.assertEqual(self.venta(con).base_centavos, 100000, 'cuenta el envío (1,050) y se devolvieron los 50')

    def test_devolver_un_mueble_sigue_restando_aunque_vaya_con_el_envio_en_la_misma_nota(self):
        lineas = [(self.mueble, 1000.0, 1, {}), (self.envio, 50.0, 1, {'is_delivery': True})]
        self.version(10.0)
        factura = self.venta_web(lineas=lineas)
        nota = self.env['account.move'].create({
            'move_type': 'out_refund', 'partner_id': factura.partner_id.id, 'invoice_date': '2030-03-04',
            'reversed_entry_id': factura.id,
            'invoice_line_ids': [
                Command.create({'product_id': self.mueble.id, 'name': 'Mueble', 'quantity': 1, 'price_unit': 400.0,
                                'tax_ids': [Command.set(self.itbms.ids)]}),
                Command.create({'product_id': self.envio.id, 'name': 'Envio', 'quantity': 1, 'price_unit': 50.0})]})
        nota.action_post()
        venta = self.venta(factura)
        self.assertEqual((venta.devuelto_centavos, venta.devuelto_envio_centavos), (40000, 5000))
        self.assertEqual(venta.base_centavos, 60000)

    def test_antes_de_descuentos_y_con_itbms_usa_el_impuesto_del_precio_de_lista(self):
        lineas = [(self.mueble, 1000.0, 1, {'discount': 10.0})]
        self.version(10.0, base_descuentos='antes', base_itbms='con')
        factura = self.venta_web(lineas=lineas)
        self.assertEqual(self.venta(factura).base_centavos, 100000 + 7000, 'lista 1,000 y su ITBMS (70), no el de 900')

    def test_el_anticipo_se_resta_de_lo_vendido_con_cualquier_posicion_de_los_descuentos(self):
        for dia, opcion in (('2030-03-04', 'despues'), ('2030-03-05', 'antes')):
            with self.subTest(base_descuentos=opcion):
                self.avanzar(f'{dia} 15:00:00')
                self.version(10.0, base_descuentos=opcion)
                orden = self.orden(lineas=[(self.mueble, 1000.0, 1, {})])
                asistente = self.env['sale.advance.payment.inv'].with_context(
                    active_model='sale.order', active_ids=orden.ids).create({
                        'advance_payment_method': 'fixed', 'fixed_amount': 300.0})
                asistente.create_invoices()
                anticipo = orden.invoice_ids.filtered(lambda f: f.state == 'draft')
                anticipo.invoice_date = dia
                anticipo.action_post()
                self.pagar(anticipo, anticipo.invoice_date.isoformat())
                final = orden._create_invoices(final=True)
                final.invoice_date = anticipo.invoice_date
                final.action_post()
                self.pagar(final, anticipo.invoice_date.isoformat())
                self.assertEqual(self.venta(anticipo).base_centavos + self.venta(final).base_centavos, 100000)

    def test_un_mensaje_de_vendedora_que_nunca_salio_no_le_quita_la_venta_al_sitio(self):
        for estado in ('fallido', 'por_enviar', 'programado'):
            with self.subTest(estado=estado):
                conv = self.hablar(self.cliente, 'vendedora', hace_dias=2, id_externo=f'507619990{len(estado)}')
                self.env.cr.execute("UPDATE dcasa_mensaje SET estado_envio = %s WHERE conversacion_id = %s",
                                    [estado, conv.id])
                self.env.invalidate_all()
                self.assertTrue(self.orden().dcasa_venta_online)
        self.hablar(self.cliente, 'vendedora', hace_dias=1, id_externo='50761999099')
        self.assertFalse(self.orden().dcasa_venta_online, 'uno que sí salió, sí cuenta')

    def test_el_pago_de_una_pasarela_lleva_la_fecha_de_panama(self):
        """A las 9 de la noche del 4 en Panamá ya es 5 en UTC: el pago no puede salir con fecha del 5."""
        self.avanzar('2030-03-05 02:00:00')
        transaccion = self.transaccion(self.orden(pago='pasarela'), 'pasarela')
        with patch('odoo.addons.account_payment.models.payment_transaction.PaymentTransaction._create_payment',
                   autospec=True) as crear:
            transaccion._create_payment()
        self.assertEqual(crear.call_args.kwargs['date'].isoformat(), '2030-03-04')
        with patch('odoo.addons.account_payment.models.payment_transaction.PaymentTransaction._create_payment',
                   autospec=True) as crear:
            transaccion._create_payment(date='2030-01-01')
        self.assertEqual(crear.call_args.kwargs['date'], '2030-01-01', 'una fecha que se pide expresamente se respeta')

    def test_un_cobro_con_fecha_de_dos_dias_antes_o_mas_queda_senalado(self):
        self.version(10.0)
        hoy = self.venta_web(fecha='2030-03-04')
        ayer = self.venta_web(fecha='2030-03-03')
        atrasado = self.venta_web(fecha='2030-03-01')
        self.assertEqual([self.venta(f).cobro_atrasado for f in (hoy, ayer, atrasado)], [False, False, True])
        buscadas = self.env['dcasa.web.venta'].with_user(self.u_nomina).search([('cobro_atrasado', '=', True)])
        self.assertEqual(buscadas, self.venta(atrasado))

    def test_la_tarifa_de_una_version_empieza_en_el_primer_periodo_despues_de_su_dia_sin_importar_la_hora(self):
        Libro = self.env['dcasa.web.movimiento']
        self.version(0.0, tarifa=10.0, tarifa_periodo='semanal', rige_desde='2030-03-04 05:00:00')   # lunes 00:00
        self.assertEqual(Libro._cron_tarifa(hoy=date(2030, 3, 4)), 0, 'el lunes en que rige no cuenta')
        self.assertEqual(Libro._cron_tarifa(hoy=date(2030, 3, 11)), 2, 'el siguiente lunes sí')
        otra = self.env['dcasa.web.reglas'].search([]).filtered(lambda v: v.tarifa_fija == 10.0)
        self.assertTrue(otra)

    def test_los_ganchos_dejan_pasar_un_choque_de_concurrencia_para_que_odoo_repita_el_cobro(self):
        self.version(10.0)
        factura = self.venta_web()      # pagada: el gancho de vendedores solo mira facturas pagadas
        choque = pg_errors.SerializationFailure('could not serialize access due to concurrent update')
        with patch.object(type(self.env['dcasa.web.venta']), '_registrar', side_effect=choque), \
                self.assertRaises(pg_errors.SerializationFailure):
            factura._invoice_paid_hook()
        with patch.object(type(self.env['dcasa.vend.comision']), '_registrar_desde_factura', side_effect=choque), \
                self.assertRaises(pg_errors.SerializationFailure):
            factura._invoice_paid_hook()

    def test_armar_vuelve_a_lanzar_un_choque_de_concurrencia_en_vez_de_seguir_con_datos_viejos(self):
        self.version(10.0)
        factura = self.venta_web()
        self.env.cr.execute('UPDATE dcasa_web_venta SET huella = NULL')       # fuerza que se recomponga
        self.env['dcasa.web.venta'].invalidate_model()
        choque = pg_errors.SerializationFailure('could not serialize access due to concurrent update')
        with patch.object(type(self.env['dcasa.web.venta']), '_reconciliar', side_effect=choque), \
                self.assertRaises(pg_errors.SerializationFailure):
            self.env['dcasa.web.venta']._poner_al_dia()
        self.assertTrue(factura)

    def test_poner_al_dia_solo_recompone_lo_que_cambio(self):
        self.version(10.0)
        cambiada, intacta = self.venta_web(), self.venta_web()
        Venta = self.env['dcasa.web.venta']
        original = type(Venta)._reconciliar
        with patch.object(type(Venta), '_reconciliar', autospec=True, side_effect=original) as recompone:
            self.assertEqual(Venta._poner_al_dia(), 2, 'se miraron las dos')
            self.assertFalse(recompone.called, 'ninguna cambió: no se recompone ninguna')
        cambiada.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable').remove_move_reconcile()
        with patch.object(type(Venta), '_reconciliar', autospec=True, side_effect=original) as recompone:
            Venta._poner_al_dia()
        self.assertEqual(recompone.call_count, 1, 'solo la que cambió')
        self.assertEqual(recompone.call_args.args[0], self.venta(cambiada))
        self.assertEqual((self.venta(cambiada).estado, self.venta(intacta).estado), ('revertida', 'comisionada'))


@tagged('post_install', '-at_install')
class TestMenores(Liquida):

    def test_una_nota_aplicada_a_dos_facturas_se_reparte_por_lo_que_se_aplico_a_cada_una(self):
        self.version(10.0)
        a = self.facturar(self.orden(), '2030-03-04')
        b = self.facturar(self.orden(), '2030-03-04')
        self.pagar(a, '2030-03-04', monto=770.0)
        nota = self.nota(a, 600.0, enlazada=False)           # 642 con ITBMS
        linea = nota.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        a.js_assign_outstanding_line(linea.id)               # 300 a la primera
        b.js_assign_outstanding_line(linea.id)               # 342 a la segunda
        self.pagar(b, '2030-03-04')
        va, vb = self.venta(a), self.venta(b)
        self.assertLess(va.devuelto_centavos, vb.devuelto_centavos, 'a la segunda se le aplicó más de la nota')
        self.assertLessEqual(abs(va.devuelto_centavos + vb.devuelto_centavos - 60000), 1,
                             'entre las dos restan los 600 de la nota, ni más ni menos')

    def test_el_barrido_va_por_lotes_y_no_deja_nada_sin_anotar(self):
        self.version(10.0)
        facturas = self.env['account.move']
        with patch.object(type(self.env['dcasa.web.venta']), '_registrar', side_effect=RuntimeError('falla')), \
                mute_logger('odoo.addons.dcasa_comision_web.models.account_move'):
            for _ in range(5):
                factura = self.facturar(self.orden())
                self.pagar(factura)
                facturas |= factura
        self.assertFalse(self.env['dcasa.web.venta'].search([]))
        with patch.object(modelo_venta, 'LOTE', 2):
            nuevas, revisadas = self.env['dcasa.web.venta']._barrido()
        self.assertEqual((nuevas, revisadas), (5, 5))
        self.assertEqual(sum(self.libro().mapped('centavos')), 5 * 10000)

    def test_el_barrido_no_se_atora_con_una_factura_que_siempre_falla(self):
        self.version(10.0)
        buena, mala = self.facturar(self.orden()), self.facturar(self.orden())
        original = type(self.env['dcasa.web.venta'])._registrar

        def a_veces(modelo, move):
            if move == mala:
                raise RuntimeError('esta factura siempre falla')
            return original(modelo, move)
        with patch.object(type(self.env['dcasa.web.venta']), '_registrar', side_effect=RuntimeError('falla')), \
                mute_logger('odoo.addons.dcasa_comision_web.models.account_move'):
            self.pagar(buena)
            self.pagar(mala)
        with patch.object(type(self.env['dcasa.web.venta']), '_registrar', a_veces), \
                mute_logger('odoo.addons.dcasa_comision_web.models.venta'):
            nuevas, _revisadas = self.env['dcasa.web.venta']._barrido()
        self.assertEqual(nuevas, 1)
        self.assertTrue(self.venta(buena) and not self.venta(mala))

    def test_la_fecha_del_periodo_no_revienta_con_extremos(self):
        liq = self.env['dcasa.web.liquidacion'].with_user(self.u_nomina).create({
            'fecha_desde': '0001-01-02', 'fecha_hasta': '9999-12-31'})
        liq.action_armar()
        self.assertFalse(liq.linea_ids)

    def test_armar_avisa_cuando_arrastra_saldo_de_antes_del_periodo(self):
        self.version(10.0)
        self.venta_web(fecha='2030-03-04')
        self.avanzar('2030-04-02 15:00:00')
        liq = self.env['dcasa.web.liquidacion'].with_user(self.u_nomina).create({
            'fecha_desde': '2030-03-15', 'fecha_hasta': '2030-03-31'})
        liq.action_armar()
        self.assertEqual(sum(liq.linea_ids.mapped('centavos')), 10000, 'toma todo lo no liquidado hasta «hasta»')
        self.assertIn('antes del 15/03/2030', liq.avisos)
        igual = self.env['dcasa.web.liquidacion'].with_user(self.u_nomina).create({
            'fecha_desde': '2030-03-01', 'fecha_hasta': '2030-03-31'})
        igual.action_armar()
        self.assertFalse(igual.avisos)

    def test_la_migracion_marca_llevada_a_lo_ya_confirmado_que_una_vendedora_atendio(self):
        atendida = self.orden(cliente=self.cliente)
        otro = self.env['res.partner'].create({'name': 'Cliente sin vendedora', 'phone': '+507 6555-0399'})
        sola = self.orden(cliente=otro)
        pagada = self.facturar(self.orden(cliente=self.cliente))
        self.pagar(pagada)
        self.hablar(self.cliente, 'vendedora', hace_dias=2)
        ordenes = atendida | sola | pagada.invoice_line_ids.sale_line_ids.order_id
        self.env.cr.execute('UPDATE sale_order SET dcasa_nacio_en_web = FALSE, dcasa_llevada_por_vendedora = FALSE, '
                            'dcasa_venta_online = FALSE WHERE id IN %s', [tuple(ordenes.ids)])
        ordenes.invalidate_recordset()
        especificacion = importlib.util.spec_from_file_location('migracion_online_comision', MIGRACION)
        modulo = importlib.util.module_from_spec(especificacion)
        especificacion.loader.exec_module(modulo)
        modulo.migrate(self.env.cr, '19.0.1.9.0')
        ordenes.invalidate_recordset()
        self.assertTrue(atendida.dcasa_llevada_por_vendedora and not atendida.dcasa_venta_online,
                        'confirmado y atendido por una vendedora antes del despliegue: no es online')
        self.assertTrue(sola.dcasa_nacio_en_web and sola.dcasa_venta_online)
        self.assertFalse(pagada.invoice_line_ids.sale_line_ids.order_id.dcasa_llevada_por_vendedora,
                         'ya pagado por completo: no se toca lo que ya pasó')

    def test_la_migracion_marca_las_cotizaciones_que_ya_armo_juan_y_respeta_a_la_vendedora(self):
        juan = self.env.ref('dcasa_conversaciones.user_juan')
        de_juan = self.orden(web=False)
        de_una_persona = self.orden(web=False)
        atendida = self.orden(web=False, cliente=self.env['res.partner'].create({
            'name': 'Cliente de Juan atendida', 'phone': '+507 6555-0397'}))
        self.env.cr.execute('UPDATE sale_order SET create_uid = %s WHERE id IN %s',
                            [juan.id, (de_juan.id, atendida.id)])
        self.hablar(atendida.partner_id, 'vendedora', hace_dias=2, id_externo='50761999007')
        (de_juan | de_una_persona | atendida).invalidate_recordset()
        especificacion = importlib.util.spec_from_file_location('migracion_online_juan', MIGRACION)
        modulo = importlib.util.module_from_spec(especificacion)
        especificacion.loader.exec_module(modulo)
        modulo.migrate(self.env.cr, '19.0.1.9.0')
        (de_juan | de_una_persona | atendida).invalidate_recordset()
        self.assertTrue(de_juan.dcasa_nacio_en_web and de_juan.dcasa_venta_online, 'la armó Juan: nació digital')
        self.assertFalse(de_una_persona.dcasa_nacio_en_web, 'la tecleó una persona: no')
        self.assertTrue(atendida.dcasa_nacio_en_web and atendida.dcasa_llevada_por_vendedora)
        self.assertFalse(atendida.dcasa_venta_online, 'de Juan pero una vendedora le escribió: es de ella')

    def test_un_hola_basta_para_que_la_venta_sea_de_la_vendedora_y_queda_para_revisar(self):
        """Decisión que se deja como está (y se vigila): un solo mensaje de una vendedora en los 30 días anteriores."""
        self.hablar(self.cliente, 'vendedora', hace_dias=5)
        orden = self.orden()
        self.assertTrue(orden.dcasa_llevada_por_vendedora and not orden.dcasa_venta_online)
        accion = self.env.ref('dcasa_comision_web.accion_pedidos_vigilados')
        dudosas = self.env['sale.order'].with_user(self.u_gerencia).search(
            safe_eval(accion.domain) + [('dcasa_llevada_por_vendedora', '=', True)])
        self.assertEqual(dudosas, orden)
