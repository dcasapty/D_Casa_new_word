"""La pantalla «Reparto»: Gerencia ve a todo el equipo y puede sacar a alguien del reparto; cada vendedora ve SOLO lo
suyo. La API (``dcasa.juan.panel.reparto``) y la pantalla en un navegador de verdad."""
import json
import re
from datetime import date, timedelta
from pathlib import Path

from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError
from odoo.service.model import call_kw
from odoo.tests import TransactionCase, tagged

from .test_panel_interfaz import GERENTE, VENDEDORA, PanelUiCase
from .test_reparto_justo import RepartoCase

ACCION_REPARTO = '/odoo/action-dcasa_conversaciones.accion_reparto'
FUENTES = Path(__file__).resolve().parents[1] / 'static' / 'src'


@tagged('post_install', '-at_install')
class TestApiDelReparto(RepartoCase):

    def setUp(self):
        super().setUp()
        self.gerencia = self.env['dcasa.juan.panel'].with_user(self.gerente)
        self.ana = self.env['dcasa.juan.panel'].with_user(self.vendedora)

    def fila(self, datos, usuario):
        return next(f for f in datos['equipo'] if f['usuario_id'] == usuario.id)

    # --- Gerencia ve todo -----------------------------------------------------------------------------------

    def test_gerencia_ve_a_cada_persona_con_lo_que_recibio_hoy_lo_que_le_espera_y_la_ultima(self):
        self.dar(self.vendedora, 2)
        self.dar(self.gerente, 1)
        self.hacer_esperar(self.beto, 3)
        datos = self.gerencia.reparto('hoy')
        self.assertTrue(datos['es_gerencia'])
        self.assertEqual((datos['modo'], datos['hoy']), ('parejo', '2026-10-09'))
        ana, beto, gema = (self.fila(datos, u) for u in (self.vendedora, self.beto, self.gerente))
        self.assertEqual((ana['recibidas'], ana['abiertas'], ana['estado']), (2, 0, 'disponible'))
        self.assertEqual((beto['recibidas'], beto['abiertas'], beto['ultima']), (0, 3, None))
        self.assertEqual((gema['recibidas'], gema['ultima']), (1, '2026-10-09T15:00:00Z'))
        self.assertEqual(datos['diferencia'], 2, 'Entre quien más recibió (2) y quien menos (0)')

    def test_la_diferencia_dice_si_va_parejo(self):
        for _n in range(7):
            self.pasar()
        self.assertEqual(self.gerencia.reparto('hoy')['diferencia'], 1)
        self.dar(self.vendedora, 3)
        recibidas = [f['recibidas'] for f in self.gerencia.reparto('hoy')['equipo'] if f['estado'] != 'fuera']
        self.assertEqual(self.gerencia.reparto('hoy')['diferencia'], max(recibidas) - min(recibidas))
        self.assertGreater(self.gerencia.reparto('hoy')['diferencia'], 1)

    def test_los_estados_de_cada_persona(self):
        self.beto.dcasa_disponible = False
        self.gerente.write({'dcasa_fuera_del_reparto': True, 'dcasa_fuera_hasta': date(2026, 10, 20)})
        datos = self.gerencia.reparto('hoy')
        self.assertEqual([self.fila(datos, u)['estado'] for u in (self.vendedora, self.beto, self.gerente)],
                         ['disponible', 'no_disponible', 'fuera'])
        self.assertEqual(self.fila(datos, self.gerente)['fuera_hasta'], '2026-10-20')
        self.assertIsNone(self.fila(datos, self.beto)['fuera_hasta'])

    def test_las_que_nadie_tiene_aparecen_aparte(self):
        self.assertEqual(self.gerencia.reparto('hoy')['sin_dueno'], {'conversaciones': 0, 'espera_mas_min': None})
        self.cliente().sudo().write({'estado': 'humano', 'ultimo_mensaje_cliente': self.AHORA - timedelta(minutes=25)})
        self.assertEqual(self.gerencia.reparto('hoy')['sin_dueno'], {'conversaciones': 1, 'espera_mas_min': 25})

    def test_siete_dias_suma_los_de_la_semana_y_hoy_solo_los_de_hoy(self):
        self.pasar()
        with freeze_time(self.AHORA + timedelta(days=2)):
            self.pasar()
            self.pasar()
            self.assertEqual(sum(f['recibidas'] for f in self.gerencia.reparto('hoy')['equipo']), 2)
            self.assertEqual(sum(f['recibidas'] for f in self.gerencia.reparto('7_dias')['equipo']), 3)
        with freeze_time(self.AHORA + timedelta(days=9)):
            self.assertEqual(sum(f['recibidas'] for f in self.gerencia.reparto('7_dias')['equipo']), 0)
            self.assertEqual(sum(f['recibidas'] for f in self.gerencia.reparto('30_dias')['equipo']), 3)

    def test_periodo_desconocido(self):
        with self.assertRaises(UserError):
            self.gerencia.reparto('siempre')

    # --- Cada vendedora ve solo lo suyo ---------------------------------------------------------------------

    def test_la_vendedora_ve_solo_lo_suyo(self):
        for _n in range(6):
            self.pasar()
        datos = self.ana.reparto('hoy')
        self.assertFalse(datos['es_gerencia'])
        self.assertEqual(datos['equipo'], [], 'Nada de las demás')
        self.assertIsNone(datos['sin_dueno'])
        self.assertIsNone(datos['diferencia'])
        self.assertEqual(datos['yo']['usuario_id'], self.vendedora.id)
        self.assertEqual(datos['yo']['recibidas'], 2)
        self.assertEqual(len(datos['mis_conversaciones']), 2)
        # En ninguna parte de lo que viaja aparece el nombre de otra persona.
        texto = json.dumps(datos)
        for otra in (self.beto, self.gerente):
            self.assertNotIn(otra.name, texto)

    def test_sus_conversaciones_son_las_que_juan_le_paso_y_dicen_como_van(self):
        propias = [c for c in (self.pasar() for _n in range(6)) if c.asignada_a == self.vendedora]
        self.assertEqual(len(propias), 2)
        tomada, suya = propias
        tomada.sudo().write({'asignada_a': self.beto.id})   # otra persona la tomó
        suya._crear_mensaje_de_odoo('Hola, te ayudo', usuario=self.vendedora)
        filas = {f['conversacion_id']: f for f in self.ana.reparto('hoy')['mis_conversaciones']}
        self.assertFalse(filas[tomada.id]['sigue_conmigo'])
        self.assertTrue(filas[suya.id]['sigue_conmigo'])
        self.assertIsNone(filas[suya.id]['esperando_desde'], 'Ya le contestó')
        self.assertIsNotNone(filas[tomada.id]['esperando_desde'], 'El cliente escribió y nadie ha contestado')

    def test_una_conversacion_que_le_paso_dos_veces_sale_una_sola_vez(self):
        self.ajustes.reparto_dias_misma_vendedora = 0
        conv = self.pasar()
        duena = conv.asignada_a
        conv._devolver(duena)
        for otra in self.equipo - duena:
            otra.dcasa_disponible = False
        with freeze_time(self.AHORA + timedelta(days=1)):
            conv._pasar_a_vendedora('Otra vez')
            filas = self.env['dcasa.juan.panel'].with_user(duena).reparto('7_dias')['mis_conversaciones']
        self.assertEqual([f['conversacion_id'] for f in filas], [conv.id])

    def test_la_gerente_tambien_tiene_lo_suyo(self):
        self.dar(self.gerente, 1)
        self.assertEqual(self.gerencia.reparto('hoy')['yo']['recibidas'], 1)

    # --- Permisos ---------------------------------------------------------------------------------------------

    def test_solo_el_equipo_de_ventas_abre_la_pantalla(self):
        for usuario in (self.interno, self.portal):
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                call_kw(self.env(user=usuario)['dcasa.juan.panel'], 'reparto', ['hoy'], {})

    def test_cambiar_el_reparto_es_solo_de_gerencia(self):
        llamadas = (('fijar_fuera_del_reparto', [self.beto.id, True, None]), ('fijar_modo_reparto', ['parejo']))
        for usuario in (self.vendedora, self.interno, self.portal):
            for metodo, argumentos in llamadas:
                with self.subTest(usuario=usuario.login, metodo=metodo), self.assertRaises(AccessError):
                    call_kw(self.env(user=usuario)['dcasa.juan.panel'], metodo, argumentos, {})
        self.assertFalse(self.beto.dcasa_fuera_del_reparto)
        self.assertEqual(self.ajustes.reparto_modo, 'parejo')

    def test_el_libro_del_reparto_solo_lo_lee_gerencia_y_nadie_lo_escribe(self):
        self.pasar()
        libro = self.env['dcasa.reparto']
        self.assertTrue(libro.with_user(self.gerente).search([]))
        with self.assertRaises(AccessError):
            libro.with_user(self.vendedora).search([])
        with self.assertRaises(AccessError):
            libro.with_user(self.gerente).create({
                'conversacion_id': self.cliente().id, 'usuario_id': self.beto.id, 'dia': date(2026, 10, 9),
                'regla': 'parejo'})

    # --- Sacar a alguien del reparto y volverla a meter ------------------------------------------------------

    def test_gerencia_saca_a_alguien_del_reparto_y_la_vuelve_a_meter(self):
        r = self.gerencia.fijar_fuera_del_reparto(self.beto.id, True, '2026-10-20')
        self.assertEqual(r, {'usuario_id': self.beto.id, 'fuera': True, 'vuelve': '2026-10-20'})
        self.assertEqual((self.beto.dcasa_fuera_del_reparto, self.beto.dcasa_fuera_hasta), (True, date(2026, 10, 20)))
        self.assertEqual(self.fila(self.gerencia.reparto('hoy'), self.beto)['estado'], 'fuera')
        self.assertNotIn(self.beto, [self.pasar().asignada_a for _n in range(6)])
        r = self.gerencia.fijar_fuera_del_reparto(self.beto.id, False)
        self.assertEqual(r, {'usuario_id': self.beto.id, 'fuera': False, 'vuelve': None})
        self.assertEqual((self.beto.dcasa_fuera_del_reparto, self.beto.dcasa_fuera_hasta), (False, False))
        self.assertIn(self.beto, [self.pasar().asignada_a for _n in range(6)])

    def test_sacar_a_alguien_no_le_quita_permisos_ni_las_conversaciones_que_ya_tiene(self):
        conv = self.pasar()
        duena = conv.asignada_a
        grupos = duena.group_ids
        self.gerencia.fijar_fuera_del_reparto(duena.id, True)
        self.assertEqual(duena.group_ids, grupos)
        self.assertEqual(conv.asignada_a, duena)
        self.assertTrue(duena.has_group('sales_team.group_sale_salesman'))
        self.assertTrue(self.Conversacion.with_user(duena).iniciar_panel()['usuario']['fuera_del_reparto'])
        self.assertTrue(self.Conversacion.with_user(duena).lista()['conversaciones'], 'Sigue viendo todo')

    def test_sin_fecha_queda_sin_fecha_de_regreso(self):
        self.gerencia.fijar_fuera_del_reparto(self.beto.id, True, '2026-10-20')
        self.gerencia.fijar_fuera_del_reparto(self.beto.id, True, None)
        self.assertFalse(self.beto.dcasa_fuera_hasta)

    def test_queda_en_el_historial_de_los_ajustes_quien_lo_hizo(self):
        antes = len(self.ajustes.message_ids)
        self.gerencia.fijar_fuera_del_reparto(self.beto.id, True, '2026-10-20')
        self.gerencia.fijar_fuera_del_reparto(self.beto.id, False)
        nuevos = self.ajustes.message_ids[:len(self.ajustes.message_ids) - antes].sorted('id')
        textos = [m.body for m in nuevos]
        self.assertIn(f'{self.gerente.name} sacó a {self.beto.name} del reparto', str(textos[0]))
        self.assertIn('Vuelve el 20/10/2026', str(textos[0]))
        self.assertIn(f'{self.gerente.name} volvió a meter a {self.beto.name}', str(textos[1]))

    def test_valida_lo_que_recibe(self):
        self.assertTrue(self.gerencia.fijar_fuera_del_reparto(self.beto.id, True, '2026-10-20'))
        malas = (
            ('no', True, None), (True, True, None), (0, True, None), (self.beto.id, 'si', None),
            (self.beto.id, True, '20/10/2026'), (self.beto.id, True, 'mañana'), (self.beto.id, True, '2026-10-09'),
            (self.beto.id, True, '2026-10-01'), (self.interno.id, True, None), (self.juan.id, True, None),
            (999999, True, None),
        )
        for usuario_id, fuera, vuelve in malas:
            with self.subTest(usuario_id=usuario_id, fuera=fuera, vuelve=vuelve), self.assertRaises(UserError):
                self.gerencia.fijar_fuera_del_reparto(usuario_id, fuera, vuelve)

    def test_gerencia_enciende_y_apaga_el_reparto_desde_la_pantalla(self):
        self.ajustes.reparto_modo = 'manual'
        r = self.gerencia.fijar_modo_reparto('parejo')
        self.assertEqual((r['modo'], self.ajustes.reparto_modo), ('parejo', 'parejo'))
        self.assertTrue(self.ajustes._fields['reparto_modo'].tracking, 'Queda en el historial de los ajustes')
        self.gerencia.fijar_modo_reparto('manual')
        self.assertEqual(self.ajustes.reparto_modo, 'manual')
        for malo in ('al_azar', '', None, 3, ['parejo']):
            with self.subTest(malo=malo), self.assertRaises(UserError):
                self.gerencia.fijar_modo_reparto(malo)

    def test_la_pantalla_de_conversaciones_sabe_el_modo_y_si_la_sacaron(self):
        panel = self.Conversacion.with_user(self.vendedora)
        datos = panel.iniciar_panel()
        self.assertEqual((datos['reparto'], datos['usuario']['fuera_del_reparto']), ('parejo', False))
        self.vendedora.dcasa_fuera_del_reparto = True
        self.assertTrue(panel.iniciar_panel()['usuario']['fuera_del_reparto'])
        self.vendedora.dcasa_fuera_hasta = date(2026, 10, 9)    # hoy mismo: ya volvió
        self.assertFalse(panel.iniciar_panel()['usuario']['fuera_del_reparto'])


