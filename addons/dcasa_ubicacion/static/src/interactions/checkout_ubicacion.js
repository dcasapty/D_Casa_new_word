/**
 * Checkout: «¿Dónde te entregamos?» (views/checkout_templates.xml, docs/UBICACION.md).
 *
 * Usa el mismo mapa que la página del enlace del chat (static/src/lib/mapa_entrega.js, que va en el paquete del sitio):
 * pin fijo, «Usar mi ubicación», buscador de barriadas y lugares de la tienda. Cuando el punto cambia (y es bueno), el
 * servidor dice la zona, el precio del envío y si lo escrito nombra otro distrito (/tienda/ubicacion/zona); con «Sí,
 * aquí es» el punto queda confirmado en los campos ocultos que viajan con el formulario. Mover el mapa después lo
 * des-confirma; un «idle» sin movimiento (Satélite, el zoom con el botón) no.
 *
 * «Confirmar» (el botón de Odoo, abajo y fijo en el celular) cuenta como el «sí» si el punto es bueno y la zona salió
 * bien. NO cuenta (auditoría 2) y en su lugar baja hasta la tarjeta del punto:
 *   - con el aviso de cruce (escribió San Miguelito y el punto está en La Chorrera): «📍 Es aquí» / «🏠 Es otra casa».
 *     Solo ese «sí» manda ``dcasa_ubic_cruce_ok`` (y el servidor lo exige: controllers/checkout.py);
 *   - si el pin se movió más de 30 m después de un «Sí» o de un GPS bueno: «👆 Moviste el pin. ¿Es aquí?» (un dedo que
 *     solo quería bajar la página arrastraba el mapa y cambiaba la casa).
 * Si falta algo, no se envía: la página baja hasta el bloque, dice ahí qué falta y lleva el foco. Sin señal, la zona
 * dice «📶 Sin señal. Toca para reintentar»; «Confirmar» (y volver la conexión) la vuelve a pedir. Si «Confirmar»
 * solo esperaba la zona («⏳ Un momento»), sigue solo cuando llega. Sin permiso de
 * ubicación, lo que falta es buscar la barriada (o «Escribir») y el foco va al buscador. Si lo que falta es un campo
 * de Odoo (la barriada o calle, la ciudad: el mapa no las llena con un punto «Fuera de nuestra lista»), la página lo
 * trae al centro de la pantalla y el navegador dice ahí qué falta (no detrás de la barra fija de «Confirmar»).
 *
 * Tras el GPS o una búsqueda, la página se desplaza para que el pin y la tarjeta queden encima de la barra fija de
 * «Confirmar» (188 px en el celular: tapaba la mitad del mapa).
 *
 * Lo escrito manda: la calle y la ciudad solo se llenan si están vacías (o si las llenó el mapa antes, o si llegó con
 * «Sí» desde la tarjeta del chat: ``data-del-chat``), y lo que llenó el mapa no cuenta como «lo que escribió» para el
 * aviso de cruce. La calle se llama «Barriada o calle» en los dos modos (el número va en «Número de casa e
 * indicaciones»); «Departamento, suite» vacío se esconde; al «Escribir», el número de casa va después de la ciudad.
 */
import { CustomerAddress } from "@portal/interactions/address";
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";

const CASA = "dcasa_referencia";
const BOTON_DE_ODOO = '[name="website_sale_main_button"]';
const MOVIDO_M = 30; // más que esto desde el último «sí» (o GPS bueno) ya es otra casa
const SIN_SENAL = "📶 Sin señal. Toca para reintentar";
const ESPERA = "⏳ Un momento: estamos viendo tu zona";
const FALTA_MOTIVO = {
    lejos: "🔍 Acércate más en el mapa y pon el pin en tu puerta",
    buscado: "👆 Ahora mueve el mapa hasta tu puerta",
    impreciso: "👆 Mueve el mapa hasta tu puerta",
};

const tactil = () => !!window.DcasaMapaEntrega?.tactil();

function faltaImprecisoSinMapa() {
    return tactil()
        ? "📍 Tu ubicación no es exacta: toca «Mi ubicación» en tu puerta o busca tu barriada"
        : "📍 La computadora no da la ubicación exacta: busca tu barriada o usa tu celular";
}

