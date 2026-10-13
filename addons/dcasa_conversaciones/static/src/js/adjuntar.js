/**
 * «Adjuntar a una factura o a un pedido»: un archivo que mandó el cliente (por ejemplo un comprobante de pago) se copia al
 * chatter de uno de SUS pedidos o facturas. La IA no interviene: el archivo nunca se le muestra.
 */
import { Component, onMounted, onWillUnmount, useExternalListener, useRef, useState } from "@odoo/owl";
import { dolares, mensajeDeError } from "./utilidades";

export class DialogoAdjuntar extends Component {
    static template = "dcasa_conversaciones.Adjuntar";
    static props = { almacen: Object };

    setup() {
        this.almacen = useState(this.props.almacen);
        this.dolares = dolares;
        this.local = useState({ cargando: true, error: null, cliente: true, pedidos: [], facturas: [], ocupado: false });
        this.refPanel = useRef("panel");
        this._previo = document.activeElement;
        useExternalListener(window, "keydown", (ev) => this.alTeclear(ev), { capture: true });
        onMounted(() => this.cargar());
        onWillUnmount(() => this._previo?.focus?.());
    }

    get archivo() {
        return this.almacen.adjuntoAAsociar;
    }

    async cargar() {
        try {
            const r = await this.almacen.documentosDelCliente();
            this.local.cliente = r.cliente;
            this.local.pedidos = r.pedidos;
            this.local.facturas = r.facturas;
        } catch (error) {
            this.local.error = mensajeDeError(error);
        } finally {
            this.local.cargando = false;
        }
    }

    cerrar() {
        this.almacen.adjuntoAAsociar = null;
        this.almacen.cerrarPanel();
    }

    alTeclear(ev) {
        if (this.almacen.panel !== "adjuntar") {
            return;
        }
        if (ev.key === "Escape") {
            ev.preventDefault();
            ev.stopPropagation();
            this.cerrar();
        } else if (ev.key === "Tab" && this.refPanel.el) {
            const enfocables = [...this.refPanel.el.querySelectorAll("button, a[href]")].filter((e) => !e.disabled);
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

    async elegir(modelo, documento) {
        if (this.local.ocupado || !this.archivo) {
            return;
        }
        this.local.ocupado = true;
        try {
            const r = await this.almacen.adjuntarADocumento(this.archivo.id, modelo, documento.id);
            if (r) {
                this.almacen.notification.add(r.ya_estaba ? `«${this.archivo.nombre}» ya estaba en ${r.documento}.` : `Adjunté «${this.archivo.nombre}» a ${r.documento}.`, { type: r.ya_estaba ? "info" : "success" });
                this.cerrar();
            }
        } finally {
            this.local.ocupado = false;
        }
    }
}
