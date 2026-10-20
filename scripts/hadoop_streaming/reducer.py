import sys
import json

clave_actual = None
contador = 0

def emitir(clave, total):
    zona, familia = json.loads(clave)
    print("{}\t{}\t{}".format(zona, familia, total))

for linea in sys.stdin:
    campos = linea.rstrip("\n").split("\t", 1)

    if len(campos) != 2:
        continue

    clave, valor = campos
    cantidad = int(valor)

    if clave_actual is not None and clave != clave_actual:
        emitir(clave_actual, contador)
        contador = 0

    clave_actual = clave
    contador += cantidad

if clave_actual is not None:
    emitir(clave_actual, contador)
