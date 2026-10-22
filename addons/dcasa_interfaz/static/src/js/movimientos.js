/**
 * «Inventario › Movimientos»: busca un producto (nombre, código o código de barras) y mira, en palabras, todo lo que
 * entró y salió, con lo que quedó después de cada movimiento; sin producto, los últimos movimientos de todos. Las
 * líneas salen de dcasa.movimientos (el servidor exige Gerencia o administrador).
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const ICONOS = {
    compra: "fa-truck",
    venta: "fa-shopping-bag",
    devolucion: "fa-undo",
    ajuste: "fa-sliders",
    traslado: "fa-exchange",
    otro: "fa-circle-o",
};

export class DcasaMovimientos extends Component {
    static template = "dcasa_interfaz.Movimientos";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.iconos = ICONOS;
        const contexto = this.props.action?.context || {};
        this.state = useState({
            tipos: [],
            texto: "",
            resultados: [],
            buscando: false,
            buscado: false,
            producto: null,
            desde: "",
            hasta: "",
            tipo: "",
            datos: null,
            filas: [],
            pagina: 0,
            cargando: false,
            error: "",
        });
        this.espera = null;
        onWillStart(async () => {
            const opciones = await this.orm.call("dcasa.movimientos", "opciones", []);
            this.state.tipos = opciones.tipos;
            await this.cargar(contexto.dcasa_producto_id || false);
        });
        onWillUnmount(() => clearTimeout(this.espera));
    }

    // ------------------------------------------------------------------
    // Buscar un producto
    // ------------------------------------------------------------------

    alEscribir(ev) {
        this.state.texto = ev.target.value;
        clearTimeout(this.espera);
        this.espera = setTimeout(() => this.buscar(), 250);
    }

    async buscar() {
        const texto = this.state.texto.trim();
        if (texto.length < 2) {
            this.state.resultados = [];
            this.state.buscado = false;
            return;
        }
        this.state.buscando = true;
        try {
            const resultados = await this.orm.call("dcasa.movimientos", "buscar_productos", [texto]);
            if (this.state.texto.trim() === texto) {
                this.state.resultados = resultados;
                this.state.buscado = true;
            }
        } finally {
            this.state.buscando = false;
        }
    }

    async teclaEnBuscar(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            clearTimeout(this.espera);
            await this.buscar();
            if (this.state.resultados.length) {
                await this.elegir(this.state.resultados[0]);
            }
        } else if (ev.key === "Escape") {
            this.state.resultados = [];
        }
    }

    async elegir(producto) {
        this.state.producto = producto;
        this.state.resultados = [];
        this.state.buscado = false;
        this.state.texto = "";
        await this.cargar(producto.id);
    }

    async quitarProducto() {
        this.state.producto = null;
        await this.cargar(false);
    }

    // ------------------------------------------------------------------
    // La línea de tiempo
    // ------------------------------------------------------------------

    get productoId() {
        return this.state.producto ? this.state.producto.id : false;
    }

    async cargar(productoId = this.productoId, pagina = 0) {
        this.state.cargando = true;
        this.state.error = "";
        try {
            const datos = await this.orm.call("dcasa.movimientos", "movimientos", [], {
                producto_id: productoId || false,
                desde: this.state.desde || false,
                hasta: this.state.hasta || false,
                tipo: this.state.tipo || false,
                pagina,
            });
            this.state.datos = datos;
            this.state.pagina = pagina;
            this.state.filas = pagina ? this.state.filas.concat(datos.filas) : datos.filas;
            if (datos.producto) {
                this.state.producto = datos.producto;
            }
        } catch (error) {
            this.state.error = error?.data?.message || "No se pudieron cargar los movimientos.";
        } finally {
            this.state.cargando = false;
        }
    }

    async cambiarTipo(clave) {
        this.state.tipo = this.state.tipo === clave ? "" : clave;
        await this.cargar();
    }

    async cambiarFechas() {
        if (this.state.desde && this.state.hasta && this.state.desde > this.state.hasta) {
            this.state.error = "«Desde» no puede ser después de «hasta».";
            return;
        }
        await this.cargar();
    }

    async limpiarFechas() {
        this.state.desde = "";
        this.state.hasta = "";
        await this.cargar();
    }

    async verMas() {
        await this.cargar(this.productoId, this.state.pagina + 1);
    }

    cantidad(valor) {
        return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(valor || 0);
    }

    abrirDocumento(fila) {
        if (!fila.documento) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: fila.documento.modelo,
            res_id: fila.documento.id,
            views: [[false, "form"]],
        });
    }

    async verProducto(fila) {
        await this.elegir({ id: fila.producto.id, nombre: fila.producto.nombre });
    }
}

registry.category("actions").add("dcasa_movimientos", DcasaMovimientos);
