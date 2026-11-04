/**
 * «Foto del catálogo»: busca un producto (nombre o código) y manda su foto con un pie armado: nombre, precio + ITBMS,
 * medidas y enlace. La disponibilidad se muestra como etiqueta (DISPONIBLE / POCAS / AGOTADO), nunca la cantidad.
 *
 * Varias de una vez (pedido de la dueña, 2026-11-03): se eligen fotos de distintos productos (buscando uno y después
 * otro, o de los cuatro «Cama Twin» que salen) y se mandan juntas, un mensaje por producto con su pie. La ventana NO se
 * cierra al enviar: se cierra cuando la vendedora termina («Listo», la X o Esc).
 */
import { Component, onMounted, onWillUnmount, useExternalListener, useRef, useState } from "@odoo/owl";
import { mensajeDeError } from "./utilidades";

const ESPERA = 250;
/** Cuántos productos se mandan de una vez (cada uno es un mensaje con su pie). */
export const MAX_PRODUCTOS_POR_TANDA = 10;
const ETIQUETA_DE_EXISTENCIAS = { disponible: "DISPONIBLE", pocas: "POCAS", agotado: "AGOTADO" };

export class BuscadorCatalogo extends Component {
    static template = "dcasa_conversaciones.Catalogo";
    static props = { almacen: Object };

    setup() {
        this.almacen = useState(this.props.almacen);
        this.local = useState({
            consulta: "",
            productos: [],
            encontrados: 0,
            buscado: false,
            cargando: false,
            error: null,
            galeria: null, // { producto, fotos, elegidas: [ref] }
            ocupado: null, // "enviar" | "caja" | "galeria" | "tanda" mientras se manda
            productoOcupado: null,
            tanda: [], // lo elegido para mandar junto: [{ producto, fotos: [ref] }], en el orden en que se eligió
            enviados: [], // ids de los productos ya enviados mientras la ventana sigue abierta
        });
        this.refConsulta = useRef("consulta");
        this.refPanel = useRef("panel");
        this._numero = 0;
        this._previo = document.activeElement;
        this.etiquetaDeExistencias = (v) => ETIQUETA_DE_EXISTENCIAS[v] || String(v || "").toUpperCase();
        useExternalListener(window, "keydown", (ev) => this.alTeclear(ev), { capture: true });
        onMounted(() => this.refConsulta.el?.focus());
        onWillUnmount(() => {
            clearTimeout(this.temporizador);
            this._previo?.focus?.();
        });
    }

    alEscribir(ev) {
        this.local.consulta = ev.target.value;
        clearTimeout(this.temporizador);
        this.temporizador = setTimeout(() => this.buscar(), ESPERA);
    }

    async buscar() {
        const consulta = this.local.consulta.trim();
        const numero = ++this._numero;
        if (consulta.length < 2) {
            Object.assign(this.local, { productos: [], encontrados: 0, buscado: false, cargando: false, error: null });
            return;
        }
        this.local.cargando = true;
        this.local.error = null;
        try {
            const r = await this.almacen.buscarCatalogo(consulta);
            if (numero === this._numero) {
                Object.assign(this.local, { productos: r.productos, encontrados: r.encontrados, buscado: true });
            }
        } catch (error) {
            if (numero === this._numero) {
                this.local.error = mensajeDeError(error);
            }
        } finally {
            if (numero === this._numero) {
                this.local.cargando = false;
            }
        }
    }

    cerrar() {
        // Mientras sale una tanda, la ventana no se cierra (ni con la X, ni con Esc, ni tocando afuera).
        if (this.local.ocupado === "tanda") {
            return;
        }
        this.almacen.cerrarPanel();
    }

    alTeclear(ev) {
        if (this.almacen.panel !== "catalogo") {
            return;
        }
        if (ev.key === "Escape") {
            ev.preventDefault();
            ev.stopPropagation();
            if (this.local.galeria) {
                this.local.galeria = null;
            } else {
                this.cerrar();
            }
        } else if (ev.key === "Tab") {
            const enfocables = [...this.refPanel.el.querySelectorAll("button, input, a[href]")].filter((e) => !e.disabled);
            if (!enfocables.length) {
                return;
            }
            const primero = enfocables[0];
            const ultimo = enfocables[enfocables.length - 1];
            if (ev.shiftKey && document.activeElement === primero) {
                ev.preventDefault();
                ultimo.focus();
            } else if (!ev.shiftKey && document.activeElement === ultimo) {
                ev.preventDefault();
                primero.focus();
            }
        }
    }

    // --- Una foto ---------------------------------------------------------------------------------

    async enviarFoto(producto) {
        this.local.ocupado = "enviar";
        this.local.productoOcupado = producto.id;
        try {
            const r = await this.almacen.enviarFotoDelCatalogo(producto.id, ["principal"]);
            if (r) {
                this.almacen.notification.add(`Foto de «${producto.nombre}» enviada.`, { type: r.enviado ? "success" : "warning" });
                this.marcarEnviado(producto.id);
            }
        } catch (error) {
            this.almacen.notification.add(mensajeDeError(error), { type: "danger" });
        } finally {
            this.local.ocupado = null;
        }
    }

    async revisarAntes(producto, fotos = ["principal"]) {
        this.local.ocupado = "caja";
        this.local.productoOcupado = producto.id;
        try {
            const preparado = await this.almacen.prepararFotoDelCatalogo(producto.id, fotos);
            this.almacen.ponerEnLaCaja(preparado);
            this.cerrar();
        } catch (error) {
            this.almacen.notification.add(mensajeDeError(error), { type: "danger" });
        } finally {
            this.local.ocupado = null;
        }
    }