@tagged('post_install', '-at_install')
class TestRepartoEnElNavegador(PanelUiCase):
    """La pantalla «Reparto» en Chromium: lo que ve una vendedora y lo que ve Gerencia."""

    def setUp(self):
        super().setUp()
        self.ajustes.reparto_modo = 'parejo'
        equipo = self.vendedora | self.gerente
        (self.env['dcasa.conversacion']._usuarios_del_panel() - equipo).write({'dcasa_fuera_del_reparto': True})
        equipo.write({'dcasa_disponible': True, 'dcasa_fuera_del_reparto': False, 'dcasa_turno': 0})
        for n in range(4):
            conv = self.registrar('Hola, busco una cama', f'5063100{n:04d}', nombre=f'Cliente Reparto {n}')
            conv._pasar_a_vendedora('Quiere una cotización')

    def test_la_vendedora_ve_solo_lo_suyo_y_puede_abrir_la_conversacion(self):
        self.navegador("""
(async () => {
    await esperar(() => document.querySelector(".o_dcj_reparto_mias .o_dcj_mis_recibidas"), "sus números");
    const titulo = document.querySelector(".o_dcj_p_titulo h1").textContent.trim();
    if (titulo !== "Mis conversaciones de hoy") { throw new Error("el título dice: " + titulo); }
    const valor = (clase) => document.querySelector(clase + " .o_dcj_p_valor").textContent.trim();
    if (valor(".o_dcj_mis_recibidas") !== "2") { throw new Error("recibidas: " + valor(".o_dcj_mis_recibidas")); }
    if (valor(".o_dcj_mis_abiertas") !== "2") { throw new Error("esperan: " + valor(".o_dcj_mis_abiertas")); }
    if (document.querySelector(".o_dcj_reparto_equipo")) { throw new Error("la vendedora no ve a todo el equipo"); }
    if (document.body.textContent.includes("Gema Gerente")) { throw new Error("nombre de otra persona a la vista"); }
    const nav = [...document.querySelectorAll(".o_dcj_p_nav_boton")].map((e) => e.textContent.trim());
    if (nav.join("|") !== "Conversaciones|Resumen|Reparto") { throw new Error("la barra: " + nav.join("|")); }
    const filas = document.querySelectorAll(".o_dcj_reparto_mias_tabla tbody tr");
    if (filas.length !== 2) { throw new Error("sus conversaciones: " + filas.length); }
    if (!filas[0].textContent.includes("Te espera")) { throw new Error("cómo va: " + filas[0].textContent); }
    const nombre = filas[0].querySelector("th").textContent.trim();
    filas[0].querySelector(".o_dcj_enlace").click();
    await esperar(() => document.querySelector(".o_dcj_hilo_cabecera"), "el hilo");
    const cabecera = () => document.querySelector(".o_dcj_hilo_cabecera");
    await esperar(() => cabecera().textContent.includes(nombre), "la conversación de " + nombre);
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", url=ACCION_REPARTO)

    def test_gerencia_ve_a_todo_el_equipo_y_saca_a_alguien_del_reparto_sin_quitarle_permisos(self):
        self.navegador("""
(async () => {
    await esperar(() => document.querySelector(".o_dcj_reparto_equipo .o_dcj_reparto_tabla"), "la tabla del equipo");
    const titulo = document.querySelector(".o_dcj_p_titulo h1").textContent.trim();
    if (titulo !== "Reparto") { throw new Error("el título dice: " + titulo); }
    const fila = (nombre) => aqui(".o_dcj_reparto_tabla tbody tr", nombre);
    const ana = fila("Ana Vendedora");
    const gema = fila("Gema Gerente");
    if (!ana || !gema) { throw new Error("falta alguien en la tabla"); }
    const recibidas = ana.querySelector(".o_dcj_reparto_recibidas").textContent.trim();
    if (recibidas !== "2") { throw new Error("Ana recibió 2: " + ana.textContent); }
    if (!ana.textContent.includes("Disponible")) { throw new Error("Ana está disponible: " + ana.textContent); }
    if (document.querySelector(".o_dcj_reparto_apagado")) { throw new Error("no debe salir el aviso de apagado"); }
    // Sacar a Ana del reparto.
    ana.querySelector(".o_dcj_sacar").click();
    await esperar(() => fila("Ana Vendedora").classList.contains("o_fuera"), "que Ana quede fuera del reparto");
    const textoDeAna = () => fila("Ana Vendedora").textContent;
    if (!textoDeAna().includes("No recibe")) { throw new Error("debe decir «No recibe»: " + textoDeAna()); }
    // Volverla a meter.
    fila("Ana Vendedora").querySelector(".o_dcj_volver").click();
    await esperar(() => !fila("Ana Vendedora").classList.contains("o_fuera"), "que Ana vuelva al reparto");
    // Y otra vez fuera, ahora con el día en que vuelve.
    fila("Ana Vendedora").querySelector(".o_dcj_sacar").click();
    const campo = () => fila("Ana Vendedora").querySelector("input[type=date]");
    const entrada = await esperar(campo, "el día en que vuelve");
    entrada.value = "2099-01-05";
    entrada.dispatchEvent(new Event("change", { bubbles: true }));
    await esperar(() => textoDeAna().includes("05/01/2099"), "la fecha de regreso");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", url=ACCION_REPARTO, login=GERENTE)
        self.env.invalidate_all()
        self.assertTrue(self.vendedora.dcasa_fuera_del_reparto)
        self.assertEqual(self.vendedora.dcasa_fuera_hasta, date(2099, 1, 5))
        self.assertTrue(self.vendedora.has_group('sales_team.group_sale_salesman'), 'Conserva sus permisos')
        self.assertEqual(self.env['dcasa.conversacion'].search_count([('asignada_a', '=', self.vendedora.id)]), 2,
                         'Y las conversaciones que ya tenía')

    def test_gerencia_enciende_el_reparto_con_un_clic_si_estaba_apagado(self):
        self.ajustes.reparto_modo = 'manual'
        self.navegador("""
(async () => {
    const aviso = await esperar(() => document.querySelector(".o_dcj_reparto_apagado"), "el aviso de reparto apagado");
    if (!aviso.textContent.includes("El reparto está apagado")) { throw new Error("dice: " + aviso.textContent); }
    aviso.querySelector(".o_dcj_encender").click();
    await esperar(() => !document.querySelector(".o_dcj_reparto_apagado"), "que el aviso desaparezca al encenderlo");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", url=ACCION_REPARTO, login=GERENTE)
        self.env.invalidate_all()
        self.assertEqual(self.ajustes.reparto_modo, 'parejo')

    def test_la_lista_de_conversaciones_dice_si_gerencia_la_saco_del_reparto(self):
        self.vendedora.dcasa_fuera_del_reparto = True
        self.navegador("""
(async () => {
    const aviso = await esperar(() => document.querySelector(".o_dcj_fuera_del_reparto"), "el aviso de fuera");
    if (!aviso.textContent.includes("Fuera del reparto")) { throw new Error("dice: " + aviso.textContent); }
    if (document.querySelector("button.o_dcj_disponible")) { throw new Error("no debe salir el interruptor"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", login=VENDEDORA)

    def test_con_el_reparto_parejo_la_vendedora_ve_el_interruptor_de_disponible(self):
        self.navegador("""
(async () => {
    const boton = await esperar(() => document.querySelector("button.o_dcj_disponible"), "el interruptor");
    if (!boton.textContent.includes("Disponible para conversaciones nuevas")) {
        throw new Error("dice: " + boton.textContent);
    }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", login=VENDEDORA)


@tagged('post_install', '-at_install')
class TestContratoDeLaPantallaReparto(TransactionCase):
    """Lo que no se ve en las otras pruebas: la marca (plano, sin amarillo sobre blanco) y lo accesible."""

    def bloque(self, scss, selector):
        inicio = scss.index(selector + ' {')
        profundidad, i = 0, scss.index('{', inicio)
        for j in range(i, len(scss)):
            profundidad += {'{': 1, '}': -1}.get(scss[j], 0)
            if profundidad == 0:
                return scss[i + 1:j]
        raise AssertionError('regla sin cerrar')

    def test_el_estilo_es_plano_y_el_amarillo_no_toca_el_blanco(self):
        reparto = self.bloque((FUENTES / 'scss' / 'panel_pantallas.scss').read_text(encoding='utf-8'), '.o_dcj_reparto')
        self.assertNotRegex(reparto, r'(linear|radial)-gradient', 'sistema plano: sin degradados')
        self.assertNotRegex(reparto, r'box-shadow', 'sin sombras')
        self.assertNotIn('FED00F', reparto.upper(), 'el amarillo solo va sobre azul (el aviso marino ya existente)')

    def test_todo_boton_y_campo_tiene_nombre_para_quien_usa_lector_de_pantalla(self):
        xml = (FUENTES / 'xml' / 'reparto.xml').read_text(encoding='utf-8')
        for boton in re.findall(r'<button[^>]*?(?:/>|>.*?</button>)', xml, re.S):
            con_nombre = 'aria-label' in boton or re.search(r'>\s*[^<\s]', boton)
            self.assertTrue(con_nombre, f'botón sin texto ni nombre: {boton[:80]}')
        for campo in re.findall(r'<input[^>]*>', xml):
            self.assertIn('aria-label', campo)

    def test_la_pantalla_esta_en_el_menu_para_todo_el_equipo_de_ventas(self):
        menu = self.env.ref('dcasa_conversaciones.menu_dcasa_panel_reparto')
        self.assertEqual(menu.group_ids, self.env.ref('sales_team.group_sale_salesman'))
        self.assertEqual(self.env.ref('dcasa_conversaciones.accion_reparto').tag, 'dcasa_juan_reparto')
