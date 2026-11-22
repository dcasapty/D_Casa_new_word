"""«Margen y rotación» de la pantalla Rotación (pedido del jefe, 2026-11-22: «que se enfoque en aquellos de mejor
rotación o prueba en nuevos SKU que mejoren márgenes»): cada producto con existencias, costo y precio cae en uno de
cuatro cuadros, según se venda bien y deje buen margen. Los cortes son las medianas de la propia tienda.

Las pruebas con la base usan productos de extremos (margen de 95 % o de 1 %, 500 unidades o ninguna) para que el
cuadro no dependa de lo que más haya en la base; las medianas se prueban aparte, con filas inventadas.
"""
import io

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged

from .comun import MarketingCommon, crear_usuario


class MargenDatos(MarketingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hoy = fields.Date.context_today(cls.env['dcasa.rotacion'].with_user(cls.gerencia))
        cls.marketing_rol = crear_usuario(cls.env, 'zzmk_rol_marketing', ['dcasa_marketing.group_marketing'])
        cls.estrella = cls.articulo('ZZRM ESTRELLA', costo=50.0, vendidas=500)
        cls.trafico = cls.articulo('ZZRM TRAFICO', costo=990.0, vendidas=500)
        cls.oportunidad = cls.articulo('ZZRM OPORTUNIDAD', costo=50.0, vendidas=0)
        cls.revisar = cls.articulo('ZZRM REVISAR', costo=990.0, vendidas=0)
        cls.sin_costo = cls.articulo('ZZRM SIN COSTO', costo=0.0, vendidas=3)
        cls.agotado = cls.articulo('ZZRM AGOTADO', costo=50.0, vendidas=3, stock=0)

    @classmethod
    def articulo(cls, nombre, costo, vendidas, stock=5):
        """Un producto de $1000 (sin ITBMS) con ese costo, con existencias y con esas unidades vendidas hace 10 días."""
        plantilla = cls.producto(nombre, stock=0, precio=1000.0)
        plantilla.standard_price = costo
        if stock:
            cls.env['stock.quant']._update_available_quantity(
                plantilla.product_variant_id, cls.bodega_principal.lot_stock_id, stock)
        if vendidas:
            MarketingCommon.facturar(cls, plantilla, vendidas, 10)
        return plantilla


@tagged('post_install', '-at_install')
class TestRotacionMargen(MargenDatos):

    def datos(self, usuario=None, **kw):
        kw.setdefault('texto', 'ZZRM')
        return self.env['dcasa.rotacion'].with_user(usuario or self.gerencia).datos(**kw)

    def cuadros(self, **kw):
        return {f['nombre']: f['cuadrante'] for f in self.datos(vista='todos', **kw)['productos']}

    # --- Cada producto en su cuadro -----------------------------------------------------------------------------------

    def test_cada_producto_cae_en_su_cuadro(self):
        self.assertEqual(self.cuadros(), {
            'ZZRM ESTRELLA': 'estrella', 'ZZRM TRAFICO': 'trafico', 'ZZRM OPORTUNIDAD': 'oportunidad',
            'ZZRM REVISAR': 'revisar',
            'ZZRM SIN COSTO': None,      # sin costo no hay margen: no se puede decir en qué cuadro cae
        })
        self.assertNotIn('ZZRM AGOTADO', self.cuadros(), 'un agotado no tiene capital parado ni cuadro')

    def test_cada_lista_trae_sus_productos(self):
        for clave, nombre in (('estrella', 'ZZRM ESTRELLA'), ('trafico', 'ZZRM TRAFICO'),
                              ('oportunidad', 'ZZRM OPORTUNIDAD'), ('revisar', 'ZZRM REVISAR')):
            with self.subTest(vista=clave):
                datos = self.datos(vista=clave)
                self.assertEqual([f['nombre'] for f in datos['productos']], [nombre])
                self.assertEqual(datos['productos'][0]['nombre_cuadrante'], {
                    'estrella': 'Estrellas', 'trafico': 'Venden mucho, dejan poco',
                    'oportunidad': 'Buen margen, se mueven poco', 'revisar': 'Ni se mueven ni dejan margen'}[clave])

    def test_los_botones_de_margen_van_aparte_de_los_de_dias(self):
        vistas = self.datos()['vistas']
        de_margen = [v['clave'] for v in vistas if v['tipo'] == 'margen']
        self.assertEqual(de_margen, ['estrella', 'trafico', 'oportunidad', 'revisar'])
        self.assertTrue(all(v['ayuda'] for v in vistas if v['tipo'] == 'margen'))
        self.assertTrue(all(v['tipo'] == 'dias' for v in vistas if v['clave'] not in de_margen))
        total = sum(v['productos'] for v in vistas if v['tipo'] == 'margen')
        todos = next(v['productos'] for v in vistas if v['clave'] == 'todos')
        self.assertLessEqual(total, todos, 'cada producto cae en un solo cuadro (o en ninguno si no tiene costo)')

    def test_los_cortes_se_dicen_en_la_pantalla(self):
        cortes = self.datos()['cortes']
        self.assertTrue(cortes['margen'] is not None and cortes['unidades'] is not None)
        self.assertIn('Se vende bien', cortes['texto'])
        self.assertIn('Buen margen', cortes['texto'])
        self.assertIn('la mitad', cortes['texto'])

    # --- Las medianas y el cuadro, con filas inventadas -------------------------------------------------------------

    def fila(self, u90, costo, precio=100.0, grupo='v30'):
        return {'grupo': grupo, 'u90': u90, 'costo': costo, 'venta_total': precio, 'stock': 1}

    def test_los_cortes_son_las_medianas_de_la_tienda(self):
        rot = self.env['dcasa.rotacion']
        filas = [self.fila(0, 60), self.fila(2, 50), self.fila(4, 40), self.fila(6, 50)]
        # Márgenes 40, 50, 60 y 50 → mediana 50. Unidades de los que sí se vendieron: 2, 4 y 6 → mediana 4.
        self.assertEqual(rot._cortes(filas), (4, 50.0))
        # Un producto sin costo o sin existencias no cuenta para ninguna mediana.
        raros = filas + [self.fila(100, 0), self.fila(100, 1, grupo=None), self.fila(100, 1, precio=0)]
        self.assertEqual(rot._cortes(raros), (4, 50.0))
        # Con una cantidad par de vendidos, la mediana es el promedio de los dos del medio.
        self.assertEqual(rot._cortes([self.fila(2, 50), self.fila(4, 50)]), (3, 50.0))
        # La mediana no es el promedio: una venta enorme no mueve el corte (unidades 1, 2 y 9; márgenes 90, 80 y 10).
        self.assertEqual(rot._cortes([self.fila(1, 10), self.fila(2, 20), self.fila(9, 90)]), (2, 80.0))

    def test_sin_ventas_o_sin_margen_no_hay_cortes(self):
        rot = self.env['dcasa.rotacion']
        # Márgenes 50 y 70 → mediana 60; nadie se vendió, así que no hay corte de unidades.
        self.assertEqual(rot._cortes([self.fila(0, 50), self.fila(0, 30)]), (None, 60.0), 'nadie se vendió')
        self.assertEqual(rot._cortes([self.fila(3, 0)]), (None, None), 'sin costo no hay margen: no cuenta para nada')
        self.assertEqual(rot._cortes([]), (None, None))
        self.assertIsNone(rot._cuadrante(self.fila(3, 0), (3, None)))
        # Si nadie se vendió, ninguno «se vende bien»: nada es estrella ni «venden mucho».
        self.assertEqual(rot._cuadrante(self.fila(0, 30), (None, 40.0)), 'oportunidad')
        self.assertEqual(rot._cuadrante(self.fila(0, 70), (None, 40.0)), 'revisar')

    def test_el_corte_cuenta_a_favor_pero_pasarse_por_poco_no(self):
        rot = self.env['dcasa.rotacion']
        cortes = (4, 50.0)
        self.assertEqual(rot._cuadrante(self.fila(4, 50), cortes), 'estrella', 'justo en el corte es de arriba')
        self.assertEqual(rot._cuadrante(self.fila(3, 50), cortes), 'oportunidad', 'una unidad menos: se mueve poco')
        self.assertEqual(rot._cuadrante(self.fila(4, 51), cortes), 'trafico', 'un punto menos de margen: deja poco')
        self.assertEqual(rot._cuadrante(self.fila(3, 51), cortes), 'revisar')
        self.assertIsNone(rot._cuadrante(self.fila(4, 50, grupo=None), cortes), 'un agotado no tiene cuadro')

    # --- Permisos --------------------------------------------------------------------------------------------------

    def test_marketing_no_ve_margenes_ni_cuadros(self):
        datos = self.datos(self.marketing_rol, vista='mas_de_90')
        self.assertFalse(datos['con_dinero'])
        self.assertIsNone(datos['cortes'])
        self.assertFalse([v for v in datos['vistas'] if v['tipo'] == 'margen'])
        for fila in self.datos(self.marketing_rol, vista='todos')['productos']:
            self.assertNotIn('cuadrante', fila)
            self.assertNotIn('nombre_cuadrante', fila)
        for clave in ('estrella', 'trafico', 'oportunidad', 'revisar'):
            with self.subTest(vista=clave), self.assertRaises(UserError):
                self.datos(self.marketing_rol, vista=clave)

    # --- Excel -----------------------------------------------------------------------------------------------------

    def leer_excel(self, usuario=None, **kw):
        from openpyxl import load_workbook  # noqa: PLC0415
        kw.setdefault('texto', 'ZZRM')
        _nombre, contenido = self.env['dcasa.rotacion'].with_user(usuario or self.gerencia)._excel(**kw)
        hoja = load_workbook(io.BytesIO(contenido))['Rotación']
        return [[c.value for c in fila] for fila in hoja.iter_rows(min_row=5)]

    def test_el_excel_trae_el_cuadro_en_la_ultima_columna(self):
        for rebaja in (None, 20):
            with self.subTest(rebaja=rebaja):
                filas = self.leer_excel(vista='todos', rebaja=rebaja)
                encabezado = filas[0]
                self.assertEqual(encabezado[-1], 'Margen y rotación')
                por_nombre = {fila[0]: fila[-1] for fila in filas[1:] if fila[0]}
                self.assertEqual(por_nombre['ZZRM ESTRELLA'], 'Estrellas')
                self.assertEqual(por_nombre['ZZRM REVISAR'], 'Ni se mueven ni dejan margen')
                self.assertEqual(por_nombre['ZZRM SIN COSTO'], '—')

    def test_el_excel_de_una_lista_de_cuadro_trae_solo_esos(self):
        filas = self.leer_excel(vista='estrella')
        self.assertEqual([fila[0] for fila in filas[1:] if fila[0]], ['ZZRM ESTRELLA'])

    def test_el_excel_sin_dinero_no_trae_la_columna(self):
        filas = self.leer_excel(usuario=self.marketing_rol, vista='todos')
        self.assertNotIn('Margen y rotación', filas[0])
        with self.assertRaises(UserError):
            self.leer_excel(usuario=self.marketing_rol, vista='estrella')


NAVEGADOR_JS = r"""
(async () => {
    const esperar = async (fn, que, ms = 25000) => {
        const inicio = Date.now();
        while (Date.now() - inicio < ms) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error("Margen y rotación: no apareció " + que);
    };
    const falla = (texto) => { throw new Error("Margen y rotación: " + texto); };
    const quieta = () => !document.querySelector(".o_dcasa_mk_actualizando");
    const plano = (el) => el.textContent.replace(/\s+/g, " ").trim();
    const filas = () => [...document.querySelectorAll(".o_dcasa_ro_fila")].map((f) => f.querySelector(".o_dcasa_mk_nombre strong").textContent.trim());
    const escribir = (entrada, valor) => { entrada.value = valor; entrada.dispatchEvent(new Event("input", { bubbles: true })); };
    await esperar(() => document.querySelector(".o_dcasa_ro .o_dcasa_ro_cuerpo"), "la pantalla de Rotación");
    const botones = () => [...document.querySelectorAll(".o_dcasa_ro_chips_margen .o_dcasa_mk_chip")];
    __CASO__
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""  # noqa: E501

CASO_GERENCIA = r"""
    await esperar(() => botones().length === 4, "los 4 botones de margen y rotación");
    const nombres = botones().map((b) => b.textContent.trim().replace(/\s+\d+$/, ""));
    const esperados = ["Estrellas", "Venden mucho, dejan poco", "Buen margen, se mueven poco",
                       "Ni se mueven ni dejan margen"];
    if (nombres.join("|") !== esperados.join("|")) { falla("los botones: " + nombres.join("|")); }
    escribir(document.querySelector(".o_dcasa_ro_buscar_texto"), "ZZRM");
    botones()[0].click();
    await esperar(() => quieta() && filas().join("|") === "ZZRM ESTRELLA", "la lista de las estrellas");
    const fila = plano(document.querySelector(".o_dcasa_ro_fila"));
    if (!fila.includes("Estrellas")) { falla("la fila no dice su cuadro: " + fila); }
    const ayuda = plano(document.querySelector(".o_dcasa_ro_ayuda_margen"));
    if (!ayuda.includes("Se venden bien y dejan buen margen")) { falla("falta para qué sirve la lista"); }
    const cortes = plano(document.querySelector(".o_dcasa_ro_cortes"));
    if (!["Se vende bien", "Buen margen", "la mitad"].every((t) => cortes.includes(t))) {
        falla("los cortes: " + cortes);
    }
    if (botones()[0].getAttribute("aria-pressed") !== "true") { falla("el botón no quedó elegido"); }
    botones()[3].click();
    await esperar(() => quieta() && filas().join("|") === "ZZRM REVISAR", "la lista de ni se mueven ni dejan margen");
    const url = new URL(document.querySelector(".o_dcasa_ro_excel").getAttribute("href"), location.origin);
    if (url.searchParams.get("vista") !== "revisar" || url.searchParams.get("texto") !== "ZZRM") {
        falla("el Excel: " + url);
    }
    if (document.documentElement.scrollWidth > window.innerWidth + 1) { falla("scroll de costado"); }
"""

CASO_MARKETING = r"""
    await esperar(() => document.querySelector(".o_dcasa_ro_lista"), "la lista");
    if (document.querySelector(".o_dcasa_ro_chips_margen") || document.querySelector(".o_dcasa_ro_cortes")) {
        falla("el rol Marketing ve los cuadros de margen");
    }
    if (/Estrellas|dejan poco|dejan margen/.test(plano(document.querySelector(".o_dcasa_ro")))) {
        falla("sale un cuadro de margen sin dinero");
    }
"""


@tagged('post_install', '-at_install')
class TestRotacionMargenEnElNavegador(MargenDatos, HttpCase):

    def setUp(self):
        super().setUp()
        self.gerencia.write({'password': 'zzmk_gerencia'})
        self.marketing_rol.write({'password': 'zzmk_rol_marketing'})

    def test_gerencia_ve_y_elige_los_cuadros(self):
        for tamano in ('390x844', '1440x900'):
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/action-dcasa_marketing.accion_rotacion',
                                NAVEGADOR_JS.replace('__CASO__', CASO_GERENCIA), ready='odoo.isReady',
                                login='zzmk_gerencia', timeout=240)

    def test_marketing_no_ve_los_cuadros(self):
        self.browser_size = '1440x900'
        self.browser_js('/odoo/action-dcasa_marketing.accion_rotacion',
                        NAVEGADOR_JS.replace('__CASO__', CASO_MARKETING), ready='odoo.isReady',
                        login='zzmk_rol_marketing', timeout=240)
