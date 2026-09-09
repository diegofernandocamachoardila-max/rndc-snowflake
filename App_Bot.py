import re
import pandas as pd
import streamlit as st
import snowflake.connector


# ============================================================
# CONFIGURACIÓN
# ============================================================

st.set_page_config(
    page_title="RNDC Bot",
    page_icon="🤖",
    layout="wide"
)

SNOWFLAKE_TABLE = "MANIFIESTOS_PROCESO4"


# ============================================================
# CONEXIÓN A SNOWFLAKE
# ============================================================

def conectar_snowflake():

    return snowflake.connector.connect(
        account=st.secrets["SNOWFLAKE_ACCOUNT"],
        user=st.secrets["SNOWFLAKE_USER"],
        password=st.secrets["SNOWFLAKE_PASSWORD"],
        role=st.secrets["SNOWFLAKE_ROLE"],
        warehouse=st.secrets["SNOWFLAKE_WAREHOUSE"],
        database=st.secrets["SNOWFLAKE_DATABASE"],
        schema=st.secrets["SNOWFLAKE_SCHEMA"]
    )


# ============================================================
# CONSULTA DEL MANIFIESTO
# ============================================================

def consultar_manifiesto(numero_manifiesto):

    conexion = None
    cursor = None

    try:

        conexion = conectar_snowflake()
        cursor = conexion.cursor()

        database = st.secrets["SNOWFLAKE_DATABASE"]
        schema = st.secrets["SNOWFLAKE_SCHEMA"]

        sql = f"""
        SELECT *
        FROM {database}.{schema}.{SNOWFLAKE_TABLE}
        WHERE TRIM(NUMMANIFIESTOCARGA) = %s
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

        return pd.DataFrame(
            registros,
            columns=columnas
        )

    finally:

        if cursor is not None:
            cursor.close()

        if conexion is not None:
            conexion.close()


# ============================================================
# OBTENER VALOR DE UN CAMPO
# ============================================================

def obtener_valor(df, nombres):

    for nombre in nombres:

        if nombre in df.columns:

            valor = df.iloc[0][nombre]

            if pd.notna(valor):

                texto = str(valor).strip()

                if texto not in (
                    "",
                    "None",
                    "nan"
                ):

                    return texto

    return "No disponible"


# ============================================================
# FORMATEAR VALOR DEL FLETE
# ============================================================

def formatear_flete(valor):

    try:

        numero = float(
            str(valor)
            .replace(",", "")
            .replace("$", "")
            .strip()
        )

        return f"${numero:,.0f}".replace(",", ".")

    except Exception:

        return valor


# ============================================================
# EXTRAER NÚMERO DE MANIFIESTO
# ============================================================

def extraer_numero(texto):

    coincidencias = re.findall(
        r"\d{5,}",
        texto
    )

    if coincidencias:

        return coincidencias[-1]

    return None


# ============================================================
# IDENTIFICAR QUÉ ESTÁ PREGUNTANDO EL USUARIO
# ============================================================

def identificar_consulta(texto):

    texto = texto.lower()

    # PLACA
    if any(
        palabra in texto
        for palabra in [
            "placa",
            "vehiculo",
            "vehículo"
        ]
    ):

        return "placa"


    # REMOLQUE
    if any(
        palabra in texto
        for palabra in [
            "remolque",
            "trailer",
            "tráiler"
        ]
    ):

        return "remolque"


    # FLETE
    if any(
        palabra in texto
        for palabra in [
            "flete",
            "valor del flete",
            "valorflete",
            "valor"
        ]
    ):

        return "flete"


    # ORIGEN
    if any(
        palabra in texto
        for palabra in [
            "origen",
            "sale de",
            "sale desde"
        ]
    ):

        return "origen"


    # DESTINO
    if any(
        palabra in texto
        for palabra in [
            "destino",
            "va para",
            "llega a"
        ]
    ):

        return "destino"


    # CONDUCTOR
    if any(
        palabra in texto
        for palabra in [
            "conductor",
            "chofer",
            "transportador"
        ]
    ):

        return "conductor"


    # FECHA
    if any(
        palabra in texto
        for palabra in [
            "fecha",
            "cuando",
            "cuándo"
        ]
    ):

        return "fecha"


    # RESUMEN GENERAL
    return "resumen"


# ============================================================
# RESPUESTA SEGÚN LA PREGUNTA
# ============================================================

def responder_consulta(df, numero, tipo):


    # --------------------------------------------------------
    # PLACA
    # --------------------------------------------------------

    if tipo == "placa":

        placa = obtener_valor(
            df,
            ["NUMPLACA"]
        )

        st.success(
            f"🚛 La placa del manifiesto "
            f"{numero} es **{placa}**."
        )

        return


    # --------------------------------------------------------
    # REMOLQUE
    # --------------------------------------------------------

    if tipo == "remolque":

        remolque = obtener_valor(
            df,
            ["NUMPLACAREMOLQUE"]
        )

        st.success(
            f"🚚 El remolque del manifiesto "
            f"{numero} es **{remolque}**."
        )

        return


    # --------------------------------------------------------
    # FLETE
    # --------------------------------------------------------

    if tipo == "flete":

        flete = obtener_valor(
            df,
            ["VALORFLETEPACTADOVIAJE"]
        )

        flete = formatear_flete(flete)

        st.success(
            f"💰 El valor del flete del manifiesto "
            f"{numero} es **{flete}**."
        )

        return


    # --------------------------------------------------------
    # ORIGEN
    # --------------------------------------------------------

    if tipo == "origen":

        origen = obtener_valor(
            df,
            [
                "CODMUNICIPIOORIGENMANIFIESTO",
                "MUNICIPIOORIGENMANIFIESTO"
            ]
        )

        st.success(
            f"📍 El origen del manifiesto "
            f"{numero} es **{origen}**."
        )

        return


    # --------------------------------------------------------
    # DESTINO
    # --------------------------------------------------------

    if tipo == "destino":

        destino = obtener_valor(
            df,
            [
                "CODMUNICIPIODESTINOMANIFIESTO",
                "MUNICIPIODESTINOMANIFIESTO"
            ]
        )

        st.success(
            f"📍 El destino del manifiesto "
            f"{numero} es **{destino}**."
        )

        return


    # --------------------------------------------------------
    # CONDUCTOR
    # --------------------------------------------------------

    if tipo == "conductor":

        conductor = obtener_valor(
            df,
            [
                "NUMIDCONDUCTOR",
                "NUMIDCONDUCTORPRINCIPAL"
            ]
        )

        st.success(
            f"👤 El conductor del manifiesto "
            f"{numero} es **{conductor}**."
        )

        return


    # --------------------------------------------------------
    # FECHA
    # --------------------------------------------------------

    if tipo == "fecha":

        fecha = obtener_valor(
            df,
            [
                "FECHAING",
                "FECHAEXPEDICIONMANIFIESTO"
            ]
        )

        st.success(
            f"📅 La fecha del manifiesto "
            f"{numero} es **{fecha}**."
        )

        return


    # ========================================================
    # RESUMEN GENERAL
    # ========================================================

    fecha = obtener_valor(
        df,
        [
            "FECHAING",
            "FECHAEXPEDICIONMANIFIESTO"
        ]
    )

    placa = obtener_valor(
        df,
        ["NUMPLACA"]
    )

    remolque = obtener_valor(
        df,
        ["NUMPLACAREMOLQUE"]
    )

    origen = obtener_valor(
        df,
        [
            "CODMUNICIPIOORIGENMANIFIESTO",
            "MUNICIPIOORIGENMANIFIESTO"
        ]
    )

    destino = obtener_valor(
        df,
        [
            "CODMUNICIPIODESTINOMANIFIESTO",
            "MUNICIPIODESTINOMANIFIESTO"
        ]
    )

    conductor = obtener_valor(
        df,
        [
            "NUMIDCONDUCTOR",
            "NUMIDCONDUCTORPRINCIPAL"
        ]
    )

    flete = obtener_valor(
        df,
        ["VALORFLETEPACTADOVIAJE"]
    )

    flete = formatear_flete(flete)


    st.success(
        f"✅ Manifiesto {numero} encontrado"
    )

    st.markdown(
        f"""