    // --- La galería ---------------------------------------------------------------------------------

    async abrirGaleria(producto) {
        this.local.ocupado = "galeria";
        this.local.productoOcupado = producto.id;
        try {
            const r = await this.almacen.fotosDelCatalogo(producto.id);
            this.local.galeria = { producto: r.producto, fotos: r.fotos, elegidas: r.fotos.length ? [r.fotos[0].ref] : [] };
        } catch (error) {
            this.almacen.notification.add(mensajeDeError(error), { type: "danger" });
        } finally {
            this.local.ocupado = null;
        }
    }

    alternarFoto(ref) {
        const g = this.local.galeria;
        const i = g.elegidas.indexOf(ref);
        if (i >= 0) {
            g.elegidas.splice(i, 1);
        } else if (g.elegidas.length < this.almacen.limites.adjuntos) {
            g.elegidas.push(ref);
        } else {
            this.almacen.notification.add(`Máximo ${this.almacen.limites.adjuntos} fotos por mensaje.`, { type: "warning" });
        }
    }

    volverALosResultados() {
        this.local.galeria = null;
    }

    async enviarElegidas() {
        const g = this.local.galeria;
        this.local.ocupado = "enviar";
        try {
            const r = await this.almacen.enviarFotoDelCatalogo(g.producto.id, g.elegidas);
            if (r) {
                this.almacen.notification.add(
                    g.elegidas.length === 1 ? "Foto enviada." : `${g.elegidas.length} fotos enviadas.`,
                    { type: r.enviado ? "success" : "warning" }
                );
                this.marcarEnviado(g.producto.id);
                this.local.galeria = null;
            }
        } catch (error) {
            this.almacen.notification.add(mensajeDeError(error), { type: "danger" });
        } finally {
            this.local.ocupado = null;
        }
    }

    // --- Varias fotos de varios productos ---------------------------------------------------------

    marcarEnviado(productoId) {
        if (!this.local.enviados.includes(productoId)) {
            this.local.enviados.push(productoId);
        }
        const i = this.local.tanda.findIndex((t) => t.producto.id === productoId);
        if (i >= 0) {
            this.local.tanda.splice(i, 1);
        }
    }

    enLaTanda(producto) {
        return this.local.tanda.find((t) => t.producto.id === producto.id) || null;
    }

    get fotosDeLaTanda() {
        return this.local.tanda.reduce((suma, t) => suma + t.fotos.length, 0);
    }

    /** Elegir o quitar la foto principal de un producto (de la lista de resultados). */
    alternarProducto(producto) {
        const i = this.local.tanda.findIndex((t) => t.producto.id === producto.id);
        if (i >= 0) {
            this.local.tanda.splice(i, 1);
            return;
        }
        if (this.local.tanda.length >= MAX_PRODUCTOS_POR_TANDA) {
            this.almacen.notification.add(`Máximo ${MAX_PRODUCTOS_POR_TANDA} productos de una vez: envía estas y sigue.`, { type: "warning" });
            return;
        }
        this.local.tanda.push({ producto, fotos: ["principal"] });
    }

    /** Desde la galería: deja en la tanda las fotos marcadas de ese producto y vuelve a los resultados. */
    agregarElegidas() {
        const g = this.local.galeria;
        const i = this.local.tanda.findIndex((t) => t.producto.id === g.producto.id);
        if (i < 0 && this.local.tanda.length >= MAX_PRODUCTOS_POR_TANDA) {
            this.almacen.notification.add(`Máximo ${MAX_PRODUCTOS_POR_TANDA} productos de una vez: envía estas y sigue.`, { type: "warning" });
            return;
        }
        const producto = this.local.productos.find((p) => p.id === g.producto.id) || g.producto;
        if (i >= 0) {
            this.local.tanda[i].fotos = [...g.elegidas];
        } else {
            this.local.tanda.push({ producto, fotos: [...g.elegidas] });
        }
        this.local.galeria = null;
    }

    vaciarTanda() {
        this.local.tanda.splice(0, this.local.tanda.length);
    }

    /** Manda lo elegido, un mensaje por producto (con su pie), en el orden en que se eligió. Si uno falla, se detiene y
     * deja elegido lo que falta, para reintentar. La ventana queda abierta. */
    async enviarTanda() {
        const total = this.local.tanda.length;
        if (!total || this.local.ocupado) {
            return;
        }
        this.local.ocupado = "tanda";
        const conversacionId = this.almacen.seleccionadaId;   // a este cliente, pase lo que pase en la pantalla
        let fotos = 0;
        let productos = 0;
        let alguno = true;
        try {
            for (const elegido of [...this.local.tanda]) {
                this.local.productoOcupado = elegido.producto.id;
                const r = await this.almacen.enviarFotoDelCatalogo(elegido.producto.id, elegido.fotos, null, conversacionId);
                if (!r) {
                    break;
                }
                alguno = alguno && r.enviado;
                fotos += elegido.fotos.length;
                productos += 1;
                this.marcarEnviado(elegido.producto.id);
            }
            if (productos) {
                const texto = productos === 1
                    ? (fotos === 1 ? "Foto enviada." : `${fotos} fotos enviadas.`)
                    : `${fotos} fotos de ${productos} productos enviadas.`;
                this.almacen.notification.add(texto, { type: alguno ? "success" : "warning" });
            }
        } catch (error) {
            this.almacen.notification.add(
                `${mensajeDeError(error)}${productos ? ` Ya salieron ${productos} de ${total}; lo que falta sigue elegido.` : ""}`,
                { type: "danger" }
            );
        } finally {
            this.local.ocupado = null;
            this.local.productoOcupado = null;
            this.refConsulta.el?.focus();
        }
    }
}
