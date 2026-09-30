/** Página «En desarrollo»: qué viene, en qué orden y qué se necesita. Sin letreros de Enterprise. */
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

const PLANES = {
    nomina: {
        titulo: "Nómina",
        icono: "fa-users",
        resumen: "Planilla de D'CASA hecha a la medida de Panamá.",
        pasos: [
            "Fichas de colaboradores: salario, cargo, cuenta bancaria y fecha de ingreso.",
            "Cálculo quincenal con seguro social, seguro educativo e impuesto sobre la renta, con las tasas que indique tu contador.",
            "Décimo tercer mes, vacaciones y prima de antigüedad.",
            "Asiento contable automático de cada planilla y comprobante de pago para cada colaborador.",
        ],
        necesita: "Las tasas y reglas vigentes validadas por tu contador (no las inventamos).",
    },
    reembolsos: {
        titulo: "Reembolsos en nómina",
        icono: "fa-undo",
        resumen: "Gastos que paga un colaborador y se le devuelven en la planilla.",
        pasos: [
            "El colaborador registra el gasto con la foto del recibo.",
            "Aprobación del administrador.",
            "Se suma a la siguiente planilla y queda contabilizado.",
        ],
        necesita: "Se construye junto con Nómina.",
    },
    fe: {
        titulo: "Facturación electrónica DGI",
        icono: "fa-qrcode",
        resumen: "Factura electrónica de Panamá (SFEP) con CUFE y código QR.",
        pasos: [
            "Contrato con un Proveedor Autorizado Calificado (PAC) de la DGI.",
            "Envío de cada factura al PAC al confirmarla y recepción del CUFE y el QR.",
            "Notas de crédito y anulaciones electrónicas.",
            "El CUFE y el QR impresos en la factura de D'CASA.",
        ],
        necesita: "Elegir el PAC y sus credenciales de prueba.",
    },
    consolidacion: {
        titulo: "Consolidación",
        icono: "fa-sitemap",
        resumen: "Estados financieros de varias empresas en uno solo.",
        pasos: [
            "Registrar cada empresa en el sistema (multiempresa ya viene incluido).",
            "Mapear las cuentas de cada empresa al plan consolidado.",
            "Eliminar operaciones entre empresas y emitir el balance consolidado.",
        ],
        necesita: "Solo aplica cuando D'CASA tenga más de una empresa.",
    },
};

export class DcasaEnDesarrollo extends Component {
    static template = "dcasa_contabilidad.EnDesarrollo";
    static props = ["*"];

    get plan() {
        return PLANES[this.props.action?.params?.clave] || PLANES.nomina;
    }
}

registry.category("actions").add("dcasa_en_desarrollo", DcasaEnDesarrollo);
