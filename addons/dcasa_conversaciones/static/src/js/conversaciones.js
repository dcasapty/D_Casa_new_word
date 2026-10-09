/**
 * «Conversaciones»: la pantalla donde el equipo atiende a los clientes con Juan (docs/JUAN_PANEL.md).
 * Tres columnas en escritorio (lista, hilo, ficha) y una a la vez en celular. Acción de cliente OWL, igual que la
 * conciliación bancaria de dcasa_contabilidad.
 */
import { Component, onMounted, onWillUnmount, useEffect, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Almacen } from "./almacen";
import { BuscadorCatalogo } from "./catalogo";
import { DialogoAdjuntar } from "./adjuntar";
import { DialogoCotizacion } from "./cotizacion";
import { FichaCliente } from "./ficha";
import { HiloConversacion } from "./hilo";
import { ListaConversaciones } from "./lista";
import { VisorImagenes } from "./visor";

const CLAVE_ABIERTA = "dcasa.conversaciones.abierta";
const CADA_CUANTO = 30_000;

function leerAbierta() {
    try {
        return Number(window.sessionStorage.getItem(CLAVE_ABIERTA)) || null;
    } catch {
        return null;
    }
}

function guardarAbierta(id) {
    try {
        if (id) {
            window.sessionStorage.setItem(CLAVE_ABIERTA, String(id));
        } else {
            window.sessionStorage.removeItem(CLAVE_ABIERTA);
        }
    } catch {
        /* sin almacenamiento: la pantalla funciona igual */
    }
}

export class DcasaConversaciones extends Component {
    static template = "dcasa_conversaciones.Conversaciones";
    static components = { ListaConversaciones, HiloConversacion, FichaCliente, BuscadorCatalogo, DialogoCotizacion, DialogoAdjuntar, VisorImagenes };
    static props = ["*"];

    setup() {
        this.action = useService("action");
        this.almacen = useState(
            new Almacen({
                orm: useService("orm"),
                bus: useService("bus_service"),
                notification: useService("notification"),
            })
        );
        this.alVolverAVer = () => {
            if (document.visibilityState === "visible") {
                this.almacen.ahora = Date.now();
                this.almacen.marcarLeida();
            }
        };
        onMounted(async () => {
            document.addEventListener("visibilitychange", this.alVolverAVer);
            this.reloj = setInterval(() => (this.almacen.ahora = Date.now()), CADA_CUANTO);
            await this.almacen.iniciar();
            const recordada = leerAbierta();
            if (recordada && !this.almacen.errorInicio) {
                this.almacen.abrir(recordada);
            }
        });
        onWillUnmount(() => {
            document.removeEventListener("visibilitychange", this.alVolverAVer);
            clearInterval(this.reloj);
            this.almacen.desuscribir();
        });
        useEffect(
            () => guardarAbierta(this.almacen.seleccionadaId),
            () => [this.almacen.seleccionadaId]
        );
    }

    get aviso() {
        const bot = this.almacen.bot;
        if (!this.almacen.iniciado) {
            return null;
        }
        if (!bot.conectado) {
            return {
                clase: "alerta",
                titulo: "Falta conectar el bot",
                texto: "El asistente todavía no contesta y «Sugerir» no funciona. Las vendedoras sí pueden atender.",
                enlace: this.almacen.usuario.es_gerencia ? "Ver Conexiones" : null,
            };
        }
        if (!bot.encendido) {
            return {
                clase: "info",
                titulo: "El asistente está apagado",
                texto: "Nadie recibe respuestas automáticas; las vendedoras atienden todo.",
                enlace: null,
            };
        }
        return null;
    }

    irAConexiones() {
        this.action.doAction("dcasa_conversaciones.accion_conexiones");
    }
}

registry.category("actions").add("dcasa_conversaciones", DcasaConversaciones);