/** ¿El elemento (o uno de sus padres) va fijo en la pantalla? Devuelve ese padre o ``null``. */
function fijo(el) {
    for (let e = el; e && e !== document.body; e = e.parentElement) {
        const posicion = getComputedStyle(e).position;
        if (posicion === "fixed" || posicion === "sticky") {
            return e;
        }
    }
    return null;
}

// El número de casa va siempre (el dueño, 2026-11-25, como en PedidosYa). Odoo, al cargar y al cambiar el país, le
// quita «required» a todo campo que no está en su lista (portal/interactions/address.js): aquí no se lo quita.
patch(CustomerAddress.prototype, {
    _markRequired(name, required) {
        return super._markRequired(name, name === CASA ? true : required);
    },
});

export class CheckoutUbicacion extends Interaction {
    // Solo el bloque del checkout: la tarjeta «Marcar mi casa» del pedido y de «¡Gracias por su compra!» lleva la misma
    // clase (para sus estilos) y sin el mapa esto fallaba («classList» de null) en esas páginas.
    static selector = "#div_dcasa_ubicacion";

    setup() {
        this.form = this.el.closest("form");
        this.ultimo = null;
        this.zonaValida = false;
        this.zonaError = false;
        this.zonaRed = false; // el error es de la red (o del tope de intentos): se puede reintentar
        this.hayCruce = false;
        this.cruceOk = false;
        this.textoPrevia = null;
        this.pedido = 0;
        this.reloj = null;
        this.relojBuscar = null;
        this.relojTexto = null;
        this.llenadoPorElMapa = new Set();
        this.etiquetaCalle = null;
        this.ancla = null; // el punto del último «sí», del GPS bueno o el que ya traía: el pin «se movió» desde aquí
        this.movido = false;
        this.sinPermiso = false;
        this.cargando = false;
        this.alinearTrasPrevia = false;
        this.alinearAlLlegar = false; // tocó «Mi ubicación» o eligió un lugar: al llegar el punto, a la vista
        this.reconfirmar = false;
        this.faltaEspera = false;
    }

