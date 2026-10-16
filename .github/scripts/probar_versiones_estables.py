"""Prueba .github/versiones_estables.json: el día que haga falta volver, los datos tienen que estar bien.

Cada versión trae un commit de 40 caracteres y un digest sha256 válidos, y los nombres coinciden con las opciones del
botón «Volver a una versión estable» (.github/workflows/volver-a-estable.yml). Sin dependencias: corre en el lint.
"""
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CAMPOS = ('desde', 'que_trae', 'codigo', 'app_version', 'imagen_digest')


def opciones_del_boton():
    texto = (RAIZ / '.github/workflows/volver-a-estable.yml').read_text(encoding='utf-8')
    bloque = re.search(r'\n      version:\n(?:        .*\n)*?        options: \[([^\]]*)\]', texto)
    if not bloque:
        raise SystemExit('No encontré las opciones de «version» en volver-a-estable.yml')
    return [opcion.strip().strip('"\'') for opcion in bloque.group(1).split(',') if opcion.strip()]


def main():
    versiones = json.loads((RAIZ / '.github/versiones_estables.json').read_text(encoding='utf-8'))
    errores = []
    if not versiones:
        errores.append('No hay ninguna versión estable')
    for nombre, datos in versiones.items():
        for campo in CAMPOS:
            if not str(datos.get(campo) or '').strip():
                errores.append(f'{nombre}: falta «{campo}»')
        if not re.fullmatch(r'[0-9a-f]{40}', str(datos.get('app_version', ''))):
            errores.append(f'{nombre}: app_version no es un SHA completo de 40 caracteres')
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', str(datos.get('imagen_digest', ''))):
            errores.append(f'{nombre}: imagen_digest no es sha256:<64 hex>')
    opciones = opciones_del_boton()
    if sorted(opciones) != sorted(versiones):
        errores.append(f'Las opciones del botón {sorted(opciones)} no coinciden con el JSON {sorted(versiones)}')
    for error in errores:
        print(f'::error::{error}')
    if errores:
        sys.exit(1)
    print(f'Versiones estables en orden: {", ".join(sorted(versiones))}')


if __name__ == '__main__':
    main()
