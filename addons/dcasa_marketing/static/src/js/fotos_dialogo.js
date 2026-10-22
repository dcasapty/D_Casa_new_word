/**
 * Las fotos de un producto en grande (pedido de la dueña, 2026-10-22): «al hacer clic en la foto debería poderse ver,
 * editar, recortar o reemplazar con mucha facilidad» y «agregar las fotos es muy poco intuitivo y limitado».
 *
 * Una ventana casi a pantalla completa con tres modos:
 *  - «Ver» (visor): la foto grande, zoom (pellizcar en el celular, la rueda o los botones en la computadora; doble toque
 *    acerca o aleja), pasar entre fotos (flechas, deslizar o las teclas ← →) y las acciones: Reemplazar (archivo o
 *    cámara), Recortar, Girar, Principal, Quitar y Descargar.
 *  - «Todas» (galería): todas en cuadrícula grande; subir varias (elegir varias o arrastrar y soltar), ordenar
 *    arrastrando (en el celular, dejando el dedo un momento) o con las flechas, elegir la principal y quitar.
 *  - «Recortar»: el recortador que ya trae Odoo (Cropper.js del editor), libre o en proporciones fijas.
 *
 * Nada se decide aquí: el servidor (product.template.dcasa_fotos_*) comprueba quién puede cambiar las fotos, gira y
 * recorta sobre la foto guardada más grande (sin re-codificar en el navegador) y devuelve la fila de fotos al día.
 * Quien no puede editar el producto solo ve y descarga.
 */