    start() {
        const q = (s) => this.el.querySelector(s);
        this.tarjeta = q(".o_dcasa_ubic_tarjeta");
        this.zona = q(".o_dcasa_ubic_zona");
        this.zonaLinea = q(".o_dcasa_ubic_dato_zona");
        this.precio = q(".o_dcasa_ubic_precio");
        this.precioLinea = q(".o_dcasa_ubic_dato_precio");
        this.cruce = q(".o_dcasa_ubic_cruce");
        this.cruceBotones = q(".o_dcasa_ubic_cruce_botones");
        this.cruceSi = q(".o_dcasa_ubic_cruce_si");
        this.cruceNo = q(".o_dcasa_ubic_cruce_no");
        this.reintentar = q(".o_dcasa_ubic_reintentar");
        this.botonSi = q(".o_dcasa_ubic_si");
        this.botonGps = q(".o_dcasa_ubic_gps");
        this.ok = q(".o_dcasa_ubic_ok");
        this.aviso = q(".o_dcasa_ubic_aviso");
        this.referencia = q(`[name=${CASA}]`);
        this.casa = q(".o_dcasa_ubic_casa");
        this.lista = q(".o_dcasa_ubic_lista");
        this.buscar = q(".o_dcasa_ubic_buscar");
        this.faltaPunto = q(".o_dcasa_ubic_falta_punto");
        this.faltaTarjeta = q(".o_dcasa_ubic_falta_tarjeta");
        this.faltaCasa = q(".o_dcasa_ubic_falta_casa");
        this.oculto = (n) => this.el.querySelector(`[name=dcasa_ubic_${n}]`);
        // Donde vive el número de casa en el modo mapa (al «Escribir» se va después de la ciudad).
        this.lugarCasa = document.createComment("casa");
        this.casa.before(this.lugarCasa);
        // «Confirmar» de Odoo: se revisa ANTES que Odoo (fase de captura) para llenar el «sí» o frenar el envío.
        this.addListener(document, "click", (ev) => this.alEnviar(ev), { capture: true });
        this.addListener(this.referencia, "input", () => this.quitarFalta(this.faltaCasa));
        for (const radio of this.el.querySelectorAll("[name=dcasa_ubic_modo]")) {
            this.addListener(radio, "change", () => this.modo());
        }
        for (const nombre of ["street", "street2", "city"]) {
            const campo = this.form && this.form.querySelector(`[name=${nombre}]`);
            if (campo) this.addListener(campo, "input", () => this.alEscribir(nombre));
        }
        // «Departamento, suite, etc.» sobra: el número y las indicaciones van en el bloque. Solo si está vacío (si
        // tiene algo, se ve: no se esconde lo que el aviso de cruce podría nombrar).
        const depto = this.form?.querySelector("[name=street2]");
        if (depto && !depto.value.trim()) depto.closest("#div_street2")?.classList.add("d-none");
        if (this.el.dataset.delChat) {
            // Dijo «Sí» a la ubicación del chat: la calle y la ciudad que tenía se cambian por las del punto.
            this.llenadoPorElMapa.add("street");
            this.llenadoPorElMapa.add("city");
        }
        this.etiquetarCalle(true);
        this.modo();
        const Mapa = window.DcasaMapaEntrega;
        if (!Mapa) return;
        this.addListener(this.botonSi, "click", () => this.confirmar(true));
        this.addListener(this.botonGps, "click", () => {
            this.alinearAlLlegar = true;
        });
        this.addListener(this.cruceSi, "click", () => this.esAqui());
        this.addListener(this.cruceNo, "click", () => this.esOtraCasa());
        this.addListener(this.reintentar, "click", () => this.previa());
        this.addListener(window, "online", () => {
            if (this.zonaError && this.zonaRed) this.previa();
        });
        this.addListener(this.buscar, "input", () => this.alBuscar());
        this.mapa = Mapa.montar({
            mapa: q(".o_dcasa_ubic_mapa"),
            clave: this.el.dataset.clave || "",
            botonGps: this.botonGps,
            aviso: this.aviso,
            permiso: q(".o_dcasa_ubic_permiso"),
            alCambiar: (p) => this.cambio(p),
            alSinMapa: () => q(".o_dcasa_ubic_mapa_marco").classList.add("o_dcasa_sin_mapa"),
            alFallarGps: (codigo) => this.alFallarGps(codigo),
        });
        if (!this.el.dataset.clave) q(".o_dcasa_ubic_mapa_marco").classList.add("o_dcasa_sin_mapa");
        const lat = parseFloat(this.el.dataset.lat), lon = parseFloat(this.el.dataset.lon);
        if (Number.isFinite(lat) && Number.isFinite(lon)) {
            // El punto de la ficha (o el del chat: «whatsapp», «enlace») o el que dio en el chat de la tienda: solo
            // falta tocar «Sí, aquí es» (o «Confirmar»). Cuenta como un «sí» previo: moverlo lejos pide otro.
            const precision = parseInt(this.el.dataset.precision, 10);
            this.cargando = true;
            this.mapa.centrar(lat, lon, 18, this.el.dataset.origen || "pin", Number.isFinite(precision) ? precision : null);
            this.cargando = false;
            this.ancla = { lat: this.ultimo?.lat ?? lat, lon: this.ultimo?.lon ?? lon };
        }
    }

    destroy() {
        clearTimeout(this.reloj);
        clearTimeout(this.relojBuscar);
        clearTimeout(this.relojTexto);
        this.mapa?.destruir();
        this.etiquetarCalle(false);
        this.ponerCasa(true);
        this.lugarCasa?.remove();
    }

    enMapa() {
        return !!this.el.querySelector("#o_dcasa_modo_mapa")?.checked;
    }

    modo() {
        const enMapa = this.enMapa();
        this.el.querySelector(".o_dcasa_ubic_parte_mapa").classList.toggle("d-none", !enMapa);
        // El número de casa y las indicaciones van siempre (en el mapa o escrita).
        this.referencia.required = true;
        this.quitarFalta(this.faltaPunto);
        this.ponerCasa(enMapa);
    }

