/**
 * «Movimiento» (pedido de la dueña, 2026-11-22): lo que más y lo que menos se mueve, comparando dos periodos, para
 * decidir qué anunciar en publicidad y redes.
 *
 * Arriba se elige el periodo (7, 15, 30, 60 o 90 días, este mes, el mes pasado o fechas a mano) y contra qué se compara
 * (el periodo de justo antes, el mismo del año pasado o fechas a mano). Debajo: el resumen (unidades, pedidos y
 * productos; el dinero solo para Gerencia y administradores), un gráfico de ventas por día o semana y la lista de
 * productos con su estado (subió, despertó, igual, bajó, se enfrió o quieto). Las cifras las calcula el servidor
 * (dcasa.movimiento_productos); aquí solo se dibujan.
 */
import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { abrirFotos } from "./fotos_dialogo";

const ESPERA_AL_ESCRIBIR = 350;
// Para qué sirve cada lista (frases de la pantalla; no son cifras).
const PARA_QUE_SIRVE = {
    venden: "Buenos para anunciar: la gente ya los busca. Revisa que alcance lo que hay antes de lanzar la campaña.",
    subieron: "Están calientes: aprovéchalos con publicaciones antes de que se enfríen.",
    bajaron: "Se venden menos que antes: una foto nueva, un video o una promoción pueden ayudar.",
    enfriaron: "Antes se vendían y ahora no: revisa si falta foto, precio o existencias, o si toca una promoción.",
    quietos: "Tienen existencias y no se mueven. En Rotación ves cuánto capital hay parado.",
    todos: "Todos los productos que se vendieron en alguno de los dos periodos o que tienen existencias.",
};
// Con qué tema de Camila se arma la campaña de cada lista.
const TEMA_DE_CAMILA = {
    venden: "vendidos",
    subieron: "vendidos",
    bajaron: "movimiento",
    enfriaron: "quietos",
    quietos: "quietos",
    todos: "movimiento",
};
const PRODUCTOS_POR_CAMPANA = 8;
// Los botones de arriba mientras llega la primera respuesta del servidor (si falla, igual se dibujan).
const PERIODOS_INICIALES = [
    { clave: "7", nombre: "Últimos 7 días" },
    { clave: "15", nombre: "Últimos 15 días" },
    { clave: "30", nombre: "Últimos 30 días" },
    { clave: "60", nombre: "Últimos 60 días" },
    { clave: "90", nombre: "Últimos 90 días" },
    { clave: "este_mes", nombre: "Este mes" },
    { clave: "mes_pasado", nombre: "Mes pasado" },
    { clave: "fechas", nombre: "Elegir fechas" },
];
const CONTRAS_INICIALES = [
    { clave: "anterior", nombre: "El periodo de justo antes" },
    { clave: "anio", nombre: "El mismo periodo del año pasado" },
    { clave: "fechas", nombre: "Elegir fechas" },
];

