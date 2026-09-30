# Auditoría de la barra lateral (`dcasa_interfaz`) — agente `navbar`

Alcance: `addons/dcasa_interfaz/static/src/{js/barra_lateral.js, xml/barra_lateral.xml, scss/barra_lateral.scss, scss/tokens.scss, scss/global.scss}`, `models/res_users.py`, `tests/test_interfaz.py`.
Método: lectura estática (vendor/odoo está vacío; lo que depende de Odoo 19 va marcado *(por verificar)*). Contrastes calculados con la fórmula WCAG sobre los tokens reales.
Referencias de línea: JS = `barra_lateral.js`, XML = `barra_lateral.xml`, SCSS = `barra_lateral.scss`, TOK = `tokens.scss`.

## 1. Resumen ejecutivo

La barra está bien construida en lo estructural (`<nav>` con nombre, enlaces reales, `aria-expanded` en grupos, acordeón a cualquier nivel, scroll interno con cabecera y pie fijos, respeta `prefers-reduced-motion`). **Lo incómodo no es un detalle visual: es el modelo de interacción por defecto.** La barra arranca en modo «auto» (franja de 68 px solo de íconos que se expande al pasar el mouse y **se recoge sola al elegir algo**), y en ese estado las secciones de la app ni siquiera existen en el DOM. Resultado: para llegar a «Ventas › Pedidos» hay que hacer dos ciclos de «acercar → esperar → ver cómo la lista se mueve → clic → la barra se cierra bajo el cursor».

Causas raíz, por orden de impacto:
1. Modo «auto» por defecto con expansión por hover + autocierre al navegar (N-01).
2. La lista se reordena debajo del puntero al expandirse (N-02).
3. Al recogerse, desaparece el elemento enfocado: el teclado pierde el foco (N-03).
4. Accesibilidad: sin salto de bloque, anillo de foco de 1,5:1 recortado por `overflow`, invisible en alto contraste (N-04, N-05).

Propuesta (sección 5): **barra fija por defecto en pantallas ≥1200 px, «riel» de íconos solo por clic (sin hover) en 992–1199 px, sin autocierre**, foco con anillo azul-600 en `outline`, enlace «Saltar al contenido», `aria-controls`, botón de colapsar con `aria-expanded`, activo desplazado a la vista. Todo son cambios pequeños sobre el código actual.

Conteo: 5 ALTO · 7 MEDIO · 8 BAJO. Ningún CRÍTICO.

## 2. Diagnóstico: por qué es incómoda (escenarios concretos)

**Escenario A — «Quiero ir a Ventas › Pedidos» (mouse, configuración por defecto).**
1. Por defecto `leerModo()` devuelve `"auto"` (JS:25-31). La barra es una franja de 68 px (`--dc-barra-w-colapsada`, TOK:47) con solo íconos; el texto está `display:none` (SCSS:255).
2. El mouse entra: `entrar()` espera 120 ms y pone `encima=true` (JS:63-69). La barra salta a 256 px **sin transición** y flota encima del contenido (SCSS:278-284).
3. Con `colapsada=false`, el `<ul>` de secciones de la app actual se inserta (XML:40). Todas las apps que estaban debajo de la activa bajan cientos de píxeles: el objetivo al que el usuario apuntaba ya no está bajo el puntero (N-02).
4. Clic en «Ventas»: `abrirApp` → `abrir` → como la app tiene `actionID` y (mientras no se haya visitado) no tiene `childrenTree`, llama `recoger()` (JS:180-182): `encima=false`, la barra vuelve a 68 px y **las secciones desaparecen** (XML:40). El usuario nunca vio las secciones de Ventas.
5. Tiene que sacar el mouse y volver a entrar (mouseenter solo se dispara al re-entrar), esperar otros 120 ms, y recién entonces ve «Pedidos». Clic → la barra se cierra otra vez (JS:180).
Coste: 2 entradas + 2 esperas + 1 reflujo inesperado por cada navegación de dos niveles. El usuario nunca puede «mirar» el menú con calma ni ubicarse, porque se cierra al primer clic.

