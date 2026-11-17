/**
 * Notas de voz para Brian del panel: el navegador graba (MediaRecorder), la página manda el audio UNA vez a
 * `/dcasa/brian/v1/voz` (solo usuarios internos) y recibe SOLO el texto, que va a la caja de Brian para revisarlo.
 *
 * Lo que no se negocia (docs/BRIAN.md › «Notas de voz»): el audio no se guarda en ningún lado (ni en el navegador: vive en
 * memoria mientras se graba y se suelta al mandarlo o al cancelar), el micrófono se apaga al terminar (las pistas se
 * detienen) y solo graba cuando la persona lo pide, con el tiempo a la vista. Un minuto como mucho: al llegar, para solo.
 * Si la pantalla se cierra mientras el navegador pide el permiso, el micrófono se apaga al llegar y no se graba nada.
 */
import { browser } from "@web/core/browser/browser";
import { rpc } from "@web/core/network/rpc";

export const RUTA_VOZ = "/dcasa/brian/v1/voz";
export const MAX_SEGUNDOS_VOZ = 60;
/** Opus a 32 kbps: una voz se entiende igual y un minuto pesa unos 240 KB (el tope es 1 MB). */
const BITS_POR_SEGUNDO = 32000;
/** Por orden: Chrome y Edge graban WebM; Firefox, Ogg (o WebM); Safari, MP4. */
const TIPOS_PREFERIDOS = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/webm", "audio/mp4"];

/** ¿Este navegador puede grabar? (Necesita una conexión segura: https o localhost.) */
export function vozSoportada() {
    return Boolean(
        browser.navigator?.mediaDevices?.getUserMedia && window.MediaRecorder && window.isSecureContext !== false
    );
}

export function tipoDeGrabacion() {
    const puede = (t) => {
        try {
            return window.MediaRecorder.isTypeSupported(t);
        } catch {
            return false;
        }
    };
    return TIPOS_PREFERIDOS.find(puede) || "";
}

/** «0:07»: los segundos como los lee cualquiera. */
export function reloj(segundos) {
    const s = Math.max(0, Math.floor(segundos || 0));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function aBase64(blob) {
    return new Promise((resolver, rechazar) => {
        const lector = new FileReader();
        lector.onload = () => resolver(String(lector.result || "").split(",")[1] || "");
        lector.onerror = () => rechazar(lector.error);
        lector.readAsDataURL(blob);
    });
}

/**
 * Una grabación. `alCambiar(segundos)` cada cuarto de segundo; `alTerminar({blob, tipo, ms})` cuando la persona toca
 * «Listo» o se llega al minuto. `cancelar()` la tira sin mandar nada.
 */
export class GrabadoraDeVoz {
    constructor({ alCambiar, alTerminar, maxSegundos = MAX_SEGUNDOS_VOZ } = {}) {
        this.alCambiar = alCambiar || (() => {});
        this.alTerminar = alTerminar || (() => {});
        this.maxSegundos = maxSegundos;
        this.partes = [];
        this.flujo = null;
        this.grabadora = null;
        this.inicio = 0;
        this.reloj = null;
        this.cancelada = false;
    }

    async empezar() {
        const flujo = await browser.navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
        });
        // Si cancelaron (o el panel se cerró) mientras el navegador pedía el permiso, el micrófono se apaga aquí mismo
        // y no se graba nada: antes el flujo llegaba después de `cancelar()` y quedaba encendido para siempre.
        if (this.cancelada) {
            for (const pista of flujo?.getTracks?.() || []) {
                pista.stop();
            }
            return;
        }
        this.flujo = flujo;
        const tipo = tipoDeGrabacion();
        const opciones = { audioBitsPerSecond: BITS_POR_SEGUNDO, ...(tipo ? { mimeType: tipo } : {}) };
        try {
            this.grabadora = new window.MediaRecorder(this.flujo, opciones);
        } catch {
            this.grabadora = new window.MediaRecorder(this.flujo);
        }
        this.grabadora.ondataavailable = (ev) => {
            if (ev.data && ev.data.size && !this.cancelada) {
                this.partes.push(ev.data);
            }
        };
        this.grabadora.onstop = () => this.alParar();
        this.grabadora.start(1000);
        this.inicio = Date.now();
        this.reloj = browser.setInterval(() => {
            const segundos = (Date.now() - this.inicio) / 1000;
            this.alCambiar(segundos);
            if (segundos >= this.maxSegundos) {
                this.terminar();
            }
        }, 250);
    }

    get grabando() {
        return this.grabadora?.state === "recording";
    }

    terminar() {
        if (this.grabando) {
            this.grabadora.stop();
        }
    }

    /** Tira lo grabado y apaga el micrófono. Sirve también antes de que el navegador dé el permiso. */
    cancelar() {
        this.cancelada = true;
        this.partes = [];
        if (this.grabando) {
            this.grabadora.stop();
        } else {
            this.liberar();
        }
    }

    alParar() {
        const ms = Math.min(Date.now() - this.inicio, this.maxSegundos * 1000);
        const tipo = (this.grabadora?.mimeType || tipoDeGrabacion() || "audio/webm").toLowerCase();
        const partes = this.partes;
        this.partes = [];
        this.liberar();
        if (!this.cancelada && partes.length) {
            this.alTerminar({ blob: new Blob(partes, { type: tipo }), tipo, ms });
        }
    }

    /** Apaga el micrófono (el navegador deja de mostrar que graba) y suelta todo. */
    liberar() {
        browser.clearInterval(this.reloj);
        this.reloj = null;
        for (const pista of this.flujo?.getTracks?.() || []) {
            pista.stop();
        }
        this.flujo = null;
        this.grabadora = null;
    }
}

/** Manda la nota a Odoo y devuelve `{ok, texto, recortado}` o `{ok: false, error}`. El audio no se guarda. */
export async function transcribir({ blob, tipo, ms }) {
    let audio = await aBase64(blob);
    try {
        return await rpc(RUTA_VOZ, { audio, mime: tipo, duracion_ms: Math.round(ms) }, { silent: true });
    } finally {
        audio = null;
    }
}
