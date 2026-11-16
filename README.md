# DonostIArrak — Arquitectura Big Data local

Proyecto de **Big Data & Cloud Computing (curso 2026–2027)**. Procesa un conjunto de correos sintéticos dirigidos al Buzón de la Ciudadanía de Donostia con **Docker Compose, HDFS, YARN, Hadoop Streaming, Apache Spark y Jupyter/PySpark**.

## Qué hay en el repositorio

| Archivo | Para qué sirve |
| --- | --- |
| `scripts/generacion_datos/generador_emails_donostia_v4_aux.py` | Genera el dataset (`dataset.csv` y `categorias_auxiliar.csv`). |
| `notebooks/run_pipeline.py` | **Punto de entrada del procesamiento.** Ingesta en HDFS, calidad, Parquet, agregaciones, Spark RDD y MLlib. |
| `scripts/hadoop_streaming/mapper.py`, `reducer.py` | Trabajo MapReduce (Hadoop Streaming sobre YARN). Se lanza aparte, después del pipeline. |
| `notebooks/prueba1.ipynb` | **Opcional.** Las mismas etapas en versión interactiva, para explorarlas paso a paso. No es necesario para ejecutar el proyecto. |
| `notebooks/config.json`, `notebooks/pipeline.json` | Rutas, recursos de Spark y parámetros del pipeline. |
| `docker-compose.yml`, `Dockerfile.*`, `hadoop.env` | Definición del clúster. |
| `evidencias/` | Capturas de la Spark UI usadas en el informe. |

## Requisitos

- Windows con PowerShell, Git, Python 3.10 o superior y Docker Desktop.
- **Al menos 8 GB de RAM asignados a Docker** (*Docker Desktop → Settings → Resources*).
- Disco libre: unas tres veces el tamaño del dataset más 10 GB (HDFS guarda 3 réplicas).
- Puertos libres: `8888`, `4040`, `9870`, `9000`, `8080`, `8081`, `7077` y `8088`.

## Ejecución completa

Todos los comandos se ejecutan desde la raíz del repositorio.

**1. Clonar el repositorio**

```powershell
git clone https://github.com/ikerelias/DonostIArrak.git
cd DonostIArrak
```

**2. Generar el dataset**

```powershell
python scripts\generacion_datos\generador_emails_donostia_v4_aux.py --n 18000000 --out notebooks\data
```

- `--n` es el número de correos. **Sin `--n` solo se generan 10.000** (unos 3 MB). Cada correo ocupa unos 296 bytes en el CSV: 15 millones dan unos 4,5 GB y 18 millones unos 5,3 GB.
- El pipeline solo lee `notebooks\data\dataset.csv` y `notebooks\data\categorias_auxiliar.csv`. Los demás archivos que crea el generador (`*.jsonl`, `dataset_modelo.csv` y los `*qa*.json`) son controles de calidad del dataset y pueden borrarse.
- El generador mantiene todos los correos en memoria antes de escribirlos: con 18 millones necesita del orden de 22 GB de RAM y tarda alrededor de media hora.

**3. Arrancar el clúster**

```powershell
docker compose up -d --build
docker compose ps
```

La primera vez tarda varios minutos en construir las imágenes.

**4. Ejecutar el pipeline**

```powershell
docker exec -w /home/jovyan/work jupyter-pyspark /usr/local/spark/bin/spark-submit run_pipeline.py --run
```

Ejecuta, en este orden:

1. Copia los dos CSV de `notebooks/data/` a HDFS (`/donostiarrak/raw`) y verifica el tamaño.
2. Une el dataset con la tabla auxiliar de categorías y aplica las reglas de calidad: los registros válidos siguen adelante y los erróneos van a cuarentena.
3. Guarda los datos limpios en Parquet particionado por categoría.
4. Calcula las agregaciones con DataFrames y el mismo recuento con Spark RDD.
5. Prepara la entrada para Hadoop Streaming.
6. Entrena un modelo Naive Bayes (Spark MLlib) y guarda accuracy y F1.

Termina con el mensaje `PIPELINE TERMINADO CORRECTAMENTE en N s`. Mientras se ejecuta, la Spark UI está en <http://localhost:4040>.

**5. Ejecutar Hadoop Streaming sobre YARN**

