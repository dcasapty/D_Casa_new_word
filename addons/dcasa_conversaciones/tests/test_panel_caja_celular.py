"""La caja de responder del chat EN EL CELULAR, en dos renglones (aprobado por la dueña el 2026-11-11).

Antes ocupaba un tercio de la pantalla (unos 211 px: quién atiende, Respuesta / Nota, las herramientas y el texto, cada
cosa en su renglón). Ahora mide la mitad y se ven dos o tres mensajes más mientras se escribe:

1. un renglón con quién atiende (corto) + «Devolver» (o «Atender») + Respuesta / Nota;
2. otro con «+» (abre el cajón con las herramientas de siempre: adjuntar, foto del catálogo, cotización, respuestas
   rápidas y programar), «Sugerir» a la vista, el texto y Enviar.

No se quitó nada: aquí se comprueba, en Chrome de verdad y en dos celulares (390 × 844 y 360 × 740), que la caja vacía
mide dos renglones, que todo sigue en 44 px para el dedo, que cada herramienta sigue estando y funcionando a un toque
más, que Respuesta / Nota funciona y la nota se ve distinta, y que nada se sale de costado. Y que en la tableta y en la
computadora la caja quedó como estaba.
"""
from odoo.tests import tagged

from .test_panel_interfaz import GERENTE, PanelUiCase

CELULARES = ((390, 844), (360, 740))
# Lo más alto que puede medir la caja vacía en el celular (dos renglones de 44 px con sus márgenes: mide unos 111).
ALTO_MAXIMO_VACIA = 130

# Ayudas que corren en el navegador, además de las de ``test_panel_interfaz.ESPERAR``.
MEDIR = """
const caja = () => document.querySelector(".o_dcj_caja");
const rect = (el) => el.getBoundingClientRect();
// ¿Se ve? (pintado, con tamaño y dentro de la ventana)
const seVe = (el) => {
    if (!el) { return false; }
    const cs = getComputedStyle(el), r = rect(el);
    return cs.display !== "none" && cs.visibility !== "hidden" && r.width > 0 && r.height > 0
        && r.left >= -0.5 && r.right <= window.innerWidth + 0.5 && r.top >= -0.5 && r.bottom <= window.innerHeight + 0.5;
};
const sinDesborde = (donde) => {
    const raiz = document.querySelector(".o_dcj");
    if (document.documentElement.scrollWidth > window.innerWidth + 1 || raiz.scrollWidth > raiz.clientWidth + 1) {
        throw new Error("se sale de costado " + donde + ": página " + document.documentElement.scrollWidth + " de " + window.innerWidth
            + ", pantalla " + raiz.scrollWidth + " de " + raiz.clientWidth);
    }
};
// Botones, selectores y cajas con menos de 44 px (los enlaces de texto dentro de una frase no cuentan).
const chicos = () => [...document.querySelectorAll(".o_dcj button, .o_dcj select, .o_dcj input:not([type=file]), .o_dcj textarea")]
    .filter((e) => !e.classList.contains("o_dcj_enlace") && getComputedStyle(e).visibility !== "hidden")
    .map((e) => [e, rect(e)])
    .filter(([, r]) => r.width > 0 && r.height > 0 && (r.width < 43.5 || r.height < 43.5))
    .map(([e, r]) => e.className + " [" + (e.getAttribute("aria-label") || e.textContent.trim().slice(0, 20)) + "] " + Math.round(r.width) + "x" + Math.round(r.height));
const sinChicos = (donde) => {
    const lista = chicos();
    if (lista.length) { throw new Error(donde + ", menos de 44 px: " + lista.join(" | ")); }
};
const cajaBaja = (donde, tope) => {
    const r = rect(caja());
    if (r.height > tope) { throw new Error(donde + ": la caja mide " + Math.round(r.height) + " px (tope " + tope + ")"); }
    if (Math.abs(r.bottom - window.innerHeight) > 4) { throw new Error(donde + ": la caja no queda pegada abajo: " + r.bottom + " de " + window.innerHeight); }
};
// Un toque de verdad: primero «pointerdown» (lo que cierra el cajón al tocar fuera) y luego el clic.
const tocar = (el) => {
    el.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, cancelable: true }));
    el.click();
};
const mas = () => document.querySelector(".o_dcj_cajon_boton");
const cajon = () => document.querySelector(".o_dcj_cajon");
const cajonAbierto = () => mas().getAttribute("aria-expanded") === "true" && seVe(cajon());
const cajonCerrado = () => mas().getAttribute("aria-expanded") === "false" && rect(cajon()).height === 0;
const herramienta = (nombre) => [...document.querySelectorAll(".o_dcj_herramientas .o_dcj_herramienta")]
    .find((b) => (b.getAttribute("aria-label") || "").includes(nombre) || b.textContent.includes(nombre));
const abrirCajon = async () => {
    if (!cajonAbierto()) { tocar(mas()); }
    await esperar(cajonAbierto, "el cajón de herramientas abierto");
    await pausa(250);
};
const abrirLaDe = async (nombre) => {
    const fila = await esperar(() => aqui(".o_dcj_fila", nombre), "la conversación de " + nombre);
    fila.click();
    await esperar(() => document.querySelector(".o_dcj_hilo_cabecera h2")?.textContent.includes(nombre)
        && !document.querySelector(".o_dcj_hilo_cuerpo .o_dcj_cargando") && caja(), "el hilo de " + nombre);
    await pausa(300);
};
const corto = () => document.querySelector(".o_dcj_barra_corto")?.textContent.trim();
"""