import { Component, onWillStart, onWillUnmount, useEffect, useExternalListener, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { isMobileOS } from "@web/core/browser/feature_detection";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { useSortable } from "@web/core/utils/sortable_owl";

const MAX_MB = 25;
const ESCALA_MAXIMA = 5;
const PROPORCIONES = [
    { clave: "libre", nombre: "Libre", valor: NaN },
    { clave: "cuadrada", nombre: "Cuadrada", valor: 1 },
    { clave: "horizontal", nombre: "Horizontal 4:3", valor: 4 / 3 },
    { clave: "vertical", nombre: "Vertical 3:4", valor: 3 / 4 },
];

/** El contenido de un archivo en base64 (sin el «data:…;base64,» de adelante). */
export function leerArchivo(archivo) {
    return new Promise((ok, mal) => {
        const lector = new FileReader();
        lector.onload = () => ok(String(lector.result).split(",")[1] || "");
        lector.onerror = () => mal(lector.error);
        lector.readAsDataURL(archivo);
    });
}

/** Por qué no se puede subir este archivo, o null si sí. */
export function problemaDelArchivo(archivo) {
    const nombre = (archivo.name || "").toLowerCase();
    if (/\.(heic|heif)$/.test(nombre)) {
        return `«${archivo.name}» es una foto del iPhone en formato HEIC: compártela como JPG (o súbela desde el celular, que la convierte sola).`;
    }
    if (!(archivo.type || "").startsWith("image/") && !/\.(jpe?g|png|webp|gif)$/.test(nombre)) {
        return `«${archivo.name}» no es una foto. Elige un JPG, PNG o WebP.`;
    }
    if (archivo.size > MAX_MB * 1024 * 1024) {
        return `«${archivo.name}» pesa más de ${MAX_MB} MB. Elige una más liviana.`;
    }
    return null;
}

function mensajeDeError(error) {
    return (error && error.data && error.data.message) || (error && error.message) || "No se pudo. Intenta otra vez.";
}

export class DcasaFotos extends Component {
    static template = "dcasa_marketing.Fotos";
    static components = { Dialog };
    static props = {
        close: Function,
        plantillaId: Number,
        modo: { type: String, optional: true },
        indice: { type: Number, optional: true },
        registro: { type: Object, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.esCelular = isMobileOS();
        this.proporciones = PROPORCIONES;
        this.state = useState({
            cargando: true,
            datos: { producto: {}, puede_editar: false, fotos: [] },
            indice: this.props.indice || 0,
            modo: this.props.modo === "galeria" ? "galeria" : "visor",
            ocupado: false,
            subiendo: null, // { hechas, total }
            mensaje: null, // { tipo: "ok" | "error", texto }
            zoom: { escala: 1, x: 0, y: 0 },
            proporcion: "libre",
            soltando: false, // se arrastran archivos encima
        });
        this.escenario = useRef("escenario");
        this.imagenRecorte = useRef("imagenRecorte");
        this.cuadricula = useRef("cuadricula");
        this.archivos = useRef("archivos");
        this.camara = useRef("camara");
        this.reemplazo = useRef("reemplazo");
        this.reemplazoCamara = useRef("reemplazoCamara");
        this.punteros = new Map();
        this.gesto = null;
        this.ultimoToque = 0;
        this.cropper = null;

        onWillStart(() => this.cargar());
        onWillUnmount(() => this.soltarRecortador());
        useExternalListener(window, "keydown", (ev) => this.alTeclear(ev));
        useEffect(
            () => {
                if (this.state.modo === "recorte") {
                    this.armarRecortador();
                }
            },
            () => [this.state.modo]
        );
        useSortable({
            ref: this.cuadricula,
            elements: ".o_dcasa_fotos_tarjeta",
            ignore: ".o_dcasa_fotos_tarjeta_botones, button, a, input",
            enable: () => this.state.datos.puede_editar && !this.state.ocupado && this.state.modo === "galeria",
            touchDelay: 250,
            cursor: "grabbing",
            onDrop: (params) => this.alSoltarEnCuadricula(params),
        });
    }

    // --- Datos --------------------------------------------------------------------------------------------------
    get fotos() {
        return this.state.datos.fotos;
    }

    get foto() {
        return this.fotos[this.state.indice] || null;
    }

    get puedeEditar() {
        return this.state.datos.puede_editar;
    }

    get titulo() {
        const p = this.state.datos.producto || {};
        return p.nombre || "Fotos del producto";
    }

    async cargar() {
        try {
            this.ponerDatos(await this.orm.call("product.template", "dcasa_fotos", [[this.props.plantillaId]]));
        } catch (error) {
            this.state.mensaje = { tipo: "error", texto: mensajeDeError(error) };
        } finally {
            this.state.cargando = false;
        }
    }

    ponerDatos(datos) {
        this.state.datos = datos;
        if (this.state.indice >= datos.fotos.length) {
            this.state.indice = Math.max(0, datos.fotos.length - 1);
        }
        if (!datos.fotos.length && this.state.modo !== "galeria") {
            this.state.modo = "galeria";
        }
    }

    /** Llama al servidor, pone las fotos al día y anota que algo cambió (al cerrar se recarga la ficha). */
    async cambiar(metodo, args, ok) {
        if (this.state.ocupado) {
            return false;
        }
        this.state.ocupado = true;
        this.state.mensaje = null;
        try {
            const datos = await this.orm.call("product.template", metodo, [[this.props.plantillaId], ...args]);
            this.ponerDatos(datos);
            if (this.props.registro) {
                this.props.registro.cambios = true;
            }
            if (ok) {
                this.state.mensaje = { tipo: "ok", texto: ok };
            }
            return true;
        } catch (error) {
            this.state.mensaje = { tipo: "error", texto: mensajeDeError(error) };
            return false;
        } finally {
            this.state.ocupado = false;
        }
    }

    // --- Navegación ---------------------------------------------------------------------------------------------
    irA(indice) {
        if (!this.fotos.length) {
            return;
        }
        this.state.indice = (indice + this.fotos.length) % this.fotos.length;
        this.reiniciarZoom();
    }

    anterior() {
        this.irA(this.state.indice - 1);
    }

    siguiente() {
        this.irA(this.state.indice + 1);
    }

    ver(indice) {
        this.state.modo = "visor";
        this.irA(indice);
    }

    verTodas() {
        this.soltarRecortador();
        this.state.modo = "galeria";
    }

    alTeclear(ev) {
        // Solo si esta ventana es la de arriba (no con «¿Quitar la foto?» abierta encima) y no se escribe en un cuadro.
        const activa = document.querySelector(".o_dialog:not(.o_inactive_modal) .o_dcasa_fotos");
        if (this.state.modo !== "visor" || !activa || ev.target.closest?.("input, textarea")) {
            return;
        }
        if (ev.key === "ArrowLeft") {
            this.anterior();
            ev.preventDefault();
        } else if (ev.key === "ArrowRight") {
            this.siguiente();
            ev.preventDefault();
        } else if (ev.key === "+" || ev.key === "=") {
            this.acercar();
        } else if (ev.key === "-") {
            this.alejar();
        }
    }

    // --- Zoom: pellizcar, rueda, doble toque y botones -----------------------------------------------------------
    get estiloImagen() {
        const z = this.state.zoom;
        return `transform: translate(${z.x}px, ${z.y}px) scale(${z.escala});`;
    }

    reiniciarZoom() {
        Object.assign(this.state.zoom, { escala: 1, x: 0, y: 0 });
    }

    ponerEscala(escala) {
        const z = this.state.zoom;
        z.escala = Math.min(ESCALA_MAXIMA, Math.max(1, escala));
        if (z.escala === 1) {
            z.x = 0;
            z.y = 0;
        } else {
            this.limitarDesplazamiento();
        }
    }

    acercar() {
        this.ponerEscala(this.state.zoom.escala * 1.5);
    }

    alejar() {
        this.ponerEscala(this.state.zoom.escala / 1.5);
    }

    limitarDesplazamiento() {
        const z = this.state.zoom;
        const caja = this.escenario.el?.getBoundingClientRect();
        if (!caja) {
            return;
        }
        const maxX = ((z.escala - 1) * caja.width) / 2;
        const maxY = ((z.escala - 1) * caja.height) / 2;
        z.x = Math.min(maxX, Math.max(-maxX, z.x));
        z.y = Math.min(maxY, Math.max(-maxY, z.y));
    }

    distancia() {
        const [a, b] = [...this.punteros.values()];
        return Math.hypot(a.x - b.x, a.y - b.y) || 1;
    }

    alBajarPuntero(ev) {
        this.punteros.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
        try {
            ev.currentTarget.setPointerCapture(ev.pointerId);
        } catch {
            // Sin captura (un puntero que ya se fue): se sigue igual.
        }
        if (this.punteros.size === 2) {
            this.gesto = { tipo: "pellizco", distancia: this.distancia(), escala: this.state.zoom.escala };
        } else if (this.punteros.size === 1) {
            this.gesto = {
                tipo: "arrastre", x: ev.clientX, y: ev.clientY,
                zx: this.state.zoom.x, zy: this.state.zoom.y, inicio: Date.now(),
            };
        }
    }

    alMoverPuntero(ev) {
        if (!this.punteros.has(ev.pointerId) || !this.gesto) {
            return;
        }
        this.punteros.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
        if (this.gesto.tipo === "pellizco" && this.punteros.size === 2) {
            this.ponerEscala(this.gesto.escala * (this.distancia() / this.gesto.distancia));
        } else if (this.gesto.tipo === "arrastre" && this.state.zoom.escala > 1) {
            this.state.zoom.x = this.gesto.zx + (ev.clientX - this.gesto.x);
            this.state.zoom.y = this.gesto.zy + (ev.clientY - this.gesto.y);
            this.limitarDesplazamiento();
        }
    }

    alSubirPuntero(ev) {
        const gesto = this.gesto;
        this.punteros.delete(ev.pointerId);
        if (this.punteros.size) {
            // Se levantó un dedo del pellizco: el otro sigue arrastrando desde donde está.
            const [otro] = [...this.punteros.values()];
            this.gesto = { tipo: "arrastre", x: otro.x, y: otro.y, zx: this.state.zoom.x, zy: this.state.zoom.y, inicio: 0 };
            return;
        }
        this.gesto = null;
        if (!gesto || gesto.tipo !== "arrastre" || !gesto.inicio) {
            return;
        }
        const dx = ev.clientX - gesto.x;
        const dy = ev.clientY - gesto.y;
        if (this.state.zoom.escala === 1 && Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) {
            // Deslizar: la foto de al lado.
            if (dx < 0) {
                this.siguiente();
            } else {
                this.anterior();
            }
            return;
        }
        if (Math.abs(dx) < 10 && Math.abs(dy) < 10 && ev.pointerType !== "mouse") {
            const ahora = Date.now();
            if (ahora - this.ultimoToque < 320) {
                this.alternarZoom();
                this.ultimoToque = 0;
            } else {
                this.ultimoToque = ahora;
            }
        }
    }

    alternarZoom() {
        this.ponerEscala(this.state.zoom.escala > 1 ? 1 : 2.5);
    }

    alRueda(ev) {
        ev.preventDefault();
        this.ponerEscala(this.state.zoom.escala * (ev.deltaY < 0 ? 1.2 : 1 / 1.2));
    }

    // --- Acciones sobre la foto que se ve -----------------------------------------------------------------------
    elegirReemplazo(conCamara = false) {
        const entrada = conCamara ? this.reemplazoCamara.el : this.reemplazo.el;
        if (entrada) {
            entrada.value = "";
            entrada.click();
        }
    }

    async alElegirReemplazo(ev) {
        const archivo = ev.target.files && ev.target.files[0];
        if (!archivo || !this.foto) {
            return;
        }
        const problema = problemaDelArchivo(archivo);
        if (problema) {
            this.state.mensaje = { tipo: "error", texto: problema };
            return;
        }
        const clave = this.foto.clave;
        await this.cambiar("dcasa_fotos_reemplazar", [clave, await leerArchivo(archivo)], "Listo: la foto quedó reemplazada.");
        this.reiniciarZoom();
    }

    async girar() {
        if (this.foto) {
            await this.cambiar("dcasa_fotos_girar", [this.foto.clave, "derecha"], "Listo: la foto quedó girada.");
        }
    }

    async hacerPrincipal(foto = this.foto) {
        if (foto && !foto.principal) {
            const ok = await this.cambiar("dcasa_fotos_principal", [foto.clave], "Listo: ahora es la foto principal.");
            if (ok && this.state.modo === "visor") {
                this.state.indice = 0;
            }
        }
    }

    quitar(foto = this.foto) {
        if (!foto) {
            return;
        }
        const posicion = this.fotos.indexOf(foto) + 1;
        this.dialog.add(ConfirmationDialog, {
            title: "Quitar la foto",
            body: foto.principal && this.fotos.length > 1
                ? `¿Quitar la foto principal? La siguiente (la ${posicion + 1}) pasa a ser la principal. No se puede deshacer.`
                : `¿Quitar la foto ${posicion}? No se puede deshacer.`,
            confirmLabel: "Sí, quitarla",
            cancelLabel: "No",
            confirm: () => this.cambiar("dcasa_fotos_quitar", [foto.clave], "Listo: la foto se quitó."),
            cancel: () => {},
        });
    }

    // --- Recortar (Cropper.js que trae Odoo en el editor) -------------------------------------------------------
    recortar() {
        if (this.foto) {
            this.reiniciarZoom();
            this.state.mensaje = null;
            this.state.modo = "recorte";
        }
    }

    async armarRecortador() {
        await loadBundle("html_editor.assets_image_cropper");
        const imagen = this.imagenRecorte.el;
        if (!imagen || this.state.modo !== "recorte") {
            return;
        }
        if (!imagen.complete) {
            await new Promise((ok) => imagen.addEventListener("load", ok, { once: true }));
        }
        this.soltarRecortador();
        const proporcion = PROPORCIONES.find((p) => p.clave === this.state.proporcion) || PROPORCIONES[0];
        // eslint-disable-next-line no-undef
        this.cropper = new Cropper(imagen, {
            viewMode: 1,
            dragMode: "move",
            autoCropArea: 0.9,
            aspectRatio: proporcion.valor,
            checkOrientation: false, // el navegador ya muestra la foto derecha y el servidor recorta igual
            background: false,
            responsive: true,
            restore: false,
            toggleDragModeOnDblclick: false,
        });
    }

    ponerProporcion(clave) {
        this.state.proporcion = clave;
        const proporcion = PROPORCIONES.find((p) => p.clave === clave);
        if (this.cropper && proporcion) {
            this.cropper.setAspectRatio(proporcion.valor);
        }
    }

    soltarRecortador() {
        if (this.cropper) {
            this.cropper.destroy();
            this.cropper = null;
        }
    }

    cancelarRecorte() {
        this.soltarRecortador();
        this.state.modo = "visor";
    }

    async guardarRecorte() {
        if (!this.cropper || !this.foto) {
            return;
        }
        const d = this.cropper.getData(true);
        const ok = await this.cambiar(
            "dcasa_fotos_recortar", [this.foto.clave, d.x, d.y, d.width, d.height], "Listo: la foto quedó recortada."
        );
        if (ok) {
            this.soltarRecortador();
            this.state.modo = "visor";
        }
    }

    // --- Galería: subir varias y ordenar ------------------------------------------------------------------------
    elegirArchivos(conCamara = false) {
        const entrada = conCamara ? this.camara.el : this.archivos.el;
        if (entrada) {
            entrada.value = "";
            entrada.click();
        }
    }

    async alElegirArchivos(ev) {
        await this.subir([...(ev.target.files || [])]);
    }

    alArrastrarEncima(ev) {
        if (!this.puedeEditar || !ev.dataTransfer || ![...ev.dataTransfer.types].includes("Files")) {
            return;
        }
        ev.preventDefault();
        this.state.soltando = true;
    }

    alSalirArrastre(ev) {
        if (!ev.currentTarget.contains(ev.relatedTarget)) {
            this.state.soltando = false;
        }
    }

    async alSoltarArchivos(ev) {
        if (!this.puedeEditar || !ev.dataTransfer) {
            return;
        }
        ev.preventDefault();
        this.state.soltando = false;
        await this.subir([...ev.dataTransfer.files]);
    }

    /** Sube las fotos de a una (con su avance), en el orden en que se eligieron. */
    async subir(archivos) {
        if (!archivos.length || this.state.ocupado) {
            return;
        }
        const problemas = [];
        const buenos = [];
        for (const archivo of archivos) {
            const problema = problemaDelArchivo(archivo);
            if (problema) {
                problemas.push(problema);
            } else {
                buenos.push(archivo);
            }
        }
        this.state.subiendo = { hechas: 0, total: buenos.length };
        let subidas = 0;
        for (const archivo of buenos) {
            const ok = await this.cambiar("dcasa_fotos_subir", [[{ nombre: archivo.name, datos: await leerArchivo(archivo) }]]);
            if (ok) {
                subidas++;
            } else if (this.state.mensaje) {
                problemas.push(`«${archivo.name}»: ${this.state.mensaje.texto}`);
            }
            this.state.subiendo.hechas++;
        }
        this.state.subiendo = null;
        if (problemas.length) {
            const inicio = subidas ? `Subí ${subidas} de ${archivos.length}. ` : "";
            this.state.mensaje = { tipo: "error", texto: inicio + problemas.join(" ") };
        } else if (subidas) {
            this.state.mensaje = {
                tipo: "ok", texto: subidas === 1 ? "Listo: la foto quedó subida." : `Listo: ${subidas} fotos subidas.`,
            };
        }
    }

    async ordenar(claves) {
        const porClave = Object.fromEntries(this.fotos.map((f) => [f.clave, f]));
        // Se ve el orden nuevo de una vez; el servidor confirma (o lo devuelve como estaba).
        this.state.datos.fotos = claves.map((c, i) => ({ ...porClave[c], principal: i === 0 }));
        if (!(await this.cambiar("dcasa_fotos_ordenar", [claves], "Listo: el orden quedó guardado."))) {
            await this.cargar();
        }
    }

    alTeclearTarjeta(ev, indice) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            this.ver(indice);
        }
    }

    alSoltarEnCuadricula({ element, previous }) {
        const movida = element.dataset.clave;
        const resto = this.fotos.map((f) => f.clave).filter((c) => c !== movida);
        const posicion = previous ? resto.indexOf(previous.dataset.clave) + 1 : 0;
        resto.splice(posicion, 0, movida);
        return this.ordenar(resto);
    }

    mover(foto, paso) {
        const claves = this.fotos.map((f) => f.clave);
        const desde = claves.indexOf(foto.clave);
        const hasta = desde + paso;
        if (desde < 0 || hasta < 0 || hasta >= claves.length) {
            return;
        }
        claves.splice(desde, 1);
        claves.splice(hasta, 0, foto.clave);
        return this.ordenar(claves);
    }
}

/**
 * Abre las fotos de un producto. ``alCambiar`` se llama al cerrar si algo cambió (para recargar la ficha o la lista).
 */
export function abrirFotos(dialogo, { plantillaId, modo = "visor", indice = 0, alCambiar = null }) {
    const registro = { cambios: false };
    return dialogo.add(
        DcasaFotos,
        { plantillaId, modo, indice, registro },
        {
            onClose: () => {
                if (registro.cambios && alCambiar) {
                    alCambiar();
                }
            },
        }
    );
}
