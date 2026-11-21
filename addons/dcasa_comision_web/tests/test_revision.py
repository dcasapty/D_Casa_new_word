"""Revisión adversarial independiente de la comisión del sitio web.

Cada prueba dice en su nombre qué se intentó. Las que **fallan hoy** demuestran un hallazgo del informe; las que
**pasan** dejan constancia de lo que se intentó y no se pudo romper. Cifras de PRUEBA.

"""
import logging
import time
from datetime import date, timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .test_comision import ComisionReloj
from .test_vendedoras import VendedoraCommon

_logger = logging.getLogger(__name__)


@tagged('post_install', '-at_install')
class TestRevisionOrigen(ComisionReloj):
    """¿Se puede fabricar el origen «web» de un pedido que no lo es?"""

    def _pedido_como(self, usuario, contexto=None, **extra):
        valores = {'partner_id': self.cliente.id, 'company_id': self.company.id, 'website_id': self.website.id,
                   'order_line': [Command.create({'product_id': self.mueble.id, 'product_uom_qty': 1,
                                                  'price_unit': 1000.0})], **extra}
        return self.env['sale.order'].with_user(usuario).with_context(**(contexto or {})).create(valores)

    def test_revision_01_una_vendedora_crea_un_pedido_de_tienda_con_website_id_y_nace_como_web(self):
        """HALLAZGO: ``website_id`` se acepta por RPC (``readonly`` solo vale en pantalla) y ``create`` lo toma como
        «nació en la web»: cualquiera que pueda crear cotizaciones fabrica una venta online."""
        orden = self._pedido_como(self.u_vendedora)
        self.assertFalse(orden.dcasa_nacio_en_web, 'un pedido creado a mano por una vendedora no nació en la página')
        self.assertFalse(orden.dcasa_venta_online)

    def test_revision_02_lo_mismo_con_el_contexto_default_website_id(self):
        orden = self.env['sale.order'].with_user(self.u_vendedora).with_context(
            default_website_id=self.website.id).create({
                'partner_id': self.cliente.id,
                'order_line': [Command.create({'product_id': self.mueble.id, 'product_uom_qty': 1,
                                               'price_unit': 1000.0})]})
        self.assertFalse(orden.dcasa_nacio_en_web)

    def test_revision_03_el_pedido_de_tienda_fabricado_como_web_cobra_comision_a_quienes_reciben(self):
        """De punta a punta: una venta de mostrador, con ``website_id`` puesto por quien la teclea, termina en el libro
        de quienes reciben (y fuera del bono de la vendedora)."""
        self.version(10.0)
        orden = self._pedido_como(self.u_gerencia, user_id=self.u_vendedora.id)
        orden.action_confirm()
        factura = self.facturar(orden)
        self.pagar(factura)
        self.assertFalse(self.libro(), 'una venta de mostrador no debe comisionar como venta del sitio')

    def test_revision_09_se_escribe_dcasa_venta_online_directamente_y_se_salta_las_tres_marcas(self):
        """HALLAZGO: ``write`` solo vigila las TRES marcas, pero todo el sistema lee ``dcasa_venta_online`` (campo
        calculado y guardado, que Odoo deja escribir por RPC): se escribe directo, sin tocar las marcas."""
        for usuario in (self.u_gerencia, self.u_nomina):
            with self.subTest(sentido='tienda -> online', usuario=usuario.login):
                tienda = self.orden(web=False)
                tienda.with_user(usuario).write({'dcasa_venta_online': True})
                self.assertFalse(tienda.dcasa_venta_online, 'una venta de tienda se volvió «online» a mano')
            with self.subTest(sentido='online -> no online', usuario=usuario.login):
                web = self.orden()
                web.with_user(usuario).write({'dcasa_venta_online': False})
                self.assertTrue(web.dcasa_venta_online, 'una venta online dejó de serlo a mano')

    def test_revision_09a_una_vendedora_saca_de_lo_online_un_pedido_suyo_de_la_pagina(self):
        """La vendedora que confirmó un pedido de la página (queda como su ``user_id``) lo escribe ella misma."""
        web = self.orden(vendedora=self.u_vendedora)
        try:
            web.with_user(self.u_vendedora).write({'dcasa_venta_online': False})
        except (AccessError, UserError):
            return
        self.assertTrue(web.dcasa_venta_online, 'la vendedora se quitó de encima lo online y ahora le suma a su meta')

    def test_revision_09b_dcasa_venta_online_se_fabrica_al_crear(self):
        orden = self.env['sale.order'].with_user(self.u_vendedora).create({
            'partner_id': self.cliente.id, 'dcasa_venta_online': True,
            'order_line': [Command.create({'product_id': self.mueble.id, 'product_uom_qty': 1,
                                           'price_unit': 1000.0})]})
        self.assertFalse(orden.dcasa_venta_online)

    def test_revision_04_duplicar_un_pedido_de_la_pagina_no_hereda_el_origen(self):
        web = self.orden()
        copia = web.copy()
        self.assertFalse(copia.dcasa_nacio_en_web, 'la copia no nació en la página')

    def test_revision_05_el_origen_no_se_cambia_por_write_ni_sudo_ni_contexto(self):
        orden = self.orden(web=False)
        with self.assertRaises(UserError):
            orden.write({'dcasa_nacio_en_web': True})
        with self.assertRaises(UserError):
            orden.sudo().with_context(dcasa_base_escribir_testigo=True).write({'dcasa_nacio_en_web': True})
        with self.assertRaises(UserError):
            orden.sudo().with_context(dcasa_base_escribir_testigo=1).write({'dcasa_via_andres': True})
        self.assertFalse(orden.dcasa_nacio_en_web)

    def test_revision_06_vendedora_que_solo_manda_un_hola_se_lleva_la_venta(self):
        """CONFIRMA lo que hace hoy el código: un solo mensaje de una vendedora en 30 días saca la venta de lo online
        (la vendedora se queda con el bono, el sitio no comisiona)."""
        self.hablar(self.cliente, 'vendedora', hace_dias=29)
        orden = self.orden()
        self.assertTrue(orden.dcasa_llevada_por_vendedora)
        self.assertFalse(orden.dcasa_venta_online)

    def test_revision_07_la_ventana_de_treinta_dias_es_exacta_en_el_borde(self):
        self.hablar(self.cliente, 'vendedora', hace_dias=31)
        self.assertTrue(self.orden().dcasa_venta_online, 'a los 31 días ya no cuenta')

    def test_revision_08_un_mensaje_de_otro_cliente_de_la_misma_empresa_si_cuenta(self):
        """El chat se busca por ``commercial_partner_id``: si habló con otro contacto de la MISMA empresa, la venta se
        la lleva la vendedora (documentado como comportamiento, no es error)."""
        empresa = self.env['res.partner'].create({'name': 'Empresa comisión', 'is_company': True})
        contacto_a = self.env['res.partner'].create({'name': 'Contacto A', 'parent_id': empresa.id})
        contacto_b = self.env['res.partner'].create({'name': 'Contacto B', 'parent_id': empresa.id})
        self.hablar(contacto_a, 'vendedora', hace_dias=1, id_externo='50761999010')
        orden = self.orden(cliente=contacto_b)
        self.assertTrue(orden.dcasa_llevada_por_vendedora)


