import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
import snowflake.connector

from snowflake.connector.pandas_tools import write_pandas
from xml.sax.saxutils import escape
from datetime import timedelta


# =============================================================================
# CONFIGURACIÓN DE LA PÁGINA
# =============================================================================

st.set_page_config(
    page_title="RNDC → Snowflake",
    page_icon="🚛",
    layout="wide"
)


# =============================================================================
# FUNCIÓN PARA LEER SECRETS
# =============================================================================

def obtener_secret(nombre):

    try:
        return st.secrets[nombre]

    except Exception:
        return None


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

RNDC_USERNAME = obtener_secret("RNDC_USERNAME")
RNDC_PASSWORD = obtener_secret("RNDC_PASSWORD")
NIT_EMPRESA = obtener_secret("NIT_EMPRESA")


SNOWFLAKE_ACCOUNT = obtener_secret("SNOWFLAKE_ACCOUNT")
SNOWFLAKE_USER = obtener_secret("SNOWFLAKE_USER")
SNOWFLAKE_PASSWORD = obtener_secret("SNOWFLAKE_PASSWORD")
SNOWFLAKE_ROLE = obtener_secret("SNOWFLAKE_ROLE")
SNOWFLAKE_WAREHOUSE = obtener_secret("SNOWFLAKE_WAREHOUSE")
SNOWFLAKE_DATABASE = obtener_secret("SNOWFLAKE_DATABASE")
SNOWFLAKE_SCHEMA = obtener_secret("SNOWFLAKE_SCHEMA")


SNOWFLAKE_TABLE = "MANIFIESTOS_PROCESO4"


# =============================================================================
# VALIDAR SECRETS
# =============================================================================

SECRETS_REQUERIDOS = [
    "RNDC_USERNAME",
    "RNDC_PASSWORD",
    "NIT_EMPRESA",
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_PASSWORD",
    "SNOWFLAKE_ROLE",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_DATABASE",
    "SNOWFLAKE_SCHEMA"
]


def validar_secrets():

    faltantes = []

    for nombre in SECRETS_REQUERIDOS:

        if not obtener_secret(nombre):

            faltantes.append(nombre)

    if faltantes:

        raise Exception(
            "Faltan los siguientes Secrets en Streamlit: "
            + ", ".join(faltantes)
        )


# =============================================================================
# URL RNDC
# =============================================================================

URL_RNDC = (
    "http://plc.mintransporte.gov.co:8080/"
    "soap/IBPMServices"
)


HEADERS_RNDC = {
    "Content-Type": "text/xml; charset=ISO-8859-1"
}


# =============================================================================
# FUNCIÓN GENERAL PARA ENVIAR CONSULTAS A RNDC
# =============================================================================

def enviar_rndc(body):

    xml_request = f"""<?xml version='1.0' encoding='ISO-8859-1'?>

<SOAP-ENV:Envelope
xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xmlns:xsd="http://www.w3.org/2001/XMLSchema">

<SOAP-ENV:Body>

<m:AtenderMensajeRNDC
xmlns:m="urn:BPMServicesIntf-IBPMServices">

<Request xsi:type="xsd:string">{escape(body)}</Request>

</m:AtenderMensajeRNDC>

</SOAP-ENV:Body>

</SOAP-ENV:Envelope>"""

    response = requests.post(

        URL_RNDC,

        data=xml_request.encode(
            "ISO-8859-1"
        ),

        headers=HEADERS_RNDC,

        timeout=120
    )

    response.raise_for_status()


    # =========================================================================
    # PROCESAR RESPUESTA SOAP
    # =========================================================================

    root = ET.fromstring(
        response.text
    )


    # Buscar cualquier nodo llamado return
    nodo_return = None

    for elemento in root.iter():

        if elemento.tag.split("}")[-1] == "return":

            nodo_return = elemento
            break


    if nodo_return is None:

        return None


    return nodo_return.text


# =============================================================================
# PROCESO 6
#
# BUSCAR MANIFIESTOS POR RANGO DE FECHAS
# =============================================================================

