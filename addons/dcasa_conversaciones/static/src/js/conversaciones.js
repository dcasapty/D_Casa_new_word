/**
 * «Conversaciones»: la pantalla donde el equipo atiende a los clientes con Juan (docs/JUAN_PANEL.md).
 * Escritorio: la lista (que puede reducirse a las fotos) y el hilo, que es lo que más espacio tiene; la ficha del cliente
 * va al lado solo en pantallas amplias y, en las demás, se abre encima y se cierra sola (ver preferencias.js).
 * Celular: una columna a la vez. Acción de cliente OWL, igual que la conciliación bancaria de dcasa_contabilidad.
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
import { escucharCambioDeTamano } from "./preferencias";
import { VisorImagenes } from "./visor";

const CLAVE_ABIERTA = "dcasa.conversaciones.abierta";
const CADA_CUANTO = 30_000;
/** Cada cuánto esta pantalla dice «sigo aquí, viendo esta conversación». */
const CADA_CUANTO_PULSO = 20_000;
/** Al volver a ver la pestaña se pone al día, salvo que se haya sincronizado hace menos de esto. */
const AL_VOLVER_SIN_PASAR_DE = 20_000;

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
                this.almacen.latido();
                // Una pestaña escondida pudo perder avisos (el navegador la duerme): al volver se pone al día.
                this.almacen.resincronizar(AL_VOLVER_SIN_PASAR_DE);
            }
        };
        onMounted(async () => {
            // Se lee ANTES de esperar al servidor: el efecto de abajo borra la marca en cuanto la pantalla se monta, y
            // «Abrir» de la pantalla Reparto (y volver a cargar la página) dependen de que todavía esté.
            const recordada = leerAbierta();
            document.addEventListener("visibilitychange", this.alVolverAVer);
            this.dejarDeEscucharElTamano = escucharCambioDeTamano(() => this.almacen.alCambiarElTamano());
            this.pulso = setInterval(() => {
                if (document.visibilityState === "visible") {
                    this.almacen.latido();
                }
            }, CADA_CUANTO_PULSO);
            this.reloj = setInterval(() => {
                this.almacen.ahora = Date.now();
                // Sin conexión en vivo no llegan avisos: la pantalla se revisa sola, para que nadie se quede sin ver un mensaje.
                if (!this.almacen.enVivo) {
                    this.almacen.resincronizar(CADA_CUANTO - 1000);
                }
            }, CADA_CUANTO);
            await this.almacen.iniciar();
            this.almacen.latido();
            if (recordada && !this.almacen.errorInicio) {
                this.almacen.abrir(recordada);
            }
        });
        onWillUnmount(() => {
            document.removeEventListener("visibilitychange", this.alVolverAVer);
            this.dejarDeEscucharElTamano?.();
            clearInterval(this.reloj);
            clearInterval(this.pulso);
            this.almacen.salir();
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