@tagged('post_install', '-at_install')
class TestRevisionProteccion(ComisionReloj):
    """«Quien cobra no aprueba lo suyo»."""

    def setUp(self):
        super().setUp()
        self.version(10.0)
        self.venta_web()
        self.avanzar('2030-04-02 15:00:00')

    def _armar(self, usuario=None, hasta='2030-03-31'):
        liq = self.env['dcasa.web.liquidacion'].with_user(usuario or self.u_nomina).create({
            'fecha_desde': '2030-03-01', 'fecha_hasta': hasta})
        liq.action_armar()
        return liq

    def test_revision_10_quien_cobra_se_suelta_de_su_ficha_y_se_aprueba_a_si_mismo(self):
        """HALLAZGO: la protección depende de que ``hr.employee.user_id`` / ``work_contact_id`` apunten al usuario, y
        «Administra la nómina» (que implica ``hr.group_hr_manager``) puede editar su propia ficha."""
        liq = self._armar()
        self.assertTrue(liq.with_user(self.u_ana).tu_cobras)
        otro = self.env['res.partner'].create({'name': 'Contacto cualquiera'})
        self.ana.with_user(self.u_ana).write({'user_id': False})              # dos ediciones de SU ficha, en dos pasos
        self.ana.with_user(self.u_ana).write({'work_contact_id': otro.id})   # (en uno solo, hr deja el contacto igual)
        with self.assertRaises(UserError):
            liq.with_user(self.u_ana).action_aprobar()
        self.assertEqual(liq.estado, 'borrador', 'quien cobra no pudo aprobar lo suyo')

    def test_revision_12_cambiar_el_reparto_justo_antes_de_aprobar_no_deja_aprobar_a_quien_pasa_a_cobrar(self):
        liq = self._armar(hasta='2030-04-30')
        self.avanzar('2030-04-03 15:00:00')
        self.version(10.0, reparto=[(self.empleado_nomina, 100.0)])
        self.venta_web(fecha='2030-04-03')
        with self.assertRaises(UserError):
            liq.with_user(self.u_nomina).action_aprobar()      # lo debido cambió: hay que armar otra vez
        liq.action_armar()
        with self.assertRaisesRegex(UserError, 'figuras entre quienes cobran'):
            liq.with_user(self.u_nomina).action_aprobar()       # ahora él cobra y no puede

    def test_revision_13_el_administrador_tecnico_ni_ve_ni_aprueba(self):
        liq = self._armar()
        with self.assertRaises(AccessError):
            liq.with_user(self.u_tecnico).action_aprobar()

    def test_revision_14_no_se_fabrican_renglones_ni_se_aprueba_con_renglones_inventados(self):
        with self.assertRaises(AccessError):
            self.env['dcasa.web.liquidacion'].with_user(self.u_nomina).create({
                'fecha_desde': '2030-03-01', 'fecha_hasta': '2030-03-31',
                'linea_ids': [Command.create({'empleado_id': self.ana.id, 'concepto': 'comision',
                                              'centavos': 99999999})]})

    def test_revision_15_aprobada_se_puede_cancelar_desde_la_pantalla(self):
        """HALLAZGO: en el formulario ``motivo_cancelacion`` se escribe con la liquidación «aprobada», pero ``write``
        solo deja editar fecha y referencia del pago: al guardar sale «no se edita» y no se puede cancelar nunca. La
        prueba de los autores usa ``_escribir`` y se salta este camino."""
        liq = self._armar()
        liq.action_aprobar()
        liq.with_user(self.u_nomina).write({'motivo_cancelacion': 'Se armó con el periodo equivocado'})
        liq.with_user(self.u_nomina).action_cancelar()
        self.assertEqual(liq.estado, 'cancelada')

    def test_revision_16_un_saldo_se_corrige_con_un_ajuste_que_existe_para_el_usuario(self):
        """HALLAZGO (funcional): la documentación manda corregir con «un ajuste» (liquidación pagada, tarifa parcial),
        pero no hay pantalla, asistente ni método público para anotarlo: el libro no tiene ``create`` para nadie."""
        modelos = self.env['ir.model'].search([('model', 'like', 'dcasa.web.%')]).mapped('model')
        self.assertTrue([m for m in modelos if 'ajuste' in m], f'ningún modelo ni asistente de ajustes: {modelos}')

    def test_revision_17_periodo_enorme_o_extremo_no_revienta(self):
        liq = self.env['dcasa.web.liquidacion'].with_user(self.u_nomina).create({
            'fecha_desde': '1900-01-01', 'fecha_hasta': '9999-12-31'})
        liq.action_armar()      # hoy: OverflowError (500) en lugar de un aviso; no es dinero


