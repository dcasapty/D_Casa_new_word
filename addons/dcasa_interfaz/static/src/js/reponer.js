/**
 * «Reponer» (Compras › Reponer): cuánto pedirle a cada proveedor según lo que se vende y lo que tarda en llegar.
 *
 * Todas las cifras las calcula el servidor (dcasa.reponer.obtener), que exige Gerencia o administrador; esta pantalla
 * solo las pinta. Paso 1: el buscador de proveedores (nombre, teléfono, RUC o un producto que vende). Paso 2: cuántos
 * meses de ventas mirar y cuántos de reserva. Después, la lista por urgencia o por proveedor, el tiempo de llegada
 * (se pone o se cambia en una ventana) y el Excel, que arma el servidor (/dcasa/reponer/excel).
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { debounce } from "@web/core/utils/timing";
import { useService } from "@web/core/utils/hooks";

const DIAS_POR_MES = 30;
const MESES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
const RESERVAS = [0, 0.5, 1, 1.5, 2, 3, 4, 5, 6];

function mensajeDeError(error) {
    return (error && error.data && error.data.message) || (error && error.message) || "Algo salió mal.";
}

/** La ventana para poner o cambiar cuánto tarda en llegar un proveedor (en meses o en días). */
export class DcasaReponerLlegada extends Component {
    static template = "dcasa_interfaz.ReponerLlegada";
    static components = { Dialog };
    static props = { proveedor: Object, alGuardar: Function, close: Function };

    setup() {
        this.orm = useService("orm");
        const dias = this.props.proveedor.llegada && this.props.proveedor.llegada.dias;
        const enMeses = !dias || dias % DIAS_POR_MES === 0;
        this.state = useState({
            cantidad: dias ? String(enMeses ? dias / DIAS_POR_MES : dias) : "",
            unidad: enMeses ? "meses" : "dias",
            error: "",
            guardando: false,
        });
    }

    get dias() {
        const numero = parseFloat(String(this.state.cantidad).replace(",", "."));
        if (!Number.isFinite(numero) || numero <= 0) {
            return null;
        }
        return Math.round(this.state.unidad === "meses" ? numero * DIAS_POR_MES : numero);
    }

    /** «= 90 días» o «= 3 meses»: lo que se va a guardar, en la otra unidad. */
    get equivale() {
        const dias = this.dias;
        if (!dias) {
            return "";
        }
        if (this.state.unidad === "meses") {
            return dias === 1 ? "= 1 día" : `= ${dias} días`;
        }
        const meses = Math.round((dias / DIAS_POR_MES) * 10) / 10;
        return meses === 1 ? "≈ 1 mes" : `≈ ${meses} meses`;
    }

    cambiarUnidad(unidad) {
        if (unidad === this.state.unidad) {
            return;
        }
        const dias = this.dias;
        this.state.unidad = unidad;
        if (dias) {
            const valor = unidad === "meses" ? Math.round((dias / DIAS_POR_MES) * 10) / 10 : dias;
            this.state.cantidad = String(valor);
        }
    }

    async guardar(ev) {
        ev?.preventDefault();
        if (!this.dias) {
            this.state.error = "Escribe cuánto tarda: un número mayor que 0.";
            return;
        }
        this.state.guardando = true;
        this.state.error = "";
        try {
            const ficha = await this.orm.call("dcasa.reponer", "poner_llegada", [
                this.props.proveedor.id,
                this.state.cantidad,
                this.state.unidad,
            ]);
            await this.props.alGuardar(ficha);
            this.props.close();
        } catch (error) {
            this.state.error = mensajeDeError(error);
        } finally {
            this.state.guardando = false;
        }
    }
}

