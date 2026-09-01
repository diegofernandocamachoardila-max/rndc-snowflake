import re
import time
from datetime import timedelta

import pandas as pd
import requests
import streamlit as st
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas


# =============================================================================
# CONFIGURACIÓN STREAMLIT
# =============================================================================

st.set_page_config(
    page_title="RNDC → Snowflake",
    page_icon="🚛",
    layout="wide"
)


# =============================================================================
# LEER SECRETS
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
# TABLA SNOWFLAKE
# =============================================================================

SNOWFLAKE_TABLE = "MANIFIESTOS_PROCESO4"


# =============================================================================
# URL RNDC
# =============================================================================

URL_RNDC = (
    "http://plc.mintransporte.gov.co:8080/"
    "soap/IBPMServices"
)


# =============================================================================
# VARIABLES DEL PROCESO 4
# =============================================================================

VARIABLES_PROCESO4 = [

    "INGRESOID",
    "NUMMANIFIESTOCARGA",
    "FECHAING",
    "NUMPLACA",
    "NUMPLACAREMOLQUE",
    "VALORFLETEPACTADOVIAJE"

]


# =============================================================================
# CONSULTA RNDC
# =============================================================================

class ConsultaRNDC:


    def __init__(self, username, password):

        self.username = username
        self.password = password
        self.session = requests.Session()


    # =========================================================================
    # CONSULTAR PROCESO 4
    # =========================================================================

    def consultar_manifiestos(
        self,
        nit_empresa,
        fecha_inicio,
        fecha_fin
    ):

        variables = ",".join(
            VARIABLES_PROCESO4
        )


        # ---------------------------------------------------------------------
        # IMPORTANTE
        #
        # FECHAING ES UN CAMPO ALFANUMÉRICO PARA EL MOTOR DEL RNDC.
        # Por eso las fechas se envían entre comillas sencillas.
        # ---------------------------------------------------------------------

        body = f"""
<root>
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
</root>
"""


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