    /** Con el mapa, el número de casa va en el bloque (debajo de «¿Es aquí?»). Al «Escribir», después de la calle y la
     *  ciudad (auditoría 2: se pedía antes que la calle). Odoo reordena la ciudad y el código postal entre ellos: el
     *  número va antes de la línea que abre el país, así queda después de los dos. */
    ponerCasa(enMapa) {
        if (!this.casa || !this.lugarCasa?.parentNode) return;
        const fuera = !enMapa && this.form;
        const pais = fuera && this.form.querySelector("#div_country");
        if (fuera && pais) {
            const antes = pais.previousElementSibling?.classList.contains("w-100") ? pais.previousElementSibling : pais;
            antes.before(this.casa);
        } else {
            this.lugarCasa.after(this.casa);
        }
        for (const clase of ["col-lg-12", "mb-2", "o_dcasa_ubicacion", "o_dcasa_ubic_casa_fuera"]) {
            this.casa.classList.toggle(clase, !!(fuera && pais));
        }
    }

    /** La calle de Odoo («Calle y número») se llama «Barriada o calle» en los dos modos: el número de casa va en
     *  «Número de casa e indicaciones» y se pedía dos veces (auditorías 1 y 2). */
    etiquetarCalle(nuestra) {
        const campo = this.form?.querySelector("[name=street]");
        const etiqueta = campo?.id && this.form.querySelector(`label[for="${campo.id}"]`);
        if (!etiqueta) return;
        if (this.etiquetaCalle === null) this.etiquetaCalle = etiqueta.textContent.trim();
        etiqueta.textContent = nuestra ? "Barriada o calle" : this.etiquetaCalle;
    }

    confirmado() {
        return this.oculto("confirmada").value === "1";
    }

    cambio(p) {
        this.ultimo = p;
        if (p.lat !== null) {
            this.sinPermiso = false;
            if (p.origen === "busqueda") {
                // Buscó otra barriada: es otro lugar a propósito, no un arrastre.
                this.ancla = null;
                this.movido = false;
            } else if (p.origen === "gps" && p.bueno) {
                this.ancla = { lat: p.lat, lon: p.lon };
                this.movido = false;
            } else if (this.ancla) {
                this.movido = window.DcasaMapaEntrega.distanciaM(p, this.ancla) > MOVIDO_M;
            }
        }
        // El mismo punto ya confirmado (Satélite, el zoom con el botón): el «sí» sigue.
        if (this.confirmado() && p.bueno && Number(this.oculto("lat").value) === p.lat
                && Number(this.oculto("lon").value) === p.lon) {
            this.actualizar();
            return;
        }
        this.desconfirmar();
        this.zonaValida = false;
        this.zonaError = false;
        this.zonaRed = false;
        this.hayCruce = false;
        this.reconfirmar = false;
        this.pedido++; // lo que estaba en camino ya no vale
        clearTimeout(this.reloj);
        // Lo trajo el GPS o la búsqueda (no un arrastre): que el pin y la tarjeta queden a la vista.
        const delCodigo = this.alinearAlLlegar && (p.origen === "gps" || p.origen === "busqueda");
        if (delCodigo) this.alinearAlLlegar = false;
        if (p.bueno) {
            this.quitarFalta(this.faltaPunto);
            this.reloj = setTimeout(() => this.previa(), 500);
            if (delCodigo && !this.cargando) this.alinearTrasPrevia = true;
        } else {
            // Sin un punto bueno no hay zona ni precio que mostrar (auditoría 1): el aviso del mapa dice qué hacer.
            this.tarjeta.classList.add("d-none");
            // GPS impreciso o una barriada buscada, con el mapa: que se vea el pin para moverlo.
            if (delCodigo && !this.cargando && p.lat !== null) this.alinear();
        }
        this.actualizar();
    }

    /** Quita el «sí» (el punto, la zona o lo escrito cambiaron). */
    desconfirmar() {
        this.oculto("confirmada").value = "";
        this.oculto("cruce_ok").value = "";
        this.cruceOk = false;
        this.ok.classList.add("d-none");
        this.quitarFalta(this.faltaTarjeta);
        this.mostrarBotones();
    }

    /** Con el aviso de cruce, «📍 Es aquí» / «🏠 Es otra casa» en lugar de «Sí, aquí es». */
    mostrarBotones() {
        const listo = this.confirmado();
        this.botonSi.classList.toggle("d-none", listo || this.hayCruce);
        this.cruceBotones.classList.toggle("d-none", listo || !this.hayCruce);
    }

