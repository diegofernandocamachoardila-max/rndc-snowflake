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
# OBTENER VALOR
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
# FORMATEAR FLETE
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
# IDENTIFICAR TODOS LOS DATOS SOLICITADOS
# ============================================================

def identificar_consultas(texto):

    texto = texto.lower()

    consultas = []

    # --------------------------------------------------------
    # PLACA
    # --------------------------------------------------------

    if any(
        palabra in texto
        for palabra in [
            "placa",
            "vehiculo",
            "vehículo"
        ]
    ):

        consultas.append("placa")


    # --------------------------------------------------------
    # REMOLQUE
    # --------------------------------------------------------

    if any(
        palabra in texto
        for palabra in [
            "remolque",
            "trailer",
            "tráiler"
        ]
    ):

        consultas.append("remolque")


    # --------------------------------------------------------
    # FLETE
    # --------------------------------------------------------

    if any(
        palabra in texto
        for palabra in [
            "flete",
            "valor del flete",
            "valorflete"
        ]
    ):

        consultas.append("flete")


    # --------------------------------------------------------
    # ORIGEN
    # --------------------------------------------------------

    if any(
        palabra in texto
        for palabra in [
            "origen",
            "sale de",
            "sale desde"
        ]
    ):

        consultas.append("origen")


    # --------------------------------------------------------
    # DESTINO
    # --------------------------------------------------------

    if any(
        palabra in texto
        for palabra in [
            "destino",
            "va para",
            "llega a"
        ]
    ):

        consultas.append("destino")


    # --------------------------------------------------------
    # CONDUCTOR
    # --------------------------------------------------------

    if any(
        palabra in texto
        for palabra in [
            "conductor",
            "chofer"
        ]
    ):

        consultas.append("conductor")


    # --------------------------------------------------------
    # FECHA
    # --------------------------------------------------------

    if any(
        palabra in texto
        for palabra in [
            "fecha",
            "cuando",
            "cuándo"
        ]
    ):

        consultas.append("fecha")


    # --------------------------------------------------------
    # SI NO PIDIÓ UN CAMPO ESPECÍFICO
    # --------------------------------------------------------

    if not consultas:

        consultas.append("resumen")


    return consultas


# ============================================================
# MOSTRAR UN CAMPO
# ============================================================

def mostrar_campo(df, numero, tipo):

    if tipo == "placa":

        valor = obtener_valor(
            df,
            ["NUMPLACA"]
        )

        st.markdown(
            f"🚛 **Placa:** {valor}"
        )


    elif tipo == "remolque":

        valor = obtener_valor(
            df,
            ["NUMPLACAREMOLQUE"]
        )

        st.markdown(
            f"🚚 **Remolque:** {valor}"
        )


    elif tipo == "flete":

        valor = obtener_valor(
            df,
            ["VALORFLETEPACTADOVIAJE"]
        )

        valor = formatear_flete(valor)

        st.markdown(
            f"💰 **Valor del flete:** {valor}"
        )


    elif tipo == "origen":

        valor = obtener_valor(
            df,
            [
                "CODMUNICIPIOORIGENMANIFIESTO",
                "MUNICIPIOORIGENMANIFIESTO"
            ]
        )

        st.markdown(
            f"📍 **Origen:** {valor}"
        )


    elif tipo == "destino":

        valor = obtener_valor(
            df,
            [
                "CODMUNICIPIODESTINOMANIFIESTO",
                "MUNICIPIODESTINOMANIFIESTO"
            ]
        )

        st.markdown(
            f"📍 **Destino:** {valor}"
        )


    elif tipo == "conductor":

        valor = obtener_valor(
            df,
            [
                "NUMIDCONDUCTOR",
                "NUMIDCONDUCTORPRINCIPAL"
            ]
        )

        st.markdown(
            f"👤 **Conductor:** {valor}"
        )


    elif tipo == "fecha":

        valor = obtener_valor(
            df,
            [
                "FECHAING",
                "FECHAEXPEDICIONMANIFIESTO"
            ]
        )

        st.markdown(
            f"📅 **Fecha:** {valor}"
        )


# ============================================================
# MOSTRAR RESUMEN
# ============================================================

def mostrar_resumen(df, numero):

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

    st.markdown(
        f"""
### 🤖 Información del manifiesto

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
        "📊 Ver información completa"
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
    placeholder="Ejemplo: Dame la placa y el valor del flete del manifiesto 0003947924"
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

                    st.success(
                        f"✅ Manifiesto {numero} encontrado"
                    )

                    tipos_consulta = identificar_consultas(
                        consulta_limpia
                    )


                    # ========================================
                    # RESUMEN
                    # ========================================

                    if "resumen" in tipos_consulta:

                        mostrar_resumen(
                            df_manifiesto,
                            numero
                        )


                    # ========================================
                    # UNO O VARIOS CAMPOS
                    # ========================================

                    else:

                        st.markdown(
                            "### 🤖 Respuesta"
                        )

                        for tipo in tipos_consulta:

                            mostrar_campo(
                                df_manifiesto,
                                numero,
                                tipo
                            )


                        with st.expander(
                            "📊 Ver información completa"
                        ):

                            st.dataframe(
                                df_manifiesto,
                                use_container_width=True,
                                hide_index=True
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
        "Esta versión permite solicitar uno o varios "
        "campos en una misma pregunta."
    )
