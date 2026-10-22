/**
 * «Marketing» (pedido de la dueña, 2026-10-22): qué empujar en una campaña, en una sola pantalla.
 *
 * Arriba se elige el periodo (Semana, 15 días o Mes: días corridos, hoy incluido) y, si se quiere, una categoría; todas
 * las secciones se filtran con eso: stock (más y menos), más vendidos, mayor movimiento, más quietos y «Fotos» (buscar
 * un producto y subirle sus fotos ahí mismo). Las cifras las calcula el servidor (dcasa.marketing); aquí solo se dibujan.
 * Tocar la foto de un producto la abre en grande; tocar su nombre abre el producto.
 */
import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { abrirFotos } from "./fotos_dialogo";

function numero(valor) {
    if (valor === null || valor === undefined) {
        return "—";
    }
    const redondo = Math.round(valor * 100) / 100;
    return Number.isInteger(redondo) ? String(redondo) : redondo.toFixed(2);
}

export class DcasaMarketing extends Component {
    static template = "dcasa_marketing.Marketing";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialogo = useService("dialog");
        this.buscador = useRef("buscador");
        this.raiz = useRef("raiz");
        this.secciones = [
            { clave: "stock", nombre: "Stock", icono: "fa-cubes" },
            { clave: "vendidos", nombre: "Más vendidos", icono: "fa-trophy" },
            { clave: "movimiento", nombre: "Movimiento", icono: "fa-exchange" },
            { clave: "quietos", nombre: "Quietos", icono: "fa-pause-circle-o" },
            { clave: "fotos", nombre: "Fotos", icono: "fa-camera" },
        ];
        this.numero = numero;
        this.state = useState({
            cargando: true,
            error: null,
            periodo: "semana",
            categoria: null,
            datos: null,
            fotos: { texto: "", filtro: "faltan", cargando: false, resultado: null, error: null },
        });
        this.peticion = 0;
        this.peticionFotos = 0;
        this.espera = null;
        onWillStart(() => Promise.all([this.cargar(), this.buscarFotos()]));
    }

    get datos() {
        return this.state.datos;
    }

    get categoriaElegida() {
        return (this.datos?.categorias || []).find((c) => c.id === this.state.categoria) || null;
    }

    // --- Lo de arriba: periodo y categoría -----------------------------------------------------------------------
    async cargar() {
        const numeroPeticion = ++this.peticion;
        this.state.cargando = true;
        this.state.error = null;
        try {
            const datos = await this.orm.call("dcasa.marketing", "datos", [], {
                periodo: this.state.periodo,
                categoria: this.state.categoria,
            });
            if (numeroPeticion === this.peticion) {
                this.state.datos = datos;
            }
        } catch (error) {
            if (numeroPeticion === this.peticion) {
                this.state.error = error?.data?.message || "No se pudo cargar Marketing. Intenta otra vez.";
            }
        } finally {
            if (numeroPeticion === this.peticion) {
                this.state.cargando = false;
            }
        }
    }

    elegirPeriodo(clave) {
        if (this.state.periodo !== clave) {
            this.state.periodo = clave;
            this.cargar();
        }
    }

    elegirCategoria(id) {
        this.state.categoria = this.state.categoria === id ? null : id;
        this.cargar();
        this.buscarFotos();
    }

    irA(clave) {
        const seccion = this.raiz.el?.querySelector(`[data-seccion="${clave}"]`);
        if (seccion) {
            seccion.scrollIntoView({ behavior: "smooth", block: "start" });
            if (clave === "fotos") {
                this.buscador.el?.focus({ preventScroll: true });
            }
        }
    }

    // --- Productos -----------------------------------------------------------------------------------------------
    verFotos(fila, modo = "visor") {
        abrirFotos(this.dialogo, {
            plantillaId: fila.id,
            modo: fila.con_foto ? modo : "galeria",
            alCambiar: () => {
                this.cargar();
                this.buscarFotos();
            },
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

    async abrirLista(ids, nombre) {
        const accion = await this.orm.call("dcasa.marketing", "accion_productos", [], { ids, nombre });
        this.action.doAction(accion, { viewType: "list" });
    }

    abrirCampanas() {
        this.action.doAction("sale.product_template_action", { viewType: "list" });
    }

    detalleQuieto(fila) {
        if (!fila.ultima_venta) {
            return "Sin ventas registradas";
        }
        const dias = fila.dias_sin_vender;
        return `Última venta: ${fila.ultima_venta_texto}` + (dias ? ` (hace ${dias} ${dias === 1 ? "día" : "días"})` : "");
    }

    // --- Fotos ---------------------------------------------------------------------------------------------------
    async buscarFotos() {
        const f = this.state.fotos;
        const numeroPeticion = ++this.peticionFotos;
        f.cargando = true;
        f.error = null;
        try {
            const resultado = await this.orm.call("dcasa.marketing", "buscar_fotos", [], {
                texto: f.texto,
                filtro: f.filtro,
                categoria: this.state.categoria,
            });
            if (numeroPeticion === this.peticionFotos) {
                f.resultado = resultado;
            }
            return resultado;
        } catch (error) {
            if (numeroPeticion === this.peticionFotos) {
                f.error = error?.data?.message || "No se pudo buscar. Intenta otra vez.";
            }
        } finally {
            if (numeroPeticion === this.peticionFotos) {
                f.cargando = false;
            }
        }
    }

    alEscribir(ev) {
        this.state.fotos.texto = ev.target.value;
        clearTimeout(this.espera);
        this.espera = setTimeout(() => this.buscarFotos(), 300);
    }

    async alTeclear(ev) {
        // El lector de códigos escribe el código y termina con Enter: si sale un solo producto, se abren sus fotos.
        if (ev.key !== "Enter") {
            return;
        }
        ev.preventDefault();
        clearTimeout(this.espera);
        this.state.fotos.texto = ev.target.value;
        const resultado = await this.buscarFotos();
        if (resultado && resultado.productos.length === 1) {
            this.verFotos(resultado.productos[0], "galeria");
        }
    }

    elegirFiltro(filtro) {
        this.state.fotos.filtro = filtro;
        this.buscarFotos();
    }

    etiquetaFotos(fila) {
        if (!fila.fotos) {
            return "Sin foto";
        }
        return fila.fotos === 1 ? "1 foto" : `${fila.fotos} fotos`;
    }
}

registry.category("actions").add("dcasa_marketing", DcasaMarketing);