**Escenario B — teclado.** Tab llega al logo → `focusin` → `entrar` → se expande a los 120 ms. Enter en una sección → `recoger()` → se elimina el `<ul>` de secciones (XML:40) → el enlace enfocado deja de existir → el foco cae a `<body>`; el siguiente Tab empieza desde el principio del documento (N-03). Un usuario de teclado no puede recorrer dos secciones seguidas sin volver a tabular ~20 paradas.

**Escenario C — lector de pantalla en modo exploración (sin foco ni hover).** La barra está colapsada, así que solo existen las apps; las secciones y grupos no están en el árbol de accesibilidad (N-06). El nombre accesible de cada app depende del `title` (XML:36), que es el último recurso de cálculo de nombre.

**Escenario D — tablet horizontal (1024 px, táctil).** ≥992 px muestra la barra; al tocar una app se expande (JS:187-191) pero no hay «tocar fuera para cerrar» ni `mouseleave` fiable: queda flotando sobre el contenido (N-11). En vertical (<992 px) se usa solo el menú nativo de Odoo, correcto pero sin la navegación de D'CASA.

**Escenario E — pantalla baja (portátil 1366×768, viewport ≈650 px).** 15 apps × 42 px + cabecera (~150) + pie (40) excede el alto: la lista hace scroll interno (bien, SCSS:119-128). Al recoger, el contenido se acorta y `scrollTop` vuelve a 0; al re-expandir, la sección activa puede quedar fuera de vista y nada la trae con `scrollIntoView` (N-10).

## 3. Hallazgos

### ALTO

**N-01 · ALTO · UX · Modo «auto» por defecto con hover y autocierre**
- `barra_lateral.js:25-31` (default `"auto"`), `:63-77` (hover 120/350 ms), `:79-82` y `:167-183` (autocierre al elegir), `:185-195`; `barra_lateral.xml:40` (`!colapsada` para renderizar secciones).
- Efecto: ver escenario A. Las secciones solo existen mientras el mouse está encima; elegir cualquier cosa cierra la barra bajo el puntero y obliga a re-entrar.
- Además depende de puntero: sin hover (teclado, táctil, lector de pantalla) el modelo funciona a medias (WCAG 2.1.1 parcial, 1.4.13).
- Recomendación: default «fija» ≥1200 px; «riel» por clic (sin hover); eliminar `recoger()` tras navegar (sección 5.1).

**N-02 · ALTO · UX · El reflujo al expandir mueve los objetivos bajo el puntero**
- `barra_lateral.xml:40` + `barra_lateral.scss:251-264` + `barra_lateral.js:55`.
- Al expandir, se inserta la lista de secciones de la app activa (puede medir 200–600 px) entre apps; además los íconos pasan de centrados a alineados a la izquierda y el logo cambia de 22 a 40 px de alto (SCSS:261 vs :79). Quien apuntaba a la app de abajo termina pulsando otra. Se suma que la expansión no tiene transición y el cambio es brusco.
- Recomendación: no mostrar/ocultar contenido según hover. En fija las secciones están siempre; en riel no se expande (sección 5.1).

**N-03 · ALTO · A11Y · Pérdida de foco al recogerse (WCAG 2.4.3, 2.4.7)**
- `barra_lateral.js:180-182` → `barra_lateral.xml:40` (`t-if="!colapsada and …"` elimina el `<ul>` con el enlace enfocado).
- Tras Enter sobre una sección en modo auto, el foco se pierde (document.body). Verificar en navegador; el mecanismo es determinista (nodo enfocado removido).
- Recomendación: no desmontar al navegar (se arregla con N-01) y, si se mantiene el riel, no retirar las secciones sino ocultarlas con `hidden`/`inert` solo cuando ninguna tenga foco.

