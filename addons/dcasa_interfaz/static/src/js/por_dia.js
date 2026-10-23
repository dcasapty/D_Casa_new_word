/**
 * «Por día» (Ventas › Hoy › Ventas por día, Facturación › Clientes › Facturado por día, Estadísticas e Inicio): el mes
 * como calendario (en el celular, una lista de días) con lo de cada día; al tocar un día, la lista de ese día y cada
 * documento se abre. Las cifras salen de dcasa.tablero.por_dia / ventas_del_dia (las mismas bases del Inicio) y el
 * servidor exige Gerencia o administrador.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const SEMANA = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
const TITULOS = {
    confirmado: "Lo vendido por día",
    facturado: "Lo facturado por día",
    con_abonos: "Facturas con abonos por día",
    completadas: "Pagadas por completo, por día",
};

/** Lo que comparten «Por día» y «Estadísticas»: el dinero, los números y abrir listas o documentos. */
export const FormatoMixin = (Base) =>
    class extends Base {
        dinero(valor) {
            const moneda = this.state.opciones?.moneda || { simbolo: "$", antes: true };
            const numero = new Intl.NumberFormat("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            }).format(Math.abs(valor || 0));
            const signo = (valor || 0) < 0 ? "-" : "";
            return moneda.antes ? `${signo}${moneda.simbolo}${numero}` : `${signo}${numero} ${moneda.simbolo}`;
        }

        numero(valor, decimales = 0) {
            return new Intl.NumberFormat("en-US", {
                minimumFractionDigits: decimales,
                maximumFractionDigits: decimales,
            }).format(valor || 0);
        }

        unidades(valor) {
            return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(valor || 0);
        }

        /** «3 ventas» / «1 factura» según la base. */
        cuantasTexto(cuantas, base) {
            const [uno, varios] = base === "confirmado" ? ["venta", "ventas"] : ["factura", "facturas"];
            return `${cuantas} ${cuantas === 1 ? uno : varios}`;
        }

        notasTexto(notas) {
            return notas === 1 ? "1 nota de crédito" : `${notas} notas de crédito`;
        }

        /** Abre la lista que explica una cifra (los pedidos o las facturas que se contaron). */
        abrirLista(a) {
            this.action.doAction({
                type: "ir.actions.act_window",
                name: a.name,
                res_model: a.res_model,
                domain: a.domain,
                views: [
                    [a.vista_lista || false, "list"],
                    [false, "form"],
                ],
            });
        }

        abrirDocumento(modelo, id) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: modelo,
                res_id: id,
                views: [[false, "form"]],
            });
        }
    };

