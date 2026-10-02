/**
 * «Vista previa móvil»: el sitio público de D'CASA tal como lo ve un visitante, en un marco de
 * teléfono (390×844), tableta (768×1024) o escritorio (1440×900). Sin modo edición: el sitio se
 * edita por código (models/sitio.py) y esta pantalla solo mira.
 *
 * La URL canónica la da dcasa.sitio.vista_previa (web.base.url). El marco usa esa URL si es del
 * mismo origen que el panel; si no (staging abierto por workers.dev), usa el origen del panel: el
 * borde solo permite enmarcar al mismo origen (frame-ancestors 'self').
 */
import { Component, onMounted, onWillStart, useExternalListener, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export const DISPOSITIVOS = [
    { clave: "telefono", nombre: "Teléfono", ancho: 390, alto: 844, icono: "fa-mobile" },
    { clave: "tableta", nombre: "Tableta", ancho: 768, alto: 1024, icono: "fa-tablet" },
    { clave: "escritorio", nombre: "Escritorio", ancho: 1440, alto: 900, icono: "fa-desktop" },
];

export class DcasaVistaPrevia extends Component {
    static template = "dcasa_interfaz.VistaPrevia";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.dispositivos = DISPOSITIVOS;
        this.escenario = useRef("escenario");
        this.state = useState({
            datos: { url: "", nombre: "", paginas: [] },
            dispositivo: "telefono",
            // Desde «Páginas» llega la ruta de la fila; desde el menú o el Inicio, la portada.
            ruta: this.props.action?.params?.ruta || "/",
            version: 1,
            escala: 1,
        });
        onWillStart(async () => {
            this.state.datos = await this.orm.call("dcasa.sitio", "vista_previa", []);
        });
        onMounted(() => this.ajustarEscala());
        useExternalListener(window, "resize", () => this.ajustarEscala());
    }

    get dispositivo() {
        return this.dispositivos.find((d) => d.clave === this.state.dispositivo) || this.dispositivos[0];
    }

    /** Origen del marco: la URL canónica si es la misma del panel; si no, el propio panel. */
    get origen() {
        const canonica = this.state.datos.url;
        if (canonica) {
            try {
                if (new URL(canonica).origin === window.location.origin) {
                    return canonica;
                }
            } catch {
                // URL inválida en web.base.url: se usa el origen del panel.
            }
        }
        return window.location.origin;
    }

    get mismoOrigen() {
        return !this.state.datos.url || this.origen === this.state.datos.url;
    }

    get rutaLimpia() {
        const ruta = (this.state.ruta || "/").trim();
        return ruta.startsWith("/") ? ruta : `/${ruta}`;
    }

    /** Dirección que se enmarca. Nunca pide el modo edición: solo se mira. */
    get direccion() {
        return `${this.origen}${this.rutaLimpia}`;
    }

    get direccionPublica() {
        return `${this.state.datos.url || this.origen}${this.rutaLimpia}`;
    }

    get estiloMarco() {
        const { ancho, alto } = this.dispositivo;
        return `width: ${ancho}px; height: ${alto}px; transform: scale(${this.state.escala});`;
    }

    get estiloEscenario() {
        const { ancho, alto } = this.dispositivo;
        return `width: ${Math.round(ancho * this.state.escala)}px; height: ${Math.round(alto * this.state.escala)}px;`;
    }

    ajustarEscala() {
        const contenedor = this.escenario.el?.parentElement;
        if (!contenedor) {
            return;
        }
        const { ancho, alto } = this.dispositivo;
        const margen = 32;
        const disponibleAncho = contenedor.clientWidth - margen;
        const disponibleAlto = contenedor.clientHeight - margen;
        const escala = Math.min(1, disponibleAncho / ancho, disponibleAlto / alto);
        this.state.escala = Math.max(0.2, Math.round(escala * 100) / 100);
    }

    elegir(dispositivo) {
        this.state.dispositivo = dispositivo.clave;
        this.ajustarEscala();
    }

    irA(ruta) {
        this.state.ruta = ruta;
        this.state.version += 1;
    }

    enviarRuta(ev) {
        ev.preventDefault();
        this.irA(this.rutaLimpia);
    }

    recargar() {
        this.state.version += 1;
    }

    abrirAparte() {
        window.open(this.direccionPublica, "_blank", "noopener");
    }

    marcoCargado() {
        this.ajustarEscala();
    }
}

registry.category("actions").add("dcasa_vista_previa", DcasaVistaPrevia);