**N-04 · ALTO · A11Y · Sin «saltar al contenido» y ~25–40 paradas de Tab antes del contenido (WCAG 2.4.1, nivel A)**
- `barra_lateral.xml:236`/`:230-233`: la barra se inserta **antes** del `NavBar` y del `o_action_manager`; no hay enlace de salto ni punto de referencia `main`.
- Paradas previas al contenido: logo, buscar, cada app (~15), secciones de la app abierta (hasta 30+ con grupos), botón de colapsar, y luego el `NavBar` nativo con el systray.
- Recomendación: enlace «Saltar al contenido» como primera parada (5.3) y, opcionalmente, teclado de flechas en la lista (roving tabindex).

**N-05 · ALTO · A11Y · Indicador de foco: contraste 1,5:1, recortado y ausente en alto contraste (WCAG 1.4.11, 2.4.7, 2.4.11)**
- `tokens.scss:43`: `--dc-foco: 0 0 0 3px var(--dc-azul-200)`. `#C3D2F6` sobre blanco = **1,51:1** (sobre niebla/azul-50: 1,40:1). Exigido ≥3:1.
- `barra_lateral.scss:74,115,147,207,247`: `outline:none` + `box-shadow`. En modo de colores forzados (Windows alto contraste) los `box-shadow` desaparecen: **no queda ningún indicador de foco**.
- `barra_lateral.scss:119-128`: la lista tiene `overflow-y:auto` (fuerza `overflow-x` no visible) y `padding:0`; los elementos ocupan el 100 % del ancho, así que el halo de 3 px se **recorta a izquierda y derecha** en apps y secciones.
- Recomendación: `outline:2px solid var(--dc-azul-600)` con `outline-offset:-2px` (hacia dentro, no se recorta) + `outline:2px solid transparent` compatible con forced-colors (5.4). El mismo token lo usan botones y buscador de Odoo (`global.scss:58`, `:41-45`): ver pregunta a `ui-backend`.

### MEDIO

**N-06 · MEDIO · A11Y · Secciones ausentes del árbol cuando está colapsada; grupos sin `aria-controls`**
- `barra_lateral.xml:40` (no se renderizan) y `:68-74` (botón con `aria-expanded` pero sin `aria-controls`, `<ul>` sin `id`). El propio encargo de auditoría pedía `aria-expanded/controls`: falta `controls`.
- Recomendación: ids estables `dc-sec-{id}` (5.2) y renderizar siempre las secciones (con la barra fija se resuelve).

**N-07 · MEDIO · A11Y · El botón de colapsar mezcla `aria-pressed` con etiqueta cambiante**
- `barra_lateral.xml:49-54`: `aria-pressed` = «fija» y además el texto cambia entre «Recoger automáticamente» y «Dejar abierto». Un lector anuncia «Recoger automáticamente, botón de alternancia, presionado», que invita a lo contrario. Además en estado colapsado el texto está oculto y el nombre sale del `title`.
- Recomendación: etiqueta constante («Barra lateral») + `aria-expanded` (5.2).

**N-08 · MEDIO · A11Y · Contenido por hover/foco sin forma de descartar (WCAG 1.4.13)**
- `barra_lateral.xml:16-17`, `barra_lateral.js:63-82`: la expansión se dispara con `mouseenter`/`focusin`, no hay Esc para descartarla. Es hoverable y persistente (bien), pero no descartable. Desaparece con la propuesta N-01.

**N-09 · MEDIO · A11Y/UX · Contrastes y estados**
- Calculados: `tinta-3` `#6B7690` sobre blanco **4,55:1** (justo); sobre `niebla` (fondo del buscador, SCSS:97-98) **4,20:1 → no cumple 4,5:1** para «Buscar» y su ícono; `kbd` a `.68rem` ≈ 10,9 px (SCSS:105) es demasiado pequeño para leerse. `tinta-2` 8,07:1 y `azul-700` sobre `azul-50` 10,0:1: correctos.
- Estados: hover (`niebla`) y activo (`azul-50`) contra blanco = **1,08:1** cada uno; apenas distinguibles entre sí y del reposo. La app activa se distingue solo por color de texto y peso 500→600 (SCSS:157-161); las secciones sí llevan barra lateral de 2 px (SCSS:214-223), las apps no. Con `aria-current` el lector está cubierto, pero un usuario de baja visión pierde «dónde estoy» (WCAG 1.4.1).
- Recomendación: buscador en `tinta-2`; fondo activo `azul-100` + barra de 3 px también en apps; hover `perla` (5.4).

