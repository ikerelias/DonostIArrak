# Proyecto DonostiArrak — Big Data

## Requisitos

- Git.
- Docker Desktop con Docker Compose, abierto y en ejecución.
- Los ficheros originales `dataset.csv` y `categorias_auxiliar.csv`, facilitados por Beñat. No se guardan en Git.

## Primera puesta en marcha

1. Clona la rama del proyecto y entra en la carpeta:

   ```powershell
   git clone https://github.com/ikerelias/DonostIArrak.git
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

   La primera ejecución construye Jupyter e inicia Jupyter con PySpark, Spark Master/Worker y HDFS (NameNode/DataNode). Mantén abierta esta terminal: ahí aparecen los registros de inicio y el enlace de Jupyter, incluido el token si está activado. Abre el enlace en el navegador y entra en `prueba1.ipynb`.

   En siguientes sesiones, abre Docker Desktop y ejecuta el mismo comando desde la raíz del repositorio. Si solo quieres detener los servicios, pulsa `Ctrl+C` en la terminal. Evita `docker compose down` si quieres conservar el HDFS local: este Compose no configura volúmenes persistentes para los datos de HDFS, y al eliminar los contenedores puedes tener que volver a cargar los CSV y regenerar los Parquet.

## Cargar o actualizar los CSV en HDFS

El notebook lee los CSV desde HDFS; ponerlos en `notebooks/data` no los copia automáticamente a HDFS. Haz la carga inicial con los contenedores arrancados. Repite estos pasos cuando recibas versiones nuevas de los CSV. Desde otra ventana de PowerShell, situada en la raíz del repositorio, ejecuta:

```powershell
docker cp .\notebooks\data\dataset.csv namenode:/tmp/dataset.csv
docker cp .\notebooks\data\categorias_auxiliar.csv namenode:/tmp/categorias_auxiliar.csv
docker compose exec namenode hdfs dfs -mkdir -p /donostiarrak/raw
docker compose exec namenode hdfs dfs -put -f /tmp/dataset.csv /donostiarrak/raw/
docker compose exec namenode hdfs dfs -put -f /tmp/categorias_auxiliar.csv /donostiarrak/raw/
docker compose exec namenode hdfs dfs -ls -h /donostiarrak/raw
```

La opción `-put -f` reemplaza en HDFS la copia anterior con el mismo nombre. Comprueba que el último comando liste los dos CSV antes de ejecutar el notebook. Después, vuelve a ejecutar el notebook desde el principio para que Spark regenere los Parquet a partir de los nuevos datos; las salidas se escriben con `overwrite`.

## Ejecutar el procesamiento

Abre `prueba1.ipynb` en Jupyter y ejecuta sus celdas en orden. La configuración de conexiones y rutas está al principio del notebook. PySpark se conecta a `spark://spark-master:7077` y lee los CSV desde `hdfs://namenode:9000/donostiarrak/raw`.

El flujo en el notebook:

1. Lee los CSV crudos desde HDFS.
2. Añade `categoria` a cada registro mediante el join por `subcategoria`.
3. Unifica las variantes acordadas de los nombres de zona.
4. Genera y verifica los Parquet particionados por categoría.
5. Ejecuta las agregaciones y comparaciones descritas en los pasos posteriores.

El Parquet preparado para ML queda en `/donostiarrak/curada/parquet_ML_unif` en HDFS. Para el entrenamiento, el notebook selecciona y guarda una muestra separada de 50.000 registros; no hace falta descargar el Parquet al ordenador para ejecutar el procesamiento de Big Data.

## Interfaces del entorno

- Jupyter: `http://localhost:8888` (el token, si se solicita, se muestra en la terminal de Compose).
- NameNode de HDFS: `http://localhost:9870`.
- DataNode: `http://localhost:9864`.
- Spark Master: `http://localhost:8080`.
- Spark Worker: `http://localhost:8081`.

## Safe Mode de HDFS

Al arrancar, HDFS puede tardar un poco en salir automáticamente de Safe Mode mientras comprueba los bloques. Si una escritura del notebook falla porque el NameNode sigue en Safe Mode, compruébalo con:

```powershell
docker compose exec namenode hdfs dfsadmin -safemode get
```

En este entorno local de un solo DataNode, si sigue activo y bloquea el procesamiento, puedes salir del modo seguro con:

```powershell
docker compose exec namenode hdfs dfsadmin -safemode leave
```

