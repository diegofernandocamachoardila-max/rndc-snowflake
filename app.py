# -*- coding: utf-8 -*-

import streamlit as st
import requests
import logging
import pandas as pd
import xml.etree.ElementTree as ET
import traceback

from xml.sax.saxutils import escape

import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas


# =============================================================================
# CONFIGURACIÓN DE LA PÁGINA
# =============================================================================

st.set_page_config(
    page_title="RNDC → Snowflake",
    page_icon="🚛",
    layout="wide"
)


# =============================================================================
# LOGGING
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# =============================================================================
# FUNCIÓN PARA LEER SECRETS
# =============================================================================

def obtener_secret(nombre):

    try:
        return str(st.secrets[nombre])

    except Exception:
        return None


# =============================================================================
# CONFIGURACIÓN RNDC
# =============================================================================

RNDC_USERNAME = obtener_secret("RNDC_USERNAME")
RNDC_PASSWORD = obtener_secret("RNDC_PASSWORD")
NIT_EMPRESA = obtener_secret("NIT_EMPRESA")


# =============================================================================
# CONFIGURACIÓN SNOWFLAKE
# =============================================================================

SNOWFLAKE_ACCOUNT = obtener_secret("SNOWFLAKE_ACCOUNT")
SNOWFLAKE_USER = obtener_secret("SNOWFLAKE_USER")
SNOWFLAKE_PASSWORD = obtener_secret("SNOWFLAKE_PASSWORD")
SNOWFLAKE_ROLE = obtener_secret("SNOWFLAKE_ROLE")
SNOWFLAKE_WAREHOUSE = obtener_secret("SNOWFLAKE_WAREHOUSE")
SNOWFLAKE_DATABASE = obtener_secret("SNOWFLAKE_DATABASE")
SNOWFLAKE_SCHEMA = obtener_secret("SNOWFLAKE_SCHEMA")


# =============================================================================
# TABLA
# =============================================================================

SNOWFLAKE_TABLE = "MANIFIESTOS_PROCESO4"


# =============================================================================
# CLASE CONSULTA RNDC
# =============================================================================