    actualizar() {
        const puede = !!(this.ultimo && this.ultimo.bueno && this.zonaValida);
        this.botonSi.disabled = !puede;
        this.cruceSi.disabled = !puede;
    }

    /** Lo que escribió el cliente (no lo que llenó el mapa: eso daba un aviso de cruce falso, auditoría 1). */
    textoEscrito() {
        const valor = (n) =>
            this.llenadoPorElMapa.has(n) ? "" : (this.form?.querySelector(`[name=${n}]`)?.value || "").trim();
        return ["street", "street2", "city"].map(valor).filter(Boolean).join(", ");
    }

    /** Escribió en la calle o la ciudad: si cambia lo que se compara con el punto, se vuelve a ver el cruce. */
    alEscribir(nombre) {
        this.llenadoPorElMapa.delete(nombre);
        clearTimeout(this.relojTexto);
        this.relojTexto = setTimeout(() => {
            if (this.ultimo?.bueno && this.zonaValida && this.textoEscrito() !== this.textoPrevia) {
                this.reconfirmar = this.confirmado();
                this.desconfirmar();
                this.previa();
            }
        }, 700);
    }

    async previa() {
        if (!this.ultimo || !this.ultimo.bueno) return;
        clearTimeout(this.reloj);
        const n = ++this.pedido;
        const texto = this.textoEscrito();
        this.textoPrevia = texto;
        this.zonaValida = false;
        this.zonaError = false;
        this.zonaRed = false;
        this.tarjeta.classList.remove("d-none");
        this.zonaLinea.classList.remove("d-none");
        this.precioLinea.classList.remove("d-none");
        this.reintentar.classList.add("d-none");
        this.zona.textContent = "…";
        this.precio.textContent = "";
        this.actualizar();
        let r;
        try {
            r = await this.waitFor(rpc("/tienda/ubicacion/zona", {
                lat: this.ultimo.lat, lon: this.ultimo.lon, texto, con_mapa: !!this.mapa?.conMapa(),
            }));
        } catch {
            // Sin señal (o el servidor no contestó): no es que el punto no sirva (auditoría 2).
            r = { error: SIN_SENAL, red: true };
        }
        if (n !== this.pedido) return;
        if (r.error) {
            this.zonaError = true;
            this.zonaRed = !!r.red || r.motivo === "tope";
            this.reconfirmar = false;
            if (this.zonaRed) {
                this.zonaLinea.classList.add("d-none");
                this.precioLinea.classList.add("d-none");
                this.textoRed = r.red ? SIN_SENAL : `⏳ ${r.error} Toca para reintentar`;
                this.reintentar.querySelector("span").textContent = this.textoRed;
                this.reintentar.classList.remove("d-none");
            } else {
                this.zona.textContent = r.error;
                this.precioLinea.classList.add("d-none");
            }
            if (this.faltaEspera) {
                // «Confirmar» esperaba la zona: ahora dice qué pasó (sin volver a pedirla sola: sin señal, sería un ciclo).
                this.faltaPunto.textContent = this.zonaRed ? this.textoRed : `📍 ${r.error}`;
                this.faltaEspera = false;
            }
            this.actualizar();
            if (this.alinearTrasPrevia) {
                // Que vea «📶 Sin señal. Toca para reintentar» (o por qué no sirve), no la barra de abajo.
                this.alinearTrasPrevia = false;
                this.alinear();
            }
            return;
        }
        this.zonaValida = true;
        // De un vistazo: la barriada (o el corregimiento) y el distrito; el precio, grande, con el camión al lado.
        this.zona.textContent = [r.barriada || r.corregimiento, r.distrito].filter(Boolean).join(", ")
            || "Fuera de nuestra lista";
        this.precio.textContent = r.precio ? `Envío ${r.precio}` : "Envío: te lo confirmamos";
        this.hayCruce = !!r.aviso;
        this.cruce.textContent = r.aviso || "";
        this.llenarSiVacio("city", r.distrito || "");
        this.llenarSiVacio("street", [r.barriada, r.corregimiento].filter(Boolean).join(", "));
        this.mostrarBotones();
        this.actualizar();
        const esperaba = this.faltaEspera;
        if (esperaba) {
            this.faltaEspera = false;
            this.quitarFalta(this.faltaPunto);
        }
        if (this.reconfirmar && !this.hayCruce) {
            // Escribió la calle después del «sí» y no hay cruce: el «sí» sigue.
            this.confirmar(false);
        }
        this.reconfirmar = false;
        if (this.alinearTrasPrevia) {
            this.alinearTrasPrevia = false;
            this.alinear();
        }
        if (esperaba) this.seguirTrasLaEspera();
    }

