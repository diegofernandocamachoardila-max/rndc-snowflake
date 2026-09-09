# -*- coding: utf-8 -*-

import os

import snowflake.connector
from fastapi import FastAPI, HTTPException


# ============================================================
# CONFIGURACIÓN DE LA API
# ============================================================

app = FastAPI(
    title="RNDC API",
    description="API para consulta de manifiestos RNDC",
    version="1.0.0"
)


# ============================================================
# CONFIGURACIÓN DE SNOWFLAKE
# ============================================================

SNOWFLAKE_ACCOUNT = os.getenv("SNOWFLAKE_ACCOUNT")
SNOWFLAKE_USER = os.getenv("SNOWFLAKE_USER")
SNOWFLAKE_PASSWORD = os.getenv("SNOWFLAKE_PASSWORD")
SNOWFLAKE_ROLE = os.getenv("SNOWFLAKE_ROLE")
SNOWFLAKE_WAREHOUSE = os.getenv("SNOWFLAKE_WAREHOUSE")
SNOWFLAKE_DATABASE = os.getenv("SNOWFLAKE_DATABASE")
SNOWFLAKE_SCHEMA = os.getenv("SNOWFLAKE_SCHEMA")

SNOWFLAKE_TABLE = "MANIFIESTOS_PROCESO4"


# ============================================================
# CONEXIÓN A SNOWFLAKE
# ============================================================

def conectar_snowflake():

    return snowflake.connector.connect(
        account=SNOWFLAKE_ACCOUNT,
        user=SNOWFLAKE_USER,
        password=SNOWFLAKE_PASSWORD,
        role=SNOWFLAKE_ROLE,
        warehouse=SNOWFLAKE_WAREHOUSE,
        database=SNOWFLAKE_DATABASE,
        schema=SNOWFLAKE_SCHEMA
    )


# ============================================================
# CONSULTA DEL MANIFIESTO
# ============================================================

def consultar_manifiesto(numero_manifiesto: str):

    conexion = None
    cursor = None

    try:

        conexion = conectar_snowflake()
        cursor = conexion.cursor()

        sql = f"""
            SELECT *
            FROM {SNOWFLAKE_DATABASE}.{SNOWFLAKE_SCHEMA}.{SNOWFLAKE_TABLE}
            WHERE NUMMANIFIESTOCARGA = %s
        """

        cursor.execute(
            sql,
            (str(numero_manifiesto).strip(),)
        )

        columnas = [
            descripcion[0]
            for descripcion in cursor.description
        ]

        registros = cursor.fetchall()

        resultados = []

        for registro in registros:

            fila = {}

            for columna, valor in zip(columnas, registro):

                if valor is None:
                    fila[columna] = None
                else:
                    fila[columna] = str(valor)

            resultados.append(fila)

        return resultados

    finally:

        if cursor is not None:
            cursor.close()

        if conexion is not None:
            conexion.close()


# ============================================================
# INICIO
# ============================================================

@app.get("/")
def inicio():

    return {
        "mensaje": "RNDC API funcionando",
        "servicio": "Consulta de manifiestos"
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():

    return {
        "status": "OK"
    }


# ============================================================
# CONSULTAR MANIFIESTO
# ============================================================

@app.get("/manifiesto/{numero_manifiesto}")
def obtener_manifiesto(numero_manifiesto: str):

    numero_manifiesto = numero_manifiesto.strip()

    if not numero_manifiesto:

        raise HTTPException(
            status_code=400,
            detail="Debe ingresar un número de manifiesto."
        )

    try:

        resultados = consultar_manifiesto(
            numero_manifiesto
        )

        if not resultados:

            return {
                "encontrado": False,
                "numero_manifiesto": numero_manifiesto,
                "mensaje": "No se encontró información para el manifiesto."
            }

        return {
            "encontrado": True,
            "numero_manifiesto": numero_manifiesto,
            "cantidad_registros": len(resultados),
            "datos": resultados
        }

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=f"Error consultando Snowflake: {str(error)}"
        )
