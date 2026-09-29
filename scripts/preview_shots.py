"""Capturas de la previsualización: python scripts/preview_shots.py <url_base> <carpeta>."""
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE, SALIDA = sys.argv[1].rstrip('/'), Path(sys.argv[2])
SALIDA.mkdir(parents=True, exist_ok=True)
# Recorre la página para que carguen las imágenes diferidas (loading="lazy").
DESPLAZAR = '''async () => {
    for (let y = 0; y < document.body.scrollHeight; y += 600) {
        window.scrollTo(0, y);
        await new Promise(r => setTimeout(r, 120));
    }
    window.scrollTo(0, 0);
}'''
PAGINAS = {'inicio': '/', 'tienda': '/shop', 'socios': '/socios', 'socios-terminos': '/socios/terminos'}

with sync_playwright() as p:
    navegador = p.chromium.launch(executable_path=os.environ.get('CHROMIUM') or None)
    for ancho, sufijo in ((1280, 'escritorio'), (390, 'movil')):
        pagina = navegador.new_page(viewport={'width': ancho, 'height': 900})
        for nombre, ruta in PAGINAS.items():
            pagina.goto(BASE + ruta, wait_until='load', timeout=120_000)
            pagina.evaluate(DESPLAZAR)
            pagina.wait_for_timeout(1500)
            pagina.screenshot(path=SALIDA / f'{nombre}-{sufijo}.png', full_page=True)
        # Ficha del primer producto de la portada.
        pagina.goto(BASE + '/', wait_until='load', timeout=120_000)
        enlace = pagina.locator('.o_dcasa_pcard_name a').first
        if enlace.count():
            pagina.goto(BASE + enlace.get_attribute('href'), wait_until='load', timeout=120_000)
            pagina.wait_for_timeout(1500)
            pagina.screenshot(path=SALIDA / f'producto-{sufijo}.png', full_page=True)
    # La cuenta de un socio de demostración (celular 6555-1234, PIN 482915).
    pagina = navegador.new_page(viewport={'width': 390, 'height': 900})
    pagina.goto(BASE + '/socios', wait_until='load')
    pagina.fill('#celular', '6555-1234')
    pagina.fill('#pin', '482915')
    pagina.press('#pin', 'Enter')
    pagina.wait_for_load_state('load')
    pagina.wait_for_timeout(1500)
    pagina.screenshot(path=SALIDA / 'socios-cuenta-movil.png', full_page=True)
    navegador.close()
print(f'Capturas en {SALIDA}')