export class DcasaReponer extends Component {
    static template = "dcasa_interfaz.Reponer";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.action = useService("action");
        // En el celular la explicación arranca cerrada (si no, tapa toda la primera pantalla); se abre al tocarla.
        this.explicacionAbierta = !useService("ui").isSmall;
        this.opcionesMeses = MESES;
        this.opcionesReserva = RESERVAS;
        this.state = useState({
            meses: 5,
            reserva: 0,
            proveedor: null, // la ficha elegida; null = «Todos los proveedores»
            buscadorAbierto: true,
            texto: "",
            resultados: [],
            total: 0,
            buscando: false,
            datos: null,
            cargando: false,
            error: "",
            vista: "urgencia", // "urgencia" | "proveedor"
        });
        this.pedidoActual = 0;
        this.busquedaActual = 0;
        this.buscarConPausa = debounce(() => this.buscar(), 300);
        onWillUnmount(() => this.buscarConPausa.cancel());
        onWillStart(() => Promise.all([this.cargar(), this.buscar()]));
    }

    // --- Datos ---------------------------------------------------------------------------------------------------

    async cargar() {
        const pedido = ++this.pedidoActual;
        this.state.cargando = true;
        this.state.error = "";
        try {
            const datos = await this.orm.call("dcasa.reponer", "obtener", [], {
                meses: this.state.meses,
                reserva: this.state.reserva,
                proveedor_id: this.state.proveedor ? this.state.proveedor.id : false,
            });
            if (pedido === this.pedidoActual) {
                this.state.datos = datos;
                if (datos.proveedor) {
                    this.state.proveedor = datos.proveedor;
                }
            }
        } catch (error) {
            if (pedido === this.pedidoActual) {
                this.state.error = mensajeDeError(error);
            }
        } finally {
            if (pedido === this.pedidoActual) {
                this.state.cargando = false;
            }
        }
    }

    async buscar() {
        const pedido = ++this.busquedaActual;
        this.state.buscando = true;
        try {
            const respuesta = await this.orm.call("dcasa.reponer", "buscar_proveedores", [this.state.texto]);
            if (pedido === this.busquedaActual) {
                this.state.resultados = respuesta.proveedores;
                this.state.total = respuesta.total;
            }
        } finally {
            if (pedido === this.busquedaActual) {
                this.state.buscando = false;
            }
        }
    }

    // --- Paso 1: el proveedor ---------------------------------------------------------------------------------------

    alEscribir(ev) {
        this.state.texto = ev.target.value;
        this.buscarConPausa();
    }

    borrarTexto() {
        this.state.texto = "";
        this.buscarConPausa.cancel();
        this.buscar();
    }

    elegir(ficha) {
        this.state.proveedor = ficha;
        this.state.buscadorAbierto = false;
        return this.cargar();
    }

    cambiarProveedor() {
        this.state.buscadorAbierto = true;
    }

    // --- Paso 2: meses y reserva -------------------------------------------------------------------------------------

    cambiarMeses(ev) {
        this.state.meses = parseInt(ev.target.value, 10);
        return this.cargar();
    }

    cambiarReserva(ev) {
        this.state.reserva = parseFloat(ev.target.value);
        return this.cargar();
    }

    textoReserva(valor) {
        if (!valor) {
            return "Sin reserva";
        }
        return valor === 1 ? "1 mes" : `${valor} meses`;
    }

    // --- Tiempo de llegada -------------------------------------------------------------------------------------------

    /** Abre la ventana del tiempo de llegada de ese proveedor (una ficha o, desde una fila, su id y nombre). */
    async ponerLlegada(proveedorId) {
        let ficha = this.state.proveedor && this.state.proveedor.id === proveedorId ? this.state.proveedor : null;
        if (!ficha) {
            const grupo = this.state.datos.grupos.find((g) => g.proveedor_id === proveedorId);
            ficha = { id: proveedorId, nombre: grupo ? grupo.proveedor : "", llegada: grupo ? grupo.llegada : null };
        }
        this.dialog.add(DcasaReponerLlegada, {
            proveedor: ficha,
            alGuardar: async (nueva) => {
                if (this.state.proveedor && this.state.proveedor.id === nueva.id) {
                    this.state.proveedor = nueva;
                }
                const enLista = this.state.resultados.findIndex((r) => r.id === nueva.id);
                if (enLista >= 0) {
                    this.state.resultados[enLista] = { ...this.state.resultados[enLista], llegada: nueva.llegada };
                }
                await this.cargar();
            },
        });
    }

    // --- La lista ----------------------------------------------------------------------------------------------------

    cambiarVista(vista) {
        this.state.vista = vista;
    }

    /** «+507 6000-0000 · RUC 123-4-5678» del proveedor elegido (lo que tenga). */
    get detalleProveedor() {
        const p = this.state.proveedor;
        if (!p) {
            return "";
        }
        return [p.telefono, p.ruc ? `RUC ${p.ruc}` : ""].filter(Boolean).join(" · ");
    }

    get filasPorId() {
        const mapa = {};
        for (const fila of this.state.datos.filas) {
            mapa[fila.producto_id] = fila;
        }
        return mapa;
    }

    filasDelGrupo(grupo) {
        const mapa = this.filasPorId;
        return grupo.producto_ids.map((id) => mapa[id]);
    }

    get urlExcel() {
        const parametros = new URLSearchParams({
            meses: String(this.state.meses),
            reserva: String(this.state.reserva),
        });
        if (this.state.proveedor) {
            parametros.set("proveedor", String(this.state.proveedor.id));
        }
        return `/dcasa/reponer/excel?${parametros.toString()}`;
    }

    numero(valor) {
        return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(valor || 0);
    }

    abrirProducto(fila) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.product",
            res_id: fila.producto_id,
            views: [[false, "form"]],
        });
    }
}

registry.category("actions").add("dcasa_reponer", DcasaReponer);