def consultar_proceso6(
    fecha_inicio,
    fecha_fin
):

    inicio = fecha_inicio.strftime(
        "%Y/%m/%d"
    )

    fin = fecha_fin.strftime(
        "%Y/%m/%d"
    )


    body = f"""<root>

<acceso>
<username>{RNDC_USERNAME}</username>
<password>{RNDC_PASSWORD}</password>
</acceso>

<solicitud>
<tipo>3</tipo>
<procesoid>6</procesoid>
</solicitud>

<variables>
INGRESOID,FECHAING,NUMMANIFIESTOCARGA
</variables>

<documento>

<NUMNITEMPRESATRANSPORTE>
{NIT_EMPRESA}
</NUMNITEMPRESATRANSPORTE>

</documento>

<documentorango>

<iniFECHAING>'{inicio}'</iniFECHAING>

<finFECHAING>'{fin}'</finFECHAING>

</documentorango>

</root>"""


    contenido = enviar_rndc(
        body
    )


    if not contenido:

        return []


    root = ET.fromstring(
        contenido.strip()
    )


    # =========================================================================
    # VALIDAR ERROR RNDC
    # =========================================================================

    error = root.find(
        ".//ErrorMSG"
    )


    if error is not None:

        mensaje = error.text or "Error desconocido RNDC"

        raise Exception(
            f"Error RNDC Proceso 6: {mensaje}"
        )


    # =========================================================================
    # EXTRAER DOCUMENTOS
    # =========================================================================

    registros = []


    documentos = root.findall(
        ".//documento"
    )


    for documento in documentos:

        registro = {}


        for campo in documento:

            nombre = (
                campo.tag
                .split("}")[-1]
            )

            registro[nombre] = (
                campo.text.strip()
                if campo.text
                else None
            )


        registros.append(
            registro
        )


    return registros


# =============================================================================
# VARIABLES DEL PROCESO 4
#
# CAMPOS QUE VAMOS A DESCARGAR
# =============================================================================

VARIABLES_PROCESO4 = """
INGRESOID,
NUMMANIFIESTOCARGA,
FECHAING,
NUMPLACA,
NUMPLACAREMOLQUE,
VALORFLETEPACTADOVIAJE,
FECHAEXPEDICIONMANIFIESTO,
CODOPERACIONTRANSPORTE,
CONSECUTIVOINFORMACIONVIAJE,
MANNROMANIFIESTOTRANSBORDO,
CODMUNICIPIOORIGENMANIFIESTO,
CODMUNICIPIODESTINOMANIFIESTO,
CODIDTITULARMANIFIESTO,
NUMIDTITULARMANIFIESTO,
CODIDCONDUCTOR,
NUMIDCONDUCTOR,
CODIDCONDUCTOR2,
NUMIDCONDUCTOR2,
RETENCIONFUENTEMANIFIESTO,
RETENCIONICAMANIFIESTOCARGA,
VALORANTICIPOMANIFIESTO,
CODMUNICIPIOPAGOSALDO,
FECHAPAGOSALDOMANIFIESTO,
CODRESPONSABLEPAGOCARGUE,
CODRESPONSABLEPAGODESCARGUE,
NITMONITOREOFLOTA,
ACEPTACIONELECTRONICA,
OBSERVACIONES,
CODVIA,
SEGURIDADQR
"""


# =============================================================================
# PROCESO 4
#
# CONSULTAR DETALLE DE UN MANIFIESTO
# =============================================================================

def consultar_proceso4(
    numero_manifiesto
):

    body = f"""<root>

<acceso>
<username>{RNDC_USERNAME}</username>
<password>{RNDC_PASSWORD}</password>
</acceso>

<solicitud>
<tipo>3</tipo>
<procesoid>4</procesoid>
</solicitud>

<variables>
{VARIABLES_PROCESO4}
</variables>

<documento>

<NUMNITEMPRESATRANSPORTE>
{NIT_EMPRESA}
</NUMNITEMPRESATRANSPORTE>

<NUMMANIFIESTOCARGA>
{numero_manifiesto}
</NUMMANIFIESTOCARGA>

</documento>

</root>"""


    contenido = enviar_rndc(
        body
    )


    if not contenido:

        return None


    root = ET.fromstring(
        contenido.strip()
    )


    # =========================================================================
    # VALIDAR ERROR RNDC
    # =========================================================================

    error = root.find(
        ".//ErrorMSG"
    )


    if error is not None:

        return None


    # =========================================================================
    # BUSCAR DOCUMENTO
    # =========================================================================

    documento = root.find(
        ".//documento"
    )


    if documento is None:

        return None


    registro = {}


    for campo in documento:

        nombre = (
            campo.tag
            .split("}")[-1]
        )


        registro[nombre] = (

            campo.text.strip()

            if campo.text

            else None

        )


    return registro


# =============================================================================
# CONSULTAR RNDC COMPLETO
#
# PASO 1 → PROCESO 6 POR FECHA
# PASO 2 → PROCESO 4 POR CADA MANIFIESTO
# =============================================================================