@tagged('post_install', '-at_install')
class TestRevisionDinero(VendedoraCommon):
    """Cuentas a mano con montos concretos."""

    def test_revision_20_cobrada_antes_de_la_primera_version_pero_registrada_despues_no_cobra_ni_cuenta_doble(self):
        """HALLAZGO: la fecha del pago la teclea Caja. Un pago de una venta online con fecha ANTERIOR al «rige desde»,
        registrado después, cuenta como «cobrado antes» para el bono de la vendedora (1,000) Y ADEMÁS el gancho lo
        comisiona al sitio con la versión de ahora (el barrido sí usa la versión del día del cobro)."""
        factura = self.facturar(self.orden(web=True, vendedora=self.u_vendedora), '2030-03-03')
        self.version(10.0)                                        # rige el 4 de marzo
        self.pagar(factura, '2030-03-03')                         # pago con fecha del 3, registrado el 4
        paga_a_la_vendedora = self.bono().cobrado > 0
        paga_al_sitio = bool(self.libro())
        self.assertFalse(paga_a_la_vendedora and paga_al_sitio,
                         'la misma venta online no puede pagar a la vendedora y al sitio a la vez')

    def test_revision_21_una_nota_aplicada_a_dos_facturas_se_resta_entera_en_cada_una(self):
        """HALLAZGO menor: ``_notas_de`` toma TODA la nota para cada factura a la que se aplicó una parte."""
        self.version(10.0)
        a = self.facturar(self.orden(), '2030-03-04')
        b = self.facturar(self.orden(), '2030-03-04')
        self.pagar(a, '2030-03-04', monto=770.0)              # a queda con 300 por cobrar
        nota = self.nota(a, 600.0, enlazada=False)            # 642 con ITBMS
        linea = nota.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        a.js_assign_outstanding_line(linea.id)                # absorbe 300 de los 642
        b.js_assign_outstanding_line(linea.id)                # absorbe los otros 342
        self.pagar(b, '2030-03-04')                           # b paga lo que le falta con dinero
        va, vb = self.venta(a), self.venta(b)
        self.assertTrue(va and vb, 'las dos facturas quedaron pagadas')
        self.assertLessEqual(va.devuelto_centavos + vb.devuelto_centavos, 60000,
                             'una nota de 600 sin ITBMS no puede restar más de 600 entre las dos facturas')

    def test_revision_22_un_pago_revertido_se_refleja_al_armar_la_liquidacion(self):
        """HALLAZGO: el libro se entera de un pago revertido o una factura vuelta a borrador solo con el barrido de la
        noche; mientras tanto se arma y se APRUEBA una liquidación que paga lo que ya no está cobrado."""
        self.version(10.0)
        factura = self.venta_web()
        factura.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable').remove_move_reconcile()
        liq = self.env['dcasa.web.liquidacion'].with_user(self.u_nomina).create({
            'fecha_desde': '2030-03-01', 'fecha_hasta': '2030-03-31'})
        liq.action_armar()
        self.assertFalse(liq.linea_ids, 'la factura ya no está pagada: no hay nada que liquidar')

    def test_revision_23_la_version_con_fecha_futura_puesta_por_error_se_puede_corregir(self):
        """HALLAZGO: una versión con el año equivocado queda para siempre (ni se edita ni se borra) y ninguna versión
        nueva puede empezar antes: el módulo queda trabado hasta esa fecha."""
        self.version(10.0, rige_desde=fields.Datetime.now() + timedelta(days=730))
        nueva = self.version(5.0)
        self.assertTrue(nueva)

    def test_revision_23b_la_fecha_que_trae_el_formulario_sigue_valida_unos_minutos_despues(self):
        """HALLAZGO (uso): el formulario trae «Rige desde» = el momento en que se abrió; quien tarda más de un minuto
        en llenarlo recibe «no se puede poner una fecha que ya pasó» al guardar."""
        por_defecto = self.env['dcasa.web.reglas'].default_get(['rige_desde'])['rige_desde']
        self.avanzar('2030-03-04 15:03:00')
        self.assertTrue(self.version(10.0, rige_desde=por_defecto))

    def test_revision_23c_antes_de_descuentos_una_devolucion_total_no_deja_comision(self):
        """HALLAZGO: con «Antes de los descuentos» la base es el precio de lista, pero lo devuelto se resta NETO (lo que
        se cobró): al devolver todo queda como base el descuento (10 % de 1,000 = 100) y se sigue pagando comisión."""
        self.version(10.0, base_descuentos='antes')
        factura = self.facturar(self.orden(lineas=[(self.mueble, 1000.0, 1, {'discount': 10.0})]))
        self.pagar(factura)
        self.assertEqual(self.venta(factura).base_centavos, 100000, 'precio de lista')
        self.nota(factura, 900.0)                                  # se devuelve TODO: 900 sin ITBMS
        self.assertEqual(self.venta(factura).base_centavos, 0, 'se devolvió todo: la base debe quedar en cero')
        self.assertEqual(self.venta(factura).comision_centavos, 0)

    def test_revision_23d_antes_de_descuentos_el_premio_tampoco_se_descuenta_de_lo_devuelto(self):
        self.version(10.0, base_descuentos='antes')
        factura = self.facturar(self.orden(lineas=[(self.mueble, 1000.0, 1, {}), (self.premio, -100.0, 1, {})]))
        self.pagar(factura)
        self.nota(factura, 900.0)                                  # devuelve todo lo que se cobró
        self.assertEqual(self.venta(factura).comision_centavos, 0, 'devuelto todo, no hay comisión')

    def test_revision_24_dos_versiones_a_la_vez_no_repiten_el_numero(self):
        self.version(10.0)
        self.version(11.0)
        numeros = self.env['dcasa.web.reglas'].search([]).mapped('numero')
        self.assertEqual(len(numeros), len(set(numeros)))

    def test_revision_25_tarifa_con_empleados_que_entran_y_salen_y_cambios_de_version(self):
        """A mano: v1 (12.34 por mes, Ana 60 / Beto 40) rige el 4/mar; v2 (100.00, solo Beto) rige el 10/abr;
        v3 (semanal 1.00, Ana 100 %) rige el 20/may (lunes 27/may el primero)."""
        Libro = self.env['dcasa.web.movimiento']
        self.version(0.0, tarifa=12.34)
        self.avanzar('2030-04-10 15:00:00')
        self.version(0.0, tarifa=100.0, reparto=[(self.beto, 100.0)])
        self.avanzar('2030-05-20 15:00:00')
        self.version(0.0, tarifa=1.0, tarifa_periodo='semanal', reparto=[(self.ana, 100.0)])
        Libro._cron_tarifa(hoy=date(2030, 5, 31))
        filas = {(f.empleado_id, f.periodo_inicio): f.centavos for f in self.libro(tipo='tarifa')}
        self.assertEqual(filas, {
            (self.ana, date(2030, 4, 1)): 741, (self.beto, date(2030, 4, 1)): 493,   # v1 a las 00:00 del 1/abr
            (self.beto, date(2030, 5, 1)): 10000,                                        # v2
            (self.ana, date(2030, 5, 27)): 100,                                          # v3, primer lunes
        })
        # idempotente y sin dobles
        self.assertEqual(Libro._cron_tarifa(hoy=date(2030, 5, 31)), 0)

    def test_revision_26_reparto_con_centavos_que_no_cuadran_suma_exacto(self):
        from odoo.addons.dcasa_comision_web.models import calculo
        for total in (1, 2, 3, 99, 100, 101, 33333, 100001):
            partes = calculo.repartir(total, [(1, 33.33), (2, 33.33), (3, 33.34)])
            self.assertEqual(sum(partes.values()), total, total)
            self.assertTrue(all(v >= 0 for v in partes.values()))

    def test_revision_27_el_reparto_que_no_suma_cien_no_se_guarda_ni_por_rpc(self):
        with self.assertRaises(ValidationError):
            self.version(10.0, reparto=[(self.ana, 60.0), (self.beto, 39.99)])
        with self.assertRaises(ValidationError):
            self.version(10.0, reparto=[(self.ana, 100.0), (self.ana, 0.01)])

    def test_revision_28_el_libro_no_se_fabrica_desde_fuera(self):
        for usuario in (self.u_nomina, self.u_gerencia, self.u_tecnico, self.u_vendedora):
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                self.env['dcasa.web.movimiento'].with_user(usuario).create({
                    'empleado_id': self.ana.id, 'company_id': self.company.id, 'tipo': 'ajuste',
                    'concepto': 'comision', 'centavos': 1000000, 'autor': 'x', 'mes': '2030-03-01', 'motivo': 'x'})

    def test_revision_29_los_candados_de_una_venta_usan_la_misma_llave_en_el_gancho_y_en_la_comparacion(self):
        """``_registrar`` toma el candado con el id de la FACTURA y ``_reconciliar`` con el id de la VENTA: dos llaves
        distintas para lo mismo (y, en cambio, la misma llave para cosas distintas cuando los ids coinciden)."""
        self.version(10.0)
        factura = self.venta_web()
        venta = self.venta(factura)
        self.env.cr.execute("SELECT objid FROM pg_locks WHERE locktype = 'advisory' AND classid = %s "
                            "AND pid = pg_backend_pid()", [731_900_102])
        llaves = {fila[0] for fila in self.env.cr.fetchall()}
        self.assertEqual(llaves, {venta.id}, f'llaves tomadas {llaves}: factura={factura.id} venta={venta.id}')

    def test_revision_31_el_barrido_con_muchas_ventas_toma_un_tiempo_razonable(self):
        """Mide (no afirma) cuánto cuesta cada venta en el barrido nocturno, que recorre TODAS las ventas con reglas."""
        self.version(10.0)
        for _ in range(25):
            self.venta_web()
        Venta = self.env['dcasa.web.venta']
        inicio, consultas = time.perf_counter(), self.env.cr.sql_log_count
        Venta._barrido()
        segundos = time.perf_counter() - inicio
        por_venta = (self.env.cr.sql_log_count - consultas) / 25
        _logger.warning('Barrido: 25 ventas en %.2f s, %.1f consultas por venta', segundos, por_venta)
        self.assertLess(por_venta, 40, 'consultas por venta en el barrido')


