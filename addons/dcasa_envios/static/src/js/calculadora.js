/**
 * Calculadora de envíos (Envíos › Calculadora).
 *
 * La pantalla NO calcula precios: todo sale del motor del servidor (addons/dcasa_envios/motor), el mismo que usan Brian
 * y, mañana, la web. Aquí solo se escribe, se pide al servidor (con una pausa corta mientras se escribe) y se pinta lo
 * que contesta: tarjetas con el total, los km, el desglose, «Copiar el precio» y la ruta en Google Maps.
 */
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const LUGAR = "dcasa.envio.lugar";
const TARIFA = "dcasa.envio.tarifa";
const PAUSA = 200;          // ms sin escribir antes de buscar
const POR_PAGINA = 20;

export const TIPOS = [
    { valor: "", nombre: "Todo" },
    { valor: "barrio", nombre: "Barrios y urbanizaciones" },
    { valor: "edificio", nombre: "Edificios y PH" },
    { valor: "referencia", nombre: "Lugares conocidos" },
    { valor: "corregimiento", nombre: "Corregimientos" },
];

export const TIPOS_NUEVOS = [
    { valor: "barrio", nombre: "Barrio o urbanización" },
    { valor: "edificio", nombre: "Edificio o PH" },
    { valor: "referencia", nombre: "Lugar conocido" },
];

/** «Casa Verde, Los Pinos» → una línea por nombre (como se guardan los otros nombres). */
export function aliasEnRenglones(texto) {
    return (texto || "").split(",").map((s) => s.trim()).filter(Boolean).join("\n");
}

/** La ruta en Google Maps desde la tienda hasta un lugar que todavía no está en la lista (por su nombre). */
export function rutaPorNombre(tienda, nombre, corr, dist) {
    const destino = `${nombre || ""}, ${corr ? corr + ", " : ""}${dist || ""}, Panamá`;
    return `https://www.google.com/maps/dir/?api=1&origin=${tienda}&destination=${encodeURIComponent(destino)}`
        + "&travelmode=driving";
}

function agregarVacio(nombre = "", dist = "") {
    return { abierto: false, nombre, alias: "", tipo: "barrio", dist, corr: "", km: "", peaje: false,
             guardando: false, error: "" };
}