**N-10 · MEDIO · UX · La sección activa no se desplaza a la vista**
- `barra_lateral.scss:119-128` (lista con scroll) y no hay `scrollIntoView` en `barra_lateral.js`. En viewport bajo, o al volver de riel a expandida, el ítem activo puede quedar oculto. (5.2 `onPatched`).

**N-11 · MEDIO · UX · Táctil y tablet**
- `barra_lateral.js:185-191`: primer toque expande (correcto), pero no hay cierre al tocar fuera ni al pulsar Esc; en 992–1199 px la barra fija de 256 px deja solo 736–943 px al contenido.
- `barra_lateral.scss:1-7`: <992 px se usa únicamente el menú nativo (decisión documentada, correcta como respaldo, pero sin búsqueda ni sección activa propias).
- Recomendación: riel por defecto 992–1199 px (sin hover), barra fija ≥1200.

**N-12 · MEDIO *(por verificar)* · UX · `childrenTree` perezoso hace inconsistente el autocierre**
- `barra_lateral.js:180` usa `item.childrenTree.length`; en `menu_service` de Odoo, `childrenTree` se crea al llamar `getMenuAsTree` (aquí `secciones(app)`, JS:112), es decir, solo para la app ya visitada. La primera vez que se entra a una app la barra se cierra; en la siguiente visita (childrenTree ya poblado) se queda abierta. Confirmar en el navegador; se evita eliminando `recoger()`.

**N-13 · MEDIO · A11Y · Hotkeys nativas *(por verificar)***
- `barra_lateral.scss:20-24` oculta con `display:none !important` `.o_menu_sections`, `.o_navbar_apps_menu`, `.o_menu_toggle`. Si el navbar de Odoo 19 registra hotkeys (Alt+número / Alt+H) sobre esos elementos, dejan de funcionar al estar ocultos. No reemplazadas por `data-hotkey` en la barra nueva.

### BAJO

**N-14 · BAJO · Logo con destino incorrecto y posible error** — `barra_lateral.xml:18`: `abrir(apps[0], ev)`; «ir al inicio» solo funciona porque «Inicio» es la app de `sequence=0` (`views/inicio_views.xml:9`). Si el usuario no ve esa app o `apps` está vacío, `abrir(undefined)` lanza `TypeError` en `item.actionID`. También `enlace(app)` devuelve `/odoo` si la app no tiene acción (JS:155-157).

**N-15 · BAJO · Rendimiento** — `barra_lateral.js:159-165` hace `replace(/\s/g,"")` sobre el base64 del ícono dos veces por app y por render (XML:35,37), y se re-renderiza en cada `ACTION_MANAGER:UI-UPDATED` (JS:45-47); `secciones(app)` se evalúa dos veces (XML:40 y :43) con `addCustomMenus`; `abierto(seccion)` (recursivo vía `contieneActiva`) se evalúa dos veces por grupo (XML:69,74). Con ~15 apps no bloquea, pero es trabajo repetido en cada navegación. Memoizar el ícono por `app.id` (5.2).

**N-16 · BAJO · Semántica** — `barra_lateral.xml:33-36`: `aria-current="true"` en la app y `"page"` en la sección, dos «actuales» a la vez; usar `location` en la app. Dos landmarks `navigation` (este y el `NavBar` nativo) *(por verificar)* con nombres poco distintos.

**N-17 · BAJO · Texto largo y zoom** — `barra_lateral.scss:143` `white-space:nowrap` sin `text-overflow:ellipsis` dentro de un `overflow:hidden` (SCSS:50): un nombre largo se corta sin señal. Anchos en px (TOK:46-47) no escalan con el tamaño de letra del navegador. Por debajo de 992 px (zoom ≥150 % en 1366) se cae al menú nativo: aceptable para reflujo (1.4.10).

