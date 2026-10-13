/**
 * Visor de fotos del hilo: ampliar, pasar de una a otra con las flechas, descargar y cerrar con Esc.
 * Accesible: el foco entra al visor, no se escapa con Tab y vuelve a donde estaba al cerrar.
 */
import { Component, onMounted, onWillUnmount, useExternalListener, useRef, useState } from "@odoo/owl";

export class VisorImagenes extends Component {
    static template = "dcasa_conversaciones.Visor";
    static props = { almacen: Object };

    setup() {
        this.almacen = useState(this.props.almacen);
        this.local = useState({ ampliada: false });
        this.refVisor = useRef("visor");
        this.refCerrar = useRef("cerrar");
        this._previo = document.activeElement;
        useExternalListener(window, "keydown", (ev) => this.alTeclear(ev), { capture: true });
        onMounted(() => this.refCerrar.el?.focus());
        onWillUnmount(() => this._previo?.focus?.());
    }

    get imagen() {
        const v = this.almacen.visor;
        return v ? v.imagenes[v.indice] : null;
    }

    get hayVarias() {
        return (this.almacen.visor?.imagenes.length || 0) > 1;
    }

    get posicion() {
        const v = this.almacen.visor;
        return v ? `${v.indice + 1} de ${v.imagenes.length}` : "";
    }

    cerrar() {
        this.almacen.cerrarVisor();
    }

    mover(delta) {
        const v = this.almacen.visor;
        if (v && v.imagenes.length > 1) {
            v.indice = (v.indice + delta + v.imagenes.length) % v.imagenes.length;
            this.local.ampliada = false;
        }
    }

    alternarZoom() {
        this.local.ampliada = !this.local.ampliada;
    }

    alTeclear(ev) {
        if (!this.almacen.visor) {
            return;
        }
        if (ev.key === "Escape") {
            ev.preventDefault();
            ev.stopPropagation();
            this.cerrar();
        } else if (ev.key === "ArrowRight") {
            ev.preventDefault();
            this.mover(1);
        } else if (ev.key === "ArrowLeft") {
            ev.preventDefault();
            this.mover(-1);
        } else if (ev.key === "Tab") {
            const enfocables = [...this.refVisor.el.querySelectorAll("button, a[href]")].filter((e) => !e.disabled);
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
}
