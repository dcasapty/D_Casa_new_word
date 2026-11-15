# El color de la cantidad del carrito

Investigación pedida por la dueña el 2026-11-15: «no quiero que el sesgo o mis gustos me nublen la visión». La marca
solo deja dos colores: el azul `#1340B1` y el amarillo `#FED00F`. La cantidad es la burbuja con el número sobre el
ícono del carrito, en el menú del sitio y en la barra del chat de Brian.

## Decisión

**Amarilla, con el número en azul noche `#0E2A6B` y un aro azul `#1340B1` de 2 px.** La misma en el menú
(`website_dcasa/static/src/scss/dcasa.scss`) y en el chat (`dcasa_brian_tienda/static/src/scss/brian_tienda.scss`).
Las pruebas: `dcasa_brian_tienda/tests/test_navegador.py`, `TestCarritoEnLaBarra`.

## Lo que dice la investigación

1. **Ningún color «vende más» por sí solo.** Las pruebas de color de botones no dan un resultado constante; un análisis
   de MeasuringU no encontró un efecto Von Restorff consistente en las elecciones. Lo que sí se sostiene: un elemento se
   nota por su contraste con lo que lo rodea, no por el tono en sí.
2. **El significado del color depende del contexto** (teoría del color en contexto, Elliot y Maier, 2012; revisión de
   Elliot, 2015). En este sitio, el visitante aprende rápido el código: el amarillo es «lo que se toca» sobre azul.
3. **Azul = confianza y competencia** (Labrecque y Milne, 2012). En tiendas con ambiente azul la gente se queda y compra
   más que con rojo (Bellizzi y Hite, 1992). Esto habla del ambiente del sitio, que ya es azul; no de una burbuja de
   1 cm.
4. **El amarillo se encuentra más rápido.** En búsqueda visual, los objetivos amarillentos se detectaron más rápido, con
   más acierto y con menos movimientos de ojo que los azulados (estudio de saliencia de los tonos únicos).
5. **Contraste mínimo (WCAG 1.4.11): 3:1** entre la burbuja y su fondo; 4.5:1 para el número.
6. **Precedente:** IKEA (muebles, azul y amarillo, cabecera siempre blanca) pone la cantidad en azul con número blanco
   (verificado el 2026-11-15 en ikea.com/us con un artículo en la bolsa). Walmart, Best Buy y Lidl no se pudieron
   verificar: bloquean navegadores automáticos. No se afirma nada de ellas.

## Lo que decidió: la medición en nuestro propio sitio

La cabecera de D'CASA cambia: **sobre la foto de la portada es vidrio oscuro** (lo primero que ve todo el que entra) y
**al bajar es vidrio claro**. IKEA no tiene ese caso: por eso su azul no se copia, se copia el razonamiento.

| Dónde | Cantidad azul | Cantidad amarilla |
| --- | --- | --- |
| Sobre la foto, celular | 1.20:1 (no se distingue) | 4.97:1 |
| Sobre la foto, computadora | 1.44:1 (no se distingue) | 4.14:1 |
| Cabecera clara | 8.76:1 | 1.47:1 sola; con aro azul, 8.76:1 el aro contra el blanco |
| El número dentro | blanco sobre azul 8.76:1 | azul noche sobre amarillo 9.12:1 |

Medido con capturas del Odoo local (mediana de los píxeles junto a la burbuja) y la fórmula de luminancia de WCAG.
Cada color falla en uno de los dos casos; **la amarilla con aro azul es la única que cumple en los dos**, y el aro
mantiene la regla de marca (el amarillo nunca toca el blanco).

## Lo que no hace

- No mete urgencia falsa: la cantidad es el estado del carrito (la primera heurística de Nielsen, visibilidad del estado
  del sistema), no una alarma. La urgencia real viene de los datos («Quedan pocas»).
- No usa rojo: fuera de la marca y en las interfaces significa error.

## Si se quisiera medir de verdad

Una prueba A/B (mitad azul, mitad amarilla, contando qué parte de los carritos llega a pagar) necesita mucho tráfico
para dar un resultado confiable; con el tráfico actual tardaría meses. Por eso se decidió por contraste y contexto.

## Fuentes

- Labrecque, L. y Milne, G. (2012). *Exciting red and competent blue: the importance of color in marketing*. Journal of
  the Academy of Marketing Science 40(5), 711-727. https://link.springer.com/content/pdf/10.1007/s11747-010-0245-y.pdf
- Bellizzi, J. y Hite, R. (1992). *Environmental color, consumer feelings, and purchase likelihood*. Psychology &
  Marketing 9, 347-363 (citado en https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2022.1028425/full).
- Elliot, A. (2015). *Color and psychological functioning: a review of theoretical and empirical work*. Frontiers in
  Psychology. https://www.frontiersin.org/articles/10.3389/fpsyg.2015.00368/full
- Saliencia de los tonos únicos (amarillo frente a azul en búsqueda visual):
  https://researchconnect.suny.edu/en/publications/salience-of-unique-hues-and-implications-for-color-theory/
- D'Zmura, M. (1991). *Color in visual search*. https://sites.socsci.uci.edu/~mdzmura/pubs/DZmura1991ColorInVisualSearch.pdf
- MeasuringU, efecto Von Restorff en elecciones: https://measuringu.com/wp-json/wp/v2/posts/581
- Contraste de las burbujas (3:1, WCAG 1.4.11): https://design.sis.gov.uk/components/badge