**N-18 · BAJO · Clases del navbar nativo *(por verificar)*** — `barra_lateral.scss:15,20-27` usa `.o_navbar`, mientras `global.scss:12` y `dcasa_base/…/backend.scss:24` usan `.o_main_navbar`. En Odoo 19 uno de los dos puede ser código muerto; el test de tercer nivel no lo detecta. Además, en edición del sitio web la barra sigue ocupando 68/256 px *(por verificar)*.

**N-19 · BAJO · Animación de layout** — `barra_lateral.scss:12` anima `grid-template-columns` del `body` (relayout completo por fotograma) al alternar el modo. Está neutralizada con reduced-motion (SCSS:287-289). Bajo impacto; desaparece si el riel/fija no se alterna por hover.

**N-20 · BAJO · Tests** — `tests/test_interfaz.py:84-136` cubre solo: modo auto inicial, fijar, acordeón, tercer nivel y enlaces sin destino. No cubre: hover/foco, teclado, `aria-*`, autocierre, táctil, persistencia, ni que el foco sobreviva a la navegación. Todo cambio lleva test (CLAUDE.md): ver 5.5.

Objetivos táctiles: app 40 px, sección 34 px, buscar 38 px, colapsar 40 px (SCSS:92,137,193,235). **Cumplen WCAG 2.2 AA 2.5.8 (≥24 px)**; quedan bajo los 44–48 px recomendados para táctil (sugerido en 5.4, no es fallo AA).

## 4. Lo que está bien hecho
- `<nav aria-label>`, lista `ul/li`, apps y secciones son `<a href>` reales: Ctrl/⌘/Mayús-clic y clic medio abren pestaña (JS:167-171); el href `/odoo/action-N` es compartible.
- Grupos como `<button aria-expanded>` (patrón disclosure correcto), íconos decorativos con `aria-hidden` y `alt=""`, `aria-current="page"` en la sección activa.
- Acordeón coherente a cualquier profundidad y abierto por defecto el grupo que contiene la página actual (JS:133-153); cubierto por test de tercer nivel.
- Scroll interno solo en la lista, con cabecera (logo/buscar) y pie fijos (SCSS:119-128); `d-print-none`; oculta sin paradas fantasma en <lg (`display:none`).
- Temporizadores con debounce (120/350 ms) y limpiados en `onWillUnmount` (JS:51); localStorage en try/catch (JS:25-31, 204-208).
- `prefers-reduced-motion` respetado (SCSS:287-289). Contraste de `tinta-2` (8,07:1) y `azul-700` (10:1) holgado.
- Integración con menús especiales del sitio web (`website_custom_menus`, JS:41,113,120-122,173-175) y con la paleta Ctrl+K (búsqueda global, JS:197-199).
- Sin flash al cargar: la clase de cuadrícula se pone en `WebClient.setup` antes del primer render (JS:221-226) y las apps ya están cargadas por el servicio de menús.
- Diseño plano acorde a la marca; azul sobre blanco; sin amarillo sobre blanco.

## 5. Rediseño propuesto (fragmentos listos; no aplicados)

### 5.1 Modelo de interacción
| Ancho | Por defecto | Comportamiento |
|---|---|---|
| ≥1200 px | **Fija** 240–256 px (empuja el contenido), secciones siempre visibles | Se puede recoger a riel con el botón; preferencia en localStorage |
| 992–1199 px | **Riel** 68 px (solo íconos) | Se expande **solo por clic/tecla** en el botón (aria-expanded); sin hover, sin autocierre; al expandir flota con fondo y `Esc` la cierra |
| <992 px | Menú nativo de Odoo | Sin cambios |
Opción B para el riel: mostrar las secciones de la app en la barra superior nativa (`body.o_dcasa_barra_riel .o_navbar .o_menu_sections{display:flex!important}`) *(por verificar en Odoo 19)*, porque en riel no caben.
Migración: el valor guardado `"auto"` se ignora y se aplica el default por ancho.

