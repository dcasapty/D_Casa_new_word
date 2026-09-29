# Rediseño del sitio D'CASA (v2)

## Diagnóstico de la v1

- **Sin fotografía.** Una mueblería vende con imágenes; la v1 era texto sobre bloques de color.
- **Sin productos ni precios en la portada.** No había nada que comprar sin entrar a la tienda:
  cero compra impulsiva.
- **Jerarquía plana.** Las secciones tenían el mismo peso y el mismo espaciado, así que no
  había un recorrido claro para el ojo.
- **Tipografía sin escala.** Titulares en caja alta de tamaño medio y poco aire.
- **Tienda y ficha de producto** con el diseño por defecto de Odoo.

## Qué tomamos de las referencias

| Referencia | Qué hace bien | Cómo lo aplicamos |
|---|---|---|
| **Case** (case-furniture) | Aire generoso, fondo cálido casi blanco, fotos grandes a sangre, colecciones en mosaico de 3 columnas, tarjetas de producto sobre fondo neutro con precio discreto | Fondo hueso, grilla de categorías 3×2 con foto, tarjetas de producto sobre hueso |
| **Burrow** | Hero con promesa + un CTA, fila de beneficios con iconos de línea, carrusel de «top rated» con precio y variante, bloque de envío con foto grande | Hero con placa, franja de beneficios, *rail* de productos con precio y «Agregar», bloque «Te lo llevas hoy» |
| **West Elm** | Ritmo editorial alternando foto grande y bloques, secciones temáticas | Alternancia foto/texto (split editorial) y galería de inspiración |

## Principios (siempre dentro del ADN)

1. **La fotografía manda y la marca firma.** El azul y el amarillo aparecen en la *placa* y en
   la banda amarilla, no pintando la página entera. El fondo base es hueso cálido (60 %).
2. **Un solo recorrido por pantalla.** Cada sección tiene un titular, una idea y un CTA.
3. **Aire.** Secciones de 96–128 px en escritorio y de 56–72 px en móvil, y un contenedor ancho
   de hasta 1440 px.
4. **Tipografía con escala.**
   - Anton en caja alta para titulares de 2 a 5 palabras, con tamaños de 40 a 88 px (`clamp`).
   - Oswald para antetítulos y navegación.
   - Inter a 16–18 px para el cuerpo.
5. **El amarillo nunca toca el blanco.**
   - Sobre fondo claro, los CTA van en azul.
   - El amarillo solo aparece sobre azul, dentro de la placa o como banda.

## Mapa de calor y conversión (compra impulsiva)

El ojo recorre la pantalla en F (arriba a la izquierda, luego hacia abajo) y la mitad del
tráfico no pasa del primer pantallazo. Por eso:

| Orden | Sección | Por qué |
|---|---|---|
| 0 | **Barra de anuncios** (entrega a todo Panamá · financiamiento · WhatsApp) | Resuelve las 3 objeciones de compra antes de hacer scroll |
| 1 | **Hero a sangre** con placa azul: titular, subtítulo y 2 CTA («Ver la tienda» y «Escríbenos por WhatsApp») | CTA en la zona caliente (arriba a la izquierda y centro) |
| 2 | **Beneficios** con 4 iconos de línea | Confianza inmediata: *te lo llevas hoy*, financiamiento, entrega, precios claros |
| 3 | **Compra por espacio**: 6 fotos de categoría | La forma natural de buscar muebles («para mi sala») |
| 4 | **Lo más buscado**: *rail* de productos con precio y botón **Agregar** | Compra impulsiva a 1 clic desde la portada |
| 5 | **Split editorial**: «Te lo llevas hoy mismo» | Diferenciador real del ADN (muebles en caja que caben en el carro) |
| 6 | **Segundo *rail***: colchones / recámaras | Segunda oportunidad de compra |
| 7 | **Socios D'CASA** (banda azul): puntos e invitación | Retención y recomendación |
| 8 | **Inspírate**: galería de ambientes | Deseo, con enlace a Instagram |
| 9 | **Guía «¿Te cabe?»** y **preguntas frecuentes** | Contenido útil para SEO y para bajar las dudas |
| 10 | **Visítanos**: dirección y WhatsApp | Tráfico a la tienda física (La Chorrera) |

**En la tienda y la ficha de producto:**
- Tarjetas grandes sobre hueso, precio visible y botón **Agregar**.
- En la ficha, junto al botón de compra: sellos de confianza (entrega, financiamiento, *te lo
  llevas hoy*) y un botón «Pregunta por este mueble por WhatsApp» con el nombre del producto ya
  escrito en el mensaje.
- En el celular, una barra fija abajo con el precio y el botón **Agregar al carrito**.

## Móvil primero

- Grillas de 1 a 2 columnas; los *rails* son carruseles horizontales con `scroll-snap` y dejan
  asomar la siguiente tarjeta (se entiende que se puede deslizar).
- Botones de al menos 48 px de alto; menú hamburguesa de Odoo.
- El hero en el celular muestra primero la foto y debajo la placa, para que el texto nunca
  tape el producto.

## Accesibilidad (WCAG 2.2 AA)

- **Contraste:** 4.5:1 como mínimo; el texto sobre foto va siempre dentro de la placa sólida.
- **Imágenes:** `alt` descriptivo en todas; las decorativas llevan `alt=""`.
- **Navegación:** foco visible y orden de tabulación lógico; *rails* con `role="region"` y
  `aria-label`.