    /** «Confirmar» esperaba la zona y ya llegó: si no falta nada, sigue solo (antes había que tocarlo otra vez y
     *  parecía que no hacía nada: staging, 2026-11-26); si falta otra cosa, la dice. */
    seguirTrasLaEspera() {
        const boton = this.botonQueEspera;
        this.botonQueEspera = null;
        if (!boton?.isConnected || !this.el.isConnected) return;
        const falta = this.loQueFalta();
        if (falta) {
            this.mostrarFalta(falta);
        } else {
            boton.click();
        }
    }

    llenarSiVacio(nombre, valor) {
        const campo = this.form?.querySelector(`[name=${nombre}]`);
        if (!campo || !valor) return;
        if (campo.value.trim() && !this.llenadoPorElMapa.has(nombre)) return;
        campo.value = valor;
        this.llenadoPorElMapa.add(nombre);
        // Lo que compara el aviso de cruce no cambia: lo del mapa no cuenta como escrito.
    }

    confirmar(conFoco) {
        if (this.botonSi.disabled || !this.ultimo) return;
        this.oculto("lat").value = this.ultimo.lat;
        this.oculto("lon").value = this.ultimo.lon;
        this.oculto("origen").value = this.ultimo.origen || "pin";
        this.oculto("precision").value = this.ultimo.precision ?? "";
        this.oculto("cruce_ok").value = this.cruceOk ? "1" : "";
        this.oculto("confirmada").value = "1";
        this.ancla = { lat: this.ultimo.lat, lon: this.ultimo.lon };
        this.movido = false;
        this.ok.classList.remove("d-none");
        this.mostrarBotones();
        this.quitarFalta(this.faltaPunto);
        this.quitarFalta(this.faltaTarjeta);
        if (conFoco && !this.referencia.value.trim()) this.referencia.focus();
    }

    /** «📍 Es aquí»: el punto es el bueno aunque lo escrito nombre otro distrito. */
    esAqui() {
        if (this.cruceSi.disabled) return;
        this.cruceOk = true;
        this.confirmar(true);
    }

    /** «🏠 Es otra casa» (un regalo: la dirección de la mamá): a buscar esa barriada, o a «Escribir». */
    esOtraCasa() {
        this.desconfirmar();
        this.aviso.textContent = "🔍 Busca la barriada de esa casa 👇 (o toca «Escribir»)";
        this.buscar.scrollIntoView({ block: "center", behavior: "smooth" });
        this.buscar.focus({ preventScroll: true });
    }

    alFallarGps(codigo) {
        this.sinPermiso = codigo === 1 && !(this.ultimo && this.ultimo.lat !== null);
        if (this.faltaPunto.textContent) this.quitarFalta(this.faltaPunto);
    }

    /** Lo que falta del punto (con el mapa), o ``null`` si ya puede contar como el «sí». */
    loQueFaltaDelPunto() {
        const p = this.ultimo;
        if (!p || p.lat === null) {
            if (this.sinPermiso) {
                return { donde: this.faltaPunto, texto: "🔍 Busca tu barriada (o toca «Escribir»)", foco: this.buscar };
            }
            return { donde: this.faltaPunto, texto: "📍 Toca «Mi ubicación» o busca tu barriada", foco: this.botonGps };
        }
        if (!p.bueno) {
            if (p.motivo === "impreciso_sin_mapa") {
                return { donde: this.faltaPunto, texto: faltaImprecisoSinMapa(),
                         foco: tactil() ? this.botonGps : this.buscar };
            }
            return { donde: this.faltaPunto, texto: FALTA_MOTIVO[p.motivo] || "📍 Falta tu ubicación",
                     foco: this.faltaPunto };
        }
        if (this.zonaError && this.zonaRed) {
            // La señal volvió (o no): se vuelve a pedir la zona en vez de repetir el error (auditoría 2).
            this.previa();
            return { donde: this.faltaPunto, texto: ESPERA, foco: this.faltaPunto, espera: true };
        }
        if (this.zonaError) return { donde: this.faltaPunto, texto: `📍 ${this.zona.textContent}`, foco: this.faltaPunto };
        if (!this.zonaValida || this.textoEscrito() !== this.textoPrevia) {
            // Todavía no está la zona, o escribió la calle o la ciudad recién: se compara otra vez con el punto.
            if (this.zonaValida) this.previa();
            return { donde: this.faltaPunto, texto: ESPERA, foco: this.faltaPunto, espera: true };
        }
        if (this.hayCruce && !this.cruceOk) {
            return { donde: null, texto: "", foco: this.cruceSi, destino: this.tarjeta };
        }
        if (this.movido) {
            return { donde: this.faltaTarjeta, texto: "👆 Moviste el pin. ¿Es aquí?", foco: this.botonSi,
                     destino: this.tarjeta };
        }
        return null;
    }