```powershell
docker cp .\scripts\hadoop_streaming\mapper.py namenode:/tmp/mapper.py
docker cp .\scripts\hadoop_streaming\reducer.py namenode:/tmp/reducer.py

docker exec namenode hadoop jar /opt/hadoop-3.2.1/share/hadoop/tools/lib/hadoop-streaming-3.2.1.jar `
    -D "mapreduce.framework.name=yarn" `
    -D "yarn.resourcemanager.hostname=resourcemanager" `
    -D "yarn.app.mapreduce.am.env=HADOOP_MAPRED_HOME=/opt/hadoop-3.2.1" `
    -D "mapreduce.map.env=HADOOP_MAPRED_HOME=/opt/hadoop-3.2.1" `
    -D "mapreduce.reduce.env=HADOOP_MAPRED_HOME=/opt/hadoop-3.2.1" `
    -D "mapreduce.job.reduces=2" `
    -files file:///tmp/mapper.py,file:///tmp/reducer.py `
    -input /donostiarrak/curada/mapreduce_entrada `
    -output /donostiarrak/resultados/hadoop_streaming `
    -mapper "python3 mapper.py" `
    -reducer "python3 reducer.py"

docker exec namenode hdfs dfs -cat "/donostiarrak/resultados/hadoop_streaming/part-*"
```

Cuenta los correos por combinación (zona, familia de escenario), el mismo cálculo que hace Spark RDD en el paso 4, para comparar ambos. Hadoop no sobrescribe directorios: para repetirlo, borrar antes la salida con `docker exec namenode hdfs dfs -rm -r /donostiarrak/resultados/hadoop_streaming`.

## Dónde quedan los resultados

Todo queda en HDFS. Se puede consultar en <http://localhost:9870> (*Utilities → Browse the file system*) o con `docker exec namenode hdfs dfs -ls <ruta>`.

| Ruta HDFS | Contenido |
| --- | --- |
| `/donostiarrak/raw` | CSV originales sin modificar |
| `/donostiarrak/curada/reto4_evaluados` | Todos los registros con su estado de calidad |
| `/donostiarrak/curada/reto4_cuarentena` | Registros descartados y motivo |
| `/donostiarrak/curada/dataset_por_categoria` | Parquet limpio, particionado por categoría |
| `/donostiarrak/curada/parquet_ML_unif` | Parquet usado para el modelo |
| `/donostiarrak/curada/mapreduce_entrada` | Entrada común de Spark RDD y Hadoop Streaming |
| `/donostiarrak/resultados/reto4_resumen`, `reto4_incidencias` | Informes de calidad |
| `/donostiarrak/resultados/mapreduce_zona_familia_spark` | Agregación con DataFrames |
| `/donostiarrak/resultados/mapreduce_spark_rdd_v3` | Agregación con Spark RDD |
| `/donostiarrak/resultados/hadoop_streaming` | Agregación con Hadoop Streaming (paso 5) |
| `/donostiarrak/resultados/mllib_baseline_metricas` | Métricas del modelo Naive Bayes |

Para ver la replicación de los bloques del dataset:

```powershell
docker exec namenode hdfs fsck /donostiarrak/raw/dataset.csv -files -blocks -locations
```

## Otros modos de ejecución

- **Comprobar rutas sin escribir nada:**

  ```powershell
  docker exec -w /home/jovyan/work jupyter-pyspark python run_pipeline.py --check
  ```

- **Prueba rápida con 20.000 correos:** no copia nada a HDFS, por lo que necesita que los CSV ya estén en `/donostiarrak/raw` (por ejemplo, tras un `--run`). Escribe solo en `/donostiarrak/resultados/prueba_integracion/` y no toca las salidas oficiales.

  ```powershell
  docker exec -w /home/jovyan/work jupyter-pyspark /usr/local/spark/bin/spark-submit run_pipeline.py --smoke-test
  ```

- **Notebook interactivo:** abrir <http://localhost:8888/lab> (si pide token, aparece en `docker logs jupyter-pyspark`), abrir `prueba1.ipynb` y ejecutar las celdas en orden. Lee los datos de `/donostiarrak/raw`, así que conviene ejecutar antes el paso 4.

## Interfaces web

| Interfaz | URL |
| --- | --- |
| JupyterLab | <http://localhost:8888> |
| Spark UI (durante una ejecución) | <http://localhost:4040> |
| HDFS NameNode | <http://localhost:9870> |
| Spark Master / Worker | <http://localhost:8080> / <http://localhost:8081> |
| YARN ResourceManager | <http://localhost:8088> |

## Parar el clúster

```powershell
docker compose stop
docker compose start
```

No usar `docker compose down -v`: borra los volúmenes de HDFS y con ellos todos los datos y resultados.

## Problemas habituales

- **`ModuleNotFoundError: pyspark`:** lanzar `--run` y `--smoke-test` con `/usr/local/spark/bin/spark-submit`, no con `python`.
- **`Falta fichero necesario`:** los CSV no están en `notebooks\data\` o tienen otro nombre.
- **Nombre de contenedor en conflicto:** hay otro proyecto Compose con los mismos nombres (`namenode`, `jupyter-pyspark`...). Pararlo con `docker compose stop` desde su carpeta.
- **HDFS en Safe Mode:** comprobar con `docker exec namenode hdfs dfsadmin -safemode get` y esperar a que salga solo.
- **La salida de Hadoop Streaming ya existe:** borrarla como se indica en el paso 5.
