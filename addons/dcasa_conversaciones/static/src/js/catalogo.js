/**
 * «Foto del catálogo»: busca un producto (nombre o código) y manda su foto con un pie armado: nombre, precio + ITBMS,
 * medidas y enlace. La disponibilidad se muestra como etiqueta (DISPONIBLE / POCAS / AGOTADO), nunca la cantidad.
 */
import { Component, onMounted, onWillUnmount, useExternalListener, useRef, useState } from "@odoo/owl";
import { mensajeDeError } from "./utilidades";

const ESPERA = 250;
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
            ocupado: null, // "enviar" | "caja" mientras se manda
            productoOcupado: null,
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
                this.cerrar();
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
                this.cerrar();
            }
        } catch (error) {
            this.almacen.notification.add(mensajeDeError(error), { type: "danger" });
        } finally {
            this.local.ocupado = null;
        }
    }
}
