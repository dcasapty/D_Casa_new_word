/** Página «En desarrollo»: qué viene, en qué orden y qué se necesita. Sin letreros de Enterprise. */
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

const PLANES = {
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
};

export class DcasaEnDesarrollo extends Component {
    static template = "dcasa_contabilidad.EnDesarrollo";
    static props = ["*"];

    get plan() {
        return PLANES[this.props.action?.params?.clave] || PLANES.fe;
    }
}

registry.category("actions").add("dcasa_en_desarrollo", DcasaEnDesarrollo);
