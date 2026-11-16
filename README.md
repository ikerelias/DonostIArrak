# DonostIArrak — Arquitectura Big Data local

Proyecto de **Big Data & Cloud Computing (curso 2026–2027)**. Procesa 15.000.000 de correos sintéticos dirigidos al Ayuntamiento de Donostia con **Docker Compose, HDFS, YARN, Hadoop Streaming, Apache Spark y Jupyter/PySpark**.

Orden de ejecución: generar el dataset (sección 4) → arrancar el clúster (sección 5) → ejecutar el pipeline Spark (sección 6) → ejecutar Hadoop Streaming y comparar con Spark RDD (sección 7).

## 1. Qué hay en el repositorio

| Archivo | Para qué sirve |
| --- | --- |
| `scripts/generacion_datos/generador_emails_donostia_v4_aux.py` | Genera el dataset (`dataset.csv` y `categorias_auxiliar.csv`). |
| `notebooks/run_pipeline.py` | **Punto de entrada único del flujo batch de Spark**: ingesta en HDFS, calidad, Parquet, agregaciones, Spark RDD y MLlib. |
| `scripts/hadoop_streaming/mapper.py`, `reducer.py` | Trabajo MapReduce con Hadoop Streaming sobre YARN. Se lanza después del pipeline (sección 7). |
| `notebooks/prueba1.ipynb` | Las mismas etapas en versión interactiva, más la comparación Hadoop Streaming / Spark RDD y los experimentos del informe. |
| `notebooks/config.json`, `notebooks/pipeline.json` | Rutas, recursos de Spark y parámetros del pipeline. |
| `docker-compose.yml`, `Dockerfile.*`, `hadoop.env` | Definición del clúster. |
| `evidencias/spark_ui/` | Capturas de la Spark UI usadas en el informe. |

## 2. Requisitos

- Windows con PowerShell, Git, Python 3.10 o superior y Docker Desktop.
- **Al menos 8 GB de RAM asignados a Docker** (*Docker Desktop → Settings → Resources*).
- Disco libre: unas tres veces el tamaño del dataset más 10 GB (HDFS guarda 3 réplicas).
- Puertos libres: `8888`, `4040`, `9870`, `9000`, `8080`, `8081`, `7077` y `8088`.

## 3. Clonar el repositorio

```powershell
git clone https://github.com/ikerelias/DonostIArrak.git
cd DonostIArrak
```

Todos los comandos siguientes se ejecutan desde la raíz del repositorio.

## 4. Generar el dataset

```powershell
python scripts\generacion_datos\generador_emails_donostia_v4_aux.py --n 15000000 --out notebooks\data
```

- `--n` es el número de correos. **Sin `--n` solo se generan 10.000.** El dataset del informe tiene 15.000.000 (unos 300 bytes por correo en el CSV).
- La semilla es fija, así que el resultado es reproducible.
- El pipeline solo lee `notebooks\data\dataset.csv` y `notebooks\data\categorias_auxiliar.csv`. Los demás archivos que crea el generador (`*.jsonl`, `dataset_modelo.csv` y los `*qa*.json`) son controles de calidad del dataset y pueden borrarse.
- El generador mantiene todos los correos en memoria antes de escribirlos, por lo que con 15 millones necesita bastante RAM y tarda un buen rato.

## 5. Arrancar el clúster

```powershell
docker compose up -d --build
docker compose ps
```

La primera vez tarda varios minutos en construir las imágenes. Se levantan nueve servicios:

| Servicio | Función |
| --- | --- |
| `namenode` y `datanode1`–`datanode3` | HDFS con replicación 3 |
| `resourcemanager`, `nodemanager1`, `historyserver` | YARN para Hadoop Streaming |
| `spark-master` y `spark-worker` | Procesamiento distribuido Spark |
| `jupyter-pyspark` | Driver del pipeline y JupyterLab |

**Solo la primera vez**, crear la carpeta del proyecto en HDFS y dar permisos al usuario del pipeline (`jovyan`):

```powershell
docker exec namenode hdfs dfs -mkdir -p /donostiarrak
docker exec namenode hdfs dfs -chown -R jovyan /donostiarrak
```

## 6. Ejecutar el pipeline Spark

```powershell
docker exec -w /home/jovyan/work jupyter-pyspark /usr/local/spark/bin/spark-submit run_pipeline.py --run
```

Ejecuta, en este orden:

1. `ingerir_csv()`: copia los dos CSV de `notebooks/data/` a HDFS (`/donostiarrak/raw`) y verifica que el tamaño coincide.
2. `procesar()`: lee con esquema explícito, une con la tabla auxiliar, unifica zonas y aplica la capa de calidad (válidos a la zona curada, errores a cuarentena). Escribe el Parquet particionado por categoría, calcula la agregación zona × familia con DataFrames, prepara la entrada MapReduce y hace el mismo recuento con Spark RDD.
3. `mllib_baseline()`: entrena Naive Bayes con Spark MLlib y guarda accuracy y F1 ponderado.

Termina con el mensaje `PIPELINE TERMINADO CORRECTAMENTE en N s`. Mientras se ejecuta, la Spark UI está en <http://localhost:4040>.

Hadoop Streaming no forma parte de este comando: el pipeline corre dentro del contenedor `jupyter-pyspark`, que no tiene el cliente de Hadoop para enviar trabajos a YARN. Se lanza desde el NameNode en la sección 7, sobre la entrada que deja este paso.

## 7. Hadoop Streaming y comparación con Spark RDD

