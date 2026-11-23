/**
 * «Rotación» (pedido de Gerencia, 2026-11-22): qué productos no se mueven, cuánto capital hay parado en ellos y qué
 * conviene hacer, medido en días sin vender y en flujo de ventas.
 *
 * Arriba: el resumen (capital parado, cuántos productos y cuántos son «ancla»). Luego una escalera por días sin vender
 * (menos de 30, 30 a 59, 60 a 89, 90 a 179, 180 o más, nunca vendido, nuevos y con pedido abierto): tocar una barra
 * filtra la lista. La lista se puede ordenar, buscar y filtrar por categoría; con «Si se rebaja» se simula el descuento
 * (sin cambiar ningún precio). Las cifras las calcula el servidor (dcasa.rotacion); aquí solo se dibujan. El dinero
 * (capital, costos, márgenes) solo llega a Gerencia y administradores: el rol Marketing ve unidades y días.
 */
import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { abrirFotos } from "./fotos_dialogo";

const ESPERA_AL_ESCRIBIR = 350;

export class DcasaRotacion extends Component {
    static template = "dcasa_marketing.Rotacion";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialogo = useService("dialog");
        this.raiz = useRef("raiz");
        this.state = useState({
            cargando: true,
            error: null,
            vista: "mas_de_90",
            categoria: null,
            texto: "",
            orden: null,
            rebaja: "",
            datos: null,
        });
        this.peticion = 0;
        this.espera = null;
        onWillStart(() => this.cargar());
    }

    get datos() {
        return this.state.datos;
    }

    // --- Pedir al servidor ---------------------------------------------------------------------------------------
    get parametros() {
        const s = this.state;
        return {
            vista: s.vista,
            categoria: s.categoria,
            texto: s.texto,
            orden: s.orden,
            rebaja: s.rebaja === "" ? null : s.rebaja,
        };
    }

    async cargar() {
        const numeroPeticion = ++this.peticion;
        this.state.cargando = true;
        this.state.error = null;
        try {
            const datos = await this.orm.call("dcasa.rotacion", "datos", [], this.parametros);
            if (numeroPeticion === this.peticion) {
                this.state.datos = datos;
                // El servidor corrige el orden (sin dinero no hay «más capital»): se muestra el que se usó.
                this.state.orden = datos.orden;
            }
        } catch (error) {
            if (numeroPeticion === this.peticion) {
                this.state.error = error?.data?.message || "No se pudo cargar la rotación. Intenta otra vez.";
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
    elegirVista(clave) {
        if (this.state.vista !== clave) {
            this.state.vista = clave;
            this.cargar();
        }
    }

    elegirVistaYBajar(clave) {
        this.elegirVista(clave);
        this.raiz.el?.querySelector('[data-seccion="lista"]')?.scrollIntoView({ behavior: "smooth", block: "start" });
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

    alRebajar(ev) {
        this.state.rebaja = ev.target.value;
        this.cargarPronto();
    }

    abrirMovimiento() {
        this.action.doAction("dcasa_marketing.accion_movimiento");
    }

    quitarRebaja() {
        this.state.rebaja = "";
        this.cargar();
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

    /** Lo que vendió en 30, 60 y 90 días: «0 · 2 · 5». */
    ritmo(fila) {
        return [fila.vendidas_30, fila.vendidas_60, fila.vendidas_90].map((u) => this.unidades(u)).join(" · ");
    }

    nombreDeGrupo(clave) {
        return (this.datos?.tarjetas || []).find((t) => t.clave === clave)?.nombre || "Agotado";
    }

    /** El ancho de la barra de un grupo, de 3 a 100 %: por capital con dinero y, sin dinero, por productos. */
    ancho(tarjeta) {
        const tarjetas = this.datos.tarjetas;
        const campo = this.datos.con_dinero ? "capital" : "productos";
        const maximo = Math.max(1, ...tarjetas.map((t) => t[campo] || 0));
        return tarjeta[campo] > 0 ? Math.max(3, Math.round((tarjeta[campo] / maximo) * 100)) : 0;
    }

    get vistaActual() {
        return (this.datos?.vistas || []).find((v) => v.clave === this.datos?.vista);
    }

    /** Los botones de días sin vender, y aparte (solo con dinero) los de margen y rotación. */
    get vistasDeDias() {
        return (this.datos?.vistas || []).filter((v) => v.tipo !== "margen");
    }

    get vistasDeMargen() {
        return (this.datos?.vistas || []).filter((v) => v.tipo === "margen");
    }

    get categoriaElegida() {
        return (this.datos?.categorias || []).find((c) => c.id === this.datos.categoria) || null;
    }

    get ordenes() {
        const todas = [
            { clave: "capital", nombre: "Más capital parado", dinero: true },
            { clave: "dias", nombre: "Más días sin vender" },
            { clave: "rotacion", nombre: "Mejor rotación (90 días)" },
            { clave: "margen", nombre: "Mejor margen", dinero: true },
            { clave: "cobertura", nombre: "Se agota primero" },
            { clave: "nombre", nombre: "Nombre (A a Z)" },
        ];
        return todas.filter((o) => !o.dinero || this.datos?.con_dinero);
    }

    get urlExcel() {
        const s = this.state;
        const parametros = new URLSearchParams({ vista: s.vista });
        if (s.categoria) {
            parametros.set("categoria", s.categoria);
        }
        if (s.texto) {
            parametros.set("texto", s.texto);
        }
        if (s.orden) {
            parametros.set("orden", s.orden);
        }
        if (s.rebaja !== "" && this.datos?.rebaja) {
            parametros.set("rebaja", this.datos.rebaja);
        }
        return `/dcasa/rotacion/excel?${parametros.toString()}`;
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
        const nombre = `Rotación · ${this.vistaActual?.nombre || "productos"}`;
        const accion = await this.orm.call("dcasa.marketing", "accion_productos", [], {
            ids: this.datos.ids,
            nombre,
        });
        this.action.doAction(accion, { viewType: "list" });
    }
}

registry.category("actions").add("dcasa_rotacion", DcasaRotacion);
