/**
 * Servicio `dcasa_brian`: abre y cierra el panel de Brian desde cualquier lugar
 * (botón flotante, barra superior, atajo Ctrl + J). El panel (brian_panel.js) se encarga
 * del foco: al abrir va a la caja de texto y al cerrar vuelve a donde estaba.
 */
import { reactive } from "@odoo/owl";
import { registry } from "@web/core/registry";

export const brianServicio = {
    dependencies: ["hotkey"],
    start(env, { hotkey }) {
        const estado = reactive({ abierto: false });

        const servicio = {
            estado,
            focoPrevio: null,
            abrir() {
                if (!estado.abierto) {
                    servicio.focoPrevio = document.activeElement;
                    estado.abierto = true;
                    document.body.classList.add("o_brian_abierto");
                }
            },
            cerrar() {
                if (estado.abierto) {
                    estado.abierto = false;
                    document.body.classList.remove("o_brian_abierto");
                }
            },
            alternar() {
                return estado.abierto ? servicio.cerrar() : servicio.abrir();
            },
        };

        // Ctrl + J en todas las pantallas, aunque el foco esté en un campo o en un diálogo.
        hotkey.add("control+j", () => servicio.alternar(), {
            global: true,
            bypassEditableProtection: true,
        });

        return servicio;
    },
};

registry.category("services").add("dcasa_brian", brianServicio);