@tagged('post_install', '-at_install')
class TestRevisionErroresYRendimiento(ComisionReloj):
    """«Un error de la comisión nunca frena un cobro» y lo que cuesta cada cobro."""

    def test_revision_40_un_error_a_mitad_de_la_anotacion_no_deja_filas_a_medias_ni_frena_el_cobro(self):
        from unittest.mock import patch

        from odoo.addons.dcasa_comision_web.models import calculo
        from odoo.tools import mute_logger
        self.version(10.0)
        factura = self.facturar(self.orden())
        with patch.object(calculo, 'repartir', side_effect=RuntimeError('reparto roto')), \
                mute_logger('odoo.addons.dcasa_comision_web.models.account_move'):
            self.pagar(factura)
        self.assertIn(factura.payment_state, ('paid', 'in_payment'), 'el cobro quedó hecho')
        self.assertFalse(self.venta(factura), 'la fila de la venta se deshizo con el savepoint')
        self.assertFalse(self.libro())
        self.env['dcasa.web.venta']._barrido()
        self.assertEqual(self.centavos_de(self.ana), 6000, 'el barrido la anota cuando el error pasa')

    def centavos_de(self, empleado):
        return sum(self.libro(empleado=empleado).mapped('centavos'))

    def test_revision_41_un_receptor_archivado_o_una_version_en_pausa_no_frena_nada(self):
        self.version(10.0)
        self.beto.active = False
        factura = self.venta_web()
        self.assertEqual(self.centavos_de(self.ana), 6000)
        self.assertEqual(self.centavos_de(self.beto), 4000, 'el archivado conserva lo suyo')
        self.avanzar('2030-03-05 15:00:00')
        self.version(0.0, reparto=[])                      # una pausa
        otra = self.venta_web(fecha='2030-03-05')
        self.assertEqual(self.venta(otra).comision_centavos, 0)
        self.assertTrue(self.venta(factura))

    def test_revision_42_cuanto_cuesta_el_gancho_en_el_cobro_de_una_venta_que_no_es_del_sitio(self):
        """Consultas que ``_registrar`` hace en el cobro de una factura de la TIENDA (la mayoría de los cobros)."""
        Venta = self.env['dcasa.web.venta']
        tienda = self.facturar(self.orden(web=False))
        self.pagar(tienda)
        Venta._registrar(tienda)                                   # calienta
        antes = self.env.cr.sql_log_count
        Venta._registrar(tienda)
        n_tienda = self.env.cr.sql_log_count - antes
        web = self.venta_web()
        antes = self.env.cr.sql_log_count
        Venta._registrar(web)                                      # ya existe: solo compara con el libro
        n_web_existente = self.env.cr.sql_log_count - antes
        _logger.warning('Gancho: factura de tienda %s consultas; factura web ya anotada %s', n_tienda,
                        n_web_existente)
        self.assertLessEqual(n_tienda, 12)

    def test_revision_43_una_factura_que_se_borra_no_deja_la_comision_viva(self):
        """Una factura vuelta a borrador y BORRADA antes del barrido: ``move_id`` queda en NULL (``set null``) y
        ``_reconciliar`` salta las ventas sin factura (``if not move: continue``): la comisión nunca se reversa."""
        from odoo.exceptions import UserError
        self.version(10.0)
        factura = self.venta_web()
        self.assertEqual(self.centavos_de(self.ana), 6000)
        factura.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable').remove_move_reconcile()
        factura.button_draft()
        try:
            with self.env.cr.savepoint():
                factura.unlink()
        except UserError:
            self.skipTest('Odoo no deja borrar una factura que ya se publicó: no hay camino')
        self.env['dcasa.web.venta']._barrido()
        self.assertEqual(self.centavos_de(self.ana), 0, 'la factura ya no existe: lo anotado debe reversarse')


