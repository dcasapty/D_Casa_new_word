/**
 * «Este cliente lo atiende Ana. ¿Lo tomas tú?» (decisión de la dueña del 2026-11-12): sale cuando una vendedora le
 * escribe (o pulsa «Atender») al cliente que atiende otra vendedora que está trabajando ahora. El servidor no lo hace sin
 * esta confirmación (``ClienteDeOtraVendedora``); aquí solo se pregunta. Tres salidas:
 *
 * - «Sí, lo tomo»: se manda y el cliente queda con quien escribe (en el hilo queda dicho y a la otra le llega un aviso).
 * - «Dejarle una nota a Ana»: al cliente no le sale nada; lo escrito pasa a una nota interna que la menciona.
 * - «Cancelar» (o Esc, o tocar fuera): no pasa nada; lo escrito sigue en la caja.
 *
 * El foco empieza en «Cancelar»: un Enter de más nunca le quita el cliente a nadie.
 */
import { Component, onMounted, onWillUnmount, useExternalListener, useRef, useState } from "@odoo/owl";

export class ConfirmarToma extends Component {
    static template = "dcasa_conversaciones.ConfirmarToma";
    static props = { almacen: Object };

    setup() {
        this.almacen = useState(this.props.almacen);
        this.refPanel = useRef("panel");
        this._previo = document.activeElement;
        useExternalListener(window, "keydown", (ev) => this.alTeclear(ev), { capture: true });
        onMounted(() => this.refPanel.el?.querySelector(".o_dcj_toma_cancelar")?.focus());
        onWillUnmount(() => this._previo?.focus?.());
    }

    get nombre() {
        return this.almacen.tomaPendiente?.duena?.nombre || "otra vendedora";
    }

    /** El nombre de pila, para los botones (que en el celular tienen que caber). */
    get pila() {
        return this.nombre.split(" ")[0];
    }

    elegir(eleccion) {
        this.almacen.tomaPendiente?.responder(eleccion);
    }

    alTeclear(ev) {
        if (!this.almacen.tomaPendiente) {
            return;
        }
        if (ev.key === "Escape") {
            ev.preventDefault();
            ev.stopPropagation();
            this.elegir(null);
        } else if (ev.key === "Tab" && this.refPanel.el) {
            const botones = [...this.refPanel.el.querySelectorAll("button")];
            const primero = botones[0];
            const ultimo = botones[botones.length - 1];
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
