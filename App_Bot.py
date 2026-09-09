import pandas as pd
import streamlit as st
import snowflake.connector


# ============================================================
# CONFIGURACIÓN DE LA APLICACIÓN
# ============================================================

st.set_page_config(
    page_title="RNDC Bot",
    page_icon="🤖",
    layout="wide"
)


# ============================================================
# CONFIGURACIÓN SNOWFLAKE
# ============================================================

SNOWFLAKE_TABLE = "MANIFIESTOS_PROCESO4"


# ============================================================
# CONEXIÓN A SNOWFLAKE
# ============================================================

def conectar_snowflake():

    conexion = snowflake.connector.connect(
        account=st.secrets["SNOWFLAKE_ACCOUNT"],
        user=st.secrets["SNOWFLAKE_USER"],
        password=st.secrets["SNOWFLAKE_PASSWORD"],
        role=st.secrets["SNOWFLAKE_ROLE"],
        warehouse=st.secrets["SNOWFLAKE_WAREHOUSE"],
        database=st.secrets["SNOWFLAKE_DATABASE"],
        schema=st.secrets["SNOWFLAKE_SCHEMA"]
    )

    return conexion


# ============================================================
# CONSULTAR MANIFIESTO EN SNOWFLAKE
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

        df = pd.DataFrame(
            registros,
            columns=columnas
        )

        return df

    finally:

        if cursor is not None:
            cursor.close()

        if conexion is not None:
            conexion.close()


# ============================================================
# TÍTULO
# ============================================================

st.title("🤖 RNDC Bot")

st.subheader("Consulta de manifiestos")

st.write(
    "Ingrese el número de manifiesto para consultar "
    "la información almacenada en Snowflake."
)


# ============================================================
# CAMPO DE CONSULTA
# ============================================================

numero_manifiesto = st.text_input(
    "Número de manifiesto",
    placeholder="Ejemplo: 123456789"
)


# ============================================================
# BOTÓN
# ============================================================

consultar = st.button(
    "🔎 CONSULTAR MANIFIESTO",
    type="primary"
)


# ============================================================
# PROCESAR CONSULTA
# ============================================================

if consultar:

    numero = numero_manifiesto.strip()

    if not numero:

        st.warning(
            "⚠️ Ingrese un número de manifiesto."
        )

    else:

        try:

            with st.spinner(
                "Consultando manifiesto en Snowflake..."
            ):

                df_manifiesto = consultar_manifiesto(numero)


            # =================================================
            # NO ENCONTRADO
            # =================================================

            if df_manifiesto.empty:

                st.warning(
                    f"⚠️ No se encontró el manifiesto {numero} "
                    "en Snowflake."
                )


            # =================================================
            # ENCONTRADO
            # =================================================

            else:

                st.success(
                    f"✅ Manifiesto {numero} encontrado."
                )

                st.write(
                    f"**Registros encontrados:** "
                    f"{len(df_manifiesto)}"
                )


                # =============================================
                # INFORMACIÓN PRINCIPAL
                # =============================================

                st.markdown(
                    "### 📋 Información principal"
                )

                campos_principales = [
                    "NUMMANIFIESTOCARGA",
                    "FECHAING",
                    "NUMPLACA",
                    "NUMPLACAREMOLQUE",
                    "VALORFLETEPACTADOVIAJE",
                    "CODMUNICIPIOORIGENMANIFIESTO",
                    "CODMUNICIPIODESTINOMANIFIESTO",
                    "NUMIDCONDUCTOR"
                ]

                campos_disponibles = [
                    campo
                    for campo in campos_principales
                    if campo in df_manifiesto.columns
                ]


                if campos_disponibles:

                    datos_principales = (
                        df_manifiesto[
                            campos_disponibles
                        ]
                        .iloc[0]
                        .to_frame(name="Valor")
                    )

                    st.dataframe(
                        datos_principales,
                        use_container_width=True
                    )


                # =============================================
                # INFORMACIÓN COMPLETA
                # =============================================

                st.markdown(
                    "### 📊 Información completa"
                )

                st.dataframe(
                    df_manifiesto,
                    use_container_width=True,
                    hide_index=True
                )


        # =====================================================
        # ERROR DE SECRETS
        # =====================================================

        except KeyError as e:

            st.error(
                "❌ Falta una configuración de Snowflake "
                "en los Secrets de Streamlit."
            )

            st.write(
                f"Configuración faltante: `{e}`"
            )


        # =====================================================
        # OTRO ERROR
        # =====================================================

        except Exception as e:

            st.error(
                "❌ Se presentó un error al consultar "
                "Snowflake."
            )

            st.exception(e)


# ============================================================
# INFORMACIÓN TÉCNICA
# ============================================================

with st.expander("ℹ️ Información técnica"):

    st.write(
        "Esta aplicación consulta la tabla "
        f"`{SNOWFLAKE_TABLE}` en Snowflake."
    )

    st.write(
        "En esta primera versión la consulta se realiza "
        "directamente sobre Snowflake."
    )

    st.write(
        "El RNDC no se consulta nuevamente al presionar "
        "el botón."
    )