export class DcasaMovimiento extends Component {
    static template = "dcasa_marketing.Movimiento";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialogo = useService("dialog");
        this.raiz = useRef("raiz");
        this.state = useState({
            cargando: true,
            error: null,
            periodo: "30",
            contra: "anterior",
            desde: "",
            hasta: "",
            contraDesde: "",
            contraHasta: "",
            vista: "venden",
            categoria: null,
            texto: "",
            orden: null,
            datos: null,
        });
        this.peticion = 0;
        this.espera = null;
        onWillStart(() => this.cargar());
    }

    get datos() {
        return this.state.datos;
    }

    get periodosIniciales() {
        return PERIODOS_INICIALES;
    }

    get contrasIniciales() {
        return CONTRAS_INICIALES;
    }

    // --- Pedir al servidor ---------------------------------------------------------------------------------------
    get parametros() {
        const s = this.state;
        return {
            periodo: s.periodo,
            contra: s.contra,
            desde: s.periodo === "fechas" ? s.desde || null : null,
            hasta: s.periodo === "fechas" ? s.hasta || null : null,
            contra_desde: s.contra === "fechas" ? s.contraDesde || null : null,
            contra_hasta: s.contra === "fechas" ? s.contraHasta || null : null,
            vista: s.vista,
            categoria: s.categoria,
            texto: s.texto,
            orden: s.orden,
        };
    }

    /** Con «Elegir fechas» no se pide nada hasta tener las dos fechas de cada tramo. */
    get faltanFechas() {
        const s = this.state;
        return (s.periodo === "fechas" && !(s.desde && s.hasta)) || (s.contra === "fechas" && !(s.contraDesde && s.contraHasta));
    }

    async cargar() {
        if (this.faltanFechas) {
            return;
        }
        const numeroPeticion = ++this.peticion;
        this.state.cargando = true;
        this.state.error = null;
        try {
            const datos = await this.orm.call("dcasa.movimiento_productos", "datos", [], this.parametros);
            if (numeroPeticion === this.peticion) {
                this.state.datos = datos;
                // El servidor corrige el orden (sin dinero no hay «más capital»): se muestra el que se usó.
                this.state.orden = datos.orden;
            }
        } catch (error) {
            if (numeroPeticion === this.peticion) {
                this.state.error = error?.data?.message || "No se pudo cargar el movimiento. Intenta otra vez.";
            }
        } finally {
            if (numeroPeticion === this.peticion) {
                this.state.cargando = false;
            }
        }
    }

    cargarPronto() {
        clearTimeout(this.espera);
        this.espera = setTimeout(() => this.cargar(), ESPERA_AL_ESCRIBIR);
    }

    // --- Lo que elige la persona ---------------------------------------------------------------------------------
    elegirPeriodo(clave) {
        this.state.periodo = clave;
        this.cargar();
    }

    elegirContra(clave) {
        this.state.contra = clave;
        this.cargar();
    }

    cambiarFecha(campo, ev) {
        this.state[campo] = ev.target.value;
        this.cargar();
    }

    elegirVista(clave) {
        if (this.state.vista !== clave) {
            this.state.vista = clave;
            // Cada lista trae su propio orden: se vuelve al que le toca.
            this.state.orden = null;
            this.cargar();
        }
    }

    elegirCategoria(id) {
        this.state.categoria = this.state.categoria === id ? null : id;
        this.cargar();
    }

    alBuscar(ev) {
        this.state.texto = ev.target.value;
        this.cargarPronto();
    }

    elegirOrden(ev) {
        this.state.orden = ev.target.value;
        this.cargar();
    }

    abrirRotacion() {
        this.action.doAction("dcasa_marketing.accion_rotacion");
    }

    // --- Cómo se dicen las cosas ---------------------------------------------------------------------------------
    dinero(valor) {
        const moneda = this.datos?.moneda || { simbolo: "$", antes: true };
        const numero = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(
            Math.abs(valor || 0)
        );
        const signo = (valor || 0) < 0 ? "-" : "";
        return moneda.antes ? `${signo}${moneda.simbolo}${numero}` : `${signo}${numero} ${moneda.simbolo}`;
    }

    numero(valor) {
        return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(valor || 0);
    }

    unidades(valor) {
        return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(valor || 0);
    }

    productosTexto(cuantos) {
        return `${this.numero(cuantos)} ${cuantos === 1 ? "producto" : "productos"}`;
    }

    /** «+12», «-3» o «0»: lo que cambió. */
    cambio(valor) {
        if (!valor) {
            return "0";
        }
        return `${valor > 0 ? "+" : "−"}${this.unidades(Math.abs(valor))}`;
    }

    /** «+22 %», «−10 %» o «—» (no hay con qué comparar). */
    porcentaje(valor) {
        if (valor === null || valor === undefined) {
            return "—";
        }
        return `${valor > 0 ? "+" : valor < 0 ? "−" : ""}${new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(Math.abs(valor))} %`;
    }

    claseDeCambio(valor) {
        return valor > 0 ? "o_dcasa_mv_sube" : valor < 0 ? "o_dcasa_mv_baja" : "";
    }

    diasTexto(dias) {
        if (dias === null || dias === undefined) {
            return "Nunca";
        }
        if (dias === 0) {
            return "Hoy";
        }
        return `hace ${dias} ${dias === 1 ? "día" : "días"}`;
    }

    cobertura(fila) {
        return fila.cobertura_dias === null ? "—" : `${this.numero(fila.cobertura_dias)} días`;
    }

    get paraQueSirve() {
        return PARA_QUE_SIRVE[this.datos?.vista] || "";
    }

    get vistaActual() {
        return (this.datos?.vistas || []).find((v) => v.clave === this.datos?.vista);
    }

    get categoriaElegida() {
        return (this.datos?.categorias || []).find((c) => c.id === this.datos.categoria) || null;
    }

    get ordenes() {
        const todas = [
            { clave: "ventas", nombre: "Más vendidos en este periodo" },
            { clave: "cambio", nombre: "Los que más subieron" },
            { clave: "baja", nombre: "Los que más bajaron" },
            { clave: "antes", nombre: "Los que más vendían antes" },
            { clave: "dias", nombre: "Más días sin vender" },
            { clave: "cobertura", nombre: "Se agotan primero" },
            { clave: "capital", nombre: "Más capital parado", dinero: true },
            { clave: "nombre", nombre: "Nombre (A a Z)" },
        ];
        return todas.filter((o) => !o.dinero || this.datos?.con_dinero);
    }

    get lineasDeResumen() {
        const r = this.datos.resumen;
        const lineas = [
            { clave: "unidades", nombre: "Unidades vendidas", dato: r.unidades, formato: (v) => this.unidades(v) },
            { clave: "pedidos", nombre: "Pedidos (facturas)", dato: r.pedidos, formato: (v) => this.numero(v) },
            { clave: "productos", nombre: "Productos que se vendieron", dato: r.productos, formato: (v) => this.numero(v) },
        ];
        if (this.datos.con_dinero && r.monto) {
            lineas.push({ clave: "monto", nombre: "Vendido (sin ITBMS)", dato: r.monto, formato: (v) => this.dinero(v) });
        }
        return lineas;
    }

    get hayCategoria() {
        return !!this.state.categoria;
    }

    /** El gráfico de ventas: dos líneas del mismo largo, este periodo y el de comparación. */
    get grafico() {
        const g = this.datos?.grafico;
        if (!g) {
            return null;
        }
        const ancho = 760;
        const alto = 190;
        const izq = 44;
        const der = 12;
        const arriba = 12;
        const abajo = 28;
        const valores = [...g.este, ...g.otro].filter((v) => v !== null);
        const maximo = Math.max(1, ...valores);
        const minimo = Math.min(0, ...valores);
        const rango = maximo - minimo || 1;
        const n = g.este.length;
        const x = (i) => izq + (n <= 1 ? (ancho - izq - der) / 2 : (i * (ancho - izq - der)) / (n - 1));
        const y = (v) => arriba + ((maximo - v) * (alto - arriba - abajo)) / rango;
        const camino = (serie) => {
            let d = "";
            let enTrazo = false;
            serie.forEach((v, i) => {
                if (v === null) {
                    enTrazo = false;
                    return;
                }
                d += `${enTrazo ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)} `;
                enTrazo = true;
            });
            return d.trim();
        };
        const puntos = (serie, tipo) =>
            n <= 40
                ? serie.map((v, i) => (v === null ? null : { x: x(i), y: y(v), v, fecha: g[tipo][i] })).filter(Boolean)
                : [];
        // Nombres de las marcas de abajo: más o menos seis, repartidas.
        const paso = Math.max(1, Math.ceil(n / 6));
        const marcas = g.fechas_este
            .map((fecha, i) => ({ x: x(i), fecha }))
            .filter((_m, i) => i % paso === 0 || i === n - 1);
        return {
            ancho,
            alto,
            izq,
            der,
            abajo,
            maximo,
            cero: y(0),
            arriba: y(maximo),
            este: camino(g.este),
            otro: camino(g.otro),
            puntosEste: puntos(g.este, "fechas_este"),
            puntosOtro: puntos(g.otro, "fechas_otro"),
            marcas,
            porSemana: g.por === "semana",
        };
    }

    /** «2026-11-05» → «5/11». */
    diaCorto(fecha) {
        const [, mes, dia] = (fecha || "").split("-");
        return dia ? `${Number(dia)}/${Number(mes)}` : "";
    }

    get urlExcel() {
        const parametros = new URLSearchParams();
        for (const [clave, valor] of Object.entries(this.parametros)) {
            if (valor !== null && valor !== undefined && valor !== "") {
                parametros.set(clave, valor);
            }
        }
        return `/dcasa/movimiento/excel?${parametros.toString()}`;
    }

    /** La lista con la que Camila arma la campaña: los primeros que se pueden ofrecer. */
    get paraCampana() {
        return (this.datos?.productos || []).slice(0, PRODUCTOS_POR_CAMPANA);
    }

    get temaDeCamila() {
        return TEMA_DE_CAMILA[this.datos?.vista] || "movimiento";
    }

    // --- Productos -----------------------------------------------------------------------------------------------
    verFotos(fila) {
        abrirFotos(this.dialogo, {
            plantillaId: fila.id,
            modo: fila.con_foto ? "visor" : "galeria",
            alCambiar: () => this.cargar(),
        });
    }

    abrirProducto(fila) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.template",
            res_id: fila.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async abrirEnProductos() {
        const nombre = `Movimiento · ${this.vistaActual?.nombre || "productos"}`;
        const accion = await this.orm.call("dcasa.marketing", "accion_productos", [], {
            ids: this.datos.ids,
            nombre,
        });
        this.action.doAction(accion, { viewType: "list" });
    }
}

registry.category("actions").add("dcasa_movimiento", DcasaMovimiento);