export class CalculadoraEnvios extends Component {
    static template = "dcasa_envios.Calculadora";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.buscador = useRef("buscador");
        this.state = useState({
            cargando: true, error: "", datos: null,
            q: "", tipo: "", distrito: "", limite: POR_PAGINA, buscando: false, resultado: null,
            km: "", peaje: false, calc: null, copiado: null,
            agregar: agregarVacio(),
        });
        this.temporizador = null;
        this.temporizadorKm = null;
        this.vuelta = 0;
        this.vueltaKm = 0;
        onMounted(() => this.cargar());
        onWillUnmount(() => {
            clearTimeout(this.temporizador);
            clearTimeout(this.temporizadorKm);
        });
    }

    // --- Datos ---------------------------------------------------------------------------------------------------
    async cargar() {
        this.state.cargando = true;
        try {
            this.state.datos = await this.orm.call(LUGAR, "datos_de_la_calculadora", []);
            this.state.error = "";
            if (!this.state.agregar.dist) {
                this.state.agregar.dist = this.distritoPorDefecto;
            }
            if (this.state.q) {
                await this.buscar();
            }
            this.buscador.el?.focus();
        } catch (error) {
            this.state.error = error?.data?.message || error?.message || "No se pudo abrir la calculadora.";
        } finally {
            this.state.cargando = false;
        }
    }

    get tipos() {
        return TIPOS;
    }

    get tiposNuevos() {
        return TIPOS_NUEVOS;
    }

    get datos() {
        return this.state.datos || { total_lugares: 0, distritos: [], provincias: [], corregimientos: {}, tarifa: {} };
    }

    get tarifa() {
        return (this.state.resultado && this.state.resultado.tarifa && { ...this.datos.tarifa,
            ...this.state.resultado.tarifa }) || this.datos.tarifa || {};
    }

    get hayDatos() {
        return this.datos.total_lugares > 0;
    }

    get distritoPorDefecto() {
        const distritos = this.datos.distritos || [];
        return distritos.includes("La Chorrera") ? "La Chorrera" : distritos[0] || "";
    }

    get corregimientosDelDistrito() {
        return (this.datos.corregimientos || {})[this.state.agregar.dist] || [];
    }

    get resultados() {
        return (this.state.resultado && this.state.resultado.resultados) || [];
    }

    get vacio() {
        return Boolean(this.state.q.trim() && this.state.resultado && !this.state.resultado.total
            && !this.state.buscando);
    }

    get hayMas() {
        return Boolean(this.state.resultado && this.state.resultado.total > this.resultados.length);
    }

    get contador() {
        const r = this.state.resultado;
        if (!this.state.q.trim() || !r) {
            const total = (this.datos.total_lugares || 0).toLocaleString("es-PA");
            return `${total} lugares en la lista. Escribe arriba para buscar.`;
        }
        if (!r.total) {
            return "Sin resultados";
        }
        if (r.total === 1) {
            return "1 lugar";
        }
        const total = r.total.toLocaleString("es-PA");
        return r.total > this.resultados.length
            ? `${total} lugares; se ven los ${this.resultados.length} que más se parecen`
            : `${total} lugares`;
    }

    get urlMapaTienda() {
        return `https://www.google.com/maps/dir/?api=1&origin=${this.datos.tienda}&travelmode=driving`;
    }

    get urlMedirNuevo() {
        const a = this.state.agregar;
        return rutaPorNombre(this.datos.tienda, a.nombre, a.corr, a.dist);
    }

    // --- Buscar --------------------------------------------------------------------------------------------------
    alEscribir(ev) {
        this.state.q = ev.target.value;
        this.state.limite = POR_PAGINA;
        clearTimeout(this.temporizador);
        this.temporizador = setTimeout(() => this.buscar(), PAUSA);
    }

    async buscar() {
        const q = this.state.q.trim();
        const vuelta = ++this.vuelta;
        if (!q) {
            this.state.resultado = null;
            this.state.buscando = false;
            return;
        }
        this.state.buscando = true;
        try {
            const resultado = await this.orm.call(LUGAR, "buscar_para_cotizar", [q], {
                tipo: this.state.tipo || null, distrito: this.state.distrito || null, limite: this.state.limite,
            });
            if (vuelta === this.vuelta) {
                this.state.resultado = resultado;
                this.state.error = "";
            }
        } catch (error) {
            if (vuelta === this.vuelta) {
                this.state.error = error?.data?.message || error?.message || "No se pudo buscar.";
            }
        } finally {
            if (vuelta === this.vuelta) {
                this.state.buscando = false;
            }
        }
    }

    elegirTipo(valor) {
        this.state.tipo = valor;
        this.state.limite = POR_PAGINA;
        this.buscar();
    }

    elegirDistrito(ev) {
        this.state.distrito = ev.target.value;
        this.state.limite = POR_PAGINA;
        this.buscar();
    }

    verMas() {
        this.state.limite += 40;
        this.buscar();
    }

    usarSugerencia(nombre) {
        this.state.q = nombre;
        this.state.limite = POR_PAGINA;
        this.buscar();
    }

    async copiar(lugar) {
        const texto = lugar.texto_cliente;
        try {
            await navigator.clipboard.writeText(texto);
        } catch {
            const area = document.createElement("textarea");
            area.value = texto;
            document.body.appendChild(area);
            area.select();
            document.execCommand("copy");
            area.remove();
        }
        this.state.copiado = lugar.id;
        setTimeout(() => {
            if (this.state.copiado === lugar.id) {
                this.state.copiado = null;
            }
        }, 1500);
    }

    // --- Calcular por kilómetros ----------------------------------------------------------------------------------
    alCambiarKm(ev) {
        this.state.km = ev.target.value;
        this.programarKm();
    }

    alCambiarPeaje(ev) {
        this.state.peaje = ev.target.checked;
        this.programarKm();
    }

    programarKm() {
        clearTimeout(this.temporizadorKm);
        this.temporizadorKm = setTimeout(() => this.calcularKm(), PAUSA);
    }

    async calcularKm() {
        const vuelta = ++this.vueltaKm;
        const km = parseFloat(this.state.km);
        if (!isFinite(km) || km < 0) {
            this.state.calc = null;
            return;
        }
        const calc = await this.orm.call(TARIFA, "cotizar_km", [km], { peaje: this.state.peaje });
        if (vuelta === this.vueltaKm) {
            this.state.calc = calc;
        }
    }

    // --- Agregar un lugar que falta --------------------------------------------------------------------------------
    abrirAgregar(nombre = "") {
        this.state.agregar = { ...agregarVacio(nombre, this.distritoPorDefecto), abierto: true };
        setTimeout(() => document.querySelector(".o_dcasa_envios .o_de_agregar input")?.focus(), 50);
    }

    cerrarAgregar() {
        this.state.agregar = agregarVacio("", this.distritoPorDefecto);
    }

    cambiarAgregar(campo, ev) {
        const valor = ev.target.type === "checkbox" ? ev.target.checked : ev.target.value;
        this.state.agregar[campo] = valor;
        if (campo === "dist") {
            this.state.agregar.corr = "";
        }
    }

    async guardarLugar(ev) {
        ev.preventDefault();
        const a = this.state.agregar;
        const km = parseFloat(a.km);
        if (!a.nombre.trim() || !isFinite(km) || km < 0) {
            a.error = "Escribe el nombre y los kilómetros por carretera desde la tienda.";
            return;
        }
        a.guardando = true;
        a.error = "";
        try {
            await this.orm.create(LUGAR, [{
                name: a.nombre.trim(), alias: aliasEnRenglones(a.alias), tipo: a.tipo, dist: a.dist,
                corr: a.corr.trim(), km, peaje: a.peaje,
            }]);
            const nombre = a.nombre.trim();
            this.notification.add(`«${nombre}» quedó en la lista, con tu nombre.`, { type: "success" });
            this.cerrarAgregar();
            this.state.datos = await this.orm.call(LUGAR, "datos_de_la_calculadora", []);
            this.state.q = nombre;
            await this.buscar();
            this.buscador.el?.scrollIntoView({ block: "start", behavior: "smooth" });
        } catch (error) {
            a.error = error?.data?.message || error?.message || "No se pudo agregar.";
        } finally {
            a.guardando = false;
        }
    }

    // --- Gerencia --------------------------------------------------------------------------------------------------
    cargarArchivo() {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "dcasa.envio.importar", views: [[false, "form"]],
            target: "new", name: "Cargar lugares y tarifa desde el archivo",
        }, { onClose: () => this.cargar() });
    }

    abrirTarifa() {
        this.action.doAction("dcasa_envios.accion_tarifa");
    }
}

registry.category("actions").add("dcasa_envios.calculadora", CalculadoraEnvios);
