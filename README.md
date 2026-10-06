# Proyecto DonostiArrak — Big Data

## Requisitos

- Docker Desktop con Docker Compose.
- Los ficheros originales `dataset.csv` y `categorias_auxiliar.csv`, colocados en `notebooks/data/`. Los CSV y los Parquet generados no se versionan en Git.

## Arranque del entorno

Desde la raíz del repositorio:

```powershell
docker compose up --build
```

Compose construye Jupyter desde `Dockerfile.jupyter`, que instala Java 11 junto con PySpark 3.3.0. Así el entorno no depende de instalar Java manualmente dentro de un contenedor ya arrancado.

Jupyter se publica en `http://localhost:8888`. Si solicita token, consúltalo localmente en la salida de Compose; no lo compartas ni lo guardes en el repositorio.

## Ingesta inicial en HDFS

Con los servicios arrancados, ejecuta desde PowerShell en la raíz del repositorio:

```powershell
docker cp .\notebooks\data\dataset.csv namenode:/tmp/dataset.csv
docker cp .\notebooks\data\categorias_auxiliar.csv namenode:/tmp/categorias_auxiliar.csv
docker compose exec namenode hdfs dfs -mkdir -p /donostiarrak/raw
docker compose exec namenode hdfs dfs -put /tmp/dataset.csv /donostiarrak/raw/
docker compose exec namenode hdfs dfs -put /tmp/categorias_auxiliar.csv /donostiarrak/raw/
```

El notebook `notebooks/prueba1.ipynb` conecta PySpark a `spark://spark-master:7077` y lee los ficheros desde `hdfs://namenode:9000`.

Los Parquet descargados y comprimidos son resultados generados por el notebook; se pueden regenerar y se excluyen del repositorio para evitar subir copias de datos.