class ConsultaRNDC:


    URLS = {

        "consulta":
        "http://plc.mintransporte.gov.co:8080/soap/IBPMServices",

        "expedicion":
        "http://rndcws2.mintransporte.gov.co:8080/soap/IBPMServices",

        "pruebas":
        "http://rndcpruebas.mintransporte.gov.co:8080/soap/IBPMServices"

    }


    # =========================================================================
    # INICIALIZACIÓN
    # =========================================================================

    def __init__(
        self,
        username,
        password,
        url_tipo="consulta"
    ):

        self.username = username
        self.password = password
        self.url = self.URLS[url_tipo]
        self.session = requests.Session()


    # =========================================================================
    # CONSULTAR MANIFIESTOS - PROCESO 4
    # =========================================================================

    def consultar_manifiestos(
        self,
        nit_empresa,
        fecha_inicio,
        fecha_fin
    ):


        logging.info(
            f"Consultando manifiestos desde "
            f"{fecha_inicio} hasta {fecha_fin}"
        )


        # =====================================================================
        # TODOS LOS CAMPOS DEL PROCESO 4
        # EXCEPTO CONSECUTIVOREMESA
        # =====================================================================

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


        # =====================================================================
        # XML RNDC
        # =====================================================================

        body = f"""<root>

<acceso>
<username>{self.username}</username>
<password>{self.password}</password>
</acceso>

<solicitud>
<tipo>3</tipo>
<procesoid>4</procesoid>
</solicitud>

<variables>
{variables}
</variables>

<documento>
<NUMNITEMPRESATRANSPORTE>{nit_empresa}</NUMNITEMPRESATRANSPORTE>
</documento>

<documentorango>
<iniFECHAING>'{fecha_inicio}'</iniFECHAING>
<finFECHAING>'{fecha_fin}'</finFECHAING>
</documentorango>

</root>"""


        # =====================================================================
        # SOAP
        # =====================================================================

        xml_request = f"""<?xml version='1.0' encoding='ISO-8859-1'?>

<SOAP-ENV:Envelope
xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xmlns:xsd="http://www.w3.org/2001/XMLSchema-instance">

<SOAP-ENV:Body>

<m:AtenderMensajeRNDC
xmlns:m="urn:BPMServicesIntf-IBPMServices">

<Request xsi:type="xsd:string">{escape(body)}</Request>

</m:AtenderMensajeRNDC>

</SOAP-ENV:Body>

</SOAP-ENV:Envelope>"""


        # =====================================================================
        # CONSULTA RNDC
        # =====================================================================

        try:

            response = self.session.post(

                self.url,

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


            return self._procesar_respuesta(
                response.text
            )


        except requests.exceptions.Timeout:

            raise Exception(
                "Timeout consultando el RNDC."
            )


        except requests.exceptions.HTTPError as e:

            raise Exception(
                f"Error HTTP: {e}"
            )


        except Exception as e:

            raise Exception(
                f"Error consultando RNDC: {e}"
            )


    # =========================================================================
    # PROCESAR RESPUESTA SOAP
    # =========================================================================

    def _procesar_respuesta(
        self,
        respuesta_xml
    ):


        try:

            root = ET.fromstring(
                respuesta_xml
            )


            fault = root.find(
                ".//{http://schemas.xmlsoap.org/soap/envelope/}Fault"
            )


            if fault is not None:

                fault_string = ""

                for child in fault:

                    fault_string += (
                        f"{child.tag}: "
                        f"{child.text}\n"
                    )


                raise Exception(
                    f"SOAP Fault: {fault_string}"
                )


            nodo_return = root.find(
                ".//return"
            )


            if nodo_return is None:

                return []


            contenido = nodo_return.text


            if not contenido:

                return []


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


                # RNDC11 = consulta procesada, pero sin documentos
                if (
                    "RNDC11" in mensaje_error
                    and "Documento no encontrado" in mensaje_error
                ):

                    return []


                raise Exception(
                    mensaje_error
                )


            return self._extraer_registros(
                contenido
            )


        except Exception as e:

            raise Exception(
                f"Error procesando respuesta: {e}"
            )


    # =========================================================================
    # EXTRAER REGISTROS
    # =========================================================================

    def _extraer_registros(
        self,
        contenido_xml
    ):


        registros = []


        try:

            contenido_xml = contenido_xml.strip()


            root = ET.fromstring(
                contenido_xml
            )


            documentos = root.findall(
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


            logging.info(
                f"Se encontraron "
                f"{len(registros)} registros."
            )


            return registros


        except Exception as e:

            logging.warning(
                f"No fue posible interpretar "
                f"documentos: {e}"
            )


            return []


    # =========================================================================
    # CONVERTIR A DATAFRAME
    # =========================================================================

    def consultar_dataframe(
        self,
        nit_empresa,
        fecha_inicio,
        fecha_fin
    ):


        registros = self.consultar_manifiestos(

            nit_empresa,

            fecha_inicio,

            fecha_fin

        )


        return pd.DataFrame(
            registros
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
# CREAR O ACTUALIZAR TABLA
# =============================================================================

def preparar_tabla_snowflake(
    conexion,
    dataframe
):


    cursor = conexion.cursor()


    try:


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


        # ---------------------------------------------------------------------
        # CONSULTAR COLUMNAS QUE YA EXISTEN
        # ---------------------------------------------------------------------

        sql_columnas = f"""
        SELECT COLUMN_NAME
        FROM {SNOWFLAKE_DATABASE}.INFORMATION_SCHEMA.COLUMNS
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


        # ---------------------------------------------------------------------
        # AGREGAR COLUMNAS NUEVAS SI NO EXISTEN
        # ---------------------------------------------------------------------

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
# ELIMINAR REGISTROS EXISTENTES EN SNOWFLAKE POR INGRESOID
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
            {SNOWFLAKE_DATABASE}.{SNOWFLAKE_SCHEMA}.{SNOWFLAKE_TABLE}

            WHERE "INGRESOID" IN (
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


        # ---------------------------------------------------------------------
        # COPIA DEL DATAFRAME
        # ---------------------------------------------------------------------

        df_snowflake = dataframe.copy()


        # ---------------------------------------------------------------------
        # COLUMNAS EN MAYÚSCULAS
        # ---------------------------------------------------------------------

        df_snowflake.columns = [

            str(columna).upper()

            for columna in df_snowflake.columns

        ]


        # ---------------------------------------------------------------------
        # CONVERTIR VALORES A STRING
        # ---------------------------------------------------------------------

        for columna in df_snowflake.columns:


            df_snowflake[columna] = (

                df_snowflake[columna]

                .astype("string")

            )


        # ---------------------------------------------------------------------
        # CONECTAR A SNOWFLAKE
        # ---------------------------------------------------------------------

        conexion = conectar_snowflake()


        # ---------------------------------------------------------------------
        # PREPARAR TABLA
        # ---------------------------------------------------------------------

        columnas_agregadas = (
            preparar_tabla_snowflake(

                conexion,

                df_snowflake

            )
        )


        # ---------------------------------------------------------------------
        # ELIMINAR DUPLICADOS YA EXISTENTES
        # ---------------------------------------------------------------------

        eliminar_registros_existentes(

            conexion,

            df_snowflake

        )


        # ---------------------------------------------------------------------
        # CARGAR DATAFRAME
        # ---------------------------------------------------------------------

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
# INTERFAZ STREAMLIT
# =============================================================================

st.title(
    "🚛 RNDC → Snowflake"
)


st.write(
    "Decarga manifiestos"
)


st.divider()


# =============================================================================
# VALIDAR SECRETS
# =============================================================================

secrets_faltantes = []


if not RNDC_USERNAME:
    secrets_faltantes.append("RNDC_USERNAME")

if not RNDC_PASSWORD:
    secrets_faltantes.append("RNDC_PASSWORD")

if not NIT_EMPRESA:
    secrets_faltantes.append("NIT_EMPRESA")

if not SNOWFLAKE_ACCOUNT:
    secrets_faltantes.append("SNOWFLAKE_ACCOUNT")

if not SNOWFLAKE_USER:
    secrets_faltantes.append("SNOWFLAKE_USER")

if not SNOWFLAKE_PASSWORD:
    secrets_faltantes.append("SNOWFLAKE_PASSWORD")

if not SNOWFLAKE_ROLE:
    secrets_faltantes.append("SNOWFLAKE_ROLE")

if not SNOWFLAKE_WAREHOUSE:
    secrets_faltantes.append("SNOWFLAKE_WAREHOUSE")

if not SNOWFLAKE_DATABASE:
    secrets_faltantes.append("SNOWFLAKE_DATABASE")

if not SNOWFLAKE_SCHEMA:
    secrets_faltantes.append("SNOWFLAKE_SCHEMA")


if secrets_faltantes:

    st.error(
        "❌ Faltan Secrets de configuración."
    )


    st.code(
        "\n".join(
            secrets_faltantes
        )
    )


    st.stop()


# =============================================================================
# FORMULARIO
# =============================================================================

columna1, columna2 = st.columns(
    2
)


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


    # =========================================================================
    # VALIDAR FECHAS
    # =========================================================================

    if fecha_fin < fecha_inicio:


        st.error(
            "❌ La fecha final no puede "
            "ser menor que la fecha inicial."
        )


        st.stop()


    # =========================================================================
    # FORMATO EXACTO RNDC
    # =========================================================================

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


        # =====================================================================
        # CREAR CONSULTA
        # =====================================================================

        consulta = ConsultaRNDC(

            RNDC_USERNAME,

            RNDC_PASSWORD,

            url_tipo="consulta"

        )


        # =====================================================================
        # CONSULTAR SOLO PROCESO 4
        # =====================================================================

        with st.spinner(
            "Consultando manifiestos del Proceso 4 en RNDC..."
        ):


            dataframe = consulta.consultar_dataframe(

                NIT_EMPRESA,

                fecha_inicio_rndc,

                fecha_fin_rndc

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
            # CONVERTIR COLUMNAS A MAYÚSCULAS
            # =================================================================

            dataframe.columns = [

                str(columna).upper()

                for columna in dataframe.columns

            ]


            # =================================================================
            # ELIMINAR DUPLICADOS POR INGRESOID
            # =================================================================

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


            duplicados_eliminados = (

                registros_antes

                -

                registros_finales

            )


            # =================================================================
            # MOSTRAR RESULTADO
            # =================================================================

            st.success(
                f"✅ Consulta RNDC exitosa: "
                f"{registros_finales} registros encontrados."
            )


            col1, col2, col3 = st.columns(
                3
            )


            col1.metric(
                "Registros RNDC",
                registros_antes
            )


            col2.metric(
                "Duplicados eliminados",
                duplicados_eliminados
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
            # CARGAR EN SNOWFLAKE
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


            col1, col2 = st.columns(
                2
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