def consultar_rndc(
    fecha_inicio,
    fecha_fin
):


    # =========================================================================
    # PASO 1
    #
    # CONSULTAR PROCESO 6 EN BLOQUES DE 5 DÍAS
    # =========================================================================

    todos_los_registros = []


    fecha_actual = fecha_inicio


    while fecha_actual <= fecha_fin:


        fecha_bloque_fin = min(

            fecha_actual + timedelta(days=4),

            fecha_fin

        )


        registros_bloque = (

            consultar_proceso6(

                fecha_actual,

                fecha_bloque_fin

            )

        )


        todos_los_registros.extend(

            registros_bloque

        )


        fecha_actual = (

            fecha_bloque_fin

            +

            timedelta(days=1)

        )


    # =========================================================================
    # VALIDAR RESULTADO PROCESO 6
    # =========================================================================

    if not todos_los_registros:

        return pd.DataFrame()


    dataframe_proceso6 = (

        pd.DataFrame(

            todos_los_registros

        )

    )


    # =========================================================================
    # BUSCAR COLUMNA NUMMANIFIESTOCARGA
    # =========================================================================

    columna_manifiesto = None


    for columna in dataframe_proceso6.columns:


        if columna.upper() == "NUMMANIFIESTOCARGA":


            columna_manifiesto = columna

            break


    if columna_manifiesto is None:


        raise Exception(

            "El Proceso 6 no devolvió "
            "la columna NUMMANIFIESTOCARGA."

        )


    # =========================================================================
    # EXTRAER MANIFIESTOS ÚNICOS
    # =========================================================================

    manifiestos = (

        dataframe_proceso6[

            columna_manifiesto

        ]

        .dropna()

        .astype(str)

        .str.strip()

        .loc[lambda serie: serie != ""]

        .drop_duplicates()

        .tolist()

    )


    if not manifiestos:


        return pd.DataFrame()


    # =========================================================================
    # PASO 2
    #
    # CONSULTAR PROCESO 4 PARA CADA MANIFIESTO
    # =========================================================================

    resultados = []


    total = len(

        manifiestos

    )


    barra_progreso = (

        st.progress(

            0,

            text=(
                "Consultando detalles "
                "de los manifiestos..."
            )

        )

    )


    estado = st.empty()


    for posicion, numero_manifiesto in enumerate(

        manifiestos,

        start=1

    ):


        estado.write(

            f"Consultando manifiesto "

            f"{posicion:,} de {total:,}"

        )


        try:


            detalle = (

                consultar_proceso4(

                    numero_manifiesto

                )

            )


            if detalle is not None:


                resultados.append(

                    detalle

                )


        except Exception:

            # Si un manifiesto individual falla,
            # continuamos con los demás
            pass


        progreso = (

            int(

                posicion

                /

                total

                *

                100

            )

        )


        barra_progreso.progress(

            progreso,

            text=(

                f"Consultando manifiesto "

                f"{posicion:,} de {total:,}"

            )

        )


    estado.empty()


    # =========================================================================
    # RESULTADO FINAL
    # =========================================================================

    dataframe_final = (

        pd.DataFrame(

            resultados

        )

    )


    return dataframe_final


# =============================================================================
# CONECTAR A SNOWFLAKE
# =============================================================================

def conectar_snowflake():

    conexion = snowflake.connector.connect(

        account=SNOWFLAKE_ACCOUNT,

        user=SNOWFLAKE_USER,

        password=SNOWFLAKE_PASSWORD,

        role=SNOWFLAKE_ROLE,

        warehouse=SNOWFLAKE_WAREHOUSE,

        database=SNOWFLAKE_DATABASE,

        schema=SNOWFLAKE_SCHEMA

    )


    return conexion


# =============================================================================
# CREAR / ACTUALIZAR TABLA EN SNOWFLAKE
# =============================================================================