## 🤖 Información del manifiesto

**Número:** `{numero}`

| Campo | Información |
|---|---|
| 🚛 Vehículo | **{placa}** |
| 🚚 Remolque | **{remolque}** |
| 📅 Fecha | **{fecha}** |
| 📍 Origen | **{origen}** |
| 📍 Destino | **{destino}** |
| 👤 Conductor | **{conductor}** |
| 💰 Valor flete | **{flete}** |
"""
    )

    with st.expander(
        "📊 Ver información completa del manifiesto"
    ):

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True
        )


# ============================================================
# INTERFAZ
# ============================================================

st.title("🤖 RNDC Bot")

st.subheader(
    "Consulta de manifiestos"
)

st.write(
    "Escriba una pregunta sobre un manifiesto."
)

consulta = st.text_input(
    "Consulta",
    placeholder="Ejemplo: ¿Cuál es la placa del manifiesto 0003947924?"
)

consultar = st.button(
    "🔎 CONSULTAR",
    type="primary"
)


# ============================================================
# EJECUCIÓN
# ============================================================

if consultar:

    consulta_limpia = consulta.strip()


    if not consulta_limpia:

        st.warning(
            "⚠️ Escriba una consulta."
        )


    else:

        numero = extraer_numero(
            consulta_limpia
        )


        if not numero:

            st.warning(
                "⚠️ No pude identificar el número "
                "del manifiesto."
            )

            st.info(
                "Ejemplo: ¿Cuál es la placa "
                "del manifiesto 0003947924?"
            )


        else:

            try:

                with st.spinner(
                    f"Consultando manifiesto {numero}..."
                ):

                    df_manifiesto = consultar_manifiesto(
                        numero
                    )


                if df_manifiesto.empty:

                    st.warning(
                        f"⚠️ No se encontró el manifiesto "
                        f"{numero} en Snowflake."
                    )


                else:

                    tipo_consulta = identificar_consulta(
                        consulta_limpia
                    )

                    responder_consulta(
                        df_manifiesto,
                        numero,
                        tipo_consulta
                    )


            except KeyError as e:

                st.error(
                    "❌ Falta una configuración de Snowflake "
                    "en los Secrets de Streamlit."
                )

                st.write(
                    f"Configuración faltante: `{e}`"
                )


            except Exception as e:

                st.error(
                    "❌ Se presentó un error "
                    "al consultar Snowflake."
                )

                st.exception(e)


# ============================================================
# INFORMACIÓN TÉCNICA
# ============================================================

with st.expander(
    "ℹ️ Información técnica"
):

    st.write(
        f"La aplicación consulta directamente "
        f"la tabla `{SNOWFLAKE_TABLE}` en Snowflake."
    )

    st.write(
        "La búsqueda se realiza mediante "
        "`NUMMANIFIESTOCARGA`."
    )

    st.write(
        "Esta versión identifica la intención "
        "de la pregunta mediante reglas."
    )
