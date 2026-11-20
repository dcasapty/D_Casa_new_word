"""Los pares de color nuevos del pago, con la fórmula WCAG (la misma de los informes de Feuxui): texto ≥ 4.5:1, borde
de un campo y ícono ≥ 3:1. Los colores se leen del propio ``pago.scss`` (no se copian aquí): si alguien cambia un tono
y el par deja de cumplir, esta prueba lo dice. Y la marca: el pago no usa amarillo ni degradados ni sombras."""
import re
from pathlib import Path

from odoo.tests import TransactionCase, tagged

SCSS = Path(__file__).resolve().parent.parent / 'static' / 'src' / 'scss'
BLANCO = '#FFFFFF'
GRIS_DEL_BOTON_APAGADO = '#566074'      # texto del botón sin método elegido, sobre #E4E7EE
FONDO_DEL_BOTON_APAGADO = '#E4E7EE'
FONDO_DEL_ICONO_DE_FALLO = '#FDECEA'
FILA_BAJO_EL_MOUSE = '#F7F8FB'


def luminancia(color):
    canales = [int(color.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a, b):
    claro, oscuro = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (claro + 0.05) / (oscuro + 0.05)


def tokens():
    """Las variables de color de dcasa.scss y de pago.scss (con sus alias), ya resueltas a #RRGGBB."""
    brutos = {}
    for archivo in ('dcasa.scss', 'pago.scss'):
        for nombre, valor in re.findall(r'^\$([a-z0-9-]+):\s*([^;/]+?);', (SCSS / archivo).read_text(), re.M):
            brutos[nombre] = valor.strip()
    resueltos = {}
    for nombre, bruto in brutos.items():
        valor = bruto
        while valor.startswith('$'):
            valor = brutos[valor[1:]]
        if re.fullmatch(r'#[0-9A-Fa-f]{6}', valor):
            resueltos[nombre] = valor.upper()
    return resueltos


@tagged('post_install', '-at_install')
class TestContrasteDelPago(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.c = tokens()

    def test_los_tokens_del_pago_existen(self):
        for nombre in ('pago-azul', 'pago-azul-osc', 'pago-navy', 'pago-tinta', 'pago-gris', 'pago-borde-campo',
                       'pago-suave', 'pago-panel', 'pago-error'):
            self.assertIn(nombre, self.c, '$' + nombre)

    def test_todo_texto_nuevo_llega_a_4_5_a_1(self):
        c = self.c
        pares = [
            ('tinta sobre blanco', c['pago-tinta'], BLANCO),
            ('tinta sobre el panel del resumen', c['pago-tinta'], c['pago-panel']),
            ('tinta sobre la fila elegida', c['pago-tinta'], c['pago-suave']),
            ('tinta sobre la fila bajo el mouse', c['pago-tinta'], FILA_BAJO_EL_MOUSE),
            ('gris sobre blanco (ayuda, líneas del total)', c['pago-gris'], BLANCO),
            ('gris sobre el panel', c['pago-gris'], c['pago-panel']),
            ('gris sobre la fila elegida (ayuda del método)', c['pago-gris'], c['pago-suave']),
            ('texto de ejemplo de un campo (placeholder)', c['pago-gris'], BLANCO),
            ('enlace azul sobre blanco', c['pago-azul'], BLANCO),
            ('enlace azul sobre el panel (resumen plegable)', c['pago-azul'], c['pago-panel']),
            ('«Aplicar» azul sobre la fila suave', c['pago-azul'], c['pago-suave']),
            ('texto del botón de pagar', BLANCO, c['pago-azul']),
            ('texto del botón de pagar bajo el mouse', BLANCO, c['pago-azul-osc']),
            ('cantidad blanca en la insignia azul', BLANCO, c['pago-azul']),
            ('total grande (navy sobre el panel)', c['pago-navy'], c['pago-panel']),
            ('total de la ventana (navy sobre el panel)', c['pago-navy'], c['pago-panel']),
            ('«Modo de prueba» navy sobre blanco', c['pago-navy'], BLANCO),
            ('«El pago no se completó» sobre blanco', c['pago-error'], BLANCO),
            ('botón de pagar sin método elegido', GRIS_DEL_BOTON_APAGADO, FONDO_DEL_BOTON_APAGADO),
        ]
        for nombre, texto, fondo in pares:
            with self.subTest(par=nombre):
                self.assertGreaterEqual(contraste(texto, fondo), 4.5, f'{nombre}: {texto} sobre {fondo}')

    def test_bordes_e_iconos_llegan_a_3_a_1(self):
        c = self.c
        pares = [
            ('borde del campo del código de descuento', c['pago-borde-campo'], BLANCO),
            ('radio elegido (azul sobre blanco)', c['pago-azul'], BLANCO),
            ('radio sin elegir', c['pago-borde-campo'], BLANCO),
            ('ícono de fallo sobre su recuadro', c['pago-error'], FONDO_DEL_ICONO_DE_FALLO),
            ('borde azul de la fila elegida sobre la fila', c['pago-azul'], c['pago-suave']),
        ]
        for nombre, trazo, fondo in pares:
            with self.subTest(par=nombre):
                self.assertGreaterEqual(contraste(trazo, fondo), 3.0, f'{nombre}: {trazo} sobre {fondo}')

    def test_la_marca_el_pago_no_usa_amarillo_ni_degradados_ni_sombras(self):
        for archivo in ('pago.scss', '../../../../dcasa_pago_tilopay/static/src/scss/tilopay.scss'):
            codigo = (SCSS / archivo).read_text()
            sin_comentarios = re.sub(r'//[^\n]*', '', re.sub(r'/\*.*?\*/', '', codigo, flags=re.S))
            self.assertNotIn('FED00F', sin_comentarios.upper(), 'el amarillo nunca toca el blanco: aquí no se usa')
            self.assertNotIn('gradient', sin_comentarios, 'sistema plano: sin degradados')
            self.assertNotIn('text-shadow', sin_comentarios)
            self.assertNotIn('drop-shadow', sin_comentarios)
            for sombra in re.findall(r'box-shadow:\s*([^;]+);', sin_comentarios):
                self.assertTrue(sombra.strip() == 'none' or re.fullmatch(r'inset 0 0 0 \d+px [^,]+', sombra.strip())
                                or re.fullmatch(r'0 0 0 \d+px [^,]+', sombra.strip()),
                                f'solo anillos planos (sin desenfoque): {sombra}')
