/**
 * Modo oscuro del panel: lo enciende y lo apaga cada persona desde su menú (el del avatar; en el celular, el menú de
 * arriba a la izquierda). Por defecto, claro.
 *
 * La elección se guarda en la cookie `color_scheme` (un año, para todo el sitio) y no en la ficha del usuario: vale
 * para ese navegador, así que alguien puede tener el celular en oscuro y la computadora en claro. El servidor lee la
 * cookie al armar la página (`ir.http.color_scheme`, en dcasa_interfaz) y entrega la hoja de estilos clara o la oscura;
 * por eso hay que recargar al cambiar. Las gráficas de Odoo leen la misma cookie para elegir sus colores.
 */
import { browser } from "@web/core/browser/browser";
import { cookie } from "@web/core/browser/cookie";
import { registry } from "@web/core/registry";

const COOKIE = "color_scheme";

export const modoOscuro = {
    /** ¿El panel está en oscuro en este navegador? */
    encendido() {
        return cookie.get(COOKIE) === "dark";
    },
    /** Guarda la elección (un año) y recarga para que el servidor entregue la otra hoja de estilos. */
    poner(oscuro) {
        cookie.set(COOKIE, oscuro ? "dark" : "light");
        this.recargar();
    },
    alternar() {
        this.poner(!this.encendido());
    },
    recargar() {
        browser.location.reload();
    },
};

function interruptorModoOscuro() {
    return {
        type: "switch",
        id: "dcasa_modo_oscuro",
        description: "Modo oscuro",
        isChecked: modoOscuro.encendido(),
        callback: () => modoOscuro.alternar(),
        sequence: 55,
    };
}

registry.category("user_menuitems").add("dcasa_modo_oscuro", interruptorModoOscuro);
