import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas

from xml.sax.saxutils import escape


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
# URLs RNDC
# =============================================================================

URL_RNDC = (
    "http://plc.mintransporte.gov.co:8080/"
    "soap/IBPMServices"
)


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
# CREAR / ACTUALIZAR TABLA
# =============================================================================

def preparar_tabla_snowflake(conexion, dataframe):

    cursor = conexion.cursor()

    try:

        columnas_sql = []

        for columna in dataframe.columns:

            columnas_sql.append(
                f'"{columna}" VARCHAR'
            )


        sql_crear_tabla = f"""

        CREATE TABLE IF NOT EXISTS
        {SNOWFLAKE_DATABASE}.
        {SNOWFLAKE_SCHEMA}.
        {SNOWFLAKE_TABLE}

        (
            {", ".join(columnas_sql)}
        )

        """

        cursor.execute(sql_crear_tabla)


        # -------------------------------------------------------------
        # CONSULTAR COLUMNAS EXISTENTES
        # -------------------------------------------------------------

        sql_columnas = f"""

        SELECT COLUMN_NAME

        FROM
        {SNOWFLAKE_DATABASE}.INFORMATION_SCHEMA.COLUMNS

        WHERE TABLE_SCHEMA = '{SNOWFLAKE_SCHEMA}'

        AND TABLE_NAME = '{SNOWFLAKE_TABLE.upper()}'

        """


        cursor.execute(sql_columnas)


        columnas_existentes = {

            fila[0].upper()

            for fila in cursor.fetchall()

        }


        # -------------------------------------------------------------
        # AGREGAR COLUMNAS NUEVAS
        # -------------------------------------------------------------

        columnas_agregadas = []


        for columna in dataframe.columns:

            if columna.upper() not in columnas_existentes:

                sql_agregar_columna = f"""

                ALTER TABLE

                {SNOWFLAKE_DATABASE}.
                {SNOWFLAKE_SCHEMA}.
                {SNOWFLAKE_TABLE}

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


            lote = ingresos_ids[
                inicio:
                inicio + tamanio_lote
            ]


            valores_sql_lista = []


            for valor in lote:

                valor_limpio = str(
                    valor
                ).replace(

                    "'",

                    "''"

                )


                valores_sql_lista.append(

                    f"'{valor_limpio}'"

                )


            valores_sql = ", ".join(
                valores_sql_lista
            )


            sql_delete = f"""

            DELETE FROM

            {SNOWFLAKE_DATABASE}.
            {SNOWFLAKE_SCHEMA}.
            {SNOWFLAKE_TABLE}

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

