# Proyecto DonostiArrak — Big Data

## Requisitos

- Git.
- Docker Desktop con Docker Compose, abierto y en ejecución.
- Los ficheros originales `dataset.csv` y `categorias_auxiliar.csv`, facilitados por Beñat. No se guardan en Git.

## Primera puesta en marcha

1. Clona la rama `main` y entra en la carpeta:

   ```powershell
   git clone --branch main https://github.com/ikerelias/DonostIArrak.git
   cd DonostIArrak
   ```

2. Crea `notebooks/data` y coloca allí los dos CSV con estos nombres exactos:

   ```text
   notebooks/data/dataset.csv
   notebooks/data/categorias_auxiliar.csv
   ```

   Los CSV están excluidos de Git. Cada integrante debe recibirlos por separado.

3. Desde la raíz del repositorio, arranca todo el entorno con:

   ```powershell
   docker compose up --build
   ```

   La primera ejecución construye Jupyter e inicia Jupyter con PySpark, Spark Master/Worker y HDFS (NameNode y tres DataNodes). Mantén abierta esta terminal: ahí aparecen los registros de inicio y el enlace de Jupyter, incluido el token si está activado. Abre el enlace en el navegador y entra en `prueba1.ipynb`.

   En siguientes sesiones, abre Docker Desktop y ejecuta el mismo comando desde la raíz del repositorio. Si solo quieres detener los servicios, pulsa `Ctrl+C` en la terminal. HDFS se guarda en volúmenes de Docker; `docker compose down` conserva esos volúmenes, mientras que `docker compose down -v` los elimina.

## Cargar o actualizar los CSV en HDFS

Coloca los dos CSV en `notebooks/data` con estos nombres exactos. Con Docker y Jupyter arrancados, abre `prueba1.ipynb` y ejecuta las celdas en orden hasta el Paso 3.1. Esa celda copia los CSV a HDFS automáticamente; no hace falta ejecutar `docker cp` ni `hdfs dfs -put` desde la terminal. Si los archivos ya están en HDFS y tienen el mismo tamaño que los locales, la celda conserva la copia existente. Cuando recibas versiones nuevas, ejecuta de nuevo el Paso 3.1 y luego vuelve a ejecutar desde el Paso 4 para regenerar los Parquet.

## Ejecutar el procesamiento

Abre `prueba1.ipynb` en Jupyter y ejecuta sus celdas en orden. La configuración de conexiones y rutas está al principio del notebook. PySpark se conecta a `spark://spark-master:7077` y lee los CSV desde `hdfs://namenode:9000/donostiarrak/raw`.

El flujo en el notebook:

1. Lee los CSV crudos desde HDFS.
2. Añade `categoria` a cada registro mediante el join por `subcategoria`.
3. Unifica las variantes acordadas de los nombres de zona.
4. Guarda y verifica el Parquet particionado por categoría en el Paso 7.1.
5. Ejecuta las agregaciones y comparaciones descritas en los pasos posteriores.

El Parquet preparado para ML queda en `/donostiarrak/curada/parquet_ML_unif` en HDFS. Para el entrenamiento, el notebook selecciona y guarda una muestra separada de 50.000 registros; no hace falta descargar el Parquet al ordenador para ejecutar el procesamiento de Big Data.

## Interfaces del entorno

- Jupyter: `http://localhost:8888` (el token, si se solicita, se muestra en la terminal de Compose).
- NameNode de HDFS: `http://localhost:9870`.
- ResourceManager de Hadoop: `http://localhost:8088`.
- Spark Master: `http://localhost:8080`.
- Spark Worker: `http://localhost:8081`.

## Safe Mode de HDFS

Al arrancar, HDFS puede tardar un poco en salir automáticamente de Safe Mode mientras comprueba los bloques. Si la primera escritura del Paso 3.1 falla porque HDFS sigue en modo seguro, comprueba el estado con:

```powershell
docker compose exec namenode hdfs dfsadmin -safemode get
```

Si el modo seguro continúa activo y bloquea el procesamiento, puedes salir manualmente con:

```powershell
docker compose exec namenode hdfs dfsadmin -safemode leave
```

