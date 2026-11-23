"""Las herramientas de Brian de Rotación y de Movimiento (``rotacion_de_inventario`` y ``comparar_movimiento``).

Las pidió la revisión independiente del 2026-11-22: era justo el canal donde se prometió que el rol Marketing no recibe
dinero y no tenía ninguna prueba. Cada prueba mira a quién le aparece la herramienta, qué claves de dinero llegan en la
respuesta y que lo exclusivo de Gerencia (los cuadros de margen, la rebaja) se niegue a Marketing.
"""
from odoo.addons.dcasa_brian.models import pasos
from odoo.tests import tagged

from .comun import MarketingCommon, crear_usuario

# Cualquier clave cuyo nombre diga dinero: si aparece en lo que recibe Marketing, es una fuga.
CLAVES_DE_DINERO = ('capital', 'costo', 'margen', 'precio', 'monto', 'vendido_en', 'simulacion', 'cortes')


def claves(valor, ruta=''):
    """Todas las claves de un resultado, anidadas (``a.b.c``)."""
    if isinstance(valor, dict):
        for clave, hijo in valor.items():
            yield f'{ruta}.{clave}'.strip('.')
            yield from claves(hijo, f'{ruta}.{clave}'.strip('.'))
    elif isinstance(valor, (list, tuple)):
        for hijo in valor:
            yield from claves(hijo, ruta)


@tagged('post_install', '-at_install')
class TestBrianRotacionMovimiento(MarketingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.marketing_rol = crear_usuario(cls.env, 'zzmk_brian_rol', ['dcasa_marketing.group_marketing'])
        cls.categoria_br = cls.env['product.category'].create({'name': 'ZZBR Categoría'})
        cls.cama = cls.producto('ZZBR Cama', 'ZZBR-CAMA', stock=5, categoria=cls.categoria_br)
        cls.cama.standard_price = 40.0
        cls.repisa = cls.producto('ZZBR Repisa', 'ZZBR-REPISA', stock=8, categoria=cls.categoria_br)
        cls.repisa.standard_price = 40.0
        MarketingCommon.facturar(cls, cls.cama, 3, 2)

    def brian(self, usuario):
        return self.env['brian.herramientas'].with_user(usuario)

    def llamar(self, usuario, herramienta, **argumentos):
        return self.brian(usuario).ejecutar(herramienta, argumentos)

    def test_quien_las_tiene(self):
        for usuario, esperado in ((self.gerencia, True), (self.marketing_rol, True), (self.vendedora, False)):
            nombres = {h['name'] for h in self.brian(usuario).catalogo()}
            with self.subTest(usuario=usuario.login):
                self.assertEqual({'rotacion_de_inventario', 'comparar_movimiento'} <= nombres, esperado)
        for herramienta in ('rotacion_de_inventario', 'comparar_movimiento'):
            self.assertFalse(self.llamar(self.vendedora, herramienta)['ok'], 'la vendedora no entra')

    def test_gerencia_recibe_el_dinero_de_rotacion_y_marketing_no(self):
        r = self.llamar(self.gerencia, 'rotacion_de_inventario', grupo='todos', categoria='ZZBR Categoría')
        self.assertTrue(r['ok'], r)
        self.assertTrue(any('capital' in k for k in claves(r['datos'])), 'Gerencia sí ve el capital parado')
        r = self.llamar(self.marketing_rol, 'rotacion_de_inventario', grupo='todos', categoria='ZZBR Categoría')
        self.assertTrue(r['ok'], r)
        codigos = {p.get('codigo') for p in r['datos']['productos']}
        self.assertEqual(codigos, {'ZZBR-CAMA', 'ZZBR-REPISA'})
        dinero = [k for k in claves(r['datos']) if any(d in k.lower().split('.')[-1] for d in CLAVES_DE_DINERO)]
        self.assertEqual(dinero, [], 'Marketing no recibe ni una cifra de dinero por Brian')

    def test_lo_exclusivo_de_gerencia_se_le_niega_a_marketing(self):
        for cuadro in ('estrella', 'trafico', 'oportunidad', 'revisar'):
            with self.subTest(cuadro=cuadro):
                self.assertTrue(self.llamar(self.gerencia, 'rotacion_de_inventario', grupo=cuadro)['ok'])
                negado = self.llamar(self.marketing_rol, 'rotacion_de_inventario', grupo=cuadro)
                self.assertFalse(negado['ok'], 'los cuadros de margen usan el costo: son de Gerencia')
        r = self.llamar(self.marketing_rol, 'rotacion_de_inventario', grupo='todos', rebaja=20,
                        categoria='ZZBR Categoría')
        self.assertNotIn('simulacion', r.get('datos', {}), 'la simulación de rebaja es de Gerencia')

    def test_comparar_movimiento_para_gerencia_y_marketing(self):
        r = self.llamar(self.gerencia, 'comparar_movimiento', periodo='30', vista='todos', categoria='ZZBR Categoría')
        self.assertTrue(r['ok'], r)
        r = self.llamar(self.marketing_rol, 'comparar_movimiento', periodo='30', vista='todos',
                        categoria='ZZBR Categoría')
        self.assertTrue(r['ok'], r)
        codigos = {p.get('codigo') for p in r['datos']['productos']}
        self.assertIn('ZZBR-CAMA', codigos)
        dinero = [k for k in claves(r['datos']) if any(d in k.lower().split('.')[-1] for d in CLAVES_DE_DINERO)]
        self.assertEqual(dinero, [], 'Marketing no recibe dinero al comparar periodos')

    def test_entradas_que_no_valen_dan_un_error_legible(self):
        for herramienta, argumentos in (('comparar_movimiento', {'periodo': 'fechas'}),
                                        ('comparar_movimiento', {'periodo': 'un-siglo'}),
                                        ('comparar_movimiento', {'contra': 'con-mi-tio'}),
                                        ('rotacion_de_inventario', {'grupo': 'ninguno'}),
                                        ('rotacion_de_inventario', {'rebaja': 500}),
                                        ('rotacion_de_inventario', {'categoria': 'No existe ZZ'})):
            with self.subTest(herramienta=herramienta, argumentos=argumentos):
                r = self.llamar(self.gerencia, herramienta, **argumentos)
                self.assertFalse(r['ok'])
                self.assertTrue(r['error'])

    def test_los_pasos_se_leen_en_palabras(self):
        self.assertEqual(pasos.titulo_paso('rotacion_de_inventario', {}), 'Revisando la rotación del inventario')
        self.assertEqual(pasos.titulo_paso('comparar_movimiento', {}), 'Comparando qué se mueve entre dos periodos')
