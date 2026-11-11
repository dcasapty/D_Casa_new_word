"""«Entregas pendientes» del Inicio cuenta lo mismo que Bodega (decisión del 2026-11-11).

El panel del Inicio contaba todas las salidas pendientes y el acceso «Bodega», solo las de pedidos con pago o abono: el
Inicio podía decir «2 entregas pendientes» y, al lado, «Bodega: nada por despachar». Ahora el panel y su cifra muestran
las mismas entregas que Bodega, en su orden, y un renglón debajo dice cuántas más esperan pago o abono y abre esa lista.
"""
import json
import os
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, new_test_user, tagged

from .bodega_comun import BodegaCommon

TODAS = [('picking_type_code', '=', 'outgoing'), ('state', 'in', ('confirmed', 'waiting', 'assigned'))]


class EntregasDelInicioCommon(BodegaCommon):
    """Una entrega con pago y otra sin pago, y nada más pendiente (lo que hubiera en la base se cancela aquí)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Picking = cls.env['stock.picking']
        cls.Picking.search(TODAS).action_cancel()
        cls.gerente = new_test_user(cls.env, login='inicio_gerente_bodega', password='inicio_gerente_bodega',
                                    groups='dcasa_base.group_gerencia')
        cls.pedido_pagado, cls.entrega_pagada = cls.venta(cls.cliente('CLIENTE DE PRUEBA CON PAGO'), [(cls.mesa, 1)])
        cls.pedido_debe, cls.entrega_debe = cls.venta(cls.cliente('CLIENTE DE PRUEBA SIN PAGO'), [(cls.mesa, 1)],
                                                      pago=0)

    def inicio(self, usuario=None):
        return self.env['dcasa.tablero'].with_user(usuario or self.gerente).obtener_datos()

    def acceso_bodega(self, datos):
        return next(a for a in datos['atajos'] if a['clave'] == 'bodega')

    def cifra(self, datos):
        return next(c for c in datos['cifras'] if c['clave'] == 'entregas')

    def abre(self, accion):
        """Las entregas que abre una lista del Inicio."""
        self.assertEqual(accion['res_model'], 'stock.picking')
        return self.Picking.search(accion['domain'])


@tagged('post_install', '-at_install')
class TestEntregasDelInicio(EntregasDelInicioCommon):

    def test_el_panel_lista_y_cuenta_solo_la_pagada_y_bodega_dice_el_mismo_numero(self):
        datos = self.inicio()
        panel = datos['entregas']
        self.assertEqual([f['nombre'] for f in panel['filas']], [self.entrega_pagada.name])
        self.assertEqual(panel['filas'][0]['cliente'], 'CLIENTE DE PRUEBA CON PAGO')
        self.assertEqual(panel['filas'][0]['origen'], self.pedido_pagado.name)
        self.assertEqual(panel['cantidad'], 1)
        # Los tres números del Inicio y la pantalla Bodega dicen lo mismo.
        self.assertEqual(self.cifra(datos)['valor'], 1)
        self.assertEqual(self.acceso_bodega(datos)['cuenta'], 1)
        self.assertEqual(self.acceso_bodega(datos)['detalle'], '1 entrega por despachar')
        self.assertEqual(self.Bodega.with_user(self.gerente).pendientes()['cuantas'], 1)
        # «Ver la entrega» y la cifra abren exactamente la que se cuenta.
        self.assertEqual(self.abre(panel['accion']), self.entrega_pagada)
        self.assertEqual(self.abre(self.cifra(datos)['accion']), self.entrega_pagada)

    def test_el_renglon_dice_cuantas_esperan_pago_y_abre_esas(self):
        esperan = self.inicio()['entregas']['esperan']
        self.assertEqual(esperan['cantidad'], 1)
        self.assertEqual(esperan['texto'], '1 más espera pago o abono')
        self.assertEqual(esperan['accion']['name'], 'Entregas que esperan pago o abono')
        self.assertEqual(self.abre(esperan['accion']), self.entrega_debe)
        # Otra sin pago: en plural, y siguen sin contarse arriba.
        _pedido, otra = self.venta(self.cliente_sin, [(self.zapatera, 1)], pago=0)
        datos = self.inicio()
        self.assertEqual(datos['entregas']['esperan']['texto'], '2 más esperan pago o abono')
        self.assertEqual(self.abre(datos['entregas']['esperan']['accion']), self.entrega_debe | otra)
        self.assertEqual(datos['entregas']['cantidad'], 1)
        self.assertEqual(self.acceso_bodega(datos)['cuenta'], 1)

    def test_sin_ninguna_sin_pagar_el_renglon_no_sale(self):
        self.cobrar(self.pedido_debe)
        datos = self.inicio()
        self.assertNotIn('esperan', datos['entregas'])
        self.assertEqual(datos['entregas']['cantidad'], 2)
        self.assertEqual({f['nombre'] for f in datos['entregas']['filas']},
                         {self.entrega_pagada.name, self.entrega_debe.name})
        self.assertEqual(self.acceso_bodega(datos)['cuenta'], 2)
        self.assertEqual(self.abre(datos['entregas']['accion']), self.entrega_pagada | self.entrega_debe)

    def test_con_un_abono_ya_se_cuenta(self):
        self.cobrar(self.pedido_debe, 0.5)
        datos = self.inicio()
        self.assertEqual(datos['entregas']['cantidad'], 2)
        self.assertNotIn('esperan', datos['entregas'])

    def test_si_ninguna_tiene_pago_el_panel_queda_en_cero_como_bodega(self):
        """El caso que se veía mal: el Inicio decía «1 entrega pendiente» y Bodega «Nada por despachar»."""
        self.entrega_pagada.action_cancel()
        datos = self.inicio()
        self.assertEqual(datos['entregas']['cantidad'], 0)
        self.assertEqual(datos['entregas']['filas'], [])
        self.assertEqual(self.cifra(datos)['valor'], 0)
        self.assertEqual(self.acceso_bodega(datos)['detalle'], 'Nada por despachar')
        self.assertFalse(self.abre(datos['entregas']['accion']))
        # Sin nada arriba, el renglón no dice «más».
        self.assertEqual(datos['entregas']['esperan']['texto'], '1 espera pago o abono')
        self.assertEqual(self.abre(datos['entregas']['esperan']['accion']), self.entrega_debe)

    def test_van_en_el_mismo_orden_que_las_tarjetas_de_bodega(self):
        """Por la fecha prometida al cliente o, si no hay, la programada; y solo las cinco primeras."""
        ahora = fields.Datetime.now()
        pagadas = self.entrega_pagada
        for dias in (9, 2, 6, 4, 8, 1):
            _pedido, entrega = self.venta(self.cliente_envio, [(self.mesa, 1)])
            entrega.scheduled_date = ahora - timedelta(days=dias)
            pagadas |= entrega
        # Una programada para hace mucho, pero prometida para dentro de un mes: va al final, como en Bodega.
        prometido, prometida = self.venta(self.cliente_retiro, [(self.mesa, 1)])
        prometida.scheduled_date = ahora - timedelta(days=30)
        prometido.commitment_date = ahora + timedelta(days=30)
        pagadas |= prometida
        datos = self.inicio()
        tarjetas = [t['id'] for t in self.Bodega.with_user(self.gerente).pendientes()['entregas']]
        self.assertEqual(set(tarjetas), set(pagadas.ids))
        self.assertEqual(tarjetas[-1], prometida.id)
        self.assertEqual([f['id'] for f in datos['entregas']['filas']], tarjetas[:5])
        self.assertEqual(datos['entregas']['filas'][0]['dias'], 9)
        self.assertEqual(datos['entregas']['cantidad'], len(pagadas))
        self.assertEqual(self.abre(datos['entregas']['accion']), pagadas)
        self.assertEqual(self.acceso_bodega(datos)['cuenta'], len(pagadas))

    def test_una_salida_que_no_es_de_un_pedido_tampoco_se_pierde(self):
        """Bodega no la muestra (no hay pago que mirar): queda en el renglón, con su nombre propio."""
        tipo = self.almacen.out_type_id
        suelta = self.Picking.create({
            'picking_type_id': tipo.id, 'partner_id': self.cliente_sin.id,
            'location_id': tipo.default_location_src_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'move_ids': [(0, 0, {'product_id': self.mesa.id, 'product_uom_qty': 1,
                                 'location_id': tipo.default_location_src_id.id,
                                 'location_dest_id': self.env.ref('stock.stock_location_customers').id})],
        })
        suelta.action_confirm()
        esperan = self.inicio()['entregas']['esperan']
        self.assertEqual(esperan['cantidad'], 2)
        self.assertEqual(esperan['texto'], '1 más espera pago o abono y 1 no sale en Bodega')
        self.assertEqual(esperan['accion']['name'], 'Entregas pendientes que no salen en Bodega')
        self.assertEqual(self.abre(esperan['accion']), self.entrega_debe | suelta)

    def test_las_frases_del_renglon(self):
        frase = self.env['dcasa.tablero']._texto_de_las_que_esperan
        self.assertEqual(frase(1, 0, True), '1 más espera pago o abono')
        self.assertEqual(frase(3, 0, True), '3 más esperan pago o abono')
        self.assertEqual(frase(3, 0, False), '3 esperan pago o abono')
        self.assertEqual(frase(0, 1, True), '1 más no sale en Bodega')
        self.assertEqual(frase(0, 2, False), '2 no salen en Bodega')
        self.assertEqual(frase(2, 2, True), '2 más esperan pago o abono y 2 no salen en Bodega')

    def test_quien_no_despacha_ve_el_panel_de_siempre(self):
        """Sin permiso de Bodega no hay acceso «Bodega» con el que comparar: el panel sigue con todas las salidas."""
        ventas = new_test_user(self.env, login='inicio_ventas_sin_bodega', groups='sales_team.group_sale_manager')
        self.assertFalse(ventas.has_group('stock.group_stock_user'))
        datos = self.inicio(ventas)
        self.assertFalse([a for a in datos['atajos'] if a['clave'] == 'bodega'])
        self.assertEqual(datos['entregas']['cantidad'], 2)
        self.assertNotIn('esperan', datos['entregas'])
        self.assertEqual(self.abre(datos['entregas']['accion']), self.entrega_pagada | self.entrega_debe)

    def test_la_vendedora_sigue_sin_panel_y_con_su_acceso_a_bodega(self):
        rol = new_test_user(self.env, login='inicio_vendedora_bodega', groups='dcasa_base.group_vendedora')
        datos = self.inicio(rol)
        self.assertIsNone(datos['entregas'])
        self.assertFalse([c for c in datos['cifras'] if c['clave'] == 'entregas'])
        self.assertEqual(self.acceso_bodega(datos)['cuenta'], 1)


RENGLON_JS = r"""
(async () => {
    const D = __DATOS__;
    const esperar = async (fn, que, ms = 20000) => {
        const inicio = Date.now();
        while (Date.now() - inicio < ms) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error('Inicio: no apareció ' + que);
    };
    const igual = (visto, esperado, que) => {
        if (JSON.stringify(visto) !== JSON.stringify(esperado)) {
            throw new Error(`${que}: se vio ${JSON.stringify(visto)} y se esperaba ${JSON.stringify(esperado)}`);
        }
    };
    const texto = (el) => el.textContent.trim().replace(/\s+/g, ' ');
    const panel = await esperar(() => document.querySelector('.o_dcasa_tablero .o_dcasa_lista_entregas'), 'el panel');
    // El panel, su contador del celular y el acceso «Bodega» dicen el mismo número.
    igual(texto(panel.querySelector('.o_dcasa_lista_numero')), '1', 'el número del panel');
    igual([...panel.querySelectorAll('.o_dcasa_lista_fila .o_dcasa_lista_texto strong')].map(texto),
          ['CLIENTE DE PRUEBA CON PAGO'], 'las entregas del panel');
    const bodega = [...document.querySelectorAll('.o_dcasa_atajo')].find((a) => texto(a).includes('Bodega'));
    igual(texto(bodega.querySelector('.o_dcasa_atajo_cuenta')), '1', 'el número del acceso «Bodega»');
    igual(texto(document.querySelector('.o_dcasa_salto_entregas strong')), '1', 'el contador «Entregas»');
    igual(texto(panel.querySelector('.o_dcasa_lista_pie:not(.o_dcasa_lista_esperan) .o_dcasa_lista_ver')),
          'Ver la entrega', 'el pie de siempre');
    // El renglón nuevo: debajo de todo, discreto (gris, nunca amarillo) y dentro de la pantalla.
    const renglon = panel.querySelector('.o_dcasa_lista_esperan');
    if (!renglon || panel.lastElementChild !== renglon) { throw new Error('el renglón va al final del panel'); }
    const boton = renglon.querySelector('button');
    igual(texto(boton), '1 más espera pago o abono', 'lo que dice el renglón');
    igual(getComputedStyle(boton).color, 'rgb(68, 80, 106)', 'el renglón, en gris');
    const caja = boton.getBoundingClientRect();
    const dentro = panel.getBoundingClientRect();
    if (caja.height < 30 || caja.left < dentro.left || caja.right > dentro.right + 1) {
        throw new Error(`el renglón se sale o es muy chico: ${JSON.stringify(caja)}`);
    }
    const raiz = document.querySelector('.o_dcasa_tablero');
    if (raiz.scrollWidth > raiz.clientWidth + 1 || document.documentElement.scrollWidth > window.innerWidth + 1) {
        throw new Error('el Inicio se sale de costado');
    }
    // En pantallas táctiles Odoo les cambia la letra a los botones: el renglón sigue igual de discreto.
    const letra = getComputedStyle(boton).fontSize;
    document.body.classList.add('o_touch_device');
    igual(getComputedStyle(boton).fontSize, letra, 'la letra del renglón en pantalla táctil');
    document.body.classList.remove('o_touch_device');
    // Al tocarlo abre la lista de las que esperan: la otra entrega, y no la que ya se puede despachar.
    boton.click();
    const filas = await esperar(() => {
        const vistas = [...document.querySelectorAll('.o_list_view .o_data_row, .o_kanban_view .o_kanban_record')];
        return vistas.filter((f) => f.textContent.trim()).length && vistas;
    }, 'la lista de las que esperan pago');
    const vistas = filas.map(texto).filter(Boolean);
    igual(vistas.length, 1, 'cuántas abre: ' + vistas.join(' | '));
    if (!vistas[0].includes(D.debe) || vistas[0].includes(D.pagada)) {
        throw new Error('abre la que espera pago, no la otra: ' + vistas[0]);
    }
    console.log('test successful');
})();
"""


@tagged('post_install', '-at_install')
class TestEntregasDelInicioEnElNavegador(HttpCase, EntregasDelInicioCommon):

    def test_el_renglon_se_ve_y_abre_las_que_esperan_pago(self):
        if os.environ.get('DCASA_SIN_NAVEGADOR'):
            self.skipTest('sin navegador')
        codigo = RENGLON_JS.replace('__DATOS__', json.dumps({
            'pagada': self.entrega_pagada.name, 'debe': self.entrega_debe.name}))
        for tamano in ('390x844', '1366x768'):
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/action-dcasa_interfaz.action_dcasa_inicio', codigo,
                                login='inicio_gerente_bodega', timeout=120)