@tagged('post_install', '-at_install')
class TestRevisionNoRomperLoExistente(VendedoraCommon):
    """Lo que NO es online da exactamente lo mismo antes y después de que exista la primera versión."""

    def test_revision_50_bono_e_inicio_de_la_tienda_son_identicos_con_y_sin_version(self):
        a = self.vender(web=False, pago='2030-03-05')
        b = self.vender(web=False, pago='2030-03-06', precio=500.0)
        self.nota(b, 200.0, fecha='2030-03-07')
        self.hablar(self.cliente, 'vendedora', hace_dias=1)
        juan = self.vender(web=True, pago='2030-03-08', precio=300.0)     # Juan + vendedora: no es online
        self.assertFalse(juan.line_ids.sale_line_ids.order_id.dcasa_venta_online)
        apartado = self.facturar(self.orden(web=False, vendedora=self.u_vendedora,
                                            lineas=[(self.mueble, 800.0, 1, {})]), '2030-03-05')
        self.pagar(apartado, '2030-03-05', monto=100.0)                     # pagada a medias: no cuenta

        def foto():
            bono = self.bono()
            tarjeta = self.Bono._para_inicio(self.u_vendedora, date(2030, 3, 10))
            return (bono.cobrado, sorted(bono.factura_ids.ids), sorted(bono.nota_ids.ids), tarjeta['avance_real'])

        antes = foto()
        self.assertEqual(antes[0], 1000.0 + 500.0 - 200.0 + 300.0)
        self.version(10.0)
        self.assertEqual(foto(), antes, 'una venta que no es online no cambia con la primera versión')
        self.assertTrue(a and b)


