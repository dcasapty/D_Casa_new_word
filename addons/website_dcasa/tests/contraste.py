"""Contraste WCAG para las pruebas de legibilidad: la misma fórmula de los informes de la comparación con Feuxui
(``docs/referencias/feuxui/``) y una sonda de navegador que da el color REAL de un texto (con la opacidad de él y de sus
padres) y el fondo que tiene detrás. 1:1 es no verse, 4,5:1 el mínimo del texto normal, 3:1 el del titular grande."""
import json
import re


def rgba(color):
    """'rgb(1, 2, 3)' / 'rgba(1, 2, 3, 0.5)' → (1, 2, 3, alfa)."""
    numeros = re.findall(r'[\d.]+', color or '')
    if len(numeros) == 3:
        return (*(int(float(n)) for n in numeros), 1.0)
    if len(numeros) == 4:
        return (*(int(float(n)) for n in numeros[:3]), float(numeros[3]))
    return None


def luminancia(rgb):
    """Luminancia relativa WCAG de (r, g, b) en 0-255."""
    def canal(c):
        c /= 255
        return c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4
    r, g, b = (canal(c) for c in rgb[:3])
    return .2126 * r + .7152 * g + .0722 * b


def contraste(a, b):
    """Razón de contraste WCAG (1 a 21) entre dos colores (r, g, b)."""
    claro, oscuro = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (claro + .05) / (oscuro + .05)


# Devuelve {color, opacidad, fondo} del texto de `sel` (o de su pseudoelemento, p. ej. '::placeholder'): `opacidad` es
# la del elemento y de todos sus padres juntas; `fondo`, los fondos de sus padres mezclados sobre blanco.
SONDA_TEXTO = r"""
((sel, pseudo) => {
    const e = document.querySelector(sel);
    if (!e) { return null; }
    const cs = getComputedStyle(e, pseudo || undefined);
    let opacidad = pseudo ? parseFloat(cs.opacity) : 1;
    for (let n = e; n; n = n.parentElement) { opacidad *= parseFloat(getComputedStyle(n).opacity); }
    const capas = [];
    for (let n = e; n; n = n.parentElement) {
        const m = getComputedStyle(n).backgroundColor.match(/[\d.]+/g).map(Number);
        const a = m.length > 3 ? m[3] : 1;
        if (a > 0) { capas.push([m[0], m[1], m[2], a]); }
        if (a === 1) { break; }
    }
    let f = [255, 255, 255];
    for (const [r, g, b, a] of capas.reverse()) {
        f = [r * a + f[0] * (1 - a), g * a + f[1] * (1 - a), b * a + f[2] * (1 - a)];
    }
    return { color: cs.color, opacidad, fondo: 'rgb(' + f.map(Math.round).join(', ') + ')' };
})
"""


def sonda(selector, pseudo=None):
    """Expresión de JavaScript que mide un texto (ver SONDA_TEXTO)."""
    return f'{SONDA_TEXTO}({json.dumps(selector)}, {json.dumps(pseudo)})'


def razon_del_texto(medida):
    """Contraste real de lo que devuelve la sonda: el color del texto con su opacidad sobre el fondo de detrás."""
    r, g, b, alfa = rgba(medida['color'])
    alfa *= medida['opacidad']
    fondo = rgba(medida['fondo'])[:3]
    efectivo = tuple(round(c * alfa + f * (1 - alfa)) for c, f in zip((r, g, b), fondo, strict=True))
    return contraste(efectivo, fondo)
