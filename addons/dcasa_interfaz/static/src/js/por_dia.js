/**
 * «Por día» (Ventas › Hoy › Ventas por día, Facturación › Clientes › Facturado por día, Estadísticas e Inicio): el mes
 * como calendario (en el celular, una lista de días) con lo de cada día; al tocar un día, la lista de ese día y cada
 * documento se abre. Las cifras salen de dcasa.tablero.por_dia / ventas_del_dia (las mismas bases del Inicio) y el
 * servidor exige Gerencia o administrador.
 *
 * Arriba del detalle del día va la tarjeta «Cobrado por forma de pago» (dcasa.tablero.cobros_del_periodo) con su selector
 * Día · Semana · Quincena · Mes: el periodo que contiene el día elegido. En la computadora vive arriba del panel de la
 * derecha; en el celular, dentro del día que se abre (y, si no hay un día abierto, arriba de la lista, con el mes).
 * Todas las cifras de la pantalla suben hasta su valor (cifras_que_suben.js).
 */
import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useCifrasQueSuben } from "./cifras_que_suben";

const SEMANA = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
const TITULOS = {
    confirmado: "Lo vendido por día",
    facturado: "Lo facturado por día",
    con_abonos: "Facturas con abonos por día",
    completadas: "Pagadas por completo, por día",
};

// Los botones de «Cobrado por forma de pago»: el periodo que contiene el día elegido.
const PERIODOS_DE_COBROS = [
    { clave: "dia", nombre: "Día" },
    { clave: "semana", nombre: "Semana" },
    { clave: "quincena", nombre: "Quincena" },
    { clave: "mes", nombre: "Mes" },
];

/**
 * Lo que comparten «Por día», «Estadísticas» y «Valor del inventario»: el dinero, los números, abrir listas o documentos
 * y las cifras que suben (la plantilla lleva ``t-ref="raiz"`` arriba y marca cada cifra con «o_dcasa_sube»).
 */