    /** ¿Qué le falta para poder seguir? ``null`` si nada (y, con el mapa, el «sí» ya quedó en los campos ocultos). */
    loQueFalta() {
        if (this.enMapa() && !this.confirmado()) {
            const falta = this.loQueFaltaDelPunto();
            if (falta) return falta;
            this.confirmar(false); // «Confirmar» cuenta como «Sí, aquí es»
        }
        if (!this.referencia.value.trim()) {
            return { donde: this.faltaCasa, texto: "🏠 Escribe tu número de casa", foco: this.referencia };
        }
        const campo = this.campoVacio();
        return campo ? { campo } : null;
    }

    /** El primer campo de Odoo que el navegador no deja pasar (la barriada o calle, la ciudad, el nombre…), o ``null``.
     *  Con un punto «Fuera de nuestra lista» (o sin la tabla de lugares) el mapa no llena la calle ni la ciudad, y el
     *  aviso del navegador salía encima de la barra fija de «Confirmar»: el cliente no veía qué le faltaba (staging,
     *  2026-11-26). Ahora la página lo trae al centro de la pantalla antes de que el navegador lo diga. */
    campoVacio() {
        if (!this.form) return null;
        for (const campo of this.form.querySelectorAll("input, select, textarea")) {
            if (campo.type === "hidden" || campo.disabled || !campo.willValidate) continue;
            if (!(campo.offsetParent || campo.getClientRects().length)) continue;
            if (!campo.checkValidity()) return campo;
        }
        return null;
    }

    alEnviar(ev) {
        const boton = ev.target?.closest?.(BOTON_DE_ODOO);
        if (!boton || !this.el.isConnected) return;
        const falta = this.loQueFalta();
        if (!falta) return; // todo bien: sigue Odoo (valida lo suyo y manda el formulario)
        ev.preventDefault();
        ev.stopPropagation();
        // Si solo espera la zona, sigue solo cuando llegue (``seguirTrasLaEspera``).
        this.botonQueEspera = falta.espera ? boton : null;
        this.mostrarFalta(falta);
    }

    mostrarFalta({ donde, texto, foco, destino, espera, campo }) {
        this.quitarFalta(this.faltaPunto);
        this.quitarFalta(this.faltaCasa);
        this.quitarFalta(this.faltaTarjeta);
        this.faltaEspera = !!espera;
        if (campo) {
            // Al centro (lejos de la barra fija de abajo) y con el aviso del navegador junto al campo.
            campo.scrollIntoView({ block: "center", behavior: "instant" });
            campo.focus({ preventScroll: true });
            campo.reportValidity();
            return;
        }
        if (donde) {
            donde.textContent = texto;
            donde.classList.remove("d-none");
        }
        if (foco === this.referencia) this.referencia.classList.add("is-invalid");
        if (destino === this.tarjeta) {
            this.alinear(foco);
        } else if (foco === this.buscar) {
            this.buscar.scrollIntoView({ block: "center", behavior: "smooth" });
        } else if (donde) {
            const casa = donde === this.faltaCasa;
            (casa ? this.referencia : this.el).scrollIntoView({ block: casa ? "center" : "start", behavior: "smooth" });
        }
        foco?.focus({ preventScroll: true });
    }

