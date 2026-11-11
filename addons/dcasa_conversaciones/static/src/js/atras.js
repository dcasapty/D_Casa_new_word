/**
 * El «atrás» del teléfono, dentro de Conversaciones.
 *
 * En el celular esta pantalla muestra una cosa a la vez (la lista, el chat, la ficha del cliente) y abre ventanas encima
 * (las fotos, el catálogo, la cotización). Para el navegador todo eso era UNA sola página: el gesto de «atrás» del iPhone
 * (deslizar desde el borde izquierdo) o el botón de Android no volvían del chat a la lista, sino que sacaban a la persona
 * de Conversaciones, a la pantalla anterior (reporte de la dueña, 2026-11-11).
 *
 * Aquí cada cosa abierta (cada «capa») pone un paso en el historial del navegador, y «atrás» cierra la de más arriba:
 * fotos → chat → lista → y recién ahí, la pantalla anterior. Cerrar con el botón de la pantalla (la flecha, la «X»)
 * quita su paso, para que el historial y lo que se ve vayan siempre juntos.
 *
 * Odoo también escucha el «atrás» (web/core/browser/router.js) y, si nadie le avisa, vuelve a cargar la pantalla
 * entera. `router.skipLoad` es su manera prevista de decirle «este retroceso lo atiende la pantalla»: se enciende
 * mientras haya pasos nuestros y Odoo lo apaga solo cada vez que atiende uno.
 */
import { onWillUnmount, useEffect } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { router } from "@web/core/browser/router";

/** Si un retroceso que pidió la pantalla no llega en este tiempo, se deja de esperar. */
const ESPERA_DEL_RETROCESO = 1000;

/**
 * @param {() => number|null} nivel cuántas capas hay abiertas ahora (0 = nada que cerrar: «atrás» sale de la pantalla;
 *     null = la pantalla todavía está abriendo: no se toca el historial)
 * @param {() => void} cerrarLaDeArriba cierra la capa de más arriba (la llama el «atrás» del teléfono)
 */
export function usarAtrasDelTelefono(nivel, cerrarLaDeArriba) {
    // Pasos de esta pantalla en el historial. Si se llega con «atrás» desde otra pantalla a un paso nuestro (o se recarga
    // la página con el chat abierto), ese paso ya está: no se vuelve a poner.
    const yaPuestos = browser.history.state?.dcasaPaso;
    let pasos = Number.isInteger(yaPuestos) && yaPuestos > 0 ? yaPuestos : 0;
    // Retrocesos que pidió la propia pantalla (se cerró algo con su botón) y todavía no llegan.
    let propios = 0;
    let temporizador = null;

    const sostener = () => {
        router.skipLoad = pasos > 0 || propios > 0;
    };

    const sincronizar = () => {
        if (propios > 0) {
            return; // hay un retroceso nuestro en camino: se pone al día cuando llegue
        }
        const n = nivel();
        if (n === null) {
            return;
        }
        if (n > pasos) {
            for (let paso = pasos + 1; paso <= n; paso++) {
                browser.history.pushState({ ...browser.history.state, dcasaPaso: paso }, "");
            }
            pasos = n;
        } else if (n < pasos) {
            const sobran = pasos - n;
            pasos = n;
            propios = 1;
            router.skipLoad = true;
            browser.history.go(-sobran);
            temporizador = browser.setTimeout(() => {
                propios = 0;
                sincronizar();
            }, ESPERA_DEL_RETROCESO);
            return;
        }
        sostener();
    };

    const alRetroceder = () => {
        if (propios > 0) {
            propios = 0;
            browser.clearTimeout(temporizador);
        } else if (pasos > 0) {
            pasos -= 1;
            cerrarLaDeArriba();
        } else {
            return; // no es un paso de esta pantalla: lo atiende Odoo
        }
        sincronizar();
        // Odoo apaga «skipLoad» al terminar de atender este mismo retroceso: se repone después.
        browser.setTimeout(sostener, 0);
    };

    browser.addEventListener("popstate", alRetroceder);
    useEffect(sincronizar, () => [nivel()]);
    onWillUnmount(() => {
        browser.removeEventListener("popstate", alRetroceder);
        browser.clearTimeout(temporizador);
        router.skipLoad = false;
    });
}