def cargar_dataframe_snowflake(dataframe):

    conexion = None


    try:

        if dataframe.empty:

            raise Exception(
                "No hay registros para cargar."
            )


        # -------------------------------------------------------------
        # COPIA DEL DATAFRAME
        # -------------------------------------------------------------

        df_snowflake = dataframe.copy()


        # -------------------------------------------------------------
        # COLUMNAS EN MAYÚSCULAS
        # -------------------------------------------------------------

        df_snowflake.columns = [

            str(columna).upper()

            for columna
            in df_snowflake.columns

        ]


        # -------------------------------------------------------------
        # CONVERTIR TODO A STRING
        # -------------------------------------------------------------

        for columna in df_snowflake.columns:

            df_snowflake[columna] = (

                df_snowflake[columna]

                .astype("string")

            )


        # -------------------------------------------------------------
        # CONECTAR
        # -------------------------------------------------------------

        conexion = conectar_snowflake()


        # -------------------------------------------------------------
        # PREPARAR TABLA
        # -------------------------------------------------------------

        columnas_agregadas = (
            preparar_tabla_snowflake(

                conexion,

                df_snowflake

            )
        )


        # -------------------------------------------------------------
        # ELIMINAR DUPLICADOS EXISTENTES
        # -------------------------------------------------------------

        eliminar_registros_existentes(

            conexion,

            df_snowflake

        )


        # -------------------------------------------------------------
        # CARGAR DATAFRAME
        # -------------------------------------------------------------

        success, chunks, rows, output = write_pandas(

            conn=conexion,

            df=df_snowflake,

            table_name=SNOWFLAKE_TABLE,

            database=SNOWFLAKE_DATABASE,

            schema=SNOWFLAKE_SCHEMA,

            quote_identifiers=True,

            auto_create_table=False,

            overwrite=False

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
# CONSULTAR RNDC
# =============================================================================

def consultar_rndc(

    fecha_inicio,

    fecha_fin

):


    # =============================================================
    # TODOS LOS CAMPOS DEL PROCESO 4
    # EXCEPTO CONSECUTIVOREMESA
    # =============================================================

    variables = """

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


    # =============================================================
    # XML RNDC
    # =============================================================

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
{variables}
</variables>

<documento>
<NUMNITEMPRESATRANSPORTE>
{NIT_EMPRESA}
</NUMNITEMPRESATRANSPORTE>
</documento>

<documentorango>

<iniFECHAING>
'{fecha_inicio}'
</iniFECHAING>

<finFECHAING>
'{fecha_fin}'
</finFECHAING>

</documentorango>

</root>"""


    # =============================================================
    # SOAP
    # =============================================================

    xml_request = f"""<?xml version='1.0' encoding='ISO-8859-1'?>

<SOAP-ENV:Envelope

xmlns:SOAP-ENV=
"http://schemas.xmlsoap.org/soap/envelope/"

xmlns:xsi=
"http://www.w3.org/2001/XMLSchema-instance"

xmlns:xsd=
"http://www.w3.org/2001/XMLSchema-instance">

<SOAP-ENV:Body>

<m:AtenderMensajeRNDC

xmlns:m=
"urn:BPMServicesIntf-IBPMServices">

<Request xsi:type="xsd:string">
{escape(body)}
</Request>

</m:AtenderMensajeRNDC>

</SOAP-ENV:Body>

</SOAP-ENV:Envelope>"""


    # =============================================================
    # CONSULTAR
    # =============================================================

    response = requests.post(

        URL_RNDC,

        data=xml_request.encode(
            "ISO-8859-1"
        ),

        headers={

            "Content-Type":

            "text/xml; charset=ISO-8859-1"

        },

        timeout=120

    )


    response.raise_for_status()


    # =============================================================
    # PROCESAR SOAP
    # =============================================================

    root = ET.fromstring(
        response.text
    )


    fault = root.find(

        ".//"
        "{http://schemas.xmlsoap.org/soap/envelope/}"
        "Fault"

    )


    if fault is not None:

        raise Exception(
            "SOAP Fault en RNDC"
        )


    nodo_return = root.find(
        ".//return"
    )


    if nodo_return is None:

        return pd.DataFrame()


    contenido = nodo_return.text


    if not contenido:

        return pd.DataFrame()


    root_rndc = ET.fromstring(
        contenido.strip()
    )


    error = root_rndc.find(
        ".//ErrorMSG"
    )


if error is not None:

    mensaje_error = (
        error.text or ""
    ).strip()

    # RNDC11 significa que la consulta fue procesada,
    # pero no se encontraron documentos para los filtros.
    if (
        "RNDC11" in mensaje_error
        and "Documento no encontrado" in mensaje_error
    ):
        return pd.DataFrame()

    raise Exception(
        mensaje_error
    )


    # =============================================================
    # EXTRAER DOCUMENTOS
    # =============================================================

    registros = []


    documentos = root_rndc.findall(
        ".//documento"
    )


    for doc in documentos:


        registro = {}


        for campo in doc:


            nombre = (

                campo.tag

                .split("}")[-1]

            )


            registro[nombre] = (
                campo.text
            )


        registros.append(
            registro
        )


    return pd.DataFrame(
        registros
    )


# =============================================================================
# INTERFAZ
# =============================================================================

st.title("🚛 RNDC → Snowflake")

st.write(
    "Consulta los manifiestos del Proceso 4 "
    "y cárgalos automáticamente a Snowflake."
)


st.divider()


# =============================================================================
# FORMULARIO
# =============================================================================

columna1, columna2 = st.columns(2)


with columna1:

    fecha_inicio = st.date_input(
        "Fecha inicial"
    )


with columna2:

    fecha_fin = st.date_input(
        "Fecha final"
    )


st.divider()


boton_consultar = st.button(

    "🚀 CONSULTAR Y CARGAR A SNOWFLAKE",

    type="primary",

    use_container_width=True

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


    fecha_inicio_rndc = (
        fecha_inicio.strftime(
            "%Y/%m/%d"
        )
    )


    fecha_fin_rndc = (
        fecha_fin.strftime(
            "%Y/%m/%d"
        )
    )


    try:


        # =========================================================
        # CONSULTA RNDC
        # =========================================================

        with st.spinner(
            "Consultando información en RNDC..."
        ):


            dataframe = consultar_rndc(

                fecha_inicio_rndc,

                fecha_fin_rndc

            )


        # =========================================================
        # VALIDAR
        # =========================================================

        if dataframe.empty:


            st.warning(
                "⚠️ No se encontraron registros "
                "para el período seleccionado."
            )


        else:


            # =====================================================
            # MAYÚSCULAS
            # =====================================================

            dataframe.columns = [

                columna.upper()

                for columna
                in dataframe.columns

            ]


            # =====================================================
            # DUPLICADOS
            # =====================================================

            registros_antes = len(
                dataframe
            )


            if "INGRESOID" in dataframe.columns:


                dataframe = (

                    dataframe

                    .drop_duplicates(

                        subset=["INGRESOID"],

                        keep="last"

                    )

                )


            registros_finales = len(
                dataframe
            )


            duplicados = (

                registros_antes

                -

                registros_finales

            )


            # =====================================================
            # MOSTRAR RESULTADO
            # =====================================================

            st.success(
                f"✅ Consulta RNDC exitosa: "
                f"{registros_finales} registros encontrados."
            )


            col1, col2, col3 = st.columns(3)


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


            # =====================================================
            # CARGAR SNOWFLAKE
            # =====================================================

            with st.spinner(
                "Cargando información a Snowflake..."
            ):


                resultado = (
                    cargar_dataframe_snowflake(

                        dataframe

                    )
                )


            # =====================================================
            # RESULTADO FINAL
            # =====================================================

            st.success(
                "🎉 CARGA EXITOSA EN SNOWFLAKE"
            )


            col1, col2 = st.columns(2)


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