### 5.2 JavaScript (cambios sobre `barra_lateral.js`)
```js
import { Component, onPatched, onWillUnmount, useRef, useState } from "@odoo/owl";
const CLAVE = "dcasa.barra_lateral.modo";      // "fija" | "riel"
const ANCHO_FIJA_MIN = 1200;

function leerModo() {
    try {
        const v = browser.localStorage.getItem(CLAVE);
        if (v === "fija" || v === "riel") { return v; }
    } catch { /* sin almacenamiento */ }
    return browser.innerWidth >= ANCHO_FIJA_MIN ? "fija" : "riel";
}

setup() {
    // …igual…
    this.state = useState({ modo: leerModo(), desplegada: false, abiertos: {}, version: 0, elegido: null });
    this.raiz = useRef("raiz");
    this.iconos = new Map();
    // Esc cierra la barra flotante del riel y devuelve el foco al botón.
    onPatched(() => {
        const activo = this.raiz.el?.querySelector("a.o_activa.o_dcasa_barra_seccion");
        const clave = activo?.getAttribute("href");
        if (activo && clave !== this.ultimoActivo) {
            this.ultimoActivo = clave;
            activo.scrollIntoView({ block: "nearest" });   // N-10
        }
    });
}
get expandida() { return this.state.modo === "fija" || this.state.desplegada; }
get colapsada() { return !this.expandida; }

// Sin entrar()/salir()/recoger(): no hay hover ni autocierre (N-01, N-02, N-03).
abrir(item, ev) {
    if (!item || (ev && (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button === 1))) { return; }
    ev?.preventDefault();
    if (this.esEspecial(item)) { this.menusSitio.open(item); }
    else { this.state.elegido = { id: item.id, actionID: item.actionID }; this.menu.selectMenu(item); }
    if (this.state.modo === "riel") { this.state.desplegada = false; }   // solo el riel flotante se cierra
}

alternarBarra() {                       // fija <-> riel
    this.state.modo = this.state.modo === "fija" ? "riel" : "fija";
    this.state.desplegada = false;
    try { browser.localStorage.setItem(CLAVE, this.state.modo); } catch { /* sesión */ }
    this.aplicarAncho();
}
alternarDesplegada() { this.state.desplegada = !this.state.desplegada; }
onTeclaBarra(ev) { if (ev.key === "Escape" && this.state.desplegada) { this.state.desplegada = false; } }

icono(app) {                            // N-15: memoizado
    let v = this.iconos.get(app.id);
    if (v === undefined) {
        const data = app.webIconData;
        v = !data || data.startsWith("data:") || data.startsWith("/")
            ? data
            : `data:${app.webIconDataMimetype || "image/svg+xml"};base64,${data.replace(/\s/g, "")}`;
        this.iconos.set(app.id, v);
    }
    return v;
}
saltarAlContenido(ev) {                 // N-04
    ev.preventDefault();
    const c = document.querySelector(".o_action_manager");
    if (c) { c.tabIndex = -1; c.focus({ preventScroll: true }); }
}
aplicarAncho() { document.body.classList.toggle("o_dcasa_barra_riel", this.state.modo === "riel"); }
```
Clave: el ancho del contenido solo depende del modo guardado, no del hover.

