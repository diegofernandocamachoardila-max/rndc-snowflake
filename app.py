# -*- coding: utf-8 -*-

import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
import snowflake.connector

from datetime import timedelta
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
# TODOS LOS CAMPOS DEL PROCESO 4
# EXCEPTO CONSECUTIVOREMESA
# =============================================================================

VARIABLES_PROCESO4 = [

    "INGRESOID",

    "NUMMANIFIESTOCARGA",

    "FECHAING",

    "NUMPLACA",

    "NUMPLACAREMOLQUE",

    "VALORFLETEPACTADOVIAJE",

    "FECHAEXPEDICIONMANIFIESTO",

    "CODOPERACIONTRANSPORTE",

    "CONSECUTIVOINFORMACIONVIAJE",

    "MANNROMANIFIESTOTRANSBORDO",

    "CODMUNICIPIOORIGENMANIFIESTO",

    "CODMUNICIPIODESTINOMANIFIESTO",

    "CODIDTITULARMANIFIESTO",

    "NUMIDTITULARMANIFIESTO",

    "CODIDCONDUCTOR",

    "NUMIDCONDUCTOR",

    "CODIDCONDUCTOR2",

    "NUMIDCONDUCTOR2",

    "RETENCIONFUENTEMANIFIESTO",

    "RETENCIONICAMANIFIESTOCARGA",

    "VALORANTICIPOMANIFIESTO",

    "CODMUNICIPIOPAGOSALDO",

    "FECHAPAGOSALDOMANIFIESTO",

    "CODRESPONSABLEPAGOCARGUE",

    "CODRESPONSABLEPAGODESCARGUE",

    "NITMONITOREOFLOTA",

    "ACEPTACIONELECTRONICA",

    "OBSERVACIONES",

    "CODVIA",

    "SEGURIDADQR"

]


# =============================================================================
# CONSULTAR RNDC
# =============================================================================