export const FormatoMixin = (Base) =>
    class extends Base {
        setup() {
            super.setup(...arguments);
            this.raiz = useRef("raiz");
            useCifrasQueSuben({ raiz: this.raiz, dinero: (valor) => this.dinero(valor) });
        }

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

        cobrosTexto(cuantos) {
            return cuantos === 1 ? "1 cobro" : `${cuantos} cobros`;
        }

        /** Abre la lista que explica una cifra (los pedidos, las facturas, los cobros o los productos que se contaron). */
        abrirLista(a) {
            this.action.doAction({
                type: "ir.actions.act_window",
                name: a.name,
                res_model: a.res_model,
                domain: a.domain,
                context: a.contexto || {},
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
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
        this.semana = SEMANA;
        this.periodosDeCobros = PERIODOS_DE_COBROS;
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
            // «Cobrado por forma de pago»: el periodo que eligió la persona (se recuerda aunque cambie de día), lo que
            // contestó el servidor y si está cargando.
            periodoCobros: "dia",
            cobro: null,
            cargandoCobro: false,
            errorCobro: "",
        });
        this.pedidoDeCobros = 0;
        this.claveDeCobros = "";
        this.cobrosEnVuelo = null;
        onWillStart(async () => {
            this.state.opciones = await this.orm.call("dcasa.tablero", "opciones_por_dia", []);
            await this.cargar(contexto.dcasa_dia || null);
            // Al abrir se espera lo cobrado (para que la tarjeta no aparezca después y empuje el detalle del día); en los
            // cambios siguientes, no: lo demás se muestra sin esperarlo y la tarjeta se atenúa hasta que llegue.
            await this.cobrosEnVuelo;
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

    /** La flecha de «▲ 12.3 %»: va aparte del número para que, al subir, el número se mueva y la flecha no. */
    get cambioFlecha() {
        const sentido = this.state.datos?.anterior?.sentido;
        return sentido === "sube" ? "▲ " : sentido === "baja" ? "▼ " : "";
    }

    /** El número de «▲ 12.3 %» sin signo (la flecha dice si sube o baja); sin base, ``null``: sale una raya. */
    get cambioNumero() {
        const cambio = this.state.datos?.anterior?.cambio;
        return cambio === null || cambio === undefined ? null : Math.abs(cambio);
    }

    // ------------------------------------------------------------------
    // Cobrado por forma de pago: el día, la semana, la quincena o el mes
    // ------------------------------------------------------------------

    /**
     * El periodo que se muestra. Día, semana y quincena salen del día elegido; sin día elegido (un mes que ya pasó, o un día
     * cerrado en el celular) se muestra el mes que se está viendo.
     */
    get periodoDeCobros() {
        return this.state.dia ? this.state.periodoCobros : "mes";
    }

    /** El día que se le manda al servidor: el elegido o, sin elegir, el primero del mes que se está viendo. */
    get diaDeCobros() {
        return this.state.dia || (this.state.datos ? `${this.state.datos.mes}-01` : "");
    }

    /** «Semana del 16 al 22 de noviembre», con mayúscula para el título de la tarjeta. */
    get tituloDeCobros() {
        const texto = this.state.cobro?.etiqueta || "";
        return texto.charAt(0).toUpperCase() + texto.slice(1);
    }

    /** Día, semana y quincena necesitan un día elegido: sin él, esos botones esperan. */
    periodoDeshabilitado(clave) {
        return !this.state.dia && clave !== "mes";
    }

    /**
     * Pide lo cobrado del periodo y el día de ahora. No bloquea a nadie: devuelve la promesa para quien quiera esperarla
     * (solo al abrir la pantalla). El último pedido manda: una respuesta vieja que llega tarde se descarta.
     */
    cargarCobros(forzar = false) {
        const dia = this.diaDeCobros;
        if (!this.state.datos || !dia) {
            return this.cobrosEnVuelo || Promise.resolve();
        }
        const periodo = this.periodoDeCobros;
        const clave = `${periodo}:${dia}`;
        if (!forzar && clave === this.claveDeCobros) {
            return this.cobrosEnVuelo || Promise.resolve();
        }
        this.claveDeCobros = clave;
        const pedido = ++this.pedidoDeCobros;
        this.state.cargandoCobro = true;
        this.state.errorCobro = "";
        const promesa = (async () => {
            try {
                const cobro = await this.orm.call("dcasa.tablero", "cobros_del_periodo", [dia], { periodo });
                if (pedido === this.pedidoDeCobros) {
                    this.state.cobro = cobro;
                }
            } catch (error) {
                if (pedido === this.pedidoDeCobros) {
                    this.claveDeCobros = "";
                    this.state.errorCobro = error?.data?.message || "No se pudo cargar lo cobrado.";
                }
            } finally {
                if (pedido === this.pedidoDeCobros) {
                    this.state.cargandoCobro = false;
                }
            }
        })();
        this.cobrosEnVuelo = promesa;
        return promesa;
    }

    async cambiarPeriodoDeCobros(clave) {
        if (this.periodoDeshabilitado(clave)) {
            return;
        }
        this.state.periodoCobros = clave;
        await this.cargarCobros();
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
            // Lo cobrado no depende de la base ni de la vendedora: si el día y el periodo siguen siendo los mismos, no
            // se vuelve a pedir (ni se anima otra vez). Y no se espera: el resto ya se puede ver.
            this.cargarCobros();
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
            // Tocar otra vez el mismo día lo cierra (en el celular, la lista se recoge): lo cobrado vuelve al mes.
            this.state.dia = null;
            this.state.detalle = null;
            this.cargarCobros();
            return;
        }
        this.state.dia = dia.fecha;
        this.state.cargandoDia = true;
        // Lo cobrado de ese día (o de su semana, quincena o mes) se pide a la vez que el detalle del día, sin esperarlo.
        this.cargarCobros();
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