@tagged('post_install', '-at_install')
class TestRevisionVendedoresConCodigo(ComisionReloj):
    """Qué hace HOY el código con las ventas con código VEN (la pregunta abierta de los autores)."""

    from odoo.addons.dcasa_socios.tests.common import SociosCommon as _Socios
    activar_vendedores = _Socios.activar_vendedores
    vendedor = _Socios.vendedor

    def setUp(self):
        import os
        from unittest.mock import patch
        super().setUp()
        entorno = patch.dict(os.environ, {'DCASA_PIN_PEPPER': 'pimienta-de-prueba'})
        entorno.start()
        self.addCleanup(entorno.stop)
        self.activar_vendedores()
        self.codigo = self.vendedor('Vendedor Código RV', '8-901-234', '6100-0901')

    def comision(self, factura):
        return self.env['dcasa.vend.comision'].search([('move_id', '=', factura.id), ('tipo', '=', 'directa')])

    def venta_con_codigo(self, web, pago, cliente):
        factura = self.facturar(self.orden(web=web, cliente=cliente, dcasa_vendedor_id=self.codigo.id), pago)
        self.pagar(factura, pago)
        return factura

    def cliente_nuevo(self, n):
        return self.env['res.partner'].create({'name': f'Cliente RV {n}', 'phone': f'+507 6555-04{n:02d}',
                                               'email': f'rv{n}@example.com'})

    def test_revision_51_la_comision_de_vendedor_de_una_venta_de_tienda_es_la_misma_con_y_sin_version(self):
        antes = self.comision(self.venta_con_codigo(False, '2030-03-04', self.cliente_nuevo(1)))
        self.version(10.0)
        despues = self.comision(self.venta_con_codigo(False, '2030-03-04', self.cliente_nuevo(2)))
        self.assertEqual((antes.resultado, antes.puntos), (despues.resultado, despues.puntos))
        self.assertGreater(despues.puntos, 0)