export class DcasaPorDia extends FormatoMixin(Component) {
    static template = "dcasa_interfaz.PorDia";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.semana = SEMANA;
        const contexto = this.props.action?.context || {};
        this.state = useState({
            opciones: null,
            datos: null,
            detalle: null,
            dia: null,
            base: contexto.dcasa_base || "facturado",
            vendedor: contexto.dcasa_vendedor ? String(contexto.dcasa_vendedor) : "",
            mes: contexto.dcasa_mes || "",
            cargando: false,
            cargandoDia: false,
            error: "",
        });
        onWillStart(async () => {
            this.state.opciones = await this.orm.call("dcasa.tablero", "opciones_por_dia", []);
            await this.cargar(contexto.dcasa_dia || null);
        });
    }

    get titulo() {
        return TITULOS[this.state.base] || "Por día";
    }

    get detalleBase() {
        const base = (this.state.opciones?.bases || []).find((b) => b.clave === this.state.base);
        return base ? base.detalle : "";
    }

    get vendedorParaElServidor() {
        const v = this.state.vendedor;
        if (!v) {
            return false;
        }
        return v === "sin" ? "sin" : parseInt(v, 10);
    }

    vendedoraElegida(opcion) {
        return this.state.vendedor === String(opcion.id);
    }

    get nombreVendedora() {
        const v = this.state.vendedor;
        const opcion = (this.state.opciones?.vendedoras || []).find((o) => String(o.id) === v);
        return opcion ? opcion.nombre : "";
    }

    /** Los huecos antes del día 1 (la semana empieza el lunes). */
    get huecos() {
        const n = this.state.datos ? this.state.datos.primer_dia_semana : 0;
        return Array.from({ length: n }, (_, i) => i);
    }

    get maximo() {
        return Math.max(1, ...(this.state.datos?.dias || []).map((d) => d.sin_itbms));
    }

    /** En el celular: los días que ya pasaron, del más reciente al primero. */
    get diasEnLista() {
        return (this.state.datos?.dias || []).filter((d) => !d.futuro).slice().reverse();
    }

    /** El ancho de la barrita de un día (0 a 100 %): solo lo que sumó (una nota de crédito sola no tiene barra). */
    ancho(dia) {
        if (!dia.sin_itbms || dia.sin_itbms <= 0) {
            return 0;
        }
        return Math.max(4, Math.round((dia.sin_itbms / this.maximo) * 100));
    }

    /** «3 facturas» o, si ese día hubo notas de crédito, «2 facturas, 1 nota». */
    cuentaDelDia(dia, base) {
        const texto = this.cuantasTexto(dia.cuantas, base);
        if (!dia.notas) {
            return texto;
        }
        return `${texto}, ${dia.notas} ${dia.notas === 1 ? "nota" : "notas"}`;
    }

    tieneVentas(dia) {
        return Boolean(dia.cuantas || dia.notas);
    }

    get indiceMes() {
        return (this.state.opciones?.meses || []).findIndex((m) => m.valor === this.state.datos?.mes);
    }

    get hayMesAnterior() {
        const i = this.indiceMes;
        return i >= 0 && i < this.state.opciones.meses.length - 1;
    }

    get hayMesSiguiente() {
        return this.indiceMes > 0;
    }

    /** «▲ 12.3 %» / «▼ 4.0 %»; sin base positiva, «—». */
    get cambioTexto() {
        const anterior = this.state.datos?.anterior;
        if (!anterior || anterior.cambio === null || anterior.cambio === undefined) {
            return "—";
        }
        const flecha = anterior.sentido === "sube" ? "▲ " : anterior.sentido === "baja" ? "▼ " : "";
        return `${flecha}${this.numero(Math.abs(anterior.cambio), 1)} %`;
    }

    get cambioClase() {
        const sentido = this.state.datos?.anterior?.sentido;
        return sentido === "sube" ? "o_bien" : sentido === "baja" ? "o_mal" : "o_igual";
    }

    async cargar(diaElegido = null) {
        this.state.cargando = true;
        this.state.error = "";
        try {
            const datos = await this.orm.call("dcasa.tablero", "por_dia", [], {
                mes: this.state.mes || false,
                base: this.state.base,
                vendedor: this.vendedorParaElServidor,
            });
            this.state.datos = datos;
            this.state.mes = datos.mes;
            let dia = diaElegido && datos.dias.find((d) => d.fecha === diaElegido && !d.futuro);
            if (!dia && datos.en_curso) {
                dia = datos.dias.find((d) => d.hoy);
            }
            if (dia) {
                await this.elegirDia(dia, true);
            } else {
                this.state.dia = null;
                this.state.detalle = null;
            }
        } catch (error) {
            this.state.error = error?.data?.message || "No se pudieron cargar las ventas.";
        } finally {
            this.state.cargando = false;
        }
    }

    async elegirDia(dia, siempre = false) {
        if (dia.futuro) {
            return;
        }
        if (!siempre && this.state.dia === dia.fecha) {
            // Tocar otra vez el mismo día lo cierra (en el celular, la lista se recoge).
            this.state.dia = null;
            this.state.detalle = null;
            return;
        }
        this.state.dia = dia.fecha;
        this.state.cargandoDia = true;
        try {
            const detalle = await this.orm.call("dcasa.tablero", "ventas_del_dia", [dia.fecha], {
                base: this.state.base,
                vendedor: this.vendedorParaElServidor,
            });
            if (this.state.dia === dia.fecha) {
                this.state.detalle = detalle;
            }
        } catch (error) {
            this.state.error = error?.data?.message || "No se pudo cargar ese día.";
        } finally {
            this.state.cargandoDia = false;
        }
    }

    async cambiarBase(clave) {
        if (clave === this.state.base) {
            return;
        }
        this.state.base = clave;
        await this.cargar(this.state.dia);
    }

    async cambiarVendedor(ev) {
        this.state.vendedor = ev.target.value;
        await this.cargar(this.state.dia);
    }

    async cambiarMes(ev) {
        this.state.mes = ev.target.value;
        await this.cargar();
    }

    async moverMes(paso) {
        const meses = this.state.opciones.meses;
        const i = this.indiceMes + paso;
        if (i < 0 || i >= meses.length) {
            return;
        }
        this.state.mes = meses[i].valor;
        await this.cargar();
    }

    abrirFila(fila) {
        this.abrirDocumento(fila.modelo, fila.id);
    }
}

registry.category("actions").add("dcasa_por_dia", DcasaPorDia);