</SOAP-ENV:Envelope>
"""


        try:

            response = self.session.post(

                URL_RNDC,

                data=xml_request.encode(
                    "ISO-8859-1"
                ),

                headers={
                    "Content-Type":
                    "text/xml; charset=ISO-8859-1"
                },

                timeout=180

            )


            response.raise_for_status()


            return self._procesar_respuesta(
                response.text
            )


        except requests.exceptions.Timeout:

            raise Exception(

                f"Timeout consultando RNDC entre "
                f"{fecha_inicio} y {fecha_fin}."

            )


        except requests.exceptions.HTTPError as e:

            raise Exception(
                f"Error HTTP RNDC: {e}"
            )


        except Exception as e:

            mensaje = str(e)

            if mensaje.startswith(
                "Error RNDC:"
            ):
                raise


            raise Exception(
                f"Error RNDC: {mensaje}"
            )


    # =========================================================================
    # PROCESAR RESPUESTA
    # =========================================================================

    def _procesar_respuesta(
        self,
        respuesta_xml
    ):

        try:

            root = ET.fromstring(
                respuesta_xml
            )


            # =============================================================
            # SOAP FAULT
            # =============================================================

            fault = root.find(
                ".//{http://schemas.xmlsoap.org/soap/envelope/}Fault"
            )


            if fault is not None:

                textos = []


                for child in fault:

                    if child.text:

                        textos.append(
                            child.text
                        )


                raise Exception(

                    "SOAP Fault: "

                    +

                    " | ".join(
                        textos
                    )

                )


            # =============================================================
            # BUSCAR RETURN
            # =============================================================

            nodo_return = None


            for nodo in root.iter():

                nombre = nodo.tag.split(
                    "}"
                )[-1]


                if nombre.lower() == "return":

                    nodo_return = nodo
                    break


            if (
                nodo_return is None
                or
                not nodo_return.text
            ):

                return []


            contenido = (
                nodo_return.text.strip()
            )


            if not contenido:

                return []


            root_rndc = ET.fromstring(
                contenido
            )


            # =============================================================
            # ERRORES RNDC
            # =============================================================

            mensaje_error = None


            for nodo in root_rndc.iter():

                nombre = nodo.tag.split(
                    "}"
                )[-1]


                if nombre == "ErrorMSG":

                    mensaje_error = (
                        nodo.text
                        or
                        ""
                    ).strip()

                    break


            if mensaje_error:


                # Documento no encontrado
                # significa simplemente sin registros.

                if (

                    "RNDC11"
                    in mensaje_error

                    and

                    "Documento no encontrado"
                    in mensaje_error

                ):

                    return []


                raise Exception(
                    mensaje_error
                )


            # =============================================================
            # REGISTROS
            # =============================================================

            registros = []


            documentos = []


            for nodo in root_rndc.iter():

                nombre = nodo.tag.split(
                    "}"
                )[-1]


                if nombre.lower() == "documento":

                    documentos.append(
                        nodo
                    )


            for doc in documentos:

                registro = {}


                for campo in doc:

                    nombre = (
                        campo.tag.split(
                            "}"
                        )[-1]
                    )


                    registro[nombre] = (
                        campo.text
                    )


                if registro:

                    registros.append(
                        registro
                    )


            return registros


        except ET.ParseError as e:

            raise Exception(

                "No fue posible interpretar "
                f"la respuesta XML del RNDC: {e}"

            )


        except Exception as e:

            mensaje = str(e)


            if mensaje.startswith(
                "Error RNDC:"
            ):

                raise


            raise Exception(

                "Error procesando respuesta: "
                f"{mensaje}"

            )


    # =========================================================================
    # DATAFRAME
    # =========================================================================

    def consultar_dataframe(
        self,
        nit_empresa,
        fecha_inicio,
        fecha_fin
    ):

        registros = (

            self.consultar_manifiestos(
                nit_empresa,
                fecha_inicio,
                fecha_fin
            )

        )


        return pd.DataFrame(
            registros
        )


# =============================================================================
# EXTRAER FECHA
# =============================================================================

def extraer_fecha(valor):

    if (
        valor is None
        or
        pd.isna(valor)
    ):

        return None


    texto = str(
        valor
    ).strip()


    # =========================================================================
    # DD/MM/YYYY
    # =========================================================================

    coincidencia = re.search(
        r"(\d{1,2}/\d{1,2}/\d{4})",
        texto
    )


    if coincidencia:

        fecha = pd.to_datetime(
            coincidencia.group(1),
            dayfirst=True,
            errors="coerce"
        )


        if pd.notna(
            fecha
        ):

            return fecha.date()


    # =========================================================================
    # YYYY/MM/DD
    # =========================================================================

    coincidencia = re.search(
        r"(\d{4}/\d{1,2}/\d{1,2})",
        texto
    )


    if coincidencia:

        fecha = pd.to_datetime(
            coincidencia.group(1),
            errors="coerce"
        )


        if pd.notna(
            fecha
        ):

            return fecha.date()


    # =========================================================================
    # YYYY-MM-DD
    # =========================================================================

    coincidencia = re.search(
        r"(\d{4}-\d{1,2}-\d{1,2})",
        texto
    )


    if coincidencia:

        fecha = pd.to_datetime(
            coincidencia.group(1),
            errors="coerce"
        )


        if pd.notna(
            fecha
        ):

            return fecha.date()


    # =========================================================================
    # INTENTO GENERAL
    # =========================================================================

    fecha = pd.to_datetime(
        texto,
        dayfirst=True,
        errors="coerce"
    )


    if pd.notna(
        fecha
    ):

        return fecha.date()


    return None


# =============================================================================
# FILTRAR PERÍODO EXACTO
# =============================================================================

def filtrar_periodo_solicitado(
    dataframe,
    fecha_inicio,
    fecha_fin
):

    if dataframe.empty:

        return dataframe


    columna_fecha = None


    for columna in dataframe.columns:

        if (

            str(
                columna
            ).upper()

            ==

            "FECHAING"

        ):

            columna_fecha = columna
            break


    # Si RNDC no devolvió FECHAING
    # no eliminamos registros.

    if columna_fecha is None:

        return dataframe


    fechas = dataframe[
        columna_fecha
    ].apply(
        extraer_fecha
    )


    mascara = fechas.apply(
        lambda fecha:
        (
            fecha is not None
            and
            fecha_inicio <= fecha <= fecha_fin
        )
    )


    return dataframe.loc[
        mascara
    ].copy()


# =============================================================================
# CONSULTAR UN RANGO Y FILTRAR UN SOLO DÍA
# =============================================================================

def consultar_y_filtrar_dia(
    consulta,
    fecha_objetivo,
    fecha_consulta_inicio,
    fecha_consulta_fin
):

    inicio_rndc = (

        fecha_consulta_inicio.strftime(
            "%Y/%m/%d"
        )

    )


    fin_rndc = (

        fecha_consulta_fin.strftime(
            "%Y/%m/%d"
        )

    )


    df = consulta.consultar_dataframe(

        NIT_EMPRESA,

        inicio_rndc,

        fin_rndc

    )


    if df.empty:

        return df


    return filtrar_periodo_solicitado(

        df,

        fecha_objetivo,

        fecha_objetivo

    )


# =============================================================================
# CONSULTAR DÍA CON ESTRATEGIAS DE RESPALDO
#
# SOLO PROCESO 4
# =============================================================================

def consultar_dia_con_respaldo(
    consulta,
    fecha_objetivo
):

    errores = []


    dia_anterior = (

        fecha_objetivo

        -

        timedelta(days=1)

    )


    dia_siguiente = (

        fecha_objetivo

        +

        timedelta(days=1)

    )


    dos_dias_despues = (

        fecha_objetivo

        +

        timedelta(days=2)

    )


    estrategias = [

        (
            "normal",
            fecha_objetivo,
            dia_siguiente
        ),

        (
            "ventana_anterior",
            dia_anterior,
            dia_siguiente
        ),

        (
            "ventana_ampliada",
            fecha_objetivo,
            dos_dias_despues
        ),

        (
            "ventana_anterior_ampliada",
            dia_anterior,
            dos_dias_despues
        )

    ]


    for nombre_estrategia, inicio, fin in estrategias:


        for intento in range(1, 3):

            try:

                df = consultar_y_filtrar_dia(

                    consulta,

                    fecha_objetivo,

                    inicio,

                    fin

                )


                return (

                    df,

                    nombre_estrategia,

                    errores

                )


            except Exception as e:

                mensaje = str(e)


                errores.append(

                    {

                        "estrategia":
                        nombre_estrategia,

                        "intento":
                        intento,

                        "inicio":
                        inicio.strftime(
                            "%Y/%m/%d"
                        ),

                        "fin":
                        fin.strftime(
                            "%Y/%m/%d"
                        ),

                        "error":
                        mensaje

                    }

                )


                if intento < 2:

                    time.sleep(
                        1
                    )


        time.sleep(
            1
        )


    resumen = " | ".join(

        [

            (

                f"{error['estrategia']} "

                f"[{error['inicio']} → {error['fin']}]: "

                f"{error['error']}"

            )

            for error in errores

        ]

    )


    raise Exception(
        resumen
    )


# =============================================================================
# CONSULTAR PERÍODO GRANDE
# =============================================================================

def consultar_periodo_grande(

    consulta,

    fecha_inicio,

    fecha_fin,

    callback_progreso=None

):

    dataframes = []

    errores_dias = []

    estrategias_usadas = []


    total_dias = (

        fecha_fin

        -

        fecha_inicio

    ).days + 1


    fecha_actual = fecha_inicio

    indice = 0


    while fecha_actual <= fecha_fin:


        indice += 1


        siguiente_dia = (

            fecha_actual

            +

            timedelta(days=1)

        )


        if callback_progreso is not None:

            callback_progreso(

                indice,

                total_dias,

                fecha_actual,

                siguiente_dia

            )


        try:

            (

                df_dia,

                estrategia,

                errores_intentos

            ) = consultar_dia_con_respaldo(

                consulta,

                fecha_actual

            )


            estrategias_usadas.append(

                (

                    fecha_actual,

                    estrategia,

                    len(df_dia)

                )

            )


            if not df_dia.empty:

                dataframes.append(
                    df_dia
                )


        except Exception as e:

            errores_dias.append(

                (

                    fecha_actual,

                    str(e)

                )

            )


        fecha_actual += (
            timedelta(days=1)
        )


    st.session_state[
        "rndc_errores_dias"
    ] = errores_dias


    st.session_state[
        "rndc_estrategias_usadas"
    ] = estrategias_usadas


    if not dataframes:

        return pd.DataFrame()


    dataframe = pd.concat(

        dataframes,

        ignore_index=True,

        sort=False

    )


    dataframe.columns = [

        str(
            columna
        ).upper()

        for columna

        in dataframe.columns

    ]


    if (

        "INGRESOID"

        in

        dataframe.columns

    ):

        dataframe = dataframe.drop_duplicates(

            subset=[
                "INGRESOID"
            ],

            keep="last"

        )


    return dataframe


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
# PREPARAR TABLA SNOWFLAKE
# =============================================================================

def preparar_tabla_snowflake(

    conexion,

    dataframe

):

    cursor = conexion.cursor()


    try:


        columnas_sql = [

            f'"{columna}" VARCHAR'

            for columna

            in dataframe.columns

        ]


        sql_crear_tabla = f"""

        CREATE TABLE IF NOT EXISTS

        {SNOWFLAKE_DATABASE}.
        {SNOWFLAKE_SCHEMA}.
        {SNOWFLAKE_TABLE}

        (

            {", ".join(columnas_sql)}

        )

        """


        cursor.execute(
            sql_crear_tabla
        )


        sql_columnas = f"""

        SELECT COLUMN_NAME

        FROM

        {SNOWFLAKE_DATABASE}
        .INFORMATION_SCHEMA.COLUMNS

        WHERE TABLE_SCHEMA = '{SNOWFLAKE_SCHEMA}'

        AND TABLE_NAME = '{SNOWFLAKE_TABLE.upper()}'

        """


        cursor.execute(
            sql_columnas
        )


        columnas_existentes = {

            fila[0].upper()

            for fila

            in cursor.fetchall()

        }


        columnas_agregadas = []


        for columna in dataframe.columns:


            if (

                columna.upper()

                not in

                columnas_existentes

            ):


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
# ELIMINAR REGISTROS EXISTENTES
# =============================================================================

def eliminar_registros_existentes(

    conexion,

    dataframe

):

    if dataframe.empty:

        return


    if (

        "INGRESOID"

        not in

        dataframe.columns

    ):

        return


    ingresos_ids = (

        dataframe[
            "INGRESOID"
        ]

        .dropna()

        .astype(str)

        .unique()

        .tolist()

    )


    if not ingresos_ids:

        return


    cursor = conexion.cursor()


    try:


        tamanio_lote = 500


        for inicio in range(

            0,

            len(
                ingresos_ids
            ),

            tamanio_lote

        ):


            lote = ingresos_ids[

                inicio:

                inicio + tamanio_lote

            ]


            valores_sql = ", ".join(

                "'" +

                valor.replace(

                    "'",

                    "''"

                )

                +

                "'"

                for valor

                in lote

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

def cargar_dataframe_snowflake(
    dataframe
):

    if dataframe.empty:

        raise Exception(
            "No hay registros para cargar."
        )


    conexion = None


    try:


        df_snowflake = dataframe.copy()


        df_snowflake.columns = [

            str(
                columna
            ).upper()

            for columna

            in df_snowflake.columns

        ]


        for columna in df_snowflake.columns:


            df_snowflake[
                columna
            ] = (

                df_snowflake[
                    columna
                ]

                .astype(
                    "string"
                )

            )


        conexion = conectar_snowflake()


        columnas_agregadas = preparar_tabla_snowflake(

            conexion,

            df_snowflake

        )


        eliminar_registros_existentes(

            conexion,

            df_snowflake

        )


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

            "rows":
            rows,

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

    "Consulta los manifiestos del Proceso 4 "
    "y cárgalos automáticamente a Snowflake."

)


st.divider()


# =============================================================================
# VALIDAR SECRETS
# =============================================================================

secrets_faltantes = []


configuracion_secrets = {

    "RNDC_USERNAME":
    RNDC_USERNAME,

    "RNDC_PASSWORD":
    RNDC_PASSWORD,

    "NIT_EMPRESA":
    NIT_EMPRESA,

    "SNOWFLAKE_ACCOUNT":
    SNOWFLAKE_ACCOUNT,

    "SNOWFLAKE_USER":
    SNOWFLAKE_USER,

    "SNOWFLAKE_PASSWORD":
    SNOWFLAKE_PASSWORD,

    "SNOWFLAKE_ROLE":
    SNOWFLAKE_ROLE,

    "SNOWFLAKE_WAREHOUSE":
    SNOWFLAKE_WAREHOUSE,

    "SNOWFLAKE_DATABASE":
    SNOWFLAKE_DATABASE,

    "SNOWFLAKE_SCHEMA":
    SNOWFLAKE_SCHEMA

}


for nombre, valor in (
    configuracion_secrets.items()
):


    if not valor:

        secrets_faltantes.append(
            nombre
        )


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


    if fecha_fin < fecha_inicio:


        st.error(

            "❌ La fecha final no puede "
            "ser menor que la fecha inicial."

        )


        st.stop()


    try:


        consulta = ConsultaRNDC(

            RNDC_USERNAME,

            RNDC_PASSWORD

        )


        mensaje_progreso = st.empty()

        barra_progreso = st.progress(
            0
        )


        def actualizar_progreso(

            indice,

            total,

            inicio,

            fin

        ):


            porcentaje = int(

                (

                    (indice - 1)

                    /

                    total

                )

                *

                100

            )


            barra_progreso.progress(

                max(

                    1,

                    porcentaje

                )

            )


            mensaje_progreso.info(

                f"Consultando día "

                f"{indice} de {total}: "

                f"{inicio.strftime('%Y/%m/%d')} "

                f"a "

                f"{fin.strftime('%Y/%m/%d')}"

            )


        with st.spinner(

            "Consultando información en RNDC..."

        ):


            dataframe = consultar_periodo_grande(

                consulta,

                fecha_inicio,

                fecha_fin,

                actualizar_progreso

            )


        barra_progreso.progress(
            100
        )


        mensaje_progreso.success(

            "✅ Consulta de todos los días terminada."

        )


        if dataframe.empty:


            st.warning(

                "⚠️ No se encontraron registros "
                "para el período seleccionado."

            )


            st.stop()


        errores_dias = st.session_state.get(

            "rndc_errores_dias",

            []

        )


        if errores_dias:


            dias_error = ", ".join(

                fecha.strftime(
                    "%Y/%m/%d"
                )

                for fecha, _ in errores_dias

            )


            st.warning(

                "⚠️ Algunos días no pudieron recuperarse "
                "después de todas las estrategias del Proceso 4: "

                f"{dias_error}"

            )


        estrategias_usadas = st.session_state.get(

            "rndc_estrategias_usadas",

            []

        )


        estrategias_respaldo = [

            (

                fecha,

                estrategia,

                registros

            )

            for (

                fecha,

                estrategia,

                registros

            )

            in estrategias_usadas

            if estrategia != "normal"

        ]


        if estrategias_respaldo:


            detalle = pd.DataFrame(

                estrategias_respaldo,

                columns=[

                    "FECHA",

                    "ESTRATEGIA",

                    "REGISTROS"

                ]

            )


            st.info(

                "🔄 Algunos días requirieron "
                "una ventana alternativa del Proceso 4."

            )


            with st.expander(

                "Ver detalle de estrategias utilizadas"

            ):

                st.dataframe(

                    detalle,

                    use_container_width=True

                )


        dataframe.columns = [

            str(
                columna
            ).upper()

            for columna

            in dataframe.columns

        ]


        registros_antes = len(
            dataframe
        )


        if (

            "INGRESOID"

            in

            dataframe.columns

        ):


            dataframe = dataframe.drop_duplicates(

                subset=[
                    "INGRESOID"
                ],

                keep="last"

            )


        registros_finales = len(
            dataframe
        )


        duplicados = (

            registros_antes

            -

            registros_finales

        )


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


        with st.spinner(

            "Cargando información a Snowflake..."

        ):


            resultado = cargar_dataframe_snowflake(

                dataframe

            )


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


    except Exception as e:


        st.error(
            "❌ Ocurrió un error"
        )


        st.exception(
            e
        )
