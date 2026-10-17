/**
 * «Inicio»: cómo va el día en D'CASA, en una pantalla.
 *
 * Las cifras vienen de dcasa.tablero.obtener_datos (respetan los permisos de quien mira)
 * y cada una abre la lista que la explica. Debajo, los accesos del día a día y las apps.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const ICONOS = {
    ventas_hoy: "fa-shopping-bag",
    cobrado_hoy: "fa-money",
    cotizaciones: "fa-file-text-o",
    mis_cotizaciones: "fa-user-o",
    web: "fa-globe",
    por_cobrar: "fa-clock-o",
    entregas: "fa-truck",
    socios: "fa-star",
};

const PERIODOS = [
    { clave: "hoy", nombre: "Hoy" },
    { clave: "semana", nombre: "Esta semana" },
    { clave: "mes", nombre: "Este mes" },
    { clave: "rango", nombre: "Un rango" },
];

export class DcasaInicio extends Component {
    static template = "dcasa_interfaz.Inicio";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.menu = useService("menu");
        this.periodos = PERIODOS;
        this.state = useState({
            datos: null,
            periodo: "hoy",
            desde: "",
            hasta: "",
            errorRango: "",
            cargandoVentas: false,
            // El interruptor «Completadas» / «Con abonos» y la vendedora (Gerencia): abren en «Completadas» y
            // «Todo el equipo» ("" en el selector; "sin" = sin vendedora; si no, el id).
            base: "completadas",
            vendedor: "",
            // El bloque «Comparar» (solo Gerencia): el botón elegido y lo que devolvió el servidor.
            cmp: {
                clave: null,
                datos: null,
                cargando: false,
                error: "",
                mes: "",
                aDesde: "",
                aHasta: "",
                bDesde: "",
                bHasta: "",
                libre: false,
                porVendedora: false,
            },
        });
        onWillStart(() => this.cargar());
    }

    async cargar() {
        this.state.datos = await this.orm.call("dcasa.tablero", "obtener_datos", []);
    }

    get apps() {
        return this.menu.getApps().filter((app) => app.xmlid !== "dcasa_interfaz.menu_dcasa_inicio");
    }

    get hoyIso() {
        const ahora = new Date();
        const mes = String(ahora.getMonth() + 1).padStart(2, "0");
        const dia = String(ahora.getDate()).padStart(2, "0");
        return `${ahora.getFullYear()}-${mes}-${dia}`;
    }

    /** Cambia el periodo de las ventas (Hoy · Esta semana · Este mes) y pide solo esa tarjeta al servidor. */
    async cambiarPeriodo(periodo) {
        this.state.periodo = periodo;
        this.state.errorRango = "";
        if (periodo === "rango") {
            if (!this.state.desde || !this.state.hasta) {
                this.state.desde = this.state.desde || this.hoyIso;
                this.state.hasta = this.state.hasta || this.hoyIso;
            }
            return this.aplicarRango();
        }
        await this.cargarVentas(periodo);
    }

    async aplicarRango() {
        if (!this.state.desde || !this.state.hasta || this.state.desde > this.state.hasta) {
            this.state.errorRango = "Escribe un rango válido: «desde» no puede ser después de «hasta».";
            return;
        }
        this.state.errorRango = "";
        await this.cargarVentas("rango", this.state.desde, this.state.hasta);
    }

    async cargarVentas(periodo, desde = false, hasta = false) {
        this.state.cargandoVentas = true;
        try {
            this.state.datos.ventas = await this.orm.call("dcasa.tablero", "ventas_del_periodo", [
                periodo,
                desde,
                hasta,
                this.state.base,
                this.vendedorParaElServidor,
            ]);
        } catch (error) {
            this.state.errorRango = error?.data?.message || "No se pudieron cargar las ventas.";
        } finally {
            this.state.cargandoVentas = false;
        }
    }

    /** Vuelve a pedir la tarjeta de ventas con el mismo periodo (al cambiar la base o la vendedora). */
    recargarVentas() {
        if (this.state.periodo === "rango") {
            return this.aplicarRango();
        }
        return this.cargarVentas(this.state.periodo);
    }

    // ------------------------------------------------------------------
    // Interruptor «Completadas» / «Con abonos» y vendedora (Gerencia)
    // ------------------------------------------------------------------

    get vendedorParaElServidor() {
        const v = this.state.vendedor;
        if (!v) {
            return false;
        }
        return v === "sin" ? "sin" : parseInt(v, 10);
    }

    vendedorElegido(opcion) {
        return this.state.vendedor === String(opcion.id);
    }

    get detalleBase() {
        const base = (this.state.datos.bases || []).find((b) => b.clave === this.state.base);
        return base ? base.detalle : "";
    }

    async cambiarBase(clave) {
        if (clave === this.state.base) {
            return;
        }
        this.state.base = clave;
        await Promise.all([this.recargarVentas(), this.recargarComparacion()]);
    }

    async cambiarVendedor(ev) {
        this.state.vendedor = ev.target.value;
        await Promise.all([this.recargarVentas(), this.recargarComparacion()]);
    }

    // ------------------------------------------------------------------
    // Comparar (Gerencia): cada botón es una comparación completa, A contra B
    // ------------------------------------------------------------------

    /** Suma o resta días a una fecha «aaaa-mm-dd» (sin horas: no depende de la zona del navegador). */
    moverDias(iso, dias) {
        const [a, m, d] = iso.split("-").map((x) => parseInt(x, 10));
        const fecha = new Date(Date.UTC(a, m - 1, d + dias));
        return fecha.toISOString().slice(0, 10);
    }

    get hoyComparar() {
        return this.state.datos.comparar?.hoy || this.hoyIso;
    }

    async elegirComparacion(clave) {
        const cmp = this.state.cmp;
        if (cmp.clave === clave) {
            // Tocar otra vez el mismo botón cierra la tabla.
            cmp.clave = null;
            cmp.datos = null;
            cmp.error = "";
            return;
        }
        cmp.clave = clave;
        cmp.datos = null;
        cmp.error = "";
        if (clave === "mes" && !cmp.mes) {
            cmp.mes = this.state.datos.comparar.meses[0]?.valor || "";
        }
        if (clave === "rango" && !cmp.aDesde) {
            // Para empezar: los últimos 7 días contra los 7 anteriores. Se cambian en el calendario.
            cmp.aHasta = this.hoyComparar;
            cmp.aDesde = this.moverDias(cmp.aHasta, -6);
            cmp.bDesde = this.moverDias(cmp.aDesde, -7);
            cmp.bHasta = this.moverDias(cmp.aDesde, -1);
        }
        await this.cargarComparacion();
    }

    async recargarComparacion() {
        if (this.state.cmp.clave) {
            await this.cargarComparacion();
        }
    }

    async cambiarMes(ev) {
        this.state.cmp.mes = ev.target.value;
        await this.cargarComparacion();
    }

    async alternarLibre(ev) {
        const cmp = this.state.cmp;
        cmp.libre = ev.target.checked;
        if (cmp.libre && !cmp.bHasta) {
            cmp.bHasta = cmp.bDesde;
        }
    }

    async aplicarRangoComparar() {
        const cmp = this.state.cmp;
        const hoy = this.hoyComparar;
        const fechas = [cmp.aDesde, cmp.aHasta, cmp.bDesde].concat(cmp.libre ? [cmp.bHasta] : []);
        if (fechas.some((f) => !f)) {
            cmp.error = "Escribe las fechas completas.";
            return;
        }
        if (fechas.some((f) => f > hoy)) {
            cmp.error = "Elige fechas de hoy hacia atrás.";
            return;
        }
        if (cmp.aDesde > cmp.aHasta || (cmp.libre && cmp.bDesde > cmp.bHasta)) {
            cmp.error = "«Desde» no puede ser después de «hasta».";
            return;
        }
        await this.cargarComparacion();
    }

    async alternarPorVendedora() {
        this.state.cmp.porVendedora = !this.state.cmp.porVendedora;
        if (this.state.cmp.porVendedora) {
            await this.cargarComparacion();
        }
    }

    /** Al tocar una fila de «Por vendedora», el selector queda en esa vendedora. */
    async elegirVendedora(fila) {
        this.state.vendedor = String(fila.vendedor);
        this.state.cmp.porVendedora = false;
        await Promise.all([this.recargarVentas(), this.cargarComparacion()]);
    }

    async cargarComparacion() {
        const cmp = this.state.cmp;
        const clave = cmp.clave;
        if (!clave) {
            return;
        }
        cmp.cargando = true;
        cmp.error = "";
        const opciones = {
            base: this.state.base,
            vendedor: this.vendedorParaElServidor,
            por_vendedora: cmp.porVendedora,
        };
        if (clave === "mes") {
            opciones.mes = cmp.mes;
        }
        if (clave === "rango") {
            Object.assign(opciones, {
                a_desde: cmp.aDesde,
                a_hasta: cmp.aHasta,
                b_desde: cmp.bDesde,
                b_hasta: cmp.libre ? cmp.bHasta : false,
                libre: cmp.libre,
            });
        }
        try {
            const datos = await this.orm.call("dcasa.tablero", "comparar_ventas", [clave], opciones);
            if (cmp.clave === clave) {
                cmp.datos = datos;
                if (clave === "rango" && !cmp.libre) {
                    cmp.bHasta = datos.b.hasta;
                }
            }
        } catch (error) {
            cmp.datos = null;
            cmp.error = error?.data?.message || "No se pudo comparar.";
        } finally {
            cmp.cargando = false;
        }
    }

    /** Un número de la tabla: «$1,234.56», «34.4 %» o «6»; sin dato, «—». */
    valorFila(fila, valor) {
        if (valor === null || valor === undefined) {
            return "—";
        }
        if (fila.formato === "moneda") {
            return this.dinero(valor);
        }
        if (fila.formato === "porcentaje") {
            return `${this.numero(valor, 1)} %`;
        }
        return this.numero(valor, 0);
    }

    numero(valor, decimales) {
        return new Intl.NumberFormat("en-US", {
            minimumFractionDigits: decimales,
            maximumFractionDigits: decimales,
        }).format(valor);
    }

    /** «▲ 27.6 %», «▼ 5.4 pts», «▲ 1», «58.3 %» (Llevas); sin base positiva, «—» (nunca se inventa un porcentaje). */
    cambioTexto(c) {
        if (!c || c.valor === null || c.valor === undefined) {
            return "—";
        }
        if (c.tipo === "llevas") {
            return `${this.numero(c.valor, 1)} %`;
        }
        const flecha = c.sentido === "sube" ? "▲ " : c.sentido === "baja" ? "▼ " : "";
        const decimales = c.tipo === "num" ? 0 : 1;
        const unidad = c.tipo === "pct" ? " %" : c.tipo === "pts" ? " pts" : "";
        return `${flecha}${this.numero(Math.abs(c.valor), decimales)}${unidad}`;
    }

    /** Azul si sube, rojo si baja; en «Falta por cobrar» al revés (que suba es malo). */
    cambioClase(c) {
        if (!c || !c.sentido || c.sentido === "igual" || c.tipo === "llevas") {
            return "o_igual";
        }
        const bueno = (c.sentido === "sube") !== Boolean(c.invertido);
        return bueno ? "o_bien" : "o_mal";
    }

    get cabeceraCambio() {
        const modo = this.state.cmp.datos?.modo;
        return modo === "llevas" ? "Llevas" : modo === "por_dia" ? "% por día" : "";
    }

    get llevasTexto() {
        const llevas = this.state.cmp.datos?.llevas;
        if (!llevas) {
            return "";
        }
        const pct = llevas.pct === null ? "—" : `${this.numero(Math.round(llevas.pct), 0)} %`;
        return `Llevas ${pct} de ${llevas.mes}`;
    }

    /** «hace 3 días» para las listas de cotizaciones y entregas. */
    espera(dias) {
        if (!dias) {
            return "de hoy";
        }
        return dias === 1 ? "hace 1 día" : `hace ${dias} días`;
    }

    get maxSemana() {
        return Math.max(1, ...this.state.datos.semana.map((d) => d.monto));
    }

    icono(cifra) {
        return ICONOS[cifra.clave] || "fa-circle";
    }

    dinero(valor) {
        const { simbolo, antes } = this.state.datos.moneda;
        const numero = new Intl.NumberFormat("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }).format(valor || 0);
        return antes ? `${simbolo}${numero}` : `${numero} ${simbolo}`;
    }

    cifra(c) {
        return c.formato === "moneda" ? this.dinero(c.valor) : new Intl.NumberFormat("en-US").format(c.valor);
    }

    abrirCifra(c) {
        this.abrirLista(c.accion);
    }

    /** Abre la lista que explica una cifra o un aviso. */
    abrirLista(a) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: a.name,
            res_model: a.res_model,
            domain: a.domain,
            // Una lista puede pedir su vista (p. ej. la de facturas, con los montos sin ITBMS).
            views: [
                [a.vista_lista || false, "list"],
                [false, "form"],
            ],
        });
    }

    /** Abre una cotización o una entrega concreta (las filas de las listas del Inicio). */
    abrirRegistro(modelo, id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: modelo,
            res_id: id,
            views: [[false, "form"]],
        });
    }

    iconoApp(app) {
        const data = app.webIconData;
        if (!data || data.startsWith("data:") || data.startsWith("/")) {
            return data;
        }
        return `data:${app.webIconDataMimetype || "image/svg+xml"};base64,${data.replace(/\s/g, "")}`;
    }

    abrirApp(app) {
        this.menu.selectMenu(app);
    }

    nuevo(modelo, contexto = {}) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: modelo,
            views: [[false, "form"]],
            context: contexto,
        });
    }

    /** «¿Qué necesito hacer?»: la Guía del negocio (módulo dcasa_guia). */
    abrirGuia() {
        // Por su menú, para que la barra de arriba y la de la izquierda digan «Guía» y no «Inicio».
        const menu = this.menu.getAll().find((m) => m.xmlid === "dcasa_guia.menu_guia");
        if (menu) {
            this.menu.selectMenu(menu);
        } else {
            this.action.doAction("dcasa_guia.accion_guia", { clearBreadcrumbs: true });
        }
    }

    /** Un acceso directo del Inicio: abre su pantalla (en la vista que dice el servidor, p. ej. lista). */
    abrirAtajo(atajo) {
        this.action.doAction(atajo.accion, atajo.vista ? { viewType: atajo.vista } : {});
    }

    abrirProducto(p) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.template",
            res_id: p.id,
            views: [[false, "form"]],
        });
    }

    verTienda() {
        window.open("/shop", "_blank");
    }

}

registry.category("actions").add("dcasa_inicio", DcasaInicio);