class CajaCelularCase(PanelUiCase):
    """Un celular con dedos (los botones de Odoo cambian de tamaño en pantallas táctiles) del tamaño que se pida."""
    touch_enabled = True

    def celular(self, ancho, alto, codigo, numero=0, **kw):
        """Corre ``codigo`` en un celular de ``ancho`` × ``alto``. En el código, ``__ANCHO__`` es el ancho pedido,
        ``__TOPE__`` el alto máximo de la caja vacía y ``__NUMERO__`` el número de la vuelta (para textos distintos)."""
        self.browser_size = f'{ancho}x{alto}'
        for marca, valor in (('__ANCHO__', ancho), ('__TOPE__', ALTO_MAXIMO_VACIA), ('__NUMERO__', numero)):
            codigo = codigo.replace(marca, str(valor))
        self.navegador(MEDIR + codigo, **kw)


@tagged('post_install', '-at_install')
class TestCajaDeDosRenglonesEnElCelular(CajaCelularCase):

    def test_la_caja_vacia_mide_dos_renglones_con_todo_a_44_px_y_respuesta_nota_funciona(self):
        self.datos_de_ejemplo()
        for ancho, alto in CELULARES:
            with self.subTest(celular=f'{ancho}x{alto}'):
                self.celular(ancho, alto, """
(async () => {
    if (window.innerWidth !== __ANCHO__) { throw new Error("el celular debe medir __ANCHO__ px y mide " + window.innerWidth); }
    const TOPE = __TOPE__;
    // --- Atiende el asistente -----------------------------------------------------------------------------
    await abrirLaDe("Karen");
    cajaBaja("caja vacía, atiende el asistente", TOPE);
    sinDesborde("con la caja vacía");
    sinChicos("con la caja vacía");
    const centro = (el) => rect(el).top + rect(el).height / 2;
    const barra = document.querySelector(".o_dcj_barra"), modo = document.querySelector(".o_dcj_modo");
    const texto = document.querySelector("#o_dcj_texto"), enviar = document.querySelector(".o_dcj_enviar");
    // Renglón 1: quién atiende + el botón + Respuesta / Nota.
    if (!seVe(barra) || !seVe(modo) || Math.abs(centro(barra) - centro(modo)) > 3) { throw new Error("quién atiende y Respuesta / Nota van en el mismo renglón"); }
    if (corto() !== "Asistente" || !seVe(document.querySelector(".o_dcj_barra_corto"))) { throw new Error("dice quién atiende, en corto: " + corto()); }
    if (!barra.textContent.includes("Atiende el asistente. Si escribes, la atiendes tú")) { throw new Error("la frase completa sigue para los lectores de pantalla"); }
    if (!barra.querySelector(".o_dcj_barra_texto").title.includes("Atiende el asistente")) { throw new Error("la frase completa sigue en el title de la barra"); }
    const atender = barra.querySelector("button");
    if (atender.textContent.trim() !== "Atender" || !seVe(atender)) { throw new Error("el botón «Atender» a la vista"); }
    if (rect(barra).right > rect(modo).left + 1) { throw new Error("quién atiende se monta sobre Respuesta / Nota"); }
    // Renglón 2: «+», Sugerir, el texto y Enviar, en ese orden y a la misma altura.
    const sugerir = herramienta("Sugerir");
    const linea = [mas(), sugerir, texto, enviar];
    if (!linea.every(seVe)) { throw new Error("«+», Sugerir, el texto y Enviar se ven sin abrir nada"); }
    for (let i = 1; i < linea.length; i++) {
        if (rect(linea[i - 1]).right > rect(linea[i]).left + 1) { throw new Error("la línea de escribir no va en orden (" + i + ")"); }
        if (Math.abs(rect(linea[i]).bottom - rect(linea[0]).bottom) > 2) { throw new Error("la línea de escribir no es un solo renglón (" + i + ")"); }
    }
    if (rect(barra).bottom > rect(texto).top) { throw new Error("la franja va encima de la línea de escribir"); }
    if (rect(texto).width < 140) { throw new Error("el texto quedó muy angosto: " + rect(texto).width); }
    if (texto.placeholder !== "Escribe tu respuesta…") { throw new Error("la pista del celular: " + texto.placeholder); }
    // Las demás herramientas están (dentro del «+»), pero no ocupan lugar hasta abrirlo. «Más» no hace falta aquí.
    for (const nombre of ["Adjuntar", "Foto del catálogo", "Cotización", "Rápidas", "Programar"]) {
        const b = herramienta(nombre);
        if (!b) { throw new Error("falta la herramienta «" + nombre + "»"); }
        if (rect(b).width > 0) { throw new Error("«" + nombre + "» debe esperar dentro del «+»"); }
    }
    if (document.querySelector(".o_dcj_mas_boton")) { throw new Error("en el celular «Programar» va en el «+»: no hay menú «Más»"); }
    // El botón flotante de Brian no tapa Enviar (en el celular Brian vive en la barra de arriba).
    const brian = document.querySelector(".o_brian_lanzador");
    if (brian && getComputedStyle(brian).display !== "none" && getComputedStyle(brian).visibility !== "hidden") {
        const f = rect(brian), e = rect(enviar);
        if (f.width > 0 && f.left < e.right && f.right > e.left && f.top < e.bottom && f.bottom > e.top) { throw new Error("el botón de Brian tapa Enviar"); }
    }

    // --- Respuesta / Nota ---------------------------------------------------------------------------------
    const [respuesta, nota] = modo.querySelectorAll("button");
    if (nota.textContent !== "Nota interna") { throw new Error("«Nota» sigue llamándose «Nota interna» para los lectores de pantalla"); }
    if (rect(nota).width > 70) { throw new Error("a la vista dice solo «Nota»: mide " + rect(nota).width); }
    if (respuesta.getAttribute("aria-pressed") !== "true" || nota.getAttribute("aria-pressed") !== "false") { throw new Error("nace en Respuesta"); }
    const blanco = getComputedStyle(caja()).backgroundColor;
    nota.click();
    await esperar(() => caja().classList.contains("o_nota") && nota.getAttribute("aria-pressed") === "true", "el modo Nota");
    if (getComputedStyle(caja()).backgroundColor === blanco) { throw new Error("en modo Nota la caja se tiñe"); }
    if (getComputedStyle(texto).borderTopStyle !== "dashed") { throw new Error("en modo Nota el texto lleva borde punteado"); }
    if (!texto.placeholder.includes("Nota")) { throw new Error("la pista de la nota: " + texto.placeholder); }
    if (enviar.getAttribute("aria-label") !== "Guardar nota") { throw new Error("en modo Nota el botón guarda la nota"); }
    if (!sugerir.disabled) { throw new Error("una nota no se le pide al asistente"); }
    cajaBaja("caja vacía en modo Nota", TOPE);
    sinChicos("en modo Nota");
    sinDesborde("en modo Nota");
    respuesta.click();
    await esperar(() => !caja().classList.contains("o_nota") && respuesta.getAttribute("aria-pressed") === "true", "volver a Respuesta");
    if (getComputedStyle(caja()).backgroundColor !== blanco) { throw new Error("al volver a Respuesta la caja queda blanca"); }

    // --- La atiendo yo: «Atiendes tú» + «Devolver» -----------------------------------------------------------
    document.querySelector(".o_dcj_volver").click();
    await esperar(() => seVe(document.querySelector(".o_dcj_lista")), "volver a la lista");
    await abrirLaDe("Marta");
    await esperar(() => corto() === "Atiendes tú", "«Atiendes tú»: " + corto());
    const devolver = document.querySelector(".o_dcj_barra button");
    if (devolver.textContent !== "Devolver al asistente") { throw new Error("el botón se sigue llamando «Devolver al asistente»: " + devolver.textContent); }
    if (!seVe(devolver) || rect(devolver).width > 100) { throw new Error("a la vista dice solo «Devolver»: mide " + rect(devolver).width); }
    cajaBaja("caja vacía, la atiendo yo", TOPE);
    sinChicos("con «Devolver»");
    sinDesborde("con «Devolver»");

    // --- Cerrada ------------------------------------------------------------------------------------------
    document.querySelector(".o_dcj_volver").click();
    await esperar(() => seVe(document.querySelector(".o_dcj_lista")), "volver a la lista");
    await abrirLaDe("Luis");
    await esperar(() => corto() === "Cerrada", "«Cerrada»: " + corto());
    cajaBaja("caja vacía, conversación cerrada", TOPE);
    sinChicos("con la conversación cerrada");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")

    def test_otra_persona_la_atiende_se_lee_su_nombre(self):
        """Gerencia abre una conversación que atiende una vendedora: se lee el nombre (la frase completa, para lectores)."""
        self.datos_de_ejemplo()
        self.celular(360, 740, """
(async () => {
    await abrirLaDe("Marta");
    await esperar(() => corto() === "Ana Vendedora", "el nombre de quien atiende: " + corto());
    const barra = document.querySelector(".o_dcj_barra");
    if (!barra.textContent.includes("La atiende Ana Vendedora.")) { throw new Error("la frase completa sigue en la barra"); }
    const nombre = document.querySelector(".o_dcj_barra_corto");
    if (!seVe(nombre) || rect(nombre).right > rect(barra.querySelector("button")).left + 1) { throw new Error("el nombre no se monta sobre «Devolver»"); }
    cajaBaja("caja vacía, la atiende otra persona", __TOPE__);
    sinChicos("con el nombre de otra persona");
    sinDesborde("con el nombre de otra persona");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", login=GERENTE)

    def test_el_mas_abre_las_herramientas_y_estan_todas_y_funcionan(self):
        self.datos_de_ejemplo()
        self.producto_de_ejemplo()
        for ancho, alto in CELULARES:
            with self.subTest(celular=f'{ancho}x{alto}'):
                self.celular(ancho, alto, """
(async () => {
    await abrirLaDe("Karen");
    const texto = document.querySelector("#o_dcj_texto"), enviar = document.querySelector(".o_dcj_enviar");
    const NOMBRES = ["Adjuntar", "Foto del catálogo", "Cotización", "Rápidas", "Programar"];
    if (!cajonCerrado()) { throw new Error("el cajón nace cerrado"); }

    // 1. «+» abre el cajón: están todas, con su nombre a la vista, a 44 px o más y dentro de la pantalla.
    await abrirCajon();
    if (!cajon().contains(document.activeElement)) { throw new Error("al abrir, el foco entra al cajón (y el teclado del celular se guarda)"); }
    for (const nombre of NOMBRES) {
        const b = herramienta(nombre);
        if (!seVe(b)) { throw new Error("«" + nombre + "» no se ve en el cajón"); }
        const r = rect(b), rotulo = b.querySelector("span");
        if (r.width < 44 || r.height < 44) { throw new Error("«" + nombre + "» mide " + Math.round(r.width) + "x" + Math.round(r.height)); }
        if (!rotulo.textContent.includes(nombre) || !seVe(rotulo) || rect(rotulo).width < 20 || rect(rotulo).right > r.right + 1) {
            throw new Error("«" + nombre + "» lleva su nombre a la vista, dentro del botón");
        }
        if (!b.title || !b.getAttribute("aria-label") || !b.querySelector(".fa")) { throw new Error("«" + nombre + "»: ícono, nombre y ayuda"); }
    }
    if (rect(cajon()).bottom > rect(texto).top + 1) { throw new Error("el cajón va encima de la línea de escribir"); }
    if (![mas(), herramienta("Sugerir"), texto, enviar].every(seVe)) { throw new Error("con el cajón abierto siguen a la vista «+», Sugerir, el texto y Enviar"); }
    cajaBaja("con el cajón abierto", window.innerHeight * 0.5);
    if (rect(document.querySelector(".o_dcj_hilo_cuerpo")).height < window.innerHeight * 0.3) { throw new Error("con el cajón abierto se siguen viendo los mensajes"); }
    sinChicos("con el cajón abierto");
    sinDesborde("con el cajón abierto");

    // 2. Se cierra con Esc (el foco vuelve al «+»), tocando el «+» y tocando fuera.
    tecla(document.activeElement, "Escape");
    await esperar(cajonCerrado, "Esc cierra el cajón");
    if (document.activeElement !== mas()) { throw new Error("al cerrar con Esc el foco vuelve al «+»"); }
    await abrirCajon();
    tocar(mas());
    await esperar(cajonCerrado, "el «+» cierra el cajón");
    await abrirCajon();
    tocar(document.querySelector(".o_dcj_hilo_cuerpo"));
    await esperar(cajonCerrado, "tocar los mensajes cierra el cajón");

    // Y con el «atrás» del teléfono (vuelve a la lista): al regresar a este chat el cajón ya no está abierto.
    await abrirCajon();
    history.back();
    await esperar(() => seVe(document.querySelector(".o_dcj_lista")), "«atrás» vuelve a la lista");
    await abrirLaDe("Karen");
    if (!cajonCerrado()) { throw new Error("después de «atrás», el cajón queda cerrado"); }

    // 3. Programar: a un toque dentro del «+».
    await abrirCajon();
    tocar(herramienta("Programar"));
    await esperar(() => document.querySelector(".o_dcj_programar") && cajonCerrado(), "la fila de programar (y el cajón cerrado)");
    sinChicos("con programar abierto");
    sinDesborde("con programar abierto");
    await abrirCajon();
    if (herramienta("Programar").getAttribute("aria-pressed") !== "true") { throw new Error("«Programar» queda marcado mientras está puesto"); }
    tocar(herramienta("Programar"));
    await esperar(() => !document.querySelector(".o_dcj_programar") && cajonCerrado(), "quitar la programación");

    // 4. Respuestas rápidas.
    await abrirCajon();
    tocar(herramienta("Rápidas"));
    await esperar(() => document.querySelector(".o_dcj_rapidas") && cajonCerrado() && texto.value === "/", "la lista de respuestas rápidas");
    sinDesborde("con las respuestas rápidas");
    await escribir(texto, "");
    await esperar(() => !document.querySelector(".o_dcj_rapidas"), "la lista de rápidas cerrada");

    // 5. Foto del catálogo y Cotización: abren su hoja.
    for (const nombre of ["Foto del catálogo", "Cotización"]) {
        await abrirCajon();
        tocar(herramienta(nombre));
        await esperar(() => document.querySelector(".o_dcj_hoja"), "la hoja de «" + nombre + "»");
        if (!cajonCerrado()) { throw new Error("al elegir «" + nombre + "» el cajón se cierra"); }
        escape();
        await esperar(() => !document.querySelector(".o_dcj_hoja"), "cerrar la hoja de «" + nombre + "»");
    }

    // 6. Adjuntar: abre el selector de archivos; el archivo queda en vista previa sobre la línea de escribir.
    const entrada = document.querySelector(".o_dcj_caja input[type=file]");
    let abrio = 0;
    entrada.click = () => { abrio++; };
    await abrirCajon();
    tocar(herramienta("Adjuntar"));
    await esperar(() => abrio === 1 && cajonCerrado(), "Adjuntar abre el selector de archivos y cierra el cajón");
    const lista = new DataTransfer();
    lista.items.add(archivo("lista.pdf", "application/pdf", PDF));
    entrada.files = lista.files;
    entrada.dispatchEvent(new Event("change", { bubbles: true }));
    const previa = await esperar(() => document.querySelector(".o_dcj_previa_listo"), "la vista previa del archivo");
    if (!seVe(previa) || !seVe(enviar) || enviar.disabled) { throw new Error("con un archivo listo se ve la vista previa y Enviar se activa"); }
    cajaBaja("con un archivo en vista previa", window.innerHeight * 0.5);
    sinChicos("con un archivo en vista previa");
    sinDesborde("con un archivo en vista previa");
    previa.querySelector("button").click();
    await esperar(() => !document.querySelector(".o_dcj_previa"), "quitar el archivo");

    // 7. En modo Nota solo se puede adjuntar (igual que en la computadora).
    aqui(".o_dcj_modo button", "Nota").click();
    await esperar(() => caja().classList.contains("o_nota"), "el modo Nota");
    await abrirCajon();
    if (herramienta("Adjuntar").disabled) { throw new Error("a una nota se le puede adjuntar"); }
    for (const nombre of ["Foto del catálogo", "Cotización", "Rápidas", "Programar"]) {
        if (!herramienta(nombre).disabled) { throw new Error("«" + nombre + "» no va en una nota"); }
    }
    tecla(document.activeElement, "Escape");
    await esperar(cajonCerrado, "cerrar el cajón");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")
        self.assertFalse(self.al_worker('/odoo/enviar'), 'Abrir herramientas no envía nada')
        self.assertFalse(self.env['ir.attachment'].sudo().search([('name', '=', 'lista.pdf')]),
                         'Lo que se quitó de la caja no se queda guardado')

    def test_con_poco_alto_la_linea_de_escribir_no_se_sale_de_la_pantalla(self):
        """El celular acostado (640 × 360) o con el teclado ocupando media pantalla (360 × 420): la caja de dos renglones
        deja ver mensajes y, con el cajón abierto (un solo renglón que se desliza), Enviar sigue a la vista."""
        self.datos_de_ejemplo()
        for ancho, alto in ((640, 360), (360, 420)):
            with self.subTest(celular=f'{ancho}x{alto}'):
                self.celular(ancho, alto, """
(async () => {
    await abrirLaDe("Karen");
    const texto = document.querySelector("#o_dcj_texto"), enviar = document.querySelector(".o_dcj_enviar");
    const mensajes = document.querySelector(".o_dcj_hilo_cuerpo"), cabecera = document.querySelector(".o_dcj_hilo_cabecera");
    cajaBaja("caja vacía con poco alto", __TOPE__);
    if (!seVe(texto) || !seVe(enviar)) { throw new Error("el texto y Enviar se ven"); }
    if (rect(mensajes).height < 60) { throw new Error("con la caja vacía quedan mensajes a la vista: " + rect(mensajes).height); }
    await abrirCajon();
    for (const nombre of ["Adjuntar", "Foto del catálogo", "Cotización", "Rápidas", "Programar"]) {
        const b = herramienta(nombre);
        if (rect(b).width < 44 || rect(b).height < 44) { throw new Error("«" + nombre + "» en el cajón: " + rect(b).width + "x" + rect(b).height); }
    }
    if (!seVe(herramienta("Adjuntar"))) { throw new Error("la primera herramienta se ve"); }
    if (!seVe(mas()) || !seVe(texto) || !seVe(enviar)) { throw new Error("con el cajón abierto, la línea de escribir sigue en la pantalla"); }
    const c = rect(caja());
    if (Math.abs(c.bottom - window.innerHeight) > 4 || c.top < rect(cabecera).bottom - 1) {
        throw new Error("con el cajón abierto la caja no cabe: " + Math.round(c.top) + " a " + Math.round(c.bottom) + " de " + window.innerHeight);
    }
    // Lo que no cabe a lo ancho se desliza dentro del cajón: la pantalla no se sale de costado.
    sinDesborde("con el cajón abierto y poco alto");
    herramienta("Programar").scrollIntoView({ block: "nearest", inline: "nearest" });
    await pausa(150);
    if (!seVe(herramienta("Programar"))) { throw new Error("«Programar» se alcanza deslizando el cajón"); }
    if (document.querySelector(".o_dcj").scrollTop !== 0 || document.documentElement.scrollTop !== 0) { throw new Error("deslizar el cajón no mueve la pantalla"); }
    tocar(herramienta("Programar"));
    await esperar(() => document.querySelector(".o_dcj_programar") && cajonCerrado(), "programar desde el cajón");
    if (!seVe(enviar)) { throw new Error("con programar abierto Enviar sigue a la vista"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")

    def test_escribir_varias_lineas_enviar_sugerir_y_devolver(self):
        self.datos_de_ejemplo()
        for numero, (ancho, alto) in enumerate(CELULARES, start=1):
            with self.subTest(celular=f'{ancho}x{alto}'):
                self.celular(ancho, alto, """
(async () => {
    const TOPE = __TOPE__;
    await abrirLaDe("Karen");
    const texto = document.querySelector("#o_dcj_texto"), enviar = document.querySelector(".o_dcj_enviar");
    const sugerir = herramienta("Sugerir");
    if (!enviar.disabled) { throw new Error("Enviar está desactivado con la caja vacía"); }
    const unaLinea = rect(texto).height;

    // 1. El texto crece con las líneas (hasta su tope) y Enviar sigue a la vista, pegado abajo.
    await escribir(texto, "Hola, Karen.\\nSí la tenemos en gris.\\nTe paso el precio.");
    await pausa(200);
    const tres = rect(texto).height;
    if (tres < unaLinea + 20) { throw new Error("con tres líneas el texto crece: " + unaLinea + " → " + tres); }
    await escribir(texto, Array.from({ length: 12 }, (_, i) => "Línea " + (i + 1) + " de Celular__NUMERO__").join("\\n"));
    await pausa(200);
    const r = rect(texto);
    if (r.height > 110) { throw new Error("el texto crece hasta un tope: " + r.height); }
    if (texto.scrollHeight <= texto.clientHeight) { throw new Error("pasado el tope, el texto se desplaza por dentro"); }
    for (const el of [mas(), sugerir, enviar]) {
        if (!seVe(el)) { throw new Error("con un texto largo siguen a la vista «+», Sugerir y Enviar"); }
        if (Math.abs(rect(el).bottom - r.bottom) > 2) { throw new Error("los botones van abajo, junto a la última línea"); }
    }
    cajaBaja("con un texto de doce líneas", window.innerHeight * 0.35);
    sinChicos("con un texto largo");
    sinDesborde("con un texto largo");

    // 2. Enviar.
    if (enviar.disabled) { throw new Error("Enviar se activa al escribir"); }
    enviar.click();
    await esperar(() => aqui(".o_dcj_burbuja_vendedora", "Línea 12 de Celular__NUMERO__"), "mi burbuja");
    await esperar(() => texto.value === "" && corto() === "Atiendes tú", "la caja vacía y «Atiendes tú»");
    await pausa(200);
    cajaBaja("después de enviar", TOPE);

    // 3. Sugerir, a la vista (sin abrir el «+»): deja el borrador en la caja, sin enviar.
    sugerir.click();
    await esperar(() => texto.value.includes("con gusto te ayudo"), "el borrador en la caja");
    sinDesborde("con el borrador");
    await escribir(texto, "");

    // 4. Devolver: pide la nota opcional y vuelve al asistente.
    const devolver = document.querySelector(".o_dcj_barra button");
    if (!devolver.textContent.includes("Devolver")) { throw new Error("el botón de la barra es «Devolver»: " + devolver.textContent); }
    devolver.click();
    const nota = await esperar(() => document.querySelector("#o_dcj_nota_bot"), "la nota para el asistente");
    sinChicos("con el formulario de devolver");
    sinDesborde("con el formulario de devolver");
    cajaBaja("con el formulario de devolver", window.innerHeight * 0.5);
    await escribir(nota, "ya quedó la visita del sábado");
    aqui(".o_dcj_devolver button", "Devolver al asistente").click();
    await esperar(() => corto() === "Asistente" && !document.querySelector(".o_dcj_devolver"), "devuelta al asistente");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", numero=numero)
                enviados = self.al_worker('/odoo/enviar')
                self.assertEqual(len(enviados), numero, 'Cada celular envió su mensaje, una vez')
                self.assertIn(f'Línea 12 de Celular{numero}', enviados[-1]['texto'])
                self.env.invalidate_all()
                self.assertEqual((self.karen.estado, self.karen.nota_para_el_bot), ('bot', 'ya quedó la visita del sábado'))


@tagged('post_install', '-at_install')
class TestCajaEnTabletaYComputadoraSigueIgual(PanelUiCase):
    """En tableta y computadora la caja no cambió: una franja y la línea con las herramientas como íconos y «Más»."""

    def test_la_caja_de_siempre(self):
        self.datos_de_ejemplo()
        for tamano in ('1366x768', '768x1024'):
            with self.subTest(pantalla=tamano):
                self.browser_size = tamano
                self.navegador(MEDIR + """
(async () => {
    await abrirConversacion("Karen");
    await pausa(300);
    const visible = (el) => !!el && getComputedStyle(el).display !== "none" && rect(el).width > 0 && rect(el).height > 0;
    const texto = document.querySelector("#o_dcj_texto"), enviar = document.querySelector(".o_dcj_enviar");
    // Nada de lo del celular: ni «+», ni «Programar» suelto, ni textos cortos.
    for (const selector of [".o_dcj_cajon_boton", ".o_dcj_herramienta_programar", ".o_dcj_cajon_ayuda", ".o_dcj_barra_corto", ".o_dcj_barra_punto"]) {
        if (document.querySelector(selector)) { throw new Error("esto es solo del celular: " + selector); }
    }
    // La línea de siempre: las cinco herramientas como íconos, «Más», el texto y «Enviar» con su palabra.
    const linea = ["Adjuntar", "Foto del catálogo", "Cotización", "Respuestas rápidas", "Sugerir", "Más acciones"].map((n) => {
        const b = herramienta(n);
        if (!visible(b)) { throw new Error("la herramienta «" + n + "» va a la vista"); }
        if (rect(b).width > 48 || rect(b).height > 48) { throw new Error("«" + n + "» es un ícono: " + rect(b).width + "x" + rect(b).height); }
        return b;
    });
    linea.push(texto, enviar);
    for (let i = 1; i < linea.length; i++) {
        if (rect(linea[i - 1]).right > rect(linea[i]).left + 1) { throw new Error("la línea de escribir no va en orden (" + i + ")"); }
        if (Math.abs(rect(linea[i]).bottom - rect(texto).bottom) > 4) { throw new Error("herramientas, texto y Enviar van en una sola línea (" + i + ")"); }
    }
    if (!visible(document.querySelector(".o_dcj_enviar_texto")) || rect(enviar).width < 80) { throw new Error("«Enviar» lleva su palabra"); }
    if (texto.placeholder !== "Escribe tu respuesta… (/ para rápidas)") { throw new Error("la pista de siempre: " + texto.placeholder); }
    // La franja de siempre: la frase entera, «Atender» como botón y «Nota interna» con sus dos palabras.
    const barra = document.querySelector(".o_dcj_barra");
    if (barra.querySelector(".o_dcj_barra_texto").textContent.trim() !== "Atiende el asistente. Si escribes, la atiendes tú y él se calla.") {
        throw new Error("la frase de la barra: " + barra.querySelector(".o_dcj_barra_texto").textContent);
    }
    if (getComputedStyle(barra).backgroundColor === "rgba(0, 0, 0, 0)") { throw new Error("la barra de quién atiende conserva su fondo"); }
    const nota = aqui(".o_dcj_modo button", "Nota interna");
    if (!nota || rect(nota).width < 90) { throw new Error("«Nota interna» se lee entero"); }
    if (rect(document.querySelector(".o_dcj_caja")).height > 100) { throw new Error("la caja vacía mide " + rect(document.querySelector(".o_dcj_caja")).height); }
    nota.click();
    await esperar(() => texto.placeholder === "Nota interna: el cliente no la ve (@ avisa)", "la pista de la nota de siempre");
    if (getComputedStyle(document.querySelector(".o_dcj_caja")).backgroundColor !== "rgb(255, 255, 255)") { throw new Error("aquí la caja de la nota sigue blanca (solo cambia el texto)"); }
    aqui(".o_dcj_modo button", "Respuesta").click();
    // «Programar» sigue en «Más»; y al tomarla, el botón dice «Devolver al asistente» entero.
    (await masAcciones("Programar")).click();
    await esperar(() => document.querySelector(".o_dcj_programar"), "programar desde «Más»");
    document.querySelector(".o_dcj_programar_quitar").click();
    barra.querySelector("button").click();
    const devolver = await esperar(() => aqui(".o_dcj_barra button", "Devolver al asistente"), "«Devolver al asistente»");
    if (rect(devolver).width < 120 || getComputedStyle(devolver).textDecorationLine.includes("underline")) { throw new Error("«Devolver al asistente» sigue siendo un botón con su frase entera"); }
    // (En tableta la ficha del cliente espera escondida a la derecha, fuera de la pantalla: se mira la página y la caja.)
    if (document.documentElement.scrollWidth > window.innerWidth + 1) { throw new Error("la página se sale de costado"); }
    const c = rect(document.querySelector(".o_dcj_caja"));
    if (c.left < 0 || c.right > window.innerWidth + 1 || rect(enviar).right > c.right) { throw new Error("la caja y Enviar caben en la pantalla"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")
                self.karen.with_user(self.vendedora).action_devolver_al_bot()   # la otra pantalla empieza igual
