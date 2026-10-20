import sys
import json

for linea in sys.stdin:
    campos = linea.rstrip("\n").split("\t", 1)

    if len(campos) != 2:
        continue

    zona, familia = campos

    clave = json.dumps(
        [zona, familia],
        ensure_ascii=True,
        separators=(",", ":")
    )

    print("{}\t1".format(clave))
