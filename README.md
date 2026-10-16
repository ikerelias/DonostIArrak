# Proyecto DonostiArrak — Big Data

## Requisitos

- Git.
- Docker Desktop con Docker Compose, abierto y en ejecución.
- Los ficheros originales `dataset.csv` y `categorias_auxiliar.csv`, que debe facilitar Beñat. No se incluyen en Git porque son los datos de entrada.

## Primera puesta en marcha

1. Clona la rama del proyecto y entra en la carpeta:

   ```powershell
   git clone --branch aitor-prueba1 https://github.com/ikerelias/DonostIArrak.git
   cd DonostIArrak
   ```

2. Crea la carpeta de datos y coloca dentro los dos CSV recibidos de Beñat. Deben quedar con estas rutas y nombres:

   ```text
   notebooks/data/dataset.csv
   notebooks/data/categorias_auxiliar.csv
   ```

   Los CSV están excluidos de Git; cada integrante debe obtenerlos por separado.

3. Desde la raíz del repositorio, arranca el entorno:

   ```powershell
   docker compose up --build
   ```

   La primera ejecución construye la imagen de Jupyter e inicia HDFS (NameNode y DataNode), Spark (master y worker) y Jupyter con PySpark. Mantén abierta esta terminal: Compose muestra ahí los registros de arranque y el enlace de Jupyter con su token. Abre ese enlace en el navegador. El notebook `prueba1.ipynb` aparece en la página principal de Jupyter.

   Para detener el entorno, pulsa `Ctrl+C` en esa terminal. En siguientes sesiones, desde la misma carpeta, ejecuta de nuevo `docker compose up --build`.

## Carga inicial de los datos en HDFS

Haz esta carga una vez por instalación, después de que los contenedores estén arrancados. Desde otra ventana de PowerShell, situada en la raíz del repositorio, ejecuta:

```powershell
docker cp .\notebooks\data\dataset.csv namenode:/tmp/dataset.csv
docker cp .\notebooks\data\categorias_auxiliar.csv namenode:/tmp/categorias_auxiliar.csv
docker compose exec namenode hdfs dfs -mkdir -p /donostiarrak/raw
docker compose exec namenode hdfs dfs -put -f /tmp/dataset.csv /donostiarrak/raw/
docker compose exec namenode hdfs dfs -put -f /tmp/categorias_auxiliar.csv /donostiarrak/raw/
docker compose exec namenode hdfs dfs -ls /donostiarrak/raw
```

El último comando debe mostrar ambos CSV. Si ya estaban cargados, `-put -f` los reemplaza por las copias locales.

## Ejecución del notebook

Abre `prueba1.ipynb` en Jupyter y ejecuta las celdas en orden. El notebook conecta PySpark con `spark://spark-master:7077`, lee los CSV desde `hdfs://namenode:9000`, añade la categoría mediante el join con `categorias_auxiliar.csv`, unifica los nombres de zona y guarda el Parquet para ML en HDFS, particionado por categoría.

La ruta final es `/donostiarrak/curada/parquet_ML_unif`. Los CSV y los Parquet generados se excluyen de Git; el notebook permite volver a generarlos.

## Interfaces del entorno

- Jupyter: `http://localhost:8888` (el token aparece en la terminal de Compose).
- NameNode de HDFS: `http://localhost:9870`.
- DataNode: `http://localhost:9864`.
- Spark Master: `http://localhost:8080`.
- Spark Worker: `http://localhost:8081`.

## Safe Mode de HDFS

Al iniciar, HDFS puede tardar un poco en salir automáticamente de Safe Mode mientras comprueba sus bloques. Si una escritura del notebook falla indicando que el NameNode sigue en Safe Mode, compruébalo con:

```powershell
docker compose exec namenode hdfs dfsadmin -safemode get
```

En este entorno local de un solo DataNode, si sigue activo y bloquea el procesamiento, se puede desactivarlo manualmente con:

```powershell
docker compose exec namenode hdfs dfsadmin -safemode leave
```