def preparar_tabla_snowflake(

    conexion,

    dataframe

):


    cursor = conexion.cursor()


    try:


        # =====================================================================
        # CREAR TABLA SI NO EXISTE
        # =====================================================================

        columnas_sql = []


        for columna in dataframe.columns:


            columnas_sql.append(

                f'"{columna}" VARCHAR'

            )


        sql_crear_tabla = f"""

        CREATE TABLE IF NOT EXISTS
        {SNOWFLAKE_DATABASE}.{SNOWFLAKE_SCHEMA}.{SNOWFLAKE_TABLE}

        (
            {", ".join(columnas_sql)}
        )

        """


        cursor.execute(

            sql_crear_tabla

        )


        # =====================================================================
        # CONSULTAR COLUMNAS EXISTENTES
        # =====================================================================

        sql_columnas = f"""

        SELECT COLUMN_NAME

        FROM
        {SNOWFLAKE_DATABASE}.INFORMATION_SCHEMA.COLUMNS

        WHERE TABLE_SCHEMA = '{SNOWFLAKE_SCHEMA}'

        AND TABLE_NAME = '{SNOWFLAKE_TABLE.upper()}'

        """


        cursor.execute(

            sql_columnas

        )


        columnas_existentes = {

            fila[0].upper()

            for fila in cursor.fetchall()

        }


        # =====================================================================
        # AGREGAR NUEVAS COLUMNAS
        # =====================================================================

        columnas_agregadas = []


        for columna in dataframe.columns:


            if columna.upper() not in columnas_existentes:


                sql_agregar_columna = f"""

                ALTER TABLE
                {SNOWFLAKE_DATABASE}.{SNOWFLAKE_SCHEMA}.{SNOWFLAKE_TABLE}

                ADD COLUMN "{columna}" VARCHAR

                """


                cursor.execute(

                    sql_agregar_columna

                )


                columnas_agregadas.append(

                    columna

                )


        return columnas_agregadas


    finally:


        cursor.close()


# =============================================================================
# ELIMINAR REGISTROS EXISTENTES POR INGRESOID
# =============================================================================

def eliminar_registros_existentes(

    conexion,

    dataframe

):


    if dataframe.empty:

        return


    if "INGRESOID" not in dataframe.columns:

        return


    cursor = conexion.cursor()


    try:


        ingresos_ids = (

            dataframe["INGRESOID"]

            .dropna()

            .astype(str)

            .unique()

            .tolist()

        )


        if not ingresos_ids:

            return


        tamanio_lote = 500


        for inicio in range(

            0,

            len(ingresos_ids),

            tamanio_lote

        ):


            lote = (

                ingresos_ids[

                    inicio:

                    inicio + tamanio_lote

                ]

            )


            valores_sql_lista = []


            for valor in lote:


                valor_limpio = (

                    str(valor)

                    .replace(

                        "'",

                        "''"

                    )

                )


                valores_sql_lista.append(

                    f"'{valor_limpio}'"

                )


            valores_sql = (

                ", ".join(

                    valores_sql_lista

                )

            )


            sql_delete = f"""

            DELETE FROM
            {SNOWFLAKE_DATABASE}.{SNOWFLAKE_SCHEMA}.{SNOWFLAKE_TABLE}

            WHERE "INGRESOID" IN
            (
                {valores_sql}
            )

            """


            cursor.execute(

                sql_delete

            )


    finally:


        cursor.close()


# =============================================================================
# CARGAR DATAFRAME A SNOWFLAKE
# =============================================================================

def cargar_dataframe_snowflake(

    dataframe

):


    conexion = None


    try:


        if dataframe.empty:


            raise Exception(

                "No hay registros para cargar."

            )


        # =====================================================================
        # COPIA
        # =====================================================================

        df_snowflake = (

            dataframe.copy()

        )


        # =====================================================================
        # MAYÚSCULAS
        # =====================================================================

        df_snowflake.columns = [

            str(columna).upper()

            for columna

            in df_snowflake.columns

        ]


        # =====================================================================
        # CONVERTIR TODO A STRING
        # =====================================================================

        for columna in df_snowflake.columns:


            df_snowflake[columna] = (

                df_snowflake[columna]

                .astype("string")

            )


        # =====================================================================
        # CONECTAR
        # =====================================================================

        conexion = (

            conectar_snowflake()

        )


        # =====================================================================
        # PREPARAR TABLA
        # =====================================================================

        columnas_agregadas = (

            preparar_tabla_snowflake(

                conexion,

                df_snowflake

            )

        )


        # =====================================================================
        # ELIMINAR DUPLICADOS EXISTENTES
        # =====================================================================

        eliminar_registros_existentes(

            conexion,

            df_snowflake

        )


        # =====================================================================
        # CARGAR
        # =====================================================================

        success, chunks, rows, output = (

            write_pandas(

                conn=conexion,

                df=df_snowflake,

                table_name=SNOWFLAKE_TABLE,

                database=SNOWFLAKE_DATABASE,

                schema=SNOWFLAKE_SCHEMA,

                quote_identifiers=True,

                auto_create_table=False,

                overwrite=False

            )

        )


        if not success:


            raise Exception(

                "Snowflake no confirmó "
                "la carga de los registros."

            )


        return {

            "rows": rows,

            "columnas_agregadas":

                columnas_agregadas

        }


    finally:


        if conexion is not None:


            conexion.close()