Cuenta los correos por combinación (zona, familia de escenario), el mismo cálculo que hace Spark RDD en la sección 6, y lee la misma entrada (`/donostiarrak/curada/mapreduce_entrada`).

**1. Copiar los scripts al NameNode:**

```powershell
docker cp .\scripts\hadoop_streaming\mapper.py namenode:/tmp/mapper.py
docker cp .\scripts\hadoop_streaming\reducer.py namenode:/tmp/reducer.py
```

**2. Lanzar el trabajo en YARN:**

```powershell
docker exec namenode hadoop jar /opt/hadoop-3.2.1/share/hadoop/tools/lib/hadoop-streaming-3.2.1.jar -D "mapreduce.framework.name=yarn" -D "yarn.resourcemanager.hostname=resourcemanager" -D "yarn.app.mapreduce.am.env=HADOOP_MAPRED_HOME=/opt/hadoop-3.2.1" -D "mapreduce.map.env=HADOOP_MAPRED_HOME=/opt/hadoop-3.2.1" -D "mapreduce.reduce.env=HADOOP_MAPRED_HOME=/opt/hadoop-3.2.1" -D "mapreduce.job.reduces=2" -files file:///tmp/mapper.py,file:///tmp/reducer.py -input /donostiarrak/curada/mapreduce_entrada -output /donostiarrak/resultados/mapreduce_hadoop_streaming_v2 -mapper "python3 mapper.py" -reducer "python3 reducer.py"
```

**3. Ver el resultado:**

```powershell
docker exec namenode hdfs dfs -cat "/donostiarrak/resultados/mapreduce_hadoop_streaming_v2/part-*"
```

Hadoop no sobrescribe directorios. Para repetir el trabajo, borrar antes la salida:

```powershell
docker exec namenode hdfs dfs -rm -r /donostiarrak/resultados/mapreduce_hadoop_streaming_v2
```

**4. Comparar con Spark RDD** (la comparación solo está en el notebook, no en `run_pipeline.py`):

1. Abrir <http://localhost:8888/lab> (si pide token: `docker logs jupyter-pyspark`) y abrir `prueba1.ipynb`.
2. Ejecutar solo estas celdas, en orden (no hace falta el notebook entero):
   - Las celdas de los **Pasos 1, 2 y 3** (configuración, Java y sesión de Spark).
   - **PASO 19.10 - MAPREDUCE CON SPARK RDD**.
   - **PASO 19.11 - COMPARACIÓN HADOOP STREAMING VS SPARK RDD**: debe terminar con `RESULTADOS IDÉNTICOS: VALIDACIÓN SUPERADA`.

## 8. Resultados y evidencias en HDFS

Todo queda en HDFS. Se puede consultar en <http://localhost:9870> (*Utilities → Browse the file system*) o con `docker exec namenode hdfs dfs -ls <ruta>`.

| Ruta HDFS | Contenido |
| --- | --- |
| `/donostiarrak/raw` | CSV originales sin modificar |
| `/donostiarrak/curada/reto4_evaluados` | Todos los registros con su estado de calidad |
| `/donostiarrak/curada/reto4_cuarentena` | Registros con errores críticos y su motivo |
| `/donostiarrak/curada/dataset_por_categoria` | Parquet de registros válidos, particionado por categoría |
| `/donostiarrak/curada/parquet_ML_unif` | Parquet usado para el modelo |
| `/donostiarrak/curada/mapreduce_entrada` | Entrada común de Spark RDD y Hadoop Streaming |
| `/donostiarrak/resultados/reto4_resumen`, `reto4_incidencias` | Informes de calidad |
| `/donostiarrak/resultados/mapreduce_zona_familia_spark` | Agregación con DataFrames |
| `/donostiarrak/resultados/mapreduce_spark_rdd_v3` | Agregación con Spark RDD |
| `/donostiarrak/resultados/mapreduce_hadoop_streaming_v2` | Agregación con Hadoop Streaming (sección 7) |
| `/donostiarrak/resultados/mllib_baseline_metricas` | Métricas del modelo Naive Bayes |

Bloques y replicación del dataset:

```powershell
docker exec namenode hdfs fsck /donostiarrak/raw/dataset.csv -files -blocks -locations
```

## 9. Interfaces web

| Interfaz | URL |
| --- | --- |
| JupyterLab | <http://localhost:8888> |
| Spark UI (durante una ejecución) | <http://localhost:4040> |
| HDFS NameNode | <http://localhost:9870> |
| Spark Master / Worker | <http://localhost:8080> / <http://localhost:8081> |
| YARN ResourceManager | <http://localhost:8088> |

## 10. Parar el clúster

```powershell
docker compose stop
docker compose start
```

No usar `docker compose down -v`: borra los volúmenes de HDFS y con ellos todos los datos y resultados.

## 11. Problemas habituales

- **`ModuleNotFoundError: pyspark`:** lanzar `--run` con `/usr/local/spark/bin/spark-submit`, no con `python`.
- **`Falta fichero necesario`:** los CSV no están en `notebooks\data\` o tienen otro nombre.
- **`Permission denied: user=jovyan`:** falta el paso de permisos en HDFS del final de la sección 5.
- **Nombre de contenedor en conflicto:** hay otro proyecto Compose con los mismos nombres (`namenode`, `jupyter-pyspark`...). Pararlo con `docker compose stop` desde su carpeta.
- **HDFS en Safe Mode:** comprobar con `docker exec namenode hdfs dfsadmin -safemode get` y esperar a que salga solo.
- **La salida de Hadoop Streaming ya existe:** borrarla como se indica en la sección 7.
