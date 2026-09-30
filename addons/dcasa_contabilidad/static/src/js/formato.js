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