def consultar_rndc(

    fecha_inicio,

    fecha_fin

):


    variables = ",".join(
        VARIABLES_PROCESO4
    )


    # =========================================================================
    # XML RNDC
    # =========================================================================

    body = f"""
<root>

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


</root>
"""


    # =========================================================================
    # SOAP
    # =========================================================================

    xml_request = f"""<?xml version='1.0' encoding='ISO-8859-1'?>

<SOAP-ENV:Envelope

xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"

xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"

xmlns:xsd="http://www.w3.org/2001/XMLSchema-instance">


<SOAP-ENV:Body>


<m:AtenderMensajeRNDC

xmlns:m="urn:BPMServicesIntf-IBPMServices">


<Request xsi:type="xsd:string">

{escape(body)}

</Request>


</m:AtenderMensajeRNDC>


</SOAP-ENV:Body>


</SOAP-ENV:Envelope>
"""


    # =========================================================================
    # CONSULTAR RNDC
    # =========================================================================

    try:


        response = requests.post(

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


    except requests.exceptions.Timeout:


        raise Exception(

            f"Timeout RNDC para el período "
            f"{fecha_inicio} a {fecha_fin}"

        )


    except requests.exceptions.RequestException as e:


        raise Exception(

            f"Error de conexión con RNDC: {e}"

        )


    # =========================================================================
    # PROCESAR SOAP
    # =========================================================================

    try:


        root = ET.fromstring(
            response.text
        )


    except Exception as e:


        raise Exception(

            f"No fue posible interpretar "
            f"la respuesta SOAP: {e}"

        )


    # =========================================================================
    # BUSCAR SOAP FAULT
    # =========================================================================

    fault = root.find(

        ".//"
        "{http://schemas.xmlsoap.org/soap/envelope/}"
        "Fault"

    )


    if fault is not None:


        mensaje_fault = []


        for elemento in fault.iter():

            if elemento.text:

                texto = elemento.text.strip()

                if texto:

                    mensaje_fault.append(
                        texto
                    )


        raise Exception(

            "SOAP Fault RNDC: "

            + " | ".join(
                mensaje_fault
            )

        )


    # =========================================================================
    # BUSCAR RETURN
    # =========================================================================

    nodo_return = root.find(
        ".//return"
    )


    if nodo_return is None:


        return pd.DataFrame()


    contenido = (
        nodo_return.text
        or ""
    ).strip()


    if not contenido:


        return pd.DataFrame()


    # =========================================================================
    # PROCESAR XML INTERNO
    # =========================================================================

    try:


        root_rndc = ET.fromstring(
            contenido
        )


    except Exception as e:


        raise Exception(

            f"No fue posible interpretar "
            f"la respuesta interna de RNDC: {e}"

        )


    # =========================================================================
    # ERROR RNDC
    # =========================================================================

    error = root_rndc.find(
        ".//ErrorMSG"
    )


    if error is not None:


        mensaje_error = (
            error.text
            or ""
        ).strip()


        # RNDC11 significa que no existen documentos
        # para esa consulta. No es un error técnico.

        if (

            "RNDC11"
            in mensaje_error

            and

            "Documento no encontrado"
            in mensaje_error

        ):


            return pd.DataFrame()


        raise Exception(
            mensaje_error
        )


    # =========================================================================
    # EXTRAER DOCUMENTOS
    # =========================================================================

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
                .upper()
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
# CONSULTA ADAPTATIVA
#
# INTENTA CONSULTAR EL RANGO COMPLETO.
#
# SI FALLA:
#
# 1. LO DIVIDE EN DOS.
# 2. CONSULTA CADA MITAD.
# 3. SI UNA MITAD FALLA, LA VUELVE A DIVIDIR.
# 4. CONTINÚA HASTA LLEGAR A UN SOLO DÍA.
#
# MUY IMPORTANTE:
#
# NO SE FILTRA FECHAING DESPUÉS.
#
# SE CONSERVA EXACTAMENTE TODO LO QUE DEVUELVA RNDC.
# =============================================================================

def consultar_rango_adaptativo(

    fecha_inicio,

    fecha_fin,

    errores,

    callback_detalle=None

):


    try:


        if callback_detalle is not None:


            callback_detalle(

                fecha_inicio,

                fecha_fin

            )


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


        dataframe = (

            consultar_rndc(

                fecha_inicio_rndc,

                fecha_fin_rndc

            )

        )


        return dataframe


    except Exception as e:


        # =====================================================================
        # SI YA ES UN SOLO DÍA
        # =====================================================================

        if fecha_inicio == fecha_fin:


            errores.append({

                "INICIO":

                fecha_inicio.strftime(
                    "%Y/%m/%d"
                ),


                "FIN":

                fecha_fin.strftime(
                    "%Y/%m/%d"
                ),


                "ERROR":

                str(e)

            })


            return pd.DataFrame()


        # =====================================================================
        # DIVIDIR EL RANGO
        # =====================================================================

        cantidad_dias = (

            fecha_fin

            -

            fecha_inicio

        ).days


        mitad = (

            fecha_inicio

            +

            timedelta(

                days=cantidad_dias // 2

            )

        )


        inicio_segunda_parte = (

            mitad

            +

            timedelta(
                days=1
            )

        )


        # =====================================================================
        # PRIMERA MITAD
        # =====================================================================

        dataframe_1 = (

            consultar_rango_adaptativo(

                fecha_inicio,

                mitad,

                errores,

                callback_detalle

            )

        )


        # =====================================================================
        # SEGUNDA MITAD
        # =====================================================================

        dataframe_2 = (

            consultar_rango_adaptativo(

                inicio_segunda_parte,

                fecha_fin,

                errores,

                callback_detalle

            )

        )


        dataframes = []


        if not dataframe_1.empty:


            dataframes.append(
                dataframe_1
            )


        if not dataframe_2.empty:


            dataframes.append(
                dataframe_2
            )


        if len(dataframes) == 0:


            return pd.DataFrame()


        return pd.concat(

            dataframes,

            ignore_index=True,

            sort=False

        )


# =============================================================================
# CONSULTAR PERÍODO GRANDE
#
# SE INTENTA PRIMERO EN BLOQUES DE 4 DÍAS.
#
# EJEMPLO:
#
# 1 - 4
# 5 - 8
# 9 - 12
#
# SI FALLA:
#
# SE DIVIDE AUTOMÁTICAMENTE.
#
# NO SE FILTRA FECHAING.
# =============================================================================

def consultar_periodo_grande(

    fecha_inicio,

    fecha_fin,

    callback_progreso=None,

    dias_por_bloque=4

):


    bloques = []


    fecha_actual = fecha_inicio


    # =========================================================================
    # CREAR BLOQUES
    # =========================================================================

    while fecha_actual <= fecha_fin:


        fecha_bloque_fin = min(

            fecha_actual

            +

            timedelta(

                days=dias_por_bloque - 1

            ),

            fecha_fin

        )


        bloques.append(

            (

                fecha_actual,

                fecha_bloque_fin

            )

        )


        fecha_actual = (

            fecha_bloque_fin

            +

            timedelta(
                days=1
            )

        )


    dataframes = []

    errores = []


    total_bloques = len(
        bloques
    )


    # =========================================================================
    # CONSULTAR CADA BLOQUE
    # =========================================================================

    for indice, bloque in enumerate(

        bloques,

        start=1

    ):


        inicio_bloque = bloque[0]

        fin_bloque = bloque[1]


        # =====================================================================
        # MOSTRAR PROGRESO
        # =====================================================================

        if callback_progreso is not None:


            callback_progreso(

                indice,

                total_bloques,

                inicio_bloque,

                fin_bloque

            )


        # =====================================================================
        # FUNCIÓN PARA MOSTRAR SUBCONSULTAS
        # =====================================================================

        def callback_detalle(

            inicio_detalle,

            fin_detalle

        ):


            if callback_progreso is not None:


                callback_progreso(

                    indice,

                    total_bloques,

                    inicio_detalle,

                    fin_detalle

                )


        # =====================================================================
        # CONSULTAR BLOQUE
        # =====================================================================

        dataframe_bloque = (

            consultar_rango_adaptativo(

                inicio_bloque,

                fin_bloque,

                errores,

                callback_detalle

            )

        )


        if not dataframe_bloque.empty:


            dataframes.append(
                dataframe_bloque
            )


    # =========================================================================
    # SI NO HUBO RESULTADOS
    # =========================================================================

    if not dataframes:


        return (

            pd.DataFrame(),

            errores

        )


    # =========================================================================
    # UNIR TODOS LOS RESULTADOS
    #
    # AQUÍ NO FILTRAMOS FECHAING.
    #
    # SE CONSERVA TODO LO QUE RNDC DEVOLVIÓ.
    # =========================================================================

    dataframe_final = pd.concat(

        dataframes,

        ignore_index=True,

        sort=False

    )


    # =========================================================================
    # MAYÚSCULAS
    # =========================================================================

    dataframe_final.columns = [

        str(
            columna
        ).upper()

        for columna

        in dataframe_final.columns

    ]


    # =========================================================================
    # ELIMINAR DUPLICADOS
    # =========================================================================

    if "INGRESOID" in dataframe_final.columns:


        dataframe_final = (

            dataframe_final

            .drop_duplicates(

                subset=[
                    "INGRESOID"
                ],

                keep="last"

            )

        )


    return (

        dataframe_final,

        errores

    )


# =============================================================================
# CONECTAR A SNOWFLAKE
# =============================================================================

def conectar_snowflake():


    conexion = (

        snowflake.connector.connect(

            account=SNOWFLAKE_ACCOUNT,

            user=SNOWFLAKE_USER,

            password=SNOWFLAKE_PASSWORD,

            role=SNOWFLAKE_ROLE,

            warehouse=SNOWFLAKE_WAREHOUSE,

            database=SNOWFLAKE_DATABASE,

            schema=SNOWFLAKE_SCHEMA

        )

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

            for fila

            in cursor.fetchall()

        }


        # =====================================================================
        # AGREGAR COLUMNAS NUEVAS
        # =====================================================================

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


    ingresos_ids = (

        dataframe[
            "INGRESOID"
        ]

        .dropna()

        .astype(
            str
        )

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


            lote = (

                ingresos_ids[

                    inicio:

                    inicio

                    +

                    tamanio_lote

                ]

            )


            valores_sql_lista = []


            for valor in lote:


                valor_limpio = (

                    str(
                        valor
                    )

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

            str(
                columna
            ).upper()

            for columna

            in df_snowflake.columns

        ]


        # =====================================================================
        # CONVERTIR TODO A STRING
        # =====================================================================

        for columna in df_snowflake.columns:


            df_snowflake[columna] = (

                df_snowflake[
                    columna
                ]

                .astype(
                    "string"
                )

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
        # ELIMINAR REGISTROS DUPLICADOS EXISTENTES
        # =====================================================================

        eliminar_registros_existentes(

            conexion,

            df_snowflake

        )


        # =====================================================================
        # CARGAR DATAFRAME
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

columna1, columna2 = (

    st.columns(
        2
    )

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


    # =========================================================================
    # VALIDAR FECHAS
    # =========================================================================

    if fecha_fin < fecha_inicio:


        st.error(

            "❌ La fecha final no puede "
            "ser menor que la fecha inicial."

        )


        st.stop()


    try:


        # =====================================================================
        # COMPONENTES DE PROGRESO
        # =====================================================================

        mensaje_progreso = (

            st.empty()

        )


        barra_progreso = (

            st.progress(
                0
            )

        )


        def actualizar_progreso(

            indice,

            total,

            inicio,

            fin

        ):


            porcentaje = int(

                (

                    indice

                    /

                    total

                )

                *

                100

            )


            barra_progreso.progress(

                min(

                    porcentaje,

                    99

                )

            )


            mensaje_progreso.info(

                f"📡 Bloque {indice} de {total}: "

                f"{inicio.strftime('%Y/%m/%d')} "

                f"a "

                f"{fin.strftime('%Y/%m/%d')}"

            )


        # =====================================================================
        # CONSULTAR RNDC
        # =====================================================================

        with st.spinner(

            "Consultando información en RNDC..."

        ):


            dataframe, errores_rndc = (

                consultar_periodo_grande(

                    fecha_inicio,

                    fecha_fin,

                    actualizar_progreso,

                    dias_por_bloque=4

                )

            )


        barra_progreso.progress(
            100
        )


        # =====================================================================
        # MOSTRAR ERRORES
        # =====================================================================

        if errores_rndc:


            st.warning(

                f"⚠️ Algunos días presentaron problemas en RNDC. "

                f"El sistema continuó descargando el resto del período."

            )


            with st.expander(

                "Ver días con error"

            ):


                dataframe_errores = (

                    pd.DataFrame(

                        errores_rndc

                    )

                )


                st.dataframe(

                    dataframe_errores,

                    use_container_width=True

                )


        # =====================================================================
        # VALIDAR RESULTADO
        # =====================================================================

        if dataframe.empty:


            st.warning(

                "⚠️ No se encontraron registros "
                "para el período seleccionado."

            )


            st.stop()


        # =====================================================================
        # ELIMINAR DUPLICADOS
        # =====================================================================

        registros_antes = len(
            dataframe
        )


        if "INGRESOID" in dataframe.columns:


            dataframe = (

                dataframe

                .drop_duplicates(

                    subset=[
                        "INGRESOID"
                    ],

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


        # =====================================================================
        # MOSTRAR RESULTADOS
        # =====================================================================

        st.success(

            f"✅ Consulta RNDC terminada: "

            f"{registros_finales} registros encontrados."

        )


        col1, col2, col3 = (

            st.columns(
                3
            )

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


        # =====================================================================
        # VISTA PREVIA
        # =====================================================================

        st.subheader(

            "Vista previa de los datos"

        )


        st.dataframe(

            dataframe,

            use_container_width=True

        )


        # =====================================================================
        # CARGAR SNOWFLAKE
        # =====================================================================

        with st.spinner(

            "Cargando información a Snowflake..."

        ):


            resultado = (

                cargar_dataframe_snowflake(

                    dataframe

                )

            )


        # =====================================================================
        # RESULTADO FINAL
        # =====================================================================

        st.success(

            "🎉 CARGA EXITOSA EN SNOWFLAKE"

        )


        col1, col2 = (

            st.columns(
                2
            )

        )


        col1.metric(

            "Registros cargados",

            resultado[
                "rows"
            ]

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
