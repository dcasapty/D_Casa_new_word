/**
 * Las cifras que suben: la animación de números del Inicio, para todas las pantallas de métricas.
 *
 * Una cifra se marca con la clase «o_dcasa_sube» y su valor en «data-valor»; el texto de la etiqueta es SIEMPRE el valor
 * final (lo pone la plantilla). Mientras sube, el número del momento va en «data-sube» y lo pinta el CSS con ::after encima
 * del texto real, que queda transparente (tablero.scss). Así ni las pruebas ni los lectores de pantalla ven un número a
 * medias.
 *
 *     <strong class="o_dcasa_sube" data-formato="moneda" t-att-data-valor="d.total" t-out="dinero(d.total)"/>
 *
 * «data-formato»: «moneda» (con el dinero de la pantalla), «entero» (miles con coma), «unidades» (hasta 2 decimales) o
 * «decimal» (con «data-decimales»). «data-prefijo» y «data-sufijo» son lo que rodea al número («▲ » y « %»).
 *
 * Reglas (las del Inicio):
 *  - Si la persona pidió menos movimiento en su aparato, no se mueve nada (el texto ya es el valor final).
 *  - Una cifra que aparece sube desde 0; una que cambia (otro periodo, mes, base o vendedora) sube desde donde estaba
 *    hasta el valor nuevo. Si el valor no cambió, no se anima.
 *  - Misma duración y misma curva en todas partes.
 *  - Sin fugas: cada cuadro pendiente se cancela al repintar la cifra y al desmontar la pantalla.
 *
 * Uso en un componente (la plantilla lleva ``t-ref="raiz"`` en su elemento de arriba):
 *
 *     this.raiz = useRef("raiz");
 *     useCifrasQueSuben({ raiz: this.raiz, dinero: (valor) => this.dinero(valor) });
 */
import { onWillUnmount, useEffect } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";

// Cuánto tarda una cifra en subir hasta su valor (el Inicio, desde siempre).
export const DURACION_SUBIDA = 700;
export const CLASE_QUE_SUBE = "o_dcasa_sube";

/** ¿La persona pidió menos movimiento en su aparato? Entonces nada sube ni se desliza. */
export function sinMovimiento() {
    return browser.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** La curva de la subida: arranca rápido y frena al llegar (cúbica de salida), de 0 a 1. */
export function curvaDeSubida(avance) {
    return 1 - (1 - avance) ** 3;
}

const formatos = new Map();

function numeroConDecimales(minimo, maximo) {
    const clave = `${minimo}:${maximo}`;
    if (!formatos.has(clave)) {
        formatos.set(
            clave,
            new Intl.NumberFormat("en-US", { minimumFractionDigits: minimo, maximumFractionDigits: maximo })
        );
    }
    return formatos.get(clave);
}

/** Cómo se escribe un valor a medias (según «data-formato» de la cifra): igual que escribe el final la plantilla. */
export function escribirCifra(el, valor, dinero) {
    const { formato, decimales, prefijo, sufijo } = el.dataset;
    let texto;
    if (formato === "moneda" && dinero) {
        return dinero(valor);
    } else if (formato === "unidades") {
        texto = numeroConDecimales(0, 2).format(valor);
    } else if (formato === "decimal") {
        const n = Math.max(0, parseInt(decimales || "1", 10) || 0);
        texto = numeroConDecimales(n, n).format(valor);
    } else {
        texto = numeroConDecimales(0, 0).format(Math.round(valor));
    }
    return `${prefijo || ""}${texto}${sufijo || ""}`;
}

/** El valor final de una cifra, o ``null`` si no trae un número (una raya, un texto: no se anima). */
function valorDe(el) {
    const crudo = el.dataset.valor;
    if (crudo === undefined || crudo === "") {
        return null;
    }
    const valor = Number(crudo);
    return Number.isFinite(valor) ? valor : null;
}

export class CifrasQueSuben {
    /** @param {(valor:number)=>string} [dinero] cómo se escribe el dinero de la pantalla (para «moneda») */
    constructor(dinero) {
        this.dinero = dinero;
        // Por cifra: el valor al que va («objetivo») y el que se ve en este momento («actual»).
        this.estado = new WeakMap();
        this.cuadros = new Map();
    }

    /** Hace subir cada cifra de ``raiz`` cuyo valor cambió desde la última vez que se miró. */
    subir(raiz) {
        if (!raiz) {
            return;
        }
        const quieto = sinMovimiento();
        for (const el of raiz.querySelectorAll(`.${CLASE_QUE_SUBE}`)) {
            const hasta = valorDe(el);
            if (hasta === null) {
                // Ya no es un número (una raya): se deja el texto y, si vuelve a haber número, sube desde 0.
                this.dejarDeSubir(el);
                this.estado.delete(el);
                continue;
            }
            const previo = this.estado.get(el);
            const desde = previo ? previo.actual : 0;
            if (previo && previo.objetivo === hasta) {
                continue;
            }
            if (!previo && hasta === desde) {
                this.estado.set(el, { objetivo: hasta, actual: hasta });
                continue;
            }
            const estado = { objetivo: hasta, actual: quieto ? hasta : desde };
            this.estado.set(el, estado);
            this.dejarDeSubir(el);
            if (quieto) {
                continue;
            }
            const empieza = browser.performance.now();
            const paso = (ahora) => {
                const avance = Math.min(1, Math.max(0, (ahora - empieza) / DURACION_SUBIDA));
                if (avance >= 1 || !el.isConnected) {
                    estado.actual = hasta;
                    this.dejarDeSubir(el);
                    return;
                }
                estado.actual = desde + (hasta - desde) * curvaDeSubida(avance);
                el.dataset.sube = escribirCifra(el, estado.actual, this.dinero);
                this.cuadros.set(el, browser.requestAnimationFrame(paso));
            };
            el.dataset.sube = escribirCifra(el, desde, this.dinero);
            this.cuadros.set(el, browser.requestAnimationFrame(paso));
        }
    }

    dejarDeSubir(el) {
        if (this.cuadros.has(el)) {
            browser.cancelAnimationFrame(this.cuadros.get(el));
            this.cuadros.delete(el);
        }
        delete el.dataset.sube;
    }

    /** Cancela todos los cuadros pendientes (al desmontar la pantalla) y deja cada cifra con su valor final. */
    parar() {
        for (const el of [...this.cuadros.keys()]) {
            this.dejarDeSubir(el);
        }
    }
}

/**
 * Hace subir las cifras de una pantalla al abrir y cada vez que cambian. ``raiz`` es un ``useRef`` (o cualquier objeto con
 * ``el``) del elemento que las contiene; ``dinero`` escribe el dinero de la pantalla. Devuelve el ``CifrasQueSuben``.
 */
export function useCifrasQueSuben({ raiz, dinero } = {}) {
    const cifras = new CifrasQueSuben(dinero);
    useEffect(() => {
        cifras.subir(raiz.el);
    });
    onWillUnmount(() => cifras.parar());
    return cifras;
}