- **Movimiento:** `prefers-reduced-motion` desactiva transiciones y el desplazamiento suave.
- **Estructura:** un solo `h1` por página.

## SEO y Google Search Console

- `title` y `meta description` propios de la portada, con palabras clave locales
  («muebles en La Chorrera», «colchones Panamá»).
- **Datos estructurados JSON-LD:** `FurnitureStore` (nombre, logo, dirección, teléfono,
  redes). Los datos de producto los emite Odoo en cada ficha.
- **Core Web Vitals:**
  - La imagen del hero se carga con `fetchpriority="high"` y dimensiones fijas (evita CLS).
  - El resto de imágenes va con `loading="lazy"`, en WebP, con `width` y `height`.
  - Fuentes con `display=swap` (vía Odoo).
- **Lo que ya da Odoo:** `sitemap.xml`, `robots.txt`, `canonical` y URLs limpias (`/shop/…`).

## Fotografía

Mientras llega la sesión de fotos real de D'CASA, el sitio usa fotografía de interiores del
tema oficial *Loftspace* de Odoo (licencia LGPL-3, guardada en
`addons/website_dcasa/static/src/img/`).
- **Portada, «Te lo llevas hoy» e «Inspírate»:** se reemplazan desde el editor (Sitio web →
  Editar → doble clic en la imagen), sin programador.
- **Fotos de «Compra por espacio»:** salen del código (`CATEGORIAS_PORTADA` en
  `models/website.py`); para cambiarlas se reemplaza el archivo `cat-<categoría>.webp`.
- **Fotos de producto:** salen de cada producto del catálogo.

Los productos de la previsualización son de demostración (fotos de producto de Odoo) y solo
existen en la base de prueba.

## Auditoría (antes de publicar)

Dos revisiones independientes (accesibilidad/SEO y código) y Lighthouse sobre la base de
demostración. Lo corregido:

- **Regla del amarillo:** el borde de la placa en el celular, la banda de socios, el anillo del
  botón flotante y el foco ya no tocan fondos claros.
- **Editor:** los botones de WhatsApp de los bloques editables usan `/whatsapp`, que redirige
  siempre al número configurado; un `wa.me` escrito en el HTML quedaría congelado al guardar.
- **Carrito en 1 clic:** aplica las mismas reglas que Odoo. Variantes, combos, precio cero
  bloqueado o tienda solo para registrados → «Elegir» lleva a la ficha.
- **Caché de página:** se separa por tarifa y posición fiscal, así ningún visitante ve el precio
  de otro.
- **Datos estructurados:** `@id`, sin campos vacíos y sin rango de precios inventado. Se escapan
  `<`, `>` y `&` dentro del `<script>`.
- **Ficha de producto:** se apagó el bloque de Odoo «Garantía de 30 días / Envío 2-3 días»
  (promesas que D'CASA no ha hecho).
- **Accesibilidad:**
  - Orden de encabezados del pie.
  - Contraste del crédito de Odoo.
  - `aria-hidden` en los iconos.
  - `role="list"` en las listas sin viñetas.
- **SEO:** descripción propia para `/shop` y título de portada de menos de 60 caracteres.
- **Bases existentes:** la migración `19.0.1.1.0` aplica los ajustes que van en `noupdate`.

Lighthouse (local, sin CDN):
- Accesibilidad 95 → corregido lo señalado.
- SEO 100 en la portada.
- El rendimiento en móvil depende del JavaScript de Odoo (≈1,5 MB sin usar en la portada); en
  producción lo compensan la caché del Worker y la compresión de Cloudflare.

## v2.1 (pedido de la dueña)

- **Hero sin placa azul** en todas las páginas: foto a sangre sobre negro, con la opacidad
  bajada (45 %) y el texto en blanco. El azul de marca queda en la cabecera y los botones.
  Las páginas de socios usan la misma cabecera, más baja (`.o_dcasa_hero_compacto`).
- **Cabecera de vidrio** (inspirada en BYS y Safetory):
  - Es una píldora flotante con desenfoque y un filo de luz, siempre visible (efecto «fijo»
    de Odoo), que se compacta al bajar.
  - El vidrio va en un `::before`: puesto en el propio nav, encerraría el menú móvil de Odoo.
- **Animaciones** (mismo sistema que BYS: `static/src/js/animaciones.js`):
  - El hero entra en cascada y la foto hace un zoom lento.
  - Las secciones aparecen al hacer scroll (`data-anim`, `data-anim-cascada`).
  - Los titulares suben palabra a palabra (`data-titular`).
  - No se anima nada dentro del editor ni con `prefers-reduced-motion`, y sin JavaScript todo
    se ve.
- **Opiniones de Google** en una cinta en movimiento (como BYS):
  - Son copia literal de la ficha de Google, en `data/resenas.json`. Cada tarjeta enlaza a la
    ficha, y el botón «Déjanos tu opinión en Google» lleva a dejar una nueva.
  - La cinta se para con el puntero o el foco.
  - **Cómo se añade una reseña:** se copia tal cual de Google al JSON y se actualiza el `total`.
- **Sin «Con la tecnología de Odoo»**, ni en el pie ni en el portal.
- **Favicon de D'CASA** (`static/src/img/favicon.png`).
- **Bases existentes:** la migración `19.0.1.2.0` pone el favicon y la cabecera fija.