# =============================================================================
# INTERFAZ
# =============================================================================

st.title(

    "🚛 RNDC → Snowflake"

)


st.write(

    "Consulta los manifiestos por fecha utilizando "
    "el Proceso 6 y descarga automáticamente el detalle "
    "de cada manifiesto con el Proceso 4."

)


st.divider()


# =============================================================================
# FORMULARIO
# =============================================================================

columna1, columna2 = (

    st.columns(2)

)


with columna1:


    fecha_inicio = (

        st.date_input(

            "Fecha inicial"

        )

    )


with columna2:


    fecha_fin = (

        st.date_input(

            "Fecha final"

        )

    )


st.divider()


boton_consultar = (

    st.button(

        "🚀 CONSULTAR Y CARGAR A SNOWFLAKE",

        type="primary",

        use_container_width=True

    )

)


# =============================================================================
# EJECUCIÓN
# =============================================================================

if boton_consultar:


    if fecha_fin < fecha_inicio:


        st.error(

            "❌ La fecha final no puede ser "
            "menor que la fecha inicial."

        )


        st.stop()


    try:


        # =====================================================================
        # VALIDAR SECRETS
        # =====================================================================

        validar_secrets()


        # =====================================================================
        # CONSULTAR RNDC
        # =====================================================================

        with st.spinner(

            "Paso 1: buscando números de manifiesto "
            "en el Proceso 6..."

        ):


            dataframe = (

                consultar_rndc(

                    fecha_inicio,

                    fecha_fin

                )

            )


        # =====================================================================
        # VALIDAR RESULTADO
        # =====================================================================

        if dataframe.empty:


            st.warning(

                "⚠️ No se encontraron registros "
                "para el período seleccionado."

            )


        else:


            # =================================================================
            # MAYÚSCULAS
            # =================================================================

            dataframe.columns = [

                str(columna).upper()

                for columna

                in dataframe.columns

            ]


            # =================================================================
            # ELIMINAR DUPLICADOS
            # =================================================================

            registros_antes = (

                len(dataframe)

            )


            if "INGRESOID" in dataframe.columns:


                dataframe = (

                    dataframe

                    .drop_duplicates(

                        subset=["INGRESOID"],

                        keep="last"

                    )

                )


            registros_finales = (

                len(dataframe)

            )


            duplicados = (

                registros_antes

                -

                registros_finales

            )


            # =================================================================
            # MOSTRAR RESULTADO
            # =================================================================

            st.success(

                f"✅ Consulta RNDC exitosa: "
                f"{registros_finales:,} registros encontrados."

            )


            col1, col2, col3 = (

                st.columns(3)

            )


            col1.metric(

                "Registros RNDC",

                registros_antes

            )


            col2.metric(

                "Duplicados eliminados",

                duplicados

            )


            col3.metric(

                "Registros finales",

                registros_finales

            )


            st.subheader(

                "Vista previa de los datos"

            )


            st.dataframe(

                dataframe,

                use_container_width=True

            )


            # =================================================================
            # CARGAR SNOWFLAKE
            # =================================================================

            with st.spinner(

                "Cargando información a Snowflake..."

            ):


                resultado = (

                    cargar_dataframe_snowflake(

                        dataframe

                    )

                )


            # =================================================================
            # RESULTADO FINAL
            # =================================================================

            st.success(

                "🎉 CARGA EXITOSA EN SNOWFLAKE"

            )


            col1, col2 = (

                st.columns(2)

            )


            col1.metric(

                "Registros cargados",

                resultado["rows"]

            )


            col2.metric(

                "Columnas nuevas",

                len(

                    resultado[
                        "columnas_agregadas"
                    ]

                )

            )


            if resultado[
                "columnas_agregadas"
            ]:


                st.info(

                    "Columnas agregadas automáticamente: "

                    +

                    ", ".join(

                        resultado[
                            "columnas_agregadas"
                        ]

                    )

                )


            st.write(

                "Destino:"

            )


            st.code(

                f"{SNOWFLAKE_DATABASE}."

                f"{SNOWFLAKE_SCHEMA}."

                f"{SNOWFLAKE_TABLE}"

            )


    except Exception as e:


        st.error(

            "❌ Ocurrió un error"

        )


        st.exception(

            e

        )
