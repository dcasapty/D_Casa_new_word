/**
 * «Conexiones»: el estado en vivo de cada canal, el QR para vincular WhatsApp, reiniciar / desvincular el puente (con
 * confirmación) y qué NOMBRES de claves faltan. Nunca se muestra el valor de una clave. El QR no se escribe en la consola
 * ni se guarda: viaja de Odoo a esta pantalla y se pinta como imagen.
 */
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { EncabezadoJuan } from "./resumen";
import { iconoDeCanal, mensajeDeError } from "./utilidades";

const CADA_CUANTO_REFRESCA = 30_000;
const CADA_CUANTO_QR = 4_000;
const MAX_INTENTOS_QR = 45; // unos 3 minutos; después hay que pedirlo de nuevo

const NOMBRES_DE_ESTADO_DEL_QR = {
    necesita_qr: "Esperando que lo escanees",
    esperando_qr: "Esperando que lo escanees",
    conectado: "WhatsApp está conectado",
    conectada: "WhatsApp está conectado",
    arrancando: "El puente está arrancando…",
    apagado: "El puente está apagado",
    desvinculada: "El número está desvinculado: escanea un código nuevo",
    desconectado: "Reconectando…",
    cerrada: "Reconectando…",
    iniciando: "El puente está arrancando…",
};

export class ConexionesJuan extends Component {
    static template = "dcasa_conversaciones.Conexiones";
    static components = { EncabezadoJuan };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.iconoDeCanal = iconoDeCanal;
        this.state = useState({
            datos: null,
            cargando: true,
            error: null,
            qr: { visible: false, cargando: false, imagen: null, estado: null, mensaje: null, intentos: 0 },
            trabajando: null, // "reiniciar" | "desvincular"
        });
        onMounted(() => {
            this.cargar();
            this.reloj = setInterval(() => this.cargar(true), CADA_CUANTO_REFRESCA);
        });
        onWillUnmount(() => {
            clearInterval(this.reloj);
            this.detenerQr();
        });
    }

    get d() {
        return this.state.datos;
    }

    async cargar(silencioso = false) {
        if (!silencioso) {
            this.state.cargando = true;
        }
        try {
            const datos = await (silencioso ? this.orm.silent : this.orm).call("dcasa.juan.panel", "conexiones", []);
            this.state.datos = datos;
            this.state.error = null;
        } catch (error) {
            if (!silencioso) {
                this.state.error = mensajeDeError(error);
            }
        } finally {
            this.state.cargando = false;
        }
    }

    /** Cómo se ve cada canal: una palabra + un ícono (nunca solo color). */
    estadoDe(canal) {
        if (!canal.activo) {
            return { clase: "apagado", icono: "fa-power-off", texto: "Apagado", ayuda: "Está apagado en Ajustes de Juan." };
        }
        if (!canal.configurado) {
            return { clase: "alerta", icono: "fa-exclamation-triangle", texto: "Faltan claves", ayuda: "Pega estas claves en el Worker de Juan (solo se muestran los nombres)." };
        }
        if (canal.conectado === false) {
            return { clase: "alerta", icono: "fa-chain-broken", texto: "Desconectado", ayuda: canal.detalle ? `Estado: ${canal.detalle}.` : "El canal no está conectado." };
        }
        if (canal.conectado === true) {
            return { clase: "ok", icono: "fa-check-circle", texto: "Conectado", ayuda: null };
        }
        return { clase: "listo", icono: "fa-check", texto: "Listo", ayuda: "Tiene todas sus claves. Este canal no reporta conexión en vivo." };
    }

    get nombreDelEstadoDelQr() {
        const q = this.state.qr;
        return NOMBRES_DE_ESTADO_DEL_QR[q.estado] || (q.mensaje ? q.mensaje : "Pidiendo el código…");
    }

    // --- El código QR ---------------------------------------------------------------------------------

    mostrarQr() {
        Object.assign(this.state.qr, { visible: true, imagen: null, estado: null, mensaje: null, intentos: 0 });
        this.pedirQr();
    }

    ocultarQr() {
        this.detenerQr();
        Object.assign(this.state.qr, { visible: false, imagen: null });
    }

    detenerQr() {
        clearTimeout(this.temporizadorQr);
        this.temporizadorQr = null;
    }

    async pedirQr() {
        const qr = this.state.qr;
        if (!qr.visible) {
            return;
        }
        qr.cargando = true;
        try {
            const r = await this.orm.silent.call("dcasa.juan.panel", "qr", []);
            qr.imagen = r.qr || null;
            qr.estado = r.estado;
            qr.mensaje = r.ok ? r.mensaje : r.mensaje || "No pude pedir el código.";
        } catch (error) {
            qr.mensaje = mensajeDeError(error);
            qr.imagen = null;
        } finally {
            qr.cargando = false;
        }
        qr.intentos++;
        if (["conectado", "conectada"].includes(qr.estado)) {
            qr.imagen = null;
            this.notification.add("WhatsApp quedó conectado.", { type: "success" });
            this.cargar(true);
            return;
        }
        if (qr.visible && qr.intentos < MAX_INTENTOS_QR) {
            this.temporizadorQr = setTimeout(() => this.pedirQr(), CADA_CUANTO_QR);
        }
    }

    get qrVencio() {
        return this.state.qr.visible && this.state.qr.intentos >= MAX_INTENTOS_QR;
    }

    // --- Reiniciar y desvincular (siempre con confirmación) ------------------------------------------------

    confirmarReiniciar() {
        this.dialog.add(ConfirmationDialog, {
            title: "¿Reiniciar el puente de WhatsApp?",
            body: "El puente se apaga y vuelve a prender en menos de un minuto. La sesión se conserva: no hace falta escanear el QR. Durante ese rato no entran ni salen mensajes de WhatsApp (los que lleguen se guardan).",
            confirmLabel: "Reiniciar",
            cancelLabel: "Cancelar",
            confirm: () => this.accion("reiniciar", "reiniciar_puente", "Se pidió reiniciar el puente. Vuelve en menos de un minuto."),
            cancel: () => {},
        });
    }

    confirmarDesvincular() {
        this.dialog.add(ConfirmationDialog, {
            title: "¿Desvincular el número de WhatsApp?",
            body: "Se cierra la sesión de WhatsApp de la tienda. Para volver a conectar, alguien tiene que escanear un QR nuevo con el teléfono. Mientras tanto nadie recibe ni contesta por WhatsApp.",
            confirmLabel: "Sí, desvincular",
            confirmClass: "btn-danger",
            cancelLabel: "No, dejarlo conectado",
            confirm: () => this.accion("desvincular", "desvincular_puente", "El número quedó desvinculado. Muestra el QR para conectarlo de nuevo."),
            cancel: () => {},
        });
    }

    async accion(clave, metodo, exito) {
        this.state.trabajando = clave;
        try {
            await this.orm.call("dcasa.juan.panel", metodo, []);
            this.notification.add(exito, { type: "success" });
            await this.cargar(true);
        } catch (error) {
            this.notification.add(mensajeDeError(error), { type: "danger" });
        } finally {
            this.state.trabajando = null;
        }
    }

    abrirAjustes() {
        this.action.doAction("dcasa_conversaciones.action_dcasa_juan_ajustes");
    }
}

registry.category("actions").add("dcasa_juan_conexiones", ConexionesJuan);
