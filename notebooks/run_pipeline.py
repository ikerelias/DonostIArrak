#!/usr/bin/env python3
"""DonostIArrak: ingesta HDFS -> calidad Spark -> Parquet -> analitica -> MLlib.

Ejecutar desde el contenedor jupyter-pyspark (carpeta /home/jovyan/work):
    python run_pipeline.py --check
    python run_pipeline.py --smoke-test   # Muestra limitada, salidas separadas
    python run_pipeline.py --run          # Ejecucion completa; sobrescribe salidas oficiales

Este script no sustituye la ejecución Hadoop Streaming/YARN del apartado C.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent


def leer_configuracion():
    with (BASE / "config.json").open(encoding="utf-8") as archivo:
        base = json.load(archivo)
    with (BASE / "pipeline.json").open(encoding="utf-8") as archivo:
        pipeline = json.load(archivo)
    for bloque in ("servicios", "rutas", "procesamiento"):
        if bloque not in base:
            raise ValueError(f"Falta el bloque '{bloque}' en config.json")
    return base, pipeline


def rutas_config(base, conf):
    servicios, rutas = base["servicios"], base["rutas"]
    uri = f"hdfs://{servicios['hdfs_host']}:{servicios['hdfs_port']}"
    raw = uri + rutas["hdfs_raw_dir"]
    curated = uri + rutas["hdfs_curated_dir"]
    results = uri + rutas["hdfs_results_dir"]
    return {
        "hdfs_uri": uri,
        "spark_master": f"spark://{servicios['spark_master_host']}:{servicios['spark_master_port']}",
        "dataset_local": BASE / rutas["local_dataset_csv"],
        "categories_local": BASE / rutas["local_categories_csv"],
        "dataset_hdfs": raw + "/" + rutas["dataset_filename"],
        "categories_hdfs": raw + "/" + rutas["categories_filename"],
        "evaluated": curated + "/" + conf["salidas"]["evaluados"],
        "curated": curated + "/" + rutas["parquet_categorized_name"],
        "quarantine": curated + "/" + conf["salidas"]["cuarentena"],
        "ml": curated + "/" + rutas["parquet_ml_name"],
        "mr_input": curated + "/" + conf["salidas"]["mapreduce_entrada"],
        "quality_summary": results + "/" + conf["salidas"]["resumen_calidad"],
        "quality_incidents": results + "/" + conf["salidas"]["incidencias_calidad"],
        "analytics": results + "/" + conf["salidas"]["analitica_zona_familia"],
        "rdd": results + "/" + conf["salidas"]["spark_rdd"],
        "mllib_metrics": results + "/" + conf["salidas"]["mllib_metricas"],
    }


def mostrar_comprobacion(base, conf, rutas):
    print("=== COMPROBACION PREVIA - SOLO LECTURA ===")
    for label in ("dataset_local", "categories_local"):
        archivo = rutas[label]
        tamano = f"{archivo.stat().st_size:,} bytes" if archivo.is_file() else "NO ENCONTRADO"
        print(f"{label}: {archivo} -> {tamano}")
    print("Spark:", rutas["spark_master"])
    print("HDFS:", rutas["hdfs_uri"])
    print("Particion:", base["procesamiento"]["partition_column"])
    print("Pasos: ingesta -> calidad -> Parquet -> resultados -> Spark RDD -> MLlib")
    print("Hadoop Streaming/YARN: tarea independiente, no incluida en este ejecutor.")
    print("Comprobacion terminada: no se ha modificado HDFS.")


def preparar_spark(base, conf, rutas):
    os.environ["JAVA_HOME"] = base["servicios"]["java_home"]
    os.environ["PATH"] = os.environ["JAVA_HOME"] + "/bin:" + os.environ.get("PATH", "")
    from pyspark.sql import SparkSession
    r = conf["spark"]
    return (
        SparkSession.builder.master(rutas["spark_master"])
        .appName(base["servicios"]["spark_app_name"] + "Pipeline")
        .config("spark.hadoop.fs.defaultFS", rutas["hdfs_uri"])
        .config("spark.executor.memory", r["executor_memory"])
        .config("spark.executor.cores", str(r["executor_cores"]))
        .config("spark.cores.max", str(r["max_cores"]))
        .config("spark.sql.shuffle.partitions", str(r["shuffle_partitions"]))
        .getOrCreate()
    )


def ingerir_csv(spark, rutas):
    """Copia sin modificar los bytes CSV originales desde el contenedor Jupyter a HDFS."""
    jvm = spark.sparkContext._jvm
    jpath = jvm.org.apache.hadoop.fs.Path
    config = spark.sparkContext._jsc.hadoopConfiguration()
    for origen, destino in (("dataset_local", "dataset_hdfs"),
                             ("categories_local", "categories_hdfs")):
        local = rutas[origen]
        if not local.is_file():
            raise FileNotFoundError(f"Falta el CSV original: {local}")
        dst = jpath(rutas[destino])
        fs = dst.getFileSystem(config)
        fs.mkdirs(dst.getParent())
        print(f"Copiando sin transformar: {local.name} -> {rutas[destino]}", flush=True)
        fs.copyFromLocalFile(False, True, jpath(local.as_uri()), dst)
        bytes_en_hdfs = fs.getFileStatus(dst).getLen()
        if bytes_en_hdfs != local.stat().st_size:
            raise RuntimeError(f"Tamanos diferentes tras copiar {local.name}: "
                               f"local={local.stat().st_size}, hdfs={bytes_en_hdfs}")
        print(f"  Copia verificada: {bytes_en_hdfs:,} bytes")


def evaluar_calidad(spark, df_raw, df_categorias, df_enriquecido, rutas, conf):
    """Aplica las mismas reglas criticas/advisory que el Reto 4 del notebook."""
    from pyspark.sql import functions as F

    t0 = time.perf_counter()
    columnas = ["email_id", "texto", "subcategoria", "categoria", "zona",
                "familia_escenario", "split", "idioma"]
    faltan = sorted(set(columnas) - set(df_enriquecido.columns))
    if faltan:
        raise ValueError(f"Columnas obligatorias ausentes: {faltan}")

    aux_repetidas = (df_categorias.groupBy("subcategoria").count()
                     .filter(F.col("count") > 1).limit(1).count())
    if aux_repetidas:
        raise ValueError("La tabla auxiliar contiene subcategorias duplicadas")
    filas_origen = df_raw.count()

    ids_repetidos = (
        df_raw.select(F.trim(F.col("email_id").cast("string")).alias("_id_normalizado"))
        .filter(F.col("_id_normalizado").isNotNull() & (F.col("_id_normalizado") != ""))
        .groupBy("_id_normalizado").count().filter(F.col("count") > 1)
        .select("_id_normalizado")
    )
    hay_duplicados = ids_repetidos.limit(1).count() > 0
    base = (df_enriquecido
            .withColumn("_id_normalizado", F.trim(F.col("email_id").cast("string")))
            .withColumn("split", F.lower(F.trim(F.col("split").cast("string")))))
    if hay_duplicados:
        base = base.join(ids_repetidos.withColumn("_id_repetido", F.lit(True)),
                         on="_id_normalizado", how="left")
    else:
        base = base.withColumn("_id_repetido", F.lit(False))

    def vacio(columna):
        return (F.col(columna).isNull() |
                (F.length(F.trim(F.col(columna).cast("string"))) == 0))

    umbral = int(conf["calidad"]["umbral_texto_corto"])
    reparto = conf["particiones_salida"]
    evaluacion = (
        base.withColumn("errores_criticos", F.concat_ws(";",
            F.when(vacio("email_id"), "ID_VACIO"),
            F.when(F.coalesce(F.col("_id_repetido"), F.lit(False)), "ID_DUPLICADO"),
            F.when(vacio("texto"), "TEXTO_VACIO"),
            F.when(vacio("subcategoria"), "SUBCATEGORIA_VACIA"),
            F.when(vacio("categoria"), "CATEGORIA_NO_ASIGNADA"),
            F.when(vacio("split") | ~F.col("split").isin("train", "validation", "test"),
                   "SPLIT_INVALIDO")
        )).withColumn("advertencias", F.concat_ws(";",
            F.when(~vacio("texto") & (F.length(F.trim(F.col("texto"))) < umbral),
                   "TEXTO_CORTO"),
            F.when(vacio("zona") | F.lower(F.trim(F.col("zona"))).isin(
                "desconocida", "desconocido", "unknown", "sin zona", "n/a"),
                "ZONA_DESCONOCIDA"),
            F.when(vacio("familia_escenario"), "FAMILIA_VACIA"),
            F.when(vacio("idioma"), "IDIOMA_VACIO")
        )).withColumn("estado_calidad",
            F.when(F.col("errores_criticos") == "", "VALIDO").otherwise("CUARENTENA"))
        .drop("_id_normalizado", "_id_repetido")
    )

    (evaluacion.coalesce(int(reparto["evaluados"])).write.mode("overwrite").parquet(rutas["evaluated"]))
    evaluados = spark.read.parquet(rutas["evaluated"])
    validos = evaluados.filter(F.col("estado_calidad") == "VALIDO").drop(
        "errores_criticos", "estado_calidad")
    cuarentena = evaluados.filter(F.col("estado_calidad") == "CUARENTENA")
    resumen = (evaluados.groupBy("estado_calidad")
               .agg(F.count("*").alias("num_registros"))
               .withColumn("porcentaje", F.round(
                   F.col("num_registros") * F.lit(100.0) / F.lit(filas_origen), 2)))
    recuentos = {r["estado_calidad"]: int(r["num_registros"]) for r in resumen.collect()}
    n_validos = recuentos.get("VALIDO", 0)
    n_cuarentena = recuentos.get("CUARENTENA", 0)
    if n_validos + n_cuarentena != filas_origen:
        raise ValueError("Los registros del CSV no cuadran con validez + cuarentena")

    def recuento_reglas(campo, tipo):
        return (evaluados.select(F.explode(F.split(F.col(campo), ";")).alias("regla"))
                .filter(F.col("regla") != "").groupBy("regla")
                .agg(F.count("*").alias("num_registros"))
                .withColumn("tipo", F.lit(tipo)))

    incidencias = (
        recuento_reglas("errores_criticos", "CRITICO")
        .unionByName(recuento_reglas("advertencias", "ADVERTENCIA"))
        .withColumn("porcentaje_sobre_total", F.round(
            F.col("num_registros") * F.lit(100.0) / F.lit(filas_origen), 2))
        .select("tipo", "regla", "num_registros", "porcentaje_sobre_total")
    )
    validos.coalesce(int(reparto["curado"])).write.mode("overwrite").parquet(rutas["curated"])
    cuarentena.coalesce(int(reparto["cuarentena"])).write.mode("overwrite").parquet(rutas["quarantine"])
    resumen.coalesce(int(reparto["informes"])).write.mode("overwrite").option("header", True).csv(
        rutas["quality_summary"])
    incidencias.coalesce(int(reparto["informes"])).write.mode("overwrite").option("header", True).csv(
        rutas["quality_incidents"])
    if spark.read.parquet(rutas["curated"]).count() != n_validos:
        raise AssertionError("Diferencia en el numero de validos guardados")
    if spark.read.parquet(rutas["quarantine"]).count() != n_cuarentena:
        raise AssertionError("Diferencia en el numero de cuarentena guardados")
    print(f"Calidad OK: {filas_origen:,} originales = "
          f"{n_validos:,} validos + {n_cuarentena:,} cuarentena "
          f"({time.perf_counter() - t0:.1f} s)", flush=True)
    return spark.read.parquet(rutas["curated"])


def procesar(spark, base, conf, rutas, limite_registros=None):
    from pyspark.sql import functions as F
    from pyspark.sql.types import StructType, StructField, StringType, BooleanType

    columns = base["procesamiento"]["original_columns"]
    esquema = StructType([StructField(c, BooleanType() if c in (
        "es_ambiguo", "tiene_multiples_incidencias") else StringType(), True)
        for c in columns])
    esquema_aux = StructType([
        StructField("categoria", StringType(), True),
        StructField("subcategoria", StringType(), True),
    ])
    df_raw = (spark.read.schema(esquema).option("header", True)
              .option("enforceSchema", False).csv(rutas["dataset_hdfs"]))
    df_cat = (spark.read.schema(esquema_aux).option("header", True)
              .option("enforceSchema", False).csv(rutas["categories_hdfs"]))
    if limite_registros is not None:
        df_raw = df_raw.limit(int(limite_registros))
        print(f"PRUEBA AISLADA: utilizando como maximo {limite_registros:,} correos", flush=True)
    enriquecido = (df_raw.join(df_cat.select("subcategoria", "categoria"),
                               on="subcategoria", how="left")
                   .replace(base["procesamiento"]["zone_equivalences"], subset=["zona"]))
    df_curada = evaluar_calidad(spark, df_raw, df_cat, enriquecido, rutas, conf)

    df_ml = df_curada.select(F.col("texto").alias("rawtext"), "categoria",
                             "subcategoria", "zona", "split")
    if df_ml.filter(F.col("categoria").isNull()).limit(1).count() > 0:
        raise ValueError("Hay registros ML sin categoria")
    part_col = base["procesamiento"]["partition_column"]
    df_ml.write.mode("overwrite").partitionBy(part_col).parquet(rutas["ml"])
    print("Parquet ML guardado:", rutas["ml"], flush=True)

    datos_mr = (
        df_curada.select(F.trim(F.col("zona")).alias("zona"),
                         F.trim(F.col("familia_escenario")).alias("familia_escenario"))
        .replace(base["procesamiento"]["zone_equivalences"], subset=["zona"])
        .withColumn("zona", F.when(F.col("zona").isNull() | (F.col("zona") == ""),
                                   "Desconocida").otherwise(F.col("zona")))
        .withColumn("familia_escenario", F.when(
            F.col("familia_escenario").isNull() |
            (F.col("familia_escenario") == ""), "SIN_FAMILIA")
            .otherwise(F.col("familia_escenario")))
    )
    analitica = (datos_mr.filter(F.lower(F.trim(F.col("zona"))) != "desconocida")
                 .groupBy("zona", "familia_escenario").count()
                 .withColumnRenamed("count", "num_mensajes"))
    analitica.write.mode("overwrite").parquet(rutas["analytics"])

    entrada_mr = datos_mr.select(F.concat_ws("\t",
        F.regexp_replace(F.col("zona"), r"[\t\r\n]", " "),
        F.regexp_replace(F.col("familia_escenario"), r"[\t\r\n]", " ")
    ).alias("value"))
    entrada_mr.coalesce(int(conf["particiones_salida"]["mapreduce_entrada"])).write.mode("overwrite").text(rutas["mr_input"])
    print("Entrada MapReduce preparada:", rutas["mr_input"], flush=True)

    from operator import add
    rdd_entrada = spark.sparkContext.textFile(rutas["mr_input"])
    rdd_salida = (rdd_entrada.map(lambda linea: linea.split("\t", 1))
        .filter(lambda campos: len(campos) == 2)
        .map(lambda campos: ((campos[0], campos[1]), 1))
        .reduceByKey(add, numPartitions=int(conf["mapreduce"]["reducers_spark"]))
        .map(lambda fila: "{}\t{}\t{}".format(fila[0][0], fila[0][1], fila[1])))
    jpath = spark.sparkContext._jvm.org.apache.hadoop.fs.Path(rutas["rdd"])
    fs = jpath.getFileSystem(spark.sparkContext._jsc.hadoopConfiguration())
    if fs.exists(jpath):
        fs.delete(jpath, True)
    rdd_salida.saveAsTextFile(rutas["rdd"])
    print("Spark RDD guardado:", rutas["rdd"], flush=True)
    return df_ml


def mllib_baseline(spark, df_ml, conf, rutas):
    """Linea base separada del modelo PyTorch, con API Spark MLlib real."""
    from pyspark.sql import functions as F
    from pyspark.ml import Pipeline
    from pyspark.ml.feature import RegexTokenizer, HashingTF, StringIndexer
    from pyspark.ml.classification import NaiveBayes
    from pyspark.ml.evaluation import MulticlassClassificationEvaluator

    m = conf["mllib"]
    datos = df_ml.filter(
        F.col("rawtext").isNotNull() & F.col("categoria").isNotNull()
        & F.col("split").isin("train", "test")
    )
    muestra = datos.sample(False, float(m["fraction"]), int(m["seed"]))
    train = muestra.filter(F.col("split") == "train").limit(int(m["max_train"])).cache()
    test = muestra.filter(F.col("split") == "test").limit(int(m["max_test"])).cache()
    n_train, n_test = train.count(), test.count()
    if n_train < 100 or n_test < 20:
        raise ValueError(f"Muestra MLlib demasiado pequena: train={n_train}, test={n_test}")
    pipeline = Pipeline(stages=[
        StringIndexer(inputCol="categoria", outputCol="label", handleInvalid="keep"),
        RegexTokenizer(inputCol="rawtext", outputCol="tokens", pattern=r"\W+"),
        HashingTF(inputCol="tokens", outputCol="features",
                  numFeatures=int(m["hashing_features"])),
        NaiveBayes(featuresCol="features", labelCol="label", modelType="multinomial"),
    ])
    predicciones = pipeline.fit(train).transform(test)
    accuracy = MulticlassClassificationEvaluator(
        labelCol="label", predictionCol="prediction", metricName="accuracy"
    ).evaluate(predicciones)
    f1 = MulticlassClassificationEvaluator(
        labelCol="label", predictionCol="prediction", metricName="f1"
    ).evaluate(predicciones)
    registro = [(int(n_train), int(n_test), float(accuracy), float(f1), int(m["seed"]))]
    schema = "train_rows long, test_rows long, accuracy double, weighted_f1 double, seed int"
    spark.createDataFrame(registro, schema=schema).coalesce(1).write.mode("overwrite").json(
        rutas["mllib_metrics"])
    train.unpersist()
    test.unpersist()
    print(f"MLlib NaiveBayes OK: train={n_train:,} test={n_test:,} "
          f"accuracy={accuracy:.4f}, F1 ponderado={f1:.4f}", flush=True)


def preparar_prueba_aislada(rutas, conf):
    """Conserva las entradas HDFS y redirige TODAS las escrituras del flujo."""
    import copy

    rutas_prueba = dict(rutas)
    config_prueba = copy.deepcopy(conf)
    raiz_resultados = rutas["quality_summary"].rsplit("/", 1)[0]
    raiz_prueba = raiz_resultados + "/prueba_integracion"
    for clave in (
        "evaluated", "curated", "quarantine", "ml", "mr_input",
        "quality_summary", "quality_incidents", "analytics", "rdd", "mllib_metrics"
    ):
        rutas_prueba[clave] = raiz_prueba + "/" + clave

    # El ensayo utiliza menos datos y menos recursos que la ejecucion real.
    config_prueba["spark"].update({
        "executor_memory": "1g", "executor_cores": 1,
        "max_cores": 1, "shuffle_partitions": 8
    })
    config_prueba["mllib"].update({
        "fraction": 0.5, "max_train": 5000,
        "max_test": 2000
    })
    config_prueba["particiones_salida"].update({
        "evaluados": 2, "curado": 2,
        "cuarentena": 2, "informes": 1,
        "mapreduce_entrada": 2
    })
    return rutas_prueba, config_prueba


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check", action="store_true", help="Revisar sin escribir datos")
    actions.add_argument("--run", action="store_true", help="Procesar todo; reescribe salidas HDFS")
    actions.add_argument("--smoke-test", action="store_true",
                         help="Prueba de 20.000 filas con salidas aisladas; no modifica resultados oficiales")
    args = parser.parse_args()
    base, conf = leer_configuracion()
    rutas = rutas_config(base, conf)
    mostrar_comprobacion(base, conf, rutas)
    if args.check:
        return
    for key in ("dataset_local", "categories_local"):
        if not rutas[key].is_file():
            raise FileNotFoundError(f"Falta fichero necesario: {rutas[key]}")
    if args.smoke_test:
        rutas, conf = preparar_prueba_aislada(rutas, conf)
        print("PRUEBA AISLADA: NO se copiara ni modificara la zona HDFS raw", flush=True)
        print("Escrituras limitadas a:", rutas["evaluated"].rsplit("/", 1)[0], flush=True)
    spark = preparar_spark(base, conf, rutas)
    start = time.perf_counter()
    try:
        if args.run:
            ingerir_csv(spark, rutas)
        ml = procesar(spark, base, conf, rutas,
                     limite_registros=20000 if args.smoke_test else None)
        mllib_baseline(spark, ml, conf, rutas)
        print(f"PIPELINE TERMINADO CORRECTAMENTE en {time.perf_counter()-start:.1f} s")
    finally:
        spark.stop()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR EN PIPELINE: {error}", file=sys.stderr, flush=True)
        raise