### 5.3 Plantilla (`barra_lateral.xml`)
```xml
<t t-name="dcasa_interfaz.BarraLateral">
    <a class="o_dcasa_saltar" href="#contenido" t-on-click="saltarAlContenido">Saltar al contenido</a>
    <nav class="o_dcasa_barra d-print-none" t-ref="raiz" aria-label="Menú de aplicaciones"
         t-att-class="{ 'o_dcasa_barra_colapsada': colapsada, 'o_dcasa_barra_flotante': state.modo === 'riel' and state.desplegada }"
         t-on-keydown="onTeclaBarra">
        <a class="o_dcasa_barra_marca" t-att-href="enlace(apps[0] || {})" t-on-click="(ev) => this.abrir(apps[0], ev)"
           aria-label="D'CASA Panamá, inicio"> … </a>

        <button type="button" class="o_dcasa_barra_buscar" t-on-click="buscar"
                aria-keyshortcuts="Control+K" title="Buscar (Ctrl + K)">
            <i class="fa fa-search" aria-hidden="true"/>
            <span class="o_dcasa_barra_texto">Buscar</span>
            <kbd class="o_dcasa_barra_texto" aria-hidden="true">Ctrl K</kbd>
        </button>

        <ul class="o_dcasa_barra_lista">
            <li t-foreach="apps" t-as="app" t-key="app.id" class="o_dcasa_barra_item" t-att-class="{'o_activa': esAppActual(app)}">
                <a class="o_dcasa_barra_app" t-att-href="enlace(app)" t-on-click="(ev) => this.abrirApp(app, ev)"
                   t-att-aria-current="esAppActual(app) ? 'location' : undefined"
                   t-att-aria-label="app.name" t-att-title="colapsada ? app.name : undefined">
                    <img t-if="icono(app)" class="o_dcasa_barra_icono" t-att-src="icono(app)" alt=""/>
                    <span class="o_dcasa_barra_texto" t-out="app.name"/>
                </a>
                <!-- Siempre en el DOM para la app activa; en riel se ocultan con [hidden] -->
                <ul t-if="esAppActual(app) and secciones(app).length" class="o_dcasa_barra_secciones"
                    t-att-hidden="colapsada ? true : undefined" t-att-aria-label="'Secciones de ' + app.name">
                    …
                </ul>
            </li>
        </ul>

        <button type="button" class="o_dcasa_barra_colapsar"
                t-on-click="() => this.state.modo === 'fija' ? this.alternarBarra() : this.alternarDesplegada()"
                aria-label="Barra lateral" t-att-aria-expanded="expandida ? 'true' : 'false'"
                t-att-title="expandida ? 'Recoger la barra lateral' : 'Expandir la barra lateral'">
            <i t-attf-class="fa {{ expandida ? 'fa-angle-double-left' : 'fa-angle-double-right' }}" aria-hidden="true"/>
            <span class="o_dcasa_barra_texto" t-out="expandida ? 'Recoger' : 'Expandir'"/>
        </button>
    </nav>
</t>

<!-- Grupo con aria-controls -->
<li t-else="" class="o_dcasa_barra_grupo">
    <button type="button" class="o_dcasa_barra_seccion o_dcasa_barra_grupo_btn"
            t-att-aria-expanded="abierto(seccion) ? 'true' : 'false'"
            t-att-aria-controls="'dc-sec-' + seccion.id"
            t-on-click="() => this.alternar(seccion, nodos)">
        <span t-out="seccion.name"/><i class="fa fa-angle-down" aria-hidden="true"/>
    </button>
    <ul t-att-id="'dc-sec-' + seccion.id" t-att-hidden="abierto(seccion) ? undefined : true" class="o_dcasa_barra_hijos">…</ul>
</li>
```
(Con `hidden` el `<ul>` sigue en el DOM y `aria-controls` siempre apunta a algo existente.) Nota: el `.o_action_manager` debe llevar `id="contenido"` o usar solo el handler `saltarAlContenido`.

