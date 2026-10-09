/**
 * «Cotización en PDF»: manda por el canal la cotización de Odoo del cliente (la abierta más reciente). Si no hay
 * ninguna, crea un BORRADOR con productos del catálogo; nunca la confirma.
 */
import { Component, onMounted, onWillUnmount, useExternalListener, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { dolares, mensajeDeError } from "./utilidades";

const ESPERA = 250;

export class DialogoCotizacion extends Component {
    static template = "dcasa_conversaciones.Cotizacion";
    static props = { almacen: Object };

    setup() {
        this.almacen = useState(this.props.almacen);
        this.action = useService("action");
        this.dolares = dolares;
        this.local = useState({
            cargando: true,
            error: null,
            tieneCliente: true,
            cotizaciones: [],
            elegida: null, // id de la cotización
            texto: "",
            modo: "ver", // "ver" | "crear"
            consulta: "",
            productos: [],
            buscado: false,
            buscando: false,
            lineas: [], // [{ variante_id, nombre, precio_texto, cantidad }]
            ocupado: false,
        });
        this.refPanel = useRef("panel");
        this._numero = 0;
        this._previo = document.activeElement;
        useExternalListener(window, "keydown", (ev) => this.alTeclear(ev), { capture: true });
        onMounted(() => this.cargar());
        onWillUnmount(() => {
            clearTimeout(this.temporizador);
            this._previo?.focus?.();
        });
    }

    get cotizacion() {
        return this.local.cotizaciones.find((c) => c.id === this.local.elegida) || null;
    }

    textoPorDefecto(cotizacion) {
        return `Aquí tienes tu cotización ${cotizacion.nombre}. Los precios son más ITBMS.`;
    }

    async cargar() {
        this.local.cargando = true;
        this.local.error = null;
        try {
            const r = await this.almacen.cotizacionesAbiertas();
            this.local.tieneCliente = r.cliente;
            this.local.cotizaciones = r.cotizaciones;
            if (r.cotizaciones.length) {
                this.elegir(r.cotizaciones[0].id);
            } else {
                this.local.modo = "crear";
            }
        } catch (error) {
            this.local.error = mensajeDeError(error);
        } finally {
            this.local.cargando = false;
        }
    }

    elegir(id) {
        this.local.elegida = id;
        const c = this.cotizacion;
        this.local.texto = c ? this.textoPorDefecto(c) : "";
    }

    cerrar() {
        this.almacen.cerrarPanel();
    }

    alTeclear(ev) {
        if (this.almacen.panel !== "cotizacion") {
            return;
        }
        if (ev.key === "Escape") {
            ev.preventDefault();
            ev.stopPropagation();
            this.cerrar();
        } else if (ev.key === "Tab") {
            const enfocables = [...this.refPanel.el.querySelectorAll("button, input, textarea, select, a[href]")].filter((e) => !e.disabled);
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

    abrirEnOdoo() {
        const c = this.cotizacion;
        if (c) {
            this.cerrar();
            this.action.doAction({
                type: "ir.actions.act_window",
                name: c.nombre,
                res_model: "sale.order",
                res_id: c.id,
                views: [[false, "form"]],
                target: "current",
            });
        }
    }

    async enviar() {
        const c = this.cotizacion;
        if (!c || this.local.ocupado) {
            return;
        }
        this.local.ocupado = true;
        try {
            const r = await this.almacen.enviarCotizacion(c.id, this.local.texto.trim() || null);
            if (r) {
                this.almacen.notification.add(`Cotización ${c.nombre} enviada en PDF.`, { type: r.enviado ? "success" : "warning" });
                this.cerrar();
            }
        } catch (error) {
            this.almacen.notification.add(mensajeDeError(error), { type: "danger" });
        } finally {
            this.local.ocupado = false;
        }
    }

    // --- Crear un borrador con productos del catálogo ----------------------------------------------

    empezarOtra() {
        this.local.modo = "crear";
        this.local.lineas = [];
        this.local.consulta = "";
        this.local.productos = [];
        this.local.buscado = false;
    }

    volver() {
        this.local.modo = "ver";
    }

    alBuscar(ev) {
        this.local.consulta = ev.target.value;
        clearTimeout(this.temporizador);
        this.temporizador = setTimeout(() => this.buscar(), ESPERA);
    }

    async buscar() {
        const consulta = this.local.consulta.trim();
        const numero = ++this._numero;
        if (consulta.length < 2) {
            Object.assign(this.local, { productos: [], buscado: false, buscando: false });
            return;
        }
        this.local.buscando = true;
        try {
            const r = await this.almacen.buscarCatalogo(consulta);
            if (numero === this._numero) {
                this.local.productos = r.productos;
                this.local.buscado = true;
            }
        } catch (error) {
            this.almacen.notification.add(mensajeDeError(error), { type: "danger" });
        } finally {
            if (numero === this._numero) {
                this.local.buscando = false;
            }
        }
    }

    agregar(producto, variante = null) {
        const id = variante ? variante.id : producto.variante_id;
        if (!id) {
            return;
        }
        const existente = this.local.lineas.find((l) => l.variante_id === id);
        if (existente) {
            existente.cantidad = Math.min(existente.cantidad + 1, 999);
        } else {
            this.local.lineas.push({
                variante_id: id,
                nombre: variante ? `${producto.nombre} · ${variante.nombre}` : producto.nombre,
                precio_texto: variante ? variante.precio_texto : producto.precio_texto,
                cantidad: 1,
            });
        }
    }

    cambiarCantidad(linea, delta) {
        linea.cantidad = Math.max(1, Math.min(999, linea.cantidad + delta));
    }

    quitar(linea) {
        const i = this.local.lineas.indexOf(linea);
        if (i >= 0) {
            this.local.lineas.splice(i, 1);
        }
    }

    async crearBorrador() {
        if (!this.local.lineas.length || this.local.ocupado) {
            return;
        }
        this.local.ocupado = true;
        try {
            const r = await this.almacen.crearCotizacion(
                this.local.lineas.map((l) => ({ variante_id: l.variante_id, cantidad: l.cantidad }))
            );
            this.local.cotizaciones = [r.cotizacion, ...this.local.cotizaciones];
            this.elegir(r.cotizacion.id);
            this.local.modo = "ver";
            this.almacen.notification.add(`Se creó el borrador ${r.cotizacion.nombre}. Revísalo y envíalo.`, { type: "success" });
        } catch (error) {
            this.almacen.notification.add(mensajeDeError(error), { type: "danger" });
        } finally {
            this.local.ocupado = false;
        }
    }
}