    quitarFalta(donde) {
        if (!donde) return;
        donde.textContent = "";
        donde.classList.add("d-none");
        if (donde === this.faltaCasa) this.referencia.classList.remove("is-invalid");
        if (donde === this.faltaPunto) this.faltaEspera = false;
    }

    /** Lo más alto de la barra fija de abajo (la de «Confirmar» en el celular) o el borde de la pantalla. */
    techoDeLaBarra() {
        let techo = window.innerHeight;
        for (const boton of document.querySelectorAll(BOTON_DE_ODOO)) {
            const barra = fijo(boton);
            const r = barra?.getBoundingClientRect();
            if (r && r.height && r.top > window.innerHeight / 3) techo = Math.min(techo, r.top);
        }
        return techo;
    }

    /** Lo más bajo de la cabecera si va fija arriba (o 0). */
    pisoDeLaCabecera() {
        const cabecera = document.querySelector("header#top");
        const r = cabecera && fijo(cabecera) && cabecera.getBoundingClientRect();
        return r && r.bottom > 0 && r.top < window.innerHeight / 3 ? r.bottom : 0;
    }

    /** Que el pin (el centro del mapa) y la tarjeta del punto queden a la vista, encima de la barra fija. Con
     *  ``boton`` («📍 Es aquí», «Sí, aquí es»), del pin (o la tarjeta) a ese botón. Si no cabe todo (320 × 640:
     *  la barra se lleva 188 px), manda el botón, o el pin. */
    alinear(boton = null) {
        const marco = this.el.querySelector(".o_dcasa_ubic_mapa_marco");
        const conMapa = this.enMapa() && marco && !marco.classList.contains("o_dcasa_sin_mapa") && marco.offsetHeight;
        const rm = conMapa ? marco.getBoundingClientRect() : null;
        const rt = this.tarjeta.classList.contains("d-none") ? null : this.tarjeta.getBoundingClientRect();
        if (!rm && !rt) return;
        // El pin mide 54 px y su punta está en el centro del mapa.
        const arriba = rm ? rm.top + rm.height / 2 - 64 : rt.top;
        const abajo = boton ? boton.getBoundingClientRect().bottom : rt ? rt.bottom : rm.top + rm.height / 2 + 32;
        const minimo = abajo - (this.techoDeLaBarra() - 8); // lo menos que hay que bajar: lo de abajo, sobre la barra
        const maximo = arriba - (this.pisoDeLaCabecera() + 8); // lo más: lo de arriba, bajo la cabecera
        const delta = minimo <= maximo ? Math.min(Math.max(0, minimo), maximo) : boton ? minimo : maximo;
        if (Math.abs(delta) < 4) return;
        window.scrollBy({ top: delta, behavior: "smooth" });
    }

    alBuscar() {
        clearTimeout(this.relojBuscar);
        const texto = this.buscar.value.trim();
        if (texto.length < 2) {
            this.lista.textContent = "";
            return;
        }
        this.relojBuscar = setTimeout(async () => {
            let r;
            try {
                r = await this.waitFor(rpc("/tienda/ubicacion/buscar", { texto }));
            } catch {
                r = { lugares: [], red: true };
            }
            this.lista.textContent = "";
            const lugares = r.lugares || [];
            if (!lugares.length) {
                const li = document.createElement("li");
                li.className = "text-muted";
                li.textContent = r.red || r.error ? "📶 Sin señal. Prueba otra vez." : "No lo encontramos. Prueba otro nombre.";
                this.lista.appendChild(li);
                return;
            }
            for (const lugar of lugares) {
                const li = document.createElement("li");
                const b = document.createElement("button");
                const s = document.createElement("small");
                b.type = "button";
                b.className = "o_dcasa_ubic_opcion";
                b.textContent = lugar.nombre;
                s.textContent = lugar.zona;
                b.appendChild(s);
                this.addListener(b, "click", () => {
                    this.alinearAlLlegar = true;
                    this.mapa.centrar(lugar.lat, lugar.lon, 17, "busqueda");
                    this.lista.textContent = "";
                    this.buscar.value = lugar.nombre;
                });
                li.appendChild(b);
                this.lista.appendChild(li);
            }
        }, 400);
    }
}

registry.category("public.interactions").add("dcasa_ubicacion.checkout", CheckoutUbicacion);
