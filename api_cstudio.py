import os
from typing import Any

import snowflake.connector
from fastapi import FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader


# ============================================================
# CONFIGURACIÓN
# ============================================================

SNOWFLAKE_TABLE = "MANIFIESTOS_PROCESO4"

app = FastAPI(
    title="RNDC API",
    description="API para consultar manifiestos RNDC almacenados en Snowflake.",
    version="1.0.0",
)


# ============================================================
# SEGURIDAD
# ============================================================

API_KEY = os.getenv("RNDC_API_KEY")

api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
)


def validar_api_key(api_key: str | None):

    # Durante las pruebas locales, si no existe RNDC_API_KEY,
    # se permite la consulta.

    if API_KEY and api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="API key inválida."
        )


# ============================================================
# CONFIGURACIÓN SNOWFLAKE
# ============================================================

def obtener_variable(nombre: str) -> str:

    valor = os.getenv(nombre)

    if not valor:
        raise RuntimeError(
            f"No está configurada la variable de entorno: {nombre}"
        )

    return valor


def conectar_snowflake():

    return snowflake.connector.connect(

        account=obtener_variable(
            "SNOWFLAKE_ACCOUNT"
        ),

        user=obtener_variable(
            "SNOWFLAKE_USER"
        ),

        password=obtener_variable(
            "SNOWFLAKE_PASSWORD"
        ),

        role=obtener_variable(
            "SNOWFLAKE_ROLE"
        ),

        warehouse=obtener_variable(
            "SNOWFLAKE_WAREHOUSE"
        ),

        database=obtener_variable(
            "SNOWFLAKE_DATABASE"
        ),

        schema=obtener_variable(
            "SNOWFLAKE_SCHEMA"
        ),
    )


# ============================================================
# ENDPOINT DE SALUD
# ============================================================

@app.get(
    "/health",
    summary="Verificar disponibilidad de la API",
)
def health():

    return {
        "status": "ok",
        "service": "RNDC API"
    }


# ============================================================
# CONSULTAR MANIFIESTO
# ============================================================

@app.get(
    "/manifiesto/{numero_manifiesto}",
    summary="Consultar un manifiesto RNDC",
)
def consultar_manifiesto(

    numero_manifiesto: str,

    api_key: str | None = Security(
        api_key_header
    ),

) -> dict[str, Any]:

    validar_api_key(api_key)

    numero = numero_manifiesto.strip()

    if not numero:

        raise HTTPException(
            status_code=400,
            detail="Debe indicar un número de manifiesto."
        )

    conexion = None
    cursor = None

    try:

        conexion = conectar_snowflake()

        cursor = conexion.cursor()

        database = obtener_variable(
            "SNOWFLAKE_DATABASE"
        )

        schema = obtener_variable(
            "SNOWFLAKE_SCHEMA"
        )

        # ====================================================
        # CONSULTA SNOWFLAKE
        # ====================================================

        sql = f"""

            SELECT

                NUMMANIFIESTOCARGA,

                FECHAING,

                NUMPLACA,

                NUMPLACAREMOLQUE,

                VALORFLETEPACTADOVIAJE,

                CODMUNICIPIOORIGENMANIFIESTO,

                CODMUNICIPIODESTINOMANIFIESTO,

                NUMIDCONDUCTOR

            FROM
                {database}.{schema}.{SNOWFLAKE_TABLE}

            WHERE
                TRIM(NUMMANIFIESTOCARGA) = %s

            LIMIT 1

        """

        cursor.execute(
            sql,
            (numero,)
        )

        fila = cursor.fetchone()

        # ====================================================
        # MANIFIESTO NO ENCONTRADO
        # ====================================================

        if not fila:

            raise HTTPException(

                status_code=404,

                detail=(
                    f"No se encontró el manifiesto "
                    f"{numero}."
                )
            )

        # ====================================================
        # CONSTRUIR RESPUESTA
        # ====================================================

        columnas = [

            descripcion[0]

            for descripcion
            in cursor.description

        ]

        datos = dict(
            zip(
                columnas,
                fila
            )
        )

        # Convertir fechas y otros valores
        # a formatos compatibles con JSON.

        datos = {

            clave:

            (
                valor.isoformat()

                if hasattr(
                    valor,
                    "isoformat"
                )

                else str(valor)
                if valor is not None
                else None

            )

            for clave, valor
            in datos.items()

        }

        return {

            "encontrado": True,

            "manifiesto": numero,

            "datos": datos

        }

    except HTTPException:

        raise

    except Exception as error:

        raise HTTPException(

            status_code=500,

            detail=(
                "Error consultando Snowflake: "
                f"{str(error)}"
            )

        )

    finally:

        if cursor is not None:

            cursor.close()

        if conexion is not None:

            conexion.close()
