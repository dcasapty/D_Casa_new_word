// Ayudas que corren DENTRO del navegador para las pruebas de la disposición compacta de «Conversaciones»
// (tests/test_panel_disposicion.py). Se inyectan una vez por página y quedan en window.__disp.
(() => {
    const pausa = (ms = 300) => new Promise((ok) => setTimeout(ok, ms));
    const esperar = async (fn, que, ms = 20000) => {
        const inicio = performance.now();
        while (performance.now() - inicio < ms) {
            const r = fn();
            if (r) {
                return r;
            }
            await pausa(100);
        }
        throw new Error("Disposición: no apareció " + que);
    };
    const aqui = (selector, texto) =>
        [...document.querySelectorAll(selector)].find((e) => !texto || e.textContent.includes(texto));
    const caja = (el) => {
        if (!el) {
            return null;
        }
        const b = el.getBoundingClientRect();
        return { x: b.left, y: b.top, w: b.width, h: b.height, b: b.bottom };
    };
    const visible = (selector) => {
        const el = document.querySelector(selector);
        if (!el) {
            return false;
        }
        const b = el.getBoundingClientRect();
        const cs = getComputedStyle(el);
        return cs.display !== "none" && cs.visibility !== "hidden" && b.width > 0 && b.height > 0;
    };
    const tecla = (el, key) => el.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));

    window.__disp = {
        pausa,
        esperar,
        aqui,
        tecla,

        /** Todo lo que se mide de la pantalla en un solo objeto. */
        medir() {
            const cuerpo = document.querySelector(".o_dcj_hilo_cuerpo");
            const raiz = document.querySelector(".o_dcj");
            const q = (s) => caja(document.querySelector(s));
            return {
                viewport: [innerWidth, innerHeight],
                raiz: caja(raiz),
                lista: q(".o_dcj_lista"),
                hilo: q(".o_dcj_hilo"),
                ficha: visible(".o_dcj_ficha") ? q(".o_dcj_ficha") : null,
                cabecera: q(".o_dcj_hilo_cabecera"),
                mensajes: caja(cuerpo),
                caja: q(".o_dcj_caja"),
                aviso: q(".o_dcj_aviso"),
                barra: q(".o_dcj_barra"),
                resumen: q(".o_dcj_resumen"),
                scroll: cuerpo ? { alto: cuerpo.scrollHeight, visible: cuerpo.clientHeight, arriba: cuerpo.scrollTop } : null,
                paginaDesplaza:
                    document.documentElement.scrollHeight > innerHeight + 1 ||
                    document.documentElement.scrollWidth > innerWidth + 1,
                desborde: raiz ? raiz.scrollWidth > raiz.clientWidth + 1 : null,
                fichaAbierta: document.querySelector(".o_dcj_boton_ficha")?.getAttribute("aria-expanded") === "true",
            };
        },

        /** Deja la ficha abierta o cerrada con el botón «Cliente». */
        async ponerFicha(abierta) {
            const boton = document.querySelector(".o_dcj_boton_ficha");
            if ((boton.getAttribute("aria-expanded") === "true") !== abierta) {
                boton.click();
            }
            await pausa(350);
            return true;
        },

        /** Botones, selectores y cajas con menos de 44 px (los enlaces de texto dentro de una frase no cuentan). */
        chicos() {
            const todos = document.querySelectorAll(".o_dcj button, .o_dcj select, .o_dcj input:not([type=file]), .o_dcj textarea");
            return [...todos]
                .filter((e) => !e.classList.contains("o_dcj_enlace") && !e.classList.contains("o_dcj_foto_boton"))
                .filter((e) => getComputedStyle(e).visibility !== "hidden")
                .map((e) => [e, e.getBoundingClientRect()])
                .filter(([, r]) => r.width > 0 && r.height > 0 && (r.width < 43.5 || r.height < 43.5))
                .map(([e, r]) => `${e.className} [${e.getAttribute("aria-label") || e.textContent.trim().slice(0, 20)}] ${Math.round(r.width)}x${Math.round(r.height)}`);
        },

        /** Escribe varias líneas en la caja, abre «Programar» desde el menú «Más» y deja el menú abierto. */
        async cajaConTodo(lineas, conMenuAbierto) {
            const texto = document.querySelector("#o_dcj_texto");
            texto.value = Array.from({ length: lineas }, (_, i) => `Línea ${i + 1}`).join("\n");
            texto.dispatchEvent(new Event("input", { bubbles: true }));
            document.querySelector(".o_dcj_mas_boton").click();
            await esperar(() => aqui(".o_dcj_menu_item", "Programar"), "Programar en el menú Más");
            aqui(".o_dcj_menu_item", "Programar").click();
            await esperar(() => document.querySelector(".o_dcj_programar"), "la fila de programar");
            if (conMenuAbierto) {
                document.querySelector(".o_dcj_mas_boton").click();
                await esperar(() => document.querySelector(".o_dcj_menu"), "el menú Más abierto");
            }
            await pausa(300);
            return true;
        },

        /** Abre «Devolver al asistente» (el formulario de la nota). */
        async abrirDevolver() {
            const atender = aqui(".o_dcj_barra button", "Atender");
            if (atender) {
                atender.click(); // la conversación estaba con el asistente: se toma para poder devolverla
            }
            const devolver = await esperar(() => aqui(".o_dcj_barra button", "Devolver"), "el botón Devolver");
            devolver.click();
            await esperar(() => document.querySelector(".o_dcj_devolver"), "el formulario de devolver");
            await pausa(200);
            return true;
        },

        /** Las herramientas de la caja: nombre accesible, tooltip, tamaño e ícono. */
        herramientas() {
            return [...document.querySelectorAll(".o_dcj_herramientas .o_dcj_herramienta")].map((b) => ({
                nombre: b.getAttribute("aria-label") || "",
                titulo: b.title,
                ancho: b.getBoundingClientRect().width,
                alto: b.getBoundingClientRect().height,
                icono: !!b.querySelector(".fa"),
            }));
        },

        /** El menú «Más» por dentro: abrir, foco, Esc, clic fuera. Devuelve lo que pasó. */
        async probarMenuMas() {
            const boton = document.querySelector(".o_dcj_mas_boton");
            const salida = { cerrado: boton.getAttribute("aria-expanded"), roles: boton.getAttribute("aria-haspopup") };
            boton.click();
            const menu = await esperar(() => document.querySelector(".o_dcj_menu"), "el menú Más");
            const c = menu.getBoundingClientRect();
            salida.abierto = boton.getAttribute("aria-expanded");
            salida.rol = menu.getAttribute("role");
            salida.opciones = [...menu.querySelectorAll("[role=menuitem]")].map((o) => o.textContent.trim());
            salida.dentro = c.left >= 0 && c.right <= innerWidth && c.top >= 0 && c.bottom <= innerHeight;
            salida.foco = document.activeElement.getAttribute("role");
            tecla(document.activeElement, "Escape");
            await pausa(150);
            salida.cerroConEsc = !document.querySelector(".o_dcj_menu");
            salida.focoAlCerrar = document.activeElement === boton;
            boton.click();
            await esperar(() => document.querySelector(".o_dcj_menu"), "el menú otra vez");
            document.querySelector(".o_dcj_hilo_cuerpo").dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
            await pausa(150);
            salida.cerroConClic = !document.querySelector(".o_dcj_menu");
            return salida;
        },

        /** Abre el menú «Más» y la fila de Programar (en celular), y dice si el menú cupo en la pantalla. */
        async menuYProgramar() {
            document.querySelector(".o_dcj_mas_boton").click();
            const menu = await esperar(() => document.querySelector(".o_dcj_menu"), "el menú Más");
            const c = menu.getBoundingClientRect();
            const dentro = c.left >= 0 && c.right <= innerWidth && c.top >= 0;
            aqui(".o_dcj_menu_item", "Programar").click();
            await esperar(() => document.querySelector(".o_dcj_programar"), "programar");
            await pausa(200);
            return { dentro };
        },

        /** Cada fila de la lista (reducida a las fotos): nombre accesible, tooltip y si esconde su texto. */
        filasDeLista() {
            return [...document.querySelectorAll(".o_dcj_fila")].map((f) => ({
                nombre: f.getAttribute("aria-label") || "",
                titulo: f.title,
                cuerpo: getComputedStyle(f.querySelector(".o_dcj_fila_cuerpo")).display,
            }));
        },

        async abrirLaDe(texto) {
            const fila = [...document.querySelectorAll(".o_dcj_fila")].find((f) => (f.getAttribute("aria-label") || f.textContent).includes(texto));
            fila.click();
            await esperar(() => document.querySelector(".o_dcj_hilo_cabecera h2")?.textContent.includes(texto), "el hilo de " + texto);
            return true;
        },

        alternarLista() {
            document.querySelector(".o_dcj_lista_toggle").click();
            return pausa(300);
        },

        /** Los hijos de la barra del hilo con tamaño: todos deben quedar en la misma fila (mismo «top»). */
        filasDeLaBarra() {
            return [...document.querySelectorAll(".o_dcj_hilo_cabecera > *")]
                .filter((e) => e.getBoundingClientRect().width > 0)
                .map((e) => Math.round(e.getBoundingClientRect().top));
        },

        alternarResumen() {
            document.querySelector(".o_dcj_resumen_titulo").click();
            return pausa(300);
        },

        /** Esc con el foco dentro de la ficha. */
        escDentroDeLaFicha() {
            document.querySelector(".o_dcj_volver_ficha").focus();
            tecla(document.activeElement, "Escape");
            return pausa(300);
        },

        focoEnElBotonCliente() {
            return document.activeElement === document.querySelector(".o_dcj_boton_ficha");
        },

        guardado() {
            return Object.entries(localStorage).filter(([k]) => k.startsWith("dcasa.conversaciones.ficha"));
        },

        /** La caja de texto: alto y si pasado el máximo se desplaza por dentro. */
        textoDeLaCaja() {
            const t = document.querySelector("#o_dcj_texto");
            return { alto: t.getBoundingClientRect().height, sigue: t.scrollHeight > t.clientHeight };
        },
    };
    return true;
})();