### 5.4 SCSS
```scss
// Foco: visible, ≥3:1, hacia dentro (no se recorta por overflow) y visible en alto contraste
.o_dcasa_barra :is(a, button):focus-visible {
    outline: 2px solid var(--dc-azul-600);   // 8,8:1 sobre blanco y 8,1:1 sobre azul-50
    outline-offset: -2px;
    box-shadow: none;
}
@media (forced-colors: active) {
    .o_dcasa_barra :is(a, button):focus-visible { outline-color: Highlight; }
    .o_dcasa_barra_item.o_activa > .o_dcasa_barra_app,
    .o_dcasa_barra_seccion.o_activa { outline: 2px solid CanvasText; outline-offset: -2px; }
}

// Saltar al contenido
.o_dcasa_saltar {
    position: absolute; left: 8px; top: -48px; z-index: 2000;
    padding: 10px 14px; background: var(--dc-azul-600); color: #fff; border-radius: var(--dc-r-sm);
    &:focus { top: 8px; }
}

// Estados: distinguibles entre sí
.o_dcasa_barra_app:hover, .o_dcasa_barra_seccion:hover { background: var(--dc-perla); color: var(--dc-tinta); }
.o_dcasa_barra_item.o_activa > .o_dcasa_barra_app { background: var(--dc-azul-100); box-shadow: inset 3px 0 0 var(--dc-azul-600); }
.o_dcasa_barra_seccion.o_activa { background: var(--dc-azul-100); }
.o_dcasa_barra_buscar { color: var(--dc-tinta-2); }
.o_dcasa_barra_buscar kbd { font-size: .75rem; }

// Texto largo y objetivos táctiles
.o_dcasa_barra_app .o_dcasa_barra_texto { overflow: hidden; text-overflow: ellipsis; }
@media (pointer: coarse) {
    .o_dcasa_barra_app { min-height: 48px; }
    .o_dcasa_barra_seccion, .o_dcasa_barra_buscar, .o_dcasa_barra_colapsar { min-height: 44px; }
}

// Anchos que escalan con la letra del usuario
:root { --dc-barra-w: 16rem; --dc-barra-w-colapsada: 4.25rem; }

// Riel: clase en <body> por modo (sustituye o_dcasa_barra_colapsada del body)
@include media-breakpoint-up(lg) {
    body.o_dcasa_con_barra.o_dcasa_barra_riel.o_web_client { grid-template-columns: var(--dc-barra-w-colapsada) minmax(0, 1fr); }
    nav.o_dcasa_barra.o_dcasa_barra_flotante { position: relative; z-index: 30; width: var(--dc-barra-w); justify-self: start; box-shadow: var(--dc-sombra-2); }
}
```
En `tokens.scss:43` (coordinar con `ui-backend`): `--dc-foco: 0 0 0 2px var(--dc-blanco), 0 0 0 4px var(--dc-azul-600);` para botones/buscador de Odoo (anillo doble visible sobre cualquier fondo).

### 5.5 Pruebas a agregar (`tests/test_interfaz.py`, tour/JS)
1. Por defecto en viewport ≥1200 px: la barra está expandida y las secciones de la app activa están en el DOM sin hover.
2. Clic en una sección no cambia el ancho de la barra ni retira el elemento enfocado (`document.activeElement` sigue dentro de `nav.o_dcasa_barra`).
3. Cada `button[aria-expanded]` tiene `aria-controls` que apunta a un `id` existente.
4. El botón de colapsar alterna `aria-expanded` y persiste en localStorage; un valor heredado `"auto"` no rompe.
5. El primer elemento tabulable es «Saltar al contenido» y mueve el foco al contenido.
6. Esc cierra el riel desplegado (viewport 1024 px).

## 6. Plan de arreglo ordenado
1. **Primero (resuelve la queja del dueño):** N-01/N-02/N-03 — default fija por ancho, riel por clic, eliminar hover y autocierre (5.1, 5.2). ~medio día.
2. N-05 foco (token + `outline` + forced-colors) y N-04 salto de bloque (5.3, 5.4). ~1–2 h.
3. N-06/N-07/N-16 ARIA: `aria-controls`, botón con `aria-expanded`, `aria-current=location`. ~1 h.
4. N-09/N-10 contrastes/estados y `scrollIntoView`. ~1 h.
5. N-15/N-14/N-17 memoización, guardas en logo, ellipsis, rem. ~1 h.
6. Verificar en navegador real (por verificar): N-12, N-13, N-18 y la edición del sitio web.
7. Tests de 5.5.

## 7. Pendientes / por verificar con Odoo 19 real
N-12 (`childrenTree` perezoso), N-13 (hotkeys del navbar ocultado), N-16 (doble landmark), N-18 (`.o_navbar` vs `.o_main_navbar`, barra durante la edición del sitio), y confirmación visual de N-03 y del recorte del halo (N-05).
