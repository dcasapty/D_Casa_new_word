/** Formato de montos y fechas de la contabilidad de D'CASA (dólares, estilo Panamá). */

const NUMERO = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function dinero(valor, moneda = { simbolo: "$", antes: true }) {
    if (valor === null || valor === undefined) {
        return "";
    }
    const negativo = valor < 0;
    const texto = NUMERO.format(Math.abs(valor));
    const conSimbolo = moneda.antes ? `${moneda.simbolo}${texto}` : `${texto} ${moneda.simbolo}`;
    return negativo ? `(${conSimbolo})` : conSimbolo;
}

export function fecha(iso) {
    if (!iso) {
        return "";
    }
    const [a, m, d] = iso.split("-");
    return `${d}/${m}/${a}`;
}

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

/** «14 oct» (con el año, «14 oct 2025», si no es el año de referencia). */
export function fechaCorta(iso, anio = null) {
    if (!iso) {
        return "";
    }
    const [a, m, d] = iso.split("-");
    const base = `${Number(d)} ${MESES[Number(m) - 1]}`;
    return anio && a !== String(anio) ? `${base} ${a}` : base;
}

/** «el 14 oct», «del 1 al 14 oct», «del 28 sep al 3 oct» o «del 29 dic 2025 al 3 ene 2026». */
export function rangoCorto(desde, hasta, anio = null) {
    if (!desde || desde === hasta) {
        return `el ${fechaCorta(hasta, anio)}`;
    }
    const [a1, m1] = desde.split("-");
    const [a2, m2] = hasta.split("-");
    if (a1 !== a2) {
        return `del ${fechaCorta(desde, "x")} al ${fechaCorta(hasta, "x")}`;
    }
    if (m1 === m2) {
        return `del ${Number(desde.split("-")[2])} al ${fechaCorta(hasta, anio)}`;
    }
    return `del ${fechaCorta(desde)} al ${fechaCorta(hasta, anio)}`;
}
