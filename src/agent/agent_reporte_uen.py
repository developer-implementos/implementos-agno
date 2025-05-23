# app/agent_setup.py
import json
import os
from agno.agent import Agent
from agno.tools.reasoning import ReasoningTools
from agno.knowledge.json import JSONKnowledgeBase
from agno.models.anthropic import Claude
from agno.vectordb.qdrant import Qdrant
from datetime import datetime
from agno.tools import tool
from config.config import Config
from storage.mongo_storage import MongoStorage
from tools.data_ventas_tool import DataVentasTool
from tools.pdf_tool import PdfTool


def create_unified_queries(uen, tipo, inicio_periodo, fin_periodo):
    """
    Crea consultas unificadas para períodos actual y anterior

    Args:
        uen (str): UEN a analizar
        tipo (str): Tipo de periodo (anual, mensual, semanal)
        inicio_periodo (str): Fecha de inicio del periodo actual
        fin_periodo (str): Fecha de fin del periodo actual

    Returns:
        list: Lista de consultas unificadas con sus objetivos
    """
    from datetime import datetime, timedelta

    # Convertir strings de fecha a objetos datetime
    fecha_inicio = datetime.strptime(inicio_periodo, '%Y-%m-%d')
    fecha_fin = datetime.strptime(fin_periodo, '%Y-%m-%d')

    # Calcular fechas del período anterior
    if tipo.lower() == 'anual':
        fecha_inicio_anterior = datetime(fecha_inicio.year - 1, fecha_inicio.month, fecha_inicio.day)
        fecha_fin_anterior = datetime(fecha_fin.year - 1, fecha_fin.month, fecha_fin.day)
    elif tipo.lower() == 'mensual':
        nuevo_mes = fecha_inicio.month - 1
        nuevo_año = fecha_inicio.year
        if nuevo_mes == 0:
            nuevo_mes = 12
            nuevo_año -= 1
        dias_mes = [31, 29 if (nuevo_año % 4 == 0 and (nuevo_año % 100 != 0 or nuevo_año % 400 == 0)) else 28,
                    31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        dia_inicio = min(fecha_inicio.day, dias_mes[nuevo_mes - 1])
        fecha_inicio_anterior = datetime(nuevo_año, nuevo_mes, dia_inicio)

        nuevo_mes = fecha_fin.month - 1
        nuevo_año = fecha_fin.year
        if nuevo_mes == 0:
            nuevo_mes = 12
            nuevo_año -= 1
        dia_fin = min(fecha_fin.day, dias_mes[nuevo_mes - 1])
        fecha_fin_anterior = datetime(nuevo_año, nuevo_mes, dia_fin)
    else:  # semanal o por defecto
        fecha_inicio_anterior = fecha_inicio - timedelta(days=7)
        fecha_fin_anterior = fecha_fin - timedelta(days=7)

    # Formatear fechas
    inicio_actual_str = fecha_inicio.strftime('%Y-%m-%d')
    fin_actual_str = fecha_fin.strftime('%Y-%m-%d')
    inicio_anterior_str = fecha_inicio_anterior.strftime('%Y-%m-%d')
    fin_anterior_str = fecha_fin_anterior.strftime('%Y-%m-%d')

    # Etiquetas para los períodos
    etiqueta_actual = f"Actual ({inicio_actual_str} a {fin_actual_str})"
    etiqueta_anterior = f"Anterior ({inicio_anterior_str} a {fin_anterior_str})"

    # Definir las queries unificadas
    queries = [
        {
            "id": "datos_compania_completa",
            "objetivo": "Obtener datos generales de toda la compañía para ambos períodos",
            "query": f"""
        WITH periodo_actual AS (
            SELECT
                '{etiqueta_actual}' as periodo,
                sum(totalNetoItem) as venta,
                sum(cantidad) as unidades,
                sum(totalMargenItem) as contribucion,
                round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen,
                count(DISTINCT documento) as transacciones,
                count(DISTINCT rutCliente) as clientes_unicos,
                count(DISTINCT uen) as uens_activas
            FROM implementos.ventasrealtime
            WHERE fecha >= '{inicio_anterior_str}'
            AND fecha <= '{fin_actual_str}'
        ),
        periodo_anterior AS (
            SELECT
                '{etiqueta_anterior}' as periodo,
                sum(totalNetoItem) as venta,
                sum(cantidad) as unidades,
                sum(totalMargenItem) as contribucion,
                round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen,
                count(DISTINCT documento) as transacciones,
                count(DISTINCT rutCliente) as clientes_unicos,
                count(DISTINCT uen) as uens_activas
            FROM implementos.ventasrealtime
            WHERE fecha >= '{inicio_anterior_str}'
            AND fecha <= '{fin_anterior_str}'
        )

        SELECT * FROM periodo_actual
        UNION ALL
        SELECT * FROM periodo_anterior
    """
        }, {
            "id": "tendencia_mensual_comparativa",
            "objetivo": f"Comparar tendencia mensual entre la UEN {uen} y toda la compañía",
            "query": f"""
        WITH meses_compania AS (
            SELECT
                toStartOfMonth(fecha) as mes,
                sum(totalNetoItem) as venta_compania,
                sum(totalMargenItem) as contribucion_compania
            FROM implementos.ventasrealtime
            WHERE fecha >= '{inicio_actual_str}'
            AND fecha <= '{fin_actual_str}'
            GROUP BY mes
            ORDER BY mes
        ),
        meses_uen AS (
            SELECT
                toStartOfMonth(fecha) as mes,
                sum(totalNetoItem) as venta_uen,
                sum(totalMargenItem) as contribucion_uen
            FROM implementos.ventasrealtime
            WHERE uen = '{uen}'
            AND fecha >= '{inicio_actual_str}'
            AND fecha <= '{fin_actual_str}'
            GROUP BY mes
            ORDER BY mes
        )
        SELECT
            mc.mes,
            mc.venta_compania,
            mc.contribucion_compania,
            round(mc.contribucion_compania / mc.venta_compania * 100, 1) as margen_compania,
            mu.venta_uen,
            mu.contribucion_uen,
            round(mu.contribucion_uen / mu.venta_uen * 100, 1) as margen_uen,
            round(mu.venta_uen / mc.venta_compania * 100, 1) as participacion_mensual
        FROM meses_compania mc
        JOIN meses_uen mu ON mc.mes = mu.mes
        ORDER BY mc.mes
    """
        }, {
            "id": "matriz_canal_compania",
            "objetivo": "Obtener desempeño de canales a nivel compañía para benchmarking",
            "query": f"""
        WITH canal_actual AS (
            SELECT
                tipoVenta as canal,
                sum(totalNetoItem) as venta_actual,
                sum(totalMargenItem) as contribucion_actual,
                round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_actual
            FROM implementos.ventasrealtime
            WHERE fecha >= '{inicio_actual_str}'
            AND fecha <= '{fin_actual_str}'
            GROUP BY tipoVenta
        ),
        canal_anterior AS (
            SELECT
                tipoVenta as canal,
                sum(totalNetoItem) as venta_anterior,
                sum(totalMargenItem) as contribucion_anterior,
                round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_anterior
            FROM implementos.ventasrealtime
            WHERE fecha >= '{inicio_anterior_str}'
            AND fecha <= '{fin_anterior_str}'
            GROUP BY tipoVenta
        )
        SELECT
            COALESCE(a.canal, b.canal) as canal,
            COALESCE(a.venta_actual, 0) as venta_actual,
            COALESCE(b.venta_anterior, 0) as venta_anterior,
            COALESCE(a.margen_actual, 0) as margen_actual,
            COALESCE(b.margen_anterior, 0) as margen_anterior,
            CASE
                WHEN b.venta_anterior IS NULL OR b.venta_anterior = 0 THEN NULL
                ELSE round((a.venta_actual - b.venta_anterior) / b.venta_anterior * 100, 2)
            END as variacion_venta_porcentaje
        FROM canal_actual a
        FULL OUTER JOIN canal_anterior b ON a.canal = b.canal
        ORDER BY COALESCE(a.venta_actual, 0) DESC
    """
        }, {
            "id": "metricas_uen_vs_promedio",
            "objetivo": f"Comparar métricas clave de la UEN {uen} contra promedios de la compañía",
            "query": f"""
        WITH metricas_uen AS (
            SELECT
                round(sum(totalNetoItem) / count(DISTINCT toStartOfMonth(fecha)), 0) as venta_mensual_promedio,
                round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_promedio,
                round(sum(totalNetoItem) / count(DISTINCT documento), 0) as ticket_promedio,
                round(sum(cantidad) / count(DISTINCT documento), 1) as unidades_por_transaccion
            FROM implementos.ventasrealtime
            WHERE uen = '{uen}'
            AND fecha >= '{inicio_actual_str}'
            AND fecha <= '{fin_actual_str}'
        ),
        metricas_compania AS (
            SELECT
                round(sum(totalNetoItem) / count(DISTINCT uen) / count(DISTINCT toStartOfMonth(fecha)), 0) as venta_mensual_promedio_uen,
                round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_promedio,
                round(sum(totalNetoItem) / count(DISTINCT documento), 0) as ticket_promedio,
                round(sum(cantidad) / count(DISTINCT documento), 1) as unidades_por_transaccion
            FROM implementos.ventasrealtime
            WHERE fecha >= '{inicio_actual_str}'
            AND fecha <= '{fin_actual_str}'
        )
        SELECT
            mu.venta_mensual_promedio as uen_venta_mensual,
            mc.venta_mensual_promedio_uen as compania_venta_mensual_por_uen,
            round((mu.venta_mensual_promedio / mc.venta_mensual_promedio_uen - 1) * 100, 1) as diferencia_venta_pct,
            mu.margen_promedio as uen_margen,
            mc.margen_promedio as compania_margen,
            round(mu.margen_promedio - mc.margen_promedio, 1) as diferencia_margen_pp,
            mu.ticket_promedio as uen_ticket,
            mc.ticket_promedio as compania_ticket,
            round((mu.ticket_promedio / mc.ticket_promedio - 1) * 100, 1) as diferencia_ticket_pct,
            mu.unidades_por_transaccion as uen_unidades_transaccion,
            mc.unidades_por_transaccion as compania_unidades_transaccion,
            round((mu.unidades_por_transaccion / mc.unidades_por_transaccion - 1) * 100, 1) as diferencia_unidades_pct
        FROM metricas_uen mu
        CROSS JOIN metricas_compania mc
    """
        },
        {
            "id": "datos_generales_uen",
            "objetivo": f"Obtener datos generales de la UEN {uen} para ambos períodos",
            "query": f"""
                WITH periodo_actual AS (
                    SELECT
                        '{etiqueta_actual}' as periodo,
                          sum(totalNetoItem) as venta,
                          sum(cantidad) as unidades,
                          sum(totalMargenItem) as contribucion,
                          round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen,
                          count(DISTINCT documento) as transacciones,
                          count(DISTINCT rutCliente) as clientes_unicos
                    FROM implementos.ventasrealtime
                    WHERE uen = '{uen}'
                    AND fecha >= '{inicio_actual_str}'
                    AND fecha <= '{fin_actual_str}'
                ),
                periodo_anterior AS (
                    SELECT
                        '{etiqueta_anterior}' as periodo,
                        sum(totalNetoItem) as venta,
                        sum(cantidad) as unidades,
                        sum(totalMargenItem) as contribucion,
                        round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen,
                        count(DISTINCT documento) as transacciones,
                        count(DISTINCT rutCliente) as clientes_unicos
                    FROM implementos.ventasrealtime
                    WHERE uen = '{uen}'
                    AND fecha >= '{inicio_anterior_str}'
                    AND fecha <= '{fin_anterior_str}'
                )

                SELECT * FROM periodo_actual
                UNION ALL
                SELECT * FROM periodo_anterior;
            """
        },
        {
            "id": "ticket_promedio",
            "objetivo": f"Obtener ticket promedio para la UEN {uen} en ambos períodos",
            "query": f"""
                SELECT
                    periodo,
                    round(sum(totalNetoItem) / uniqExact(documento), 1) as ticket_promedio
                FROM (
                    SELECT
                        toDate(fecha) as fecha,
                        documento,
                        totalNetoItem,
                        if(fecha >= '{inicio_actual_str}' AND fecha <= '{fin_actual_str}',
                           '{etiqueta_actual}', '{etiqueta_anterior}') as periodo
                    FROM implementos.ventasrealtime
                    WHERE uen = '{uen}'
                    AND ((fecha >= '{inicio_actual_str}' AND fecha <= '{fin_actual_str}')
                         OR (fecha >= '{inicio_anterior_str}' AND fecha <= '{fin_anterior_str}'))
                )
                GROUP BY periodo
            """
        },
        {
            "id": "comparacion_uens",
            "objetivo": "Comparar todas las UENs en ambos períodos",
            "query": f"""
                WITH datos_actual AS (
              SELECT
                  uen,
                  sum(totalNetoItem) as venta_actual,
                  sum(cantidad) as unidades_actual,
                  sum(totalMargenItem) as contribucion_actual,
                  round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_actual,
                  round(sum(totalNetoItem) / (
                      SELECT sum(totalNetoItem)
                      FROM implementos.ventasrealtime
                      WHERE fecha >= '{inicio_actual_str}' AND fecha <= '{fin_actual_str}'
                  ) * 100, 2) as participacion_actual
              FROM implementos.ventasrealtime
              WHERE fecha >= '{inicio_actual_str}'
              AND fecha <= '{fin_actual_str}'
              AND uen IS NOT NULL
              AND uen != ''
              AND uen != 'ZSERVICIOS DE ADMINISTRACION E INSUMOS'
              AND uen != 'RIEGO'
              GROUP BY uen
          ),
          datos_anterior AS (
              SELECT
                  uen,
                  sum(totalNetoItem) as venta_anterior,
                  sum(cantidad) as unidades_anterior,
                  sum(totalMargenItem) as contribucion_anterior,
                  round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_anterior,
                  round(sum(totalNetoItem) / (
                      SELECT sum(totalNetoItem)
                      FROM implementos.ventasrealtime
                      WHERE fecha >= '{inicio_anterior_str}' AND fecha <= '{fin_anterior_str}'
                  ) * 100, 2) as participacion_anterior
              FROM implementos.ventasrealtime
              WHERE fecha >= '{inicio_anterior_str}'
              AND fecha <= '{fin_anterior_str}'
              AND uen IS NOT NULL
              AND uen != ''
              AND uen != 'ZSERVICIOS DE ADMINISTRACION E INSUMOS'
              AND uen != 'RIEGO'
              GROUP BY uen
          )

          SELECT
              COALESCE(a.uen, b.uen) as uen,
              a.venta_actual,
              b.venta_anterior,
              a.unidades_actual,
              b.unidades_anterior,
              a.contribucion_actual,
              b.contribucion_anterior,
              a.margen_actual,
              b.margen_anterior,
              a.participacion_actual,
              b.participacion_anterior,
              CASE
                  WHEN b.venta_anterior IS NULL OR b.venta_anterior = 0 THEN NULL
                  ELSE round((a.venta_actual - b.venta_anterior) / b.venta_anterior * 100, 2)
              END as variacion_venta_porcentaje
          FROM datos_actual a
          FULL OUTER JOIN datos_anterior b ON a.uen = b.uen
          WHERE COALESCE(a.uen, b.uen) IS NOT NULL
          ORDER BY COALESCE(a.venta_actual, 0) DESC
          LIMIT 25
            """
        },
        {
            "id": "analisis_canal",
            "objetivo": f"Análisis por canal para la UEN {uen} en ambos períodos",
            "query": f"""
                WITH datos_actual AS (
                SELECT
                    tipoVenta as canal,
                    sum(totalNetoItem) as venta_actual,
                    sum(cantidad) as unidades_actual,
                    sum(totalMargenItem) as contribucion_actual,
                    round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_actual,
                    round(sum(totalNetoItem) / (
                        SELECT sum(totalNetoItem)
                        FROM implementos.ventasrealtime
                        WHERE uen = '{uen}' AND fecha >= '{inicio_actual_str}' AND fecha <= '{fin_actual_str}'
                    ) * 100, 2) as participacion_actual,
                    round(sum(totalNetoItem) / uniqExact(documento), 1) as ticket_promedio_actual
                FROM implementos.ventasrealtime
                WHERE uen = '{uen}'
                AND fecha >= '{inicio_actual_str}'
                AND fecha <= '{fin_actual_str}'
                GROUP BY tipoVenta
            ),
            datos_anterior AS (
                SELECT
                    tipoVenta as canal,
                    sum(totalNetoItem) as venta_anterior,
                    sum(cantidad) as unidades_anterior,
                    sum(totalMargenItem) as contribucion_anterior,
                    round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_anterior,
                    round(sum(totalNetoItem) / (
                        SELECT sum(totalNetoItem)
                        FROM implementos.ventasrealtime
                        WHERE uen = '{uen}' AND fecha >= '{inicio_anterior_str}' AND fecha <= '{fin_anterior_str}'
                    ) * 100, 2) as participacion_anterior,
                    round(sum(totalNetoItem) / uniqExact(documento), 1) as ticket_promedio_anterior
                FROM implementos.ventasrealtime
                WHERE uen = '{uen}'
                AND fecha >= '{inicio_anterior_str}'
                AND fecha <= '{fin_anterior_str}'
                GROUP BY tipoVenta
            )

            SELECT
                COALESCE(a.canal, b.canal) as canal,

                -- Ventas (actual, anterior, variación)
                COALESCE(a.venta_actual, 0) as venta_actual,
                COALESCE(b.venta_anterior, 0) as venta_anterior,
                COALESCE(
                    CASE
                        WHEN b.venta_anterior IS NULL OR b.venta_anterior = 0 THEN
                            CASE
                                WHEN a.venta_actual IS NULL OR a.venta_actual = 0 THEN 0
                                ELSE 100
                            END
                        ELSE round((a.venta_actual - b.venta_anterior) / b.venta_anterior * 100, 2)
                    END,
                    0
                ) as variacion_venta,

                -- Unidades (actual, anterior, variación)
                COALESCE(a.unidades_actual, 0) as unidades_actual,
                COALESCE(b.unidades_anterior, 0) as unidades_anterior,
                COALESCE(
                    CASE
                        WHEN b.unidades_anterior IS NULL OR b.unidades_anterior = 0 THEN
                            CASE
                                WHEN a.unidades_actual IS NULL OR a.unidades_actual = 0 THEN 0
                                ELSE 100
                            END
                        ELSE round((a.unidades_actual - b.unidades_anterior) / b.unidades_anterior * 100, 2)
                    END,
                    0
                ) as variacion_unidades,
                COALESCE(a.contribucion_actual, 0) as contribucion_actual,
                COALESCE(b.contribucion_anterior, 0) as contribucion_anterior,
                COALESCE(
                    CASE
                        WHEN b.contribucion_anterior IS NULL OR b.contribucion_anterior = 0 THEN
                            CASE
                                WHEN a.contribucion_actual IS NULL OR a.contribucion_actual = 0 THEN 0
                                ELSE 100
                            END
                        ELSE round((a.contribucion_actual - b.contribucion_anterior) / b.contribucion_anterior * 100, 2)
                    END,
                    0
                ) as variacion_contribucion,
                COALESCE(a.margen_actual, 0) as margen_actual,
                COALESCE(b.margen_anterior, 0) as margen_anterior,
                COALESCE(a.participacion_actual, 0) as participacion_actual,
                COALESCE(b.participacion_anterior, 0) as participacion_anterior,
                COALESCE(a.ticket_promedio_actual, 0) as ticket_promedio_actual,
                COALESCE(b.ticket_promedio_anterior, 0) as ticket_promedio_anterior

            FROM datos_actual a
            FULL OUTER JOIN datos_anterior b ON a.canal = b.canal
            WHERE COALESCE(a.canal, b.canal) IS NOT NULL
            ORDER BY COALESCE(a.venta_actual, 0) DESC
            """
        },
        {
            "id": "performance_sucursal",
            "objetivo": f"Performance por sucursal para la UEN {uen} en ambos períodos",
            "query": f"""
                WITH datos_actual AS (
                SELECT
                    sucursal,
                    sum(totalNetoItem) as venta_actual,
                    sum(cantidad) as unidades_actual,
                    sum(totalMargenItem) as contribucion_actual,
                    round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_actual,
                    round(sum(totalNetoItem) / (
                        SELECT sum(totalNetoItem)
                        FROM implementos.ventasrealtime
                        WHERE uen = '{uen}' AND fecha >= '{inicio_actual_str}' AND fecha <= '{fin_actual_str}'
                    ) * 100, 2) as participacion_actual,
                    round(sum(totalNetoItem) / uniqExact(documento), 1) as ticket_promedio_actual
                FROM implementos.ventasrealtime
                WHERE uen = '{uen}'
                AND fecha >= '{inicio_actual_str}'
                AND fecha <= '{fin_actual_str}'
                GROUP BY sucursal
              ),
              datos_anterior AS (
                SELECT
                    sucursal,
                    sum(totalNetoItem) as venta_anterior,
                    sum(cantidad) as unidades_anterior,
                    sum(totalMargenItem) as contribucion_anterior,
                    round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_anterior,
                    round(sum(totalNetoItem) / (
                        SELECT sum(totalNetoItem)
                        FROM implementos.ventasrealtime
                        WHERE uen = '{uen}' AND fecha >= '{inicio_anterior_str}' AND fecha <= '{fin_anterior_str}'
                    ) * 100, 2) as participacion_anterior,
                    round(sum(totalNetoItem) / uniqExact(documento), 1) as ticket_promedio_anterior
                FROM implementos.ventasrealtime
                WHERE uen = '{uen}'
                AND fecha >= '{inicio_anterior_str}'
                AND fecha <= '{fin_anterior_str}'
                GROUP BY sucursal
              )

              SELECT
                COALESCE(a.sucursal, b.sucursal) as sucursal,
                COALESCE(a.venta_actual, 0) as venta_actual,
                COALESCE(b.venta_anterior, 0) as venta_anterior,
                COALESCE(
                    CASE
                        WHEN b.venta_anterior IS NULL OR b.venta_anterior = 0 THEN
                            CASE
                                WHEN a.venta_actual IS NULL OR a.venta_actual = 0 THEN 0
                                ELSE 100
                            END
                        ELSE round((a.venta_actual - b.venta_anterior) / b.venta_anterior * 100, 2)
                    END,
                    0
                ) as variacion_venta,
                COALESCE(a.unidades_actual, 0) as unidades_actual,
                COALESCE(b.unidades_anterior, 0) as unidades_anterior,
                COALESCE(
                    CASE
                        WHEN b.unidades_anterior IS NULL OR b.unidades_anterior = 0 THEN
                            CASE
                                WHEN a.unidades_actual IS NULL OR a.unidades_actual = 0 THEN 0
                                ELSE 100
                            END
                        ELSE round((a.unidades_actual - b.unidades_anterior) / b.unidades_anterior * 100, 2)
                    END,
                    0
                ) as variacion_unidades,
                COALESCE(a.contribucion_actual, 0) as contribucion_actual,
                COALESCE(b.contribucion_anterior, 0) as contribucion_anterior,
                COALESCE(
                    CASE
                        WHEN b.contribucion_anterior IS NULL OR b.contribucion_anterior = 0 THEN
                            CASE
                                WHEN a.contribucion_actual IS NULL OR a.contribucion_actual = 0 THEN 0
                                ELSE 100
                            END
                        ELSE round((a.contribucion_actual - b.contribucion_anterior) / b.contribucion_anterior * 100, 2)
                    END,
                    0
                ) as variacion_contribucion,
                COALESCE(a.margen_actual, 0) as margen_actual,
                COALESCE(b.margen_anterior, 0) as margen_anterior,
                COALESCE(a.participacion_actual, 0) as participacion_actual,
                COALESCE(b.participacion_anterior, 0) as participacion_anterior,
                COALESCE(a.ticket_promedio_actual, 0) as ticket_promedio_actual,
                COALESCE(b.ticket_promedio_anterior, 0) as ticket_promedio_anterior
              FROM datos_actual a
              FULL OUTER JOIN datos_anterior b ON a.sucursal = b.sucursal
              WHERE COALESCE(a.sucursal, b.sucursal) IS NOT NULL
              ORDER BY COALESCE(a.venta_actual, 0) DESC
            """
        },
        {
            "id": "analisis_categorias",
            "objetivo": f"Análisis de categorías para la UEN {uen} en ambos períodos",
            "query": f"""
                WITH datos_actual AS (
                SELECT
                    categoria,
                    sum(totalNetoItem) as venta_actual,
                    sum(cantidad) as unidades_actual,
                    sum(totalMargenItem) as contribucion_actual,
                    round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_actual,
                    round(sum(totalNetoItem) / (
                        SELECT sum(totalNetoItem)
                        FROM implementos.ventasrealtime
                        WHERE uen = '{uen}' AND fecha >= '{inicio_actual_str}' AND fecha <= '{fin_actual_str}'
                    ) * 100, 2) as participacion_actual
                FROM implementos.ventasrealtime
                WHERE uen = '{uen}'
                AND fecha >= '{inicio_actual_str}'
                AND fecha <= '{fin_actual_str}'
                GROUP BY categoria
              ),
              datos_anterior AS (
                SELECT
                    categoria,
                    sum(totalNetoItem) as venta_anterior,
                    sum(cantidad) as unidades_anterior,
                    sum(totalMargenItem) as contribucion_anterior,
                    round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_anterior,
                    round(sum(totalNetoItem) / (
                        SELECT sum(totalNetoItem)
                        FROM implementos.ventasrealtime
                        WHERE uen = '{uen}' AND fecha >= '{inicio_anterior_str}' AND fecha <= '{fin_anterior_str}'
                    ) * 100, 2) as participacion_anterior
                FROM implementos.ventasrealtime
                WHERE uen = '{uen}'
                AND fecha >= '{inicio_anterior_str}'
                AND fecha <= '{fin_anterior_str}'
                GROUP BY categoria
              )

              SELECT
                COALESCE(a.categoria, b.categoria) as categoria,
                COALESCE(a.venta_actual, 0) as venta_actual,
                COALESCE(b.venta_anterior, 0) as venta_anterior,
                COALESCE(
                    CASE
                        WHEN b.venta_anterior IS NULL OR b.venta_anterior = 0 THEN
                            CASE
                                WHEN a.venta_actual IS NULL OR a.venta_actual = 0 THEN 0
                                ELSE 100
                            END
                        ELSE round((a.venta_actual - b.venta_anterior) / b.venta_anterior * 100, 2)
                    END,
                    0
                ) as variacion_venta,
                COALESCE(a.unidades_actual, 0) as unidades_actual,
                COALESCE(b.unidades_anterior, 0) as unidades_anterior,
                COALESCE(
                    CASE
                        WHEN b.unidades_anterior IS NULL OR b.unidades_anterior = 0 THEN
                            CASE
                                WHEN a.unidades_actual IS NULL OR a.unidades_actual = 0 THEN 0
                                ELSE 100
                            END
                        ELSE round((a.unidades_actual - b.unidades_anterior) / b.unidades_anterior * 100, 2)
                    END,
                    0
                ) as variacion_unidades,
                COALESCE(a.contribucion_actual, 0) as contribucion_actual,
                COALESCE(b.contribucion_anterior, 0) as contribucion_anterior,
                COALESCE(
                    CASE
                        WHEN b.contribucion_anterior IS NULL OR b.contribucion_anterior = 0 THEN
                            CASE
                                WHEN a.contribucion_actual IS NULL OR a.contribucion_actual = 0 THEN 0
                                ELSE 100
                            END
                        ELSE round((a.contribucion_actual - b.contribucion_anterior) / b.contribucion_anterior * 100, 2)
                    END,
                    0
                ) as variacion_contribucion,
                COALESCE(a.margen_actual, 0) as margen_actual,
                COALESCE(b.margen_anterior, 0) as margen_anterior,
                COALESCE(a.participacion_actual, 0) as participacion_actual,
                COALESCE(b.participacion_anterior, 0) as participacion_anterior
              FROM datos_actual a
              FULL OUTER JOIN datos_anterior b ON a.categoria = b.categoria
              WHERE COALESCE(a.categoria, b.categoria) IS NOT NULL
              ORDER BY COALESCE(a.venta_actual, 0) DESC
            """
        },
        {
            "id": "matriz_categoria_canal",
            "objetivo": f"Matriz de categoría por canal para la UEN {uen} en ambos períodos",
            "query": f"""
                              WITH total_categoria_actual AS (
                  SELECT
                      categoria,
                      sum(totalNetoItem) as venta_total
                  FROM implementos.ventasrealtime
                  WHERE uen = '{uen}'
                  AND fecha >= '{inicio_actual_str}'
                  AND fecha <= '{fin_actual_str}'
                  GROUP BY categoria
              ),
              total_categoria_anterior AS (
                  SELECT
                      categoria,
                      sum(totalNetoItem) as venta_total
                  FROM implementos.ventasrealtime
                  WHERE uen = '{uen}'
                  AND fecha >= '{inicio_anterior_str}'
                  AND fecha <= '{fin_anterior_str}'
                  GROUP BY categoria
              ),
              detalle_actual AS (
                  SELECT
                      categoria,
                      tipoVenta as canal,
                      sum(totalNetoItem) as venta_actual
                  FROM implementos.ventasrealtime
                  WHERE uen = '{uen}'
                  AND fecha >= '{inicio_actual_str}'
                  AND fecha <= '{fin_actual_str}'
                  GROUP BY categoria, tipoVenta
              ),
              detalle_anterior AS (
                  SELECT
                      categoria,
                      tipoVenta as canal,
                      sum(totalNetoItem) as venta_anterior
                  FROM implementos.ventasrealtime
                  WHERE uen = '{uen}'
                  AND fecha >= '{inicio_anterior_str}'
                  AND fecha <= '{fin_anterior_str}'
                  GROUP BY categoria, tipoVenta
              )

              SELECT
                  COALESCE(a.categoria, b.categoria) as categoria,
                  COALESCE(a.canal, b.canal) as canal,
                  COALESCE(a.venta_actual, 0) as venta_actual,
                  COALESCE(b.venta_anterior, 0) as venta_anterior,
                  CASE
                      WHEN b.venta_anterior IS NULL OR b.venta_anterior = 0 THEN
                          CASE
                              WHEN a.venta_actual IS NULL OR a.venta_actual = 0 THEN 0
                              ELSE 100
                          END
                      ELSE round((a.venta_actual - b.venta_anterior) / nullIf(b.venta_anterior, 0) * 100, 2)
                  END as variacion_venta,
                  CASE
                      WHEN ta.venta_total IS NULL OR ta.venta_total = 0 THEN 0
                      ELSE round(a.venta_actual / ta.venta_total * 100, 2)
                  END as participacion_categoria_actual,
                  CASE
                      WHEN tb.venta_total IS NULL OR tb.venta_total = 0 THEN 0
                      ELSE round(b.venta_anterior / tb.venta_total * 100, 2)
                  END as participacion_categoria_anterior
              FROM detalle_actual a
              FULL OUTER JOIN detalle_anterior b ON a.categoria = b.categoria AND a.canal = b.canal
              LEFT JOIN total_categoria_actual ta ON COALESCE(a.categoria, b.categoria) = ta.categoria
              LEFT JOIN total_categoria_anterior tb ON COALESCE(a.categoria, b.categoria) = tb.categoria
              WHERE COALESCE(a.categoria, b.categoria) IS NOT NULL
              ORDER BY COALESCE(a.categoria, b.categoria), COALESCE(a.canal, b.canal)
            """
        },
        {
            "id": "participacion_sucursal",
            "objetivo": f"Participación de {uen} en cada sucursal en ambos períodos",
            "query": f"""
                WITH total_sucursal_actual AS (
                SELECT
                    sucursal,
                    sum(totalNetoItem) as venta_total_actual
                FROM implementos.ventasrealtime
                WHERE fecha >= '{inicio_actual_str}'
                AND fecha <= '{fin_actual_str}'
                GROUP BY sucursal
              ),
              uen_sucursal_actual AS (
                SELECT
                    sucursal,
                    sum(totalNetoItem) as venta_uen_actual
                FROM implementos.ventasrealtime
                WHERE uen = '{uen}'
                AND fecha >= '{inicio_actual_str}'
                AND fecha <= '{fin_actual_str}'
                GROUP BY sucursal
              ),
              total_sucursal_anterior AS (
                SELECT
                    sucursal,
                    sum(totalNetoItem) as venta_total_anterior
                FROM implementos.ventasrealtime
                WHERE fecha >= '{inicio_anterior_str}'
                AND fecha <= '{fin_anterior_str}'
                GROUP BY sucursal
              ),
              uen_sucursal_anterior AS (
                SELECT
                    sucursal,
                    sum(totalNetoItem) as venta_uen_anterior
                FROM implementos.ventasrealtime
                WHERE uen = '{uen}'
                AND fecha >= '{inicio_anterior_str}'
                AND fecha <= '{fin_anterior_str}'
                GROUP BY sucursal
              )

              SELECT
                COALESCE(ea.sucursal, eb.sucursal) as sucursal,
                COALESCE(ea.venta_uen_actual, 0) as venta_uen_actual,
                COALESCE(eb.venta_uen_anterior, 0) as venta_uen_anterior,
                COALESCE(
                    CASE
                        WHEN eb.venta_uen_anterior IS NULL OR eb.venta_uen_anterior = 0 THEN
                            CASE
                                WHEN ea.venta_uen_actual IS NULL OR ea.venta_uen_actual = 0 THEN 0
                                ELSE 100
                            END
                        ELSE round((ea.venta_uen_actual - eb.venta_uen_anterior) / eb.venta_uen_anterior * 100, 2)
                    END,
                    0
                ) as variacion_venta_uen,
                COALESCE(ta.venta_total_actual, 0) as venta_total_actual,
                COALESCE(tb.venta_total_anterior, 0) as venta_total_anterior,
                COALESCE(round(ea.venta_uen_actual / ta.venta_total_actual * 100, 2), 0) as participacion_sucursal_actual,
                COALESCE(round(eb.venta_uen_anterior / tb.venta_total_anterior * 100, 2), 0) as participacion_sucursal_anterior
              FROM uen_sucursal_actual ea
              FULL OUTER JOIN uen_sucursal_anterior eb ON ea.sucursal = eb.sucursal
              LEFT JOIN total_sucursal_actual ta ON COALESCE(ea.sucursal, eb.sucursal) = ta.sucursal
              LEFT JOIN total_sucursal_anterior tb ON COALESCE(ea.sucursal, eb.sucursal) = tb.sucursal
              WHERE COALESCE(ea.sucursal, eb.sucursal) IS NOT NULL
              ORDER BY COALESCE(ea.venta_uen_actual, 0) DESC
            """
        },
        {
            "id": "desempeno_linea",
            "objetivo": f"Desempeño por línea de producto para la UEN {uen} en ambos períodos",
            "query": f"""
                WITH datos_actual AS (
              SELECT
                  linea,
                  sum(totalNetoItem) as venta_actual,
                  sum(cantidad) as unidades_actual,
                  sum(totalMargenItem) as contribucion_actual,
                  round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_actual,
                  round(sum(totalNetoItem) / (
                      SELECT sum(totalNetoItem)
                      FROM implementos.ventasrealtime
                      WHERE uen = '{uen}' AND fecha >= '{inicio_actual_str}' AND fecha <= '{fin_actual_str}'
                  ) * 100, 2) as participacion_actual
              FROM implementos.ventasrealtime
              WHERE uen = '{uen}'
              AND fecha >= '{inicio_actual_str}'
              AND fecha <= '{fin_actual_str}'
              GROUP BY linea
            ),
            datos_anterior AS (
              SELECT
                  linea,
                  sum(totalNetoItem) as venta_anterior,
                  sum(cantidad) as unidades_anterior,
                  sum(totalMargenItem) as contribucion_anterior,
                  round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_anterior,
                  round(sum(totalNetoItem) / (
                      SELECT sum(totalNetoItem)
                      FROM implementos.ventasrealtime
                      WHERE uen = '{uen}' AND fecha >= '{inicio_anterior_str}' AND fecha <= '{fin_anterior_str}'
                  ) * 100, 2) as participacion_anterior
              FROM implementos.ventasrealtime
              WHERE uen = '{uen}'
              AND fecha >= '{inicio_anterior_str}'
              AND fecha <= '{fin_anterior_str}'
              GROUP BY linea
            )

            SELECT
              COALESCE(a.linea, b.linea) as linea,
              COALESCE(a.venta_actual, 0) as venta_actual,
              COALESCE(b.venta_anterior, 0) as venta_anterior,
              COALESCE(
                  CASE
                      WHEN b.venta_anterior IS NULL OR b.venta_anterior = 0 THEN
                          CASE
                              WHEN a.venta_actual IS NULL OR a.venta_actual = 0 THEN 0
                              ELSE 100
                          END
                      ELSE round((a.venta_actual - b.venta_anterior) / b.venta_anterior * 100, 2)
                  END,
                  0
              ) as variacion_venta,
              COALESCE(a.unidades_actual, 0) as unidades_actual,
              COALESCE(b.unidades_anterior, 0) as unidades_anterior,
              COALESCE(
                  CASE
                      WHEN b.unidades_anterior IS NULL OR b.unidades_anterior = 0 THEN
                          CASE
                              WHEN a.unidades_actual IS NULL OR a.unidades_actual = 0 THEN 0
                              ELSE 100
                          END
                      ELSE round((a.unidades_actual - b.unidades_anterior) / b.unidades_anterior * 100, 2)
                  END,
                  0
              ) as variacion_unidades,
              COALESCE(a.contribucion_actual, 0) as contribucion_actual,
              COALESCE(b.contribucion_anterior, 0) as contribucion_anterior,
              COALESCE(
                  CASE
                      WHEN b.contribucion_anterior IS NULL OR b.contribucion_anterior = 0 THEN
                          CASE
                              WHEN a.contribucion_actual IS NULL OR a.contribucion_actual = 0 THEN 0
                              ELSE 100
                          END
                      ELSE round((a.contribucion_actual - b.contribucion_anterior) / b.contribucion_anterior * 100, 2)
                  END,
                  0
              ) as variacion_contribucion,
              COALESCE(a.margen_actual, 0) as margen_actual,
              COALESCE(b.margen_anterior, 0) as margen_anterior,
              COALESCE(a.participacion_actual, 0) as participacion_actual,
              COALESCE(b.participacion_anterior, 0) as participacion_anterior
            FROM datos_actual a
            FULL OUTER JOIN datos_anterior b ON a.linea = b.linea
            WHERE COALESCE(a.linea, b.linea) IS NOT NULL
            ORDER BY COALESCE(a.venta_actual, 0) DESC
            """
        },
        {
            "id": "clientes_estrategicos",
            "objetivo": f"Análisis de clientes estratégicos para la UEN {uen} en ambos períodos",
            "query": f"""
                WITH datos_actual AS (
                SELECT
                    rutCliente,
                    nombreCliente,
                    sum(totalNetoItem) as venta_actual,
                    sum(cantidad) as unidades_actual,
                    sum(totalMargenItem) as contribucion_actual,
                    round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_actual,
                    uniqExact(toDate(fecha)) as dias_compra_actual,
                    round(sum(totalNetoItem) / uniqExact(documento), 1) as ticket_promedio_actual
                FROM implementos.ventasrealtime
                WHERE uen = '{uen}'
                AND fecha >= '{inicio_actual_str}'
                AND fecha <= '{fin_actual_str}'
                AND rutCliente != '66666666-6'
                GROUP BY rutCliente, nombreCliente
                ORDER BY venta_actual DESC
                LIMIT 10
              ),
              datos_anterior AS (
                SELECT
                    rutCliente,
                    nombreCliente,
                    sum(totalNetoItem) as venta_anterior,
                    sum(cantidad) as unidades_anterior,
                    sum(totalMargenItem) as contribucion_anterior,
                    round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_anterior,
                    uniqExact(toDate(fecha)) as dias_compra_anterior,
                    round(sum(totalNetoItem) / uniqExact(documento), 1) as ticket_promedio_anterior
                FROM implementos.ventasrealtime
                WHERE uen = '{uen}'
                AND fecha >= '{inicio_anterior_str}'
                AND fecha <= '{fin_anterior_str}'
                AND rutCliente != '66666666-6'
                GROUP BY rutCliente, nombreCliente
                ORDER BY venta_anterior DESC
                LIMIT 10
              ),
              combinados AS (
                SELECT
                    a.rutCliente,
                    a.nombreCliente
                FROM datos_actual a

                UNION DISTINCT

                SELECT
                    b.rutCliente,
                    b.nombreCliente
                FROM datos_anterior b
              )

              SELECT
                c.rutCliente,
                c.nombreCliente,
                COALESCE(a.venta_actual, 0) as venta_actual,
                COALESCE(b.venta_anterior, 0) as venta_anterior,
                COALESCE(
                    CASE
                        WHEN b.venta_anterior IS NULL OR b.venta_anterior = 0 THEN
                            CASE
                                WHEN a.venta_actual IS NULL OR a.venta_actual = 0 THEN 0
                                ELSE 100
                            END
                        ELSE round((a.venta_actual - b.venta_anterior) / b.venta_anterior * 100, 2)
                    END,
                    0
                ) as variacion_venta,
                COALESCE(a.unidades_actual, 0) as unidades_actual,
                COALESCE(b.unidades_anterior, 0) as unidades_anterior,
                COALESCE(a.contribucion_actual, 0) as contribucion_actual,
                COALESCE(b.contribucion_anterior, 0) as contribucion_anterior,
                COALESCE(a.margen_actual, 0) as margen_actual,
                COALESCE(b.margen_anterior, 0) as margen_anterior,
                COALESCE(a.dias_compra_actual, 0) as dias_compra_actual,
                COALESCE(b.dias_compra_anterior, 0) as dias_compra_anterior,
                COALESCE(a.ticket_promedio_actual, 0) as ticket_promedio_actual,
                COALESCE(b.ticket_promedio_anterior, 0) as ticket_promedio_anterior
              FROM combinados c
              LEFT JOIN datos_actual a ON c.rutCliente = a.rutCliente
              LEFT JOIN datos_anterior b ON c.rutCliente = b.rutCliente
              ORDER BY COALESCE(a.venta_actual, 0) DESC
            """
        },
        {
            "id": "clientes_perdida",
            "objetivo": f"Clientes con mayor pérdida de venta para UEN {uen}",
            "query": f"""
                WITH actual AS (
              SELECT
                  rutCliente,
                  nombreCliente,
                  sum(totalNetoItem) as venta_actual
              FROM implementos.ventasrealtime
              WHERE uen = '{uen}'
              AND fecha >= '{inicio_actual_str}'
              AND fecha <= '{fin_actual_str}'
              AND rutCliente != '66666666-6'
              GROUP BY rutCliente, nombreCliente
            ),
            anterior AS (
              SELECT
                  rutCliente,
                  nombreCliente,
                  sum(totalNetoItem) as venta_anterior
              FROM implementos.ventasrealtime
              WHERE uen = '{uen}'
              AND fecha >= '{inicio_anterior_str}'
              AND fecha <= '{fin_anterior_str}'
              AND rutCliente != '66666666-6'
              GROUP BY rutCliente, nombreCliente
            )
            SELECT
              b.rutCliente,
              b.nombreCliente,
              COALESCE(a.venta_actual, 0) as venta_actual,
              b.venta_anterior,
              round(COALESCE(a.venta_actual, 0) - b.venta_anterior, 1) as diferencia,
              round((COALESCE(a.venta_actual, 0) - b.venta_anterior) / nullif(b.venta_anterior, 0) * 100, 1) as variacion_porcentual
            FROM anterior b
            LEFT JOIN actual a ON b.rutCliente = a.rutCliente
            WHERE a.venta_actual IS NULL OR a.venta_actual < b.venta_anterior
            ORDER BY diferencia ASC
            LIMIT 10
            """
        },
        {
            "id": "resumen_boleta",
            "objetivo": f"Resumen de CLIENTE CON BOLETA para UEN {uen} en ambos períodos",
            "query": f"""
                WITH datos_actual AS (
                SELECT
                    sum(totalNetoItem) as venta_actual,
                    sum(cantidad) as unidades_actual,
                    sum(totalMargenItem) as contribucion_actual,
                    round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_actual,
                    round(sum(totalNetoItem) / (
                        SELECT sum(totalNetoItem)
                        FROM implementos.ventasrealtime
                        WHERE uen = '{uen}' AND fecha >= '{inicio_actual_str}' AND fecha <= '{fin_actual_str}'
                    ) * 100, 2) as participacion_actual
                FROM implementos.ventasrealtime
                WHERE uen = '{uen}'
                AND fecha >= '{inicio_actual_str}'
                AND fecha <= '{fin_actual_str}'
                AND rutCliente = '66666666-6'
              ),
              datos_anterior AS (
                SELECT
                    sum(totalNetoItem) as venta_anterior,
                    sum(cantidad) as unidades_anterior,
                    sum(totalMargenItem) as contribucion_anterior,
                    round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_anterior,
                    round(sum(totalNetoItem) / (
                        SELECT sum(totalNetoItem)
                        FROM implementos.ventasrealtime
                        WHERE uen = '{uen}' AND fecha >= '{inicio_anterior_str}' AND fecha <= '{fin_anterior_str}'
                    ) * 100, 2) as participacion_anterior
                FROM implementos.ventasrealtime
                WHERE uen = '{uen}'
                AND fecha >= '{inicio_anterior_str}'
                AND fecha <= '{fin_anterior_str}'
                AND rutCliente = '66666666-6'
              )

              SELECT
                COALESCE(a.venta_actual, 0) as venta_actual,
                COALESCE(b.venta_anterior, 0) as venta_anterior,
                COALESCE(
                    CASE
                        WHEN b.venta_anterior IS NULL OR b.venta_anterior = 0 THEN
                            CASE
                                WHEN a.venta_actual IS NULL OR a.venta_actual = 0 THEN 0
                                ELSE 100
                            END
                        ELSE round((a.venta_actual - b.venta_anterior) / b.venta_anterior * 100, 2)
                    END,
                    0
                ) as variacion_venta,
                COALESCE(a.unidades_actual, 0) as unidades_actual,
                COALESCE(b.unidades_anterior, 0) as unidades_anterior,
                COALESCE(
                    CASE
                        WHEN b.unidades_anterior IS NULL OR b.unidades_anterior = 0 THEN
                            CASE
                                WHEN a.unidades_actual IS NULL OR a.unidades_actual = 0 THEN 0
                                ELSE 100
                            END
                        ELSE round((a.unidades_actual - b.unidades_anterior) / b.unidades_anterior * 100, 2)
                    END,
                    0
                ) as variacion_unidades,
                COALESCE(a.contribucion_actual, 0) as contribucion_actual,
                COALESCE(b.contribucion_anterior, 0) as contribucion_anterior,
                COALESCE(
                    CASE
                        WHEN b.contribucion_anterior IS NULL OR b.contribucion_anterior = 0 THEN
                            CASE
                                WHEN a.contribucion_actual IS NULL OR a.contribucion_actual = 0 THEN 0
                                ELSE 100
                            END
                        ELSE round((a.contribucion_actual - b.contribucion_anterior) / b.contribucion_anterior * 100, 2)
                    END,
                    0
                ) as variacion_contribucion,
                COALESCE(a.margen_actual, 0) as margen_actual,
                COALESCE(b.margen_anterior, 0) as margen_anterior,
                COALESCE(a.participacion_actual, 0) as participacion_actual,
                COALESCE(b.participacion_anterior, 0) as participacion_anterior
              FROM datos_actual a
              CROSS JOIN datos_anterior b
            """
        },
        {
            "id": "performance_vendedores",
            "objetivo": f"Performance de vendedores para la UEN {uen} en ambos períodos",
            "query": f"""
                WITH datos_actual AS (
                SELECT
                    nombreVendedor,
                    sum(totalNetoItem) as venta_actual,
                    sum(cantidad) as unidades_actual,
                    sum(totalMargenItem) as contribucion_actual,
                    round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_actual,
                    round(sum(totalNetoItem) / uniqExact(documento), 1) as ticket_promedio_actual
                FROM implementos.ventasrealtime
                WHERE uen = '{uen}'
                AND fecha >= '{inicio_actual_str}'
                AND fecha <= '{fin_actual_str}'
                GROUP BY nombreVendedor
                ORDER BY venta_actual DESC
                LIMIT 10
              ),
              datos_anterior AS (
                SELECT
                    nombreVendedor,
                    sum(totalNetoItem) as venta_anterior,
                    sum(cantidad) as unidades_anterior,
                    sum(totalMargenItem) as contribucion_anterior,
                    round(sum(totalMargenItem) / sum(totalNetoItem) * 100, 1) as margen_anterior,
                    round(sum(totalNetoItem) / uniqExact(documento), 1) as ticket_promedio_anterior
                FROM implementos.ventasrealtime
                WHERE uen = '{uen}'
                AND fecha >= '{inicio_anterior_str}'
                AND fecha <= '{fin_anterior_str}'
                GROUP BY nombreVendedor
                ORDER BY venta_anterior DESC
                LIMIT 10
              ),
              combinados AS (
                SELECT
                    nombreVendedor
                FROM datos_actual

                UNION DISTINCT

                SELECT
                    nombreVendedor
                FROM datos_anterior
              )

              SELECT
                c.nombreVendedor,
                COALESCE(a.venta_actual, 0) as venta_actual,
                COALESCE(b.venta_anterior, 0) as venta_anterior,
                COALESCE(
                    CASE
                        WHEN b.venta_anterior IS NULL OR b.venta_anterior = 0 THEN
                            CASE
                                WHEN a.venta_actual IS NULL OR a.venta_actual = 0 THEN 0
                                ELSE 100
                            END
                        ELSE round((a.venta_actual - b.venta_anterior) / b.venta_anterior * 100, 2)
                    END,
                    0
                ) as variacion_venta,
                COALESCE(a.unidades_actual, 0) as unidades_actual,
                COALESCE(b.unidades_anterior, 0) as unidades_anterior,
                COALESCE(a.contribucion_actual, 0) as contribucion_actual,
                COALESCE(b.contribucion_anterior, 0) as contribucion_anterior,
                COALESCE(a.margen_actual, 0) as margen_actual,
                COALESCE(b.margen_anterior, 0) as margen_anterior,
                COALESCE(a.ticket_promedio_actual, 0) as ticket_promedio_actual,
                COALESCE(b.ticket_promedio_anterior, 0) as ticket_promedio_anterior
              FROM combinados c
              LEFT JOIN datos_actual a ON c.nombreVendedor = a.nombreVendedor
              LEFT JOIN datos_anterior b ON c.nombreVendedor = b.nombreVendedor
              ORDER BY COALESCE(a.venta_actual, 0) DESC
            """
        },
        {
            "id": "vendedores_caida",
            "objetivo": f"Vendedores con caída en ventas para UEN {uen}",
            "query": f"""
                WITH actual AS (
                SELECT
                    nombreVendedor,
                    sum(totalNetoItem) as venta_actual
                FROM implementos.ventasrealtime
                WHERE uen = '{uen}'
                AND fecha >= '{inicio_actual_str}'
                AND fecha <= '{fin_actual_str}'
                GROUP BY nombreVendedor
              ),
              anterior AS (
                SELECT
                    nombreVendedor,
                    sum(totalNetoItem) as venta_anterior
                FROM implementos.ventasrealtime
                WHERE uen = '{uen}'
                AND fecha >= '{inicio_anterior_str}'
                AND fecha <= '{fin_anterior_str}'
                GROUP BY nombreVendedor
              )
              SELECT
                b.nombreVendedor,
                COALESCE(a.venta_actual, 0) as venta_actual,
                b.venta_anterior,
                round(COALESCE(a.venta_actual, 0) - b.venta_anterior, 1) as diferencia,
                round((COALESCE(a.venta_actual, 0) - b.venta_anterior) / nullif(b.venta_anterior, 0) * 100, 1) as variacion_porcentual
              FROM anterior b
              LEFT JOIN actual a ON b.nombreVendedor = a.nombreVendedor
              WHERE a.venta_actual IS NULL OR a.venta_actual < b.venta_anterior
              ORDER BY diferencia ASC
              LIMIT 5
            """
        },
        {
            "id": "analisis_atipicos",
            "objetivo": f"Análisis de datos atípicos para la UEN {uen}",
            "query": f"""
                WITH stats AS (
                SELECT
                    avg(totalMargenItem / totalNetoItem) as avg_margen,
                    stddevPop(totalMargenItem / totalNetoItem) as stddev_margen,
                    avg(descuento / precio) as avg_descuento,
                    stddevPop(descuento / precio) as stddev_descuento
                FROM implementos.ventasrealtime
                WHERE uen = '{uen}'
                AND fecha >= '{inicio_actual_str}'
                AND fecha <= '{fin_actual_str}'
                AND totalNetoItem > 0
                AND precio > 0
              )
              SELECT
                documento,
                fecha,
                rutCliente,
                nombreCliente,
                sucursal,
                tipoVenta,
                sku,
                round(totalNetoItem, 1) as totalNetoItem,
                round(totalMargenItem, 1) as totalMargenItem,
                round(totalMargenItem / totalNetoItem * 100, 1) as margen_porcentaje,
                round(precio, 1) as precio,
                round(descuento, 1) as descuento,
                round(descuento / precio * 100, 1) as descuento_porcentaje,
                round(totalMargenItem / totalNetoItem, 1) as margen_ratio,
                round(descuento / precio, 1) as descuento_ratio,
                round(((totalMargenItem / totalNetoItem) - (SELECT avg_margen FROM stats)) / (SELECT stddev_margen FROM stats), 1) as z_score_margen,
                round(((descuento / precio) - (SELECT avg_descuento FROM stats)) / (SELECT stddev_descuento FROM stats), 1) as z_score_descuento
              FROM implementos.ventasrealtime
              WHERE uen = '{uen}'
              AND fecha >= '{inicio_actual_str}'
              AND fecha <= '{fin_actual_str}'
              AND (
                ((totalMargenItem / totalNetoItem) - (SELECT avg_margen FROM stats)) / (SELECT stddev_margen FROM stats) < -2
                OR ((totalMargenItem / totalNetoItem) - (SELECT avg_margen FROM stats)) / (SELECT stddev_margen FROM stats) > 2
                OR ((descuento / precio) - (SELECT avg_descuento FROM stats)) / (SELECT stddev_descuento FROM stats) > 2
              )
              ORDER BY abs(((totalMargenItem / totalNetoItem) - (SELECT avg_margen FROM stats)) / (SELECT stddev_margen FROM stats)) DESC
              LIMIT 10
            """
        },
        {
            "id": "proyeccion_simple",
            "objetivo": f"Proyección simple para la UEN {uen}",
            "query": f"""
                WITH meses AS (
                    SELECT
                        toStartOfMonth(fecha) as mes,
                        sum(totalNetoItem) as venta
                    FROM implementos.ventasrealtime
                    WHERE uen = '{uen}'
                    AND fecha >= '2025-01-01'
                    AND fecha <= '{fin_actual_str}'
                    GROUP BY mes
                    ORDER BY mes
                )
                SELECT
                    mes,
                    venta,
                    avg(venta) OVER (ORDER BY mes ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) as promedio_movil
                FROM meses
            """
        },
        {
            "id": "comparacion_crecimiento",
            "objetivo": "Comparación de UENs por crecimiento",
            "query": f"""
                WITH actual AS (
                    SELECT
                        uen,
                        sum(totalNetoItem) as venta_actual
                    FROM implementos.ventasrealtime
                    WHERE fecha >= '{inicio_actual_str}'
                    AND fecha <= '{fin_actual_str}'
                    GROUP BY uen
                ),
                anterior AS (
                    SELECT
                        uen,
                        sum(totalNetoItem) as venta_anterior
                    FROM implementos.ventasrealtime
                    WHERE fecha >= '{inicio_anterior_str}'
                    AND fecha <= '{fin_anterior_str}'
                    GROUP BY uen
                )
                SELECT
                    a.uen,
                    a.venta_actual,
                    b.venta_anterior,
                    round((a.venta_actual - b.venta_anterior) / b.venta_anterior * 100, 1) as variacion_porcentual
                FROM actual a
                JOIN anterior b ON a.uen = b.uen
                ORDER BY variacion_porcentual DESC
            """
        },
        {
            "id": "impacto_descuentos",
            "objetivo": f"Impacto de descuentos en margen para la UEN {uen} en ambos períodos",
            "query": f"""
                WITH actual AS (
                    SELECT
                        '{etiqueta_actual}' as periodo,
                        round(avg(descuento / precio) * 100, 1) as descuento_promedio,
                        round(sum(descuento) / sum(precio) * 100, 1) as descuento_ponderado,
                        round(sum(totalNetoItem * (descuento / precio)), 1) as impacto_descuento
                    FROM implementos.ventasrealtime
                    WHERE uen = '{uen}'
                    AND fecha >= '{inicio_actual_str}'
                    AND fecha <= '{fin_actual_str}'
                    AND precio > 0
                ),
                anterior AS (
                    SELECT
                        '{etiqueta_anterior}' as periodo,
                        round(avg(descuento / precio) * 100, 1) as descuento_promedio,
                        round(sum(descuento) / sum(precio) * 100, 1) as descuento_ponderado,
                        round(sum(totalNetoItem * (descuento / precio)), 1) as impacto_descuento
                    FROM implementos.ventasrealtime
                    WHERE uen = '{uen}'
                    AND fecha >= '{inicio_anterior_str}'
                    AND fecha <= '{fin_anterior_str}'
                    AND precio > 0
                )

                SELECT * FROM actual
                UNION ALL
                SELECT * FROM anterior
            """
        }
    ]

    return queries


def execute_unified_queries(uen, tipo, inicio_periodo, fin_periodo):
    """
    Ejecuta las consultas unificadas y retorna los resultados

    Args:
        uen (str): UEN a analizar
        tipo (str): Tipo de periodo (anual, mensual, semanal)
        inicio_periodo (str): Fecha de inicio del periodo
        fin_periodo (str): Fecha de fin del periodo

    Returns:
        list: Lista de objetos con objetivo y datos
    """
    try:
        # Obtener las consultas unificadas
        queries = create_unified_queries(uen, tipo, inicio_periodo, fin_periodo)

        # Instanciar la clase para ejecutar consultas
        clickhouseData = DataVentasTool()

        # Lista para resultados
        resultados = []

        # Ejecutar cada consulta
        for query_obj in queries:
            # Preparar objeto de resultado
            result_obj = {
                "id": query_obj["id"],
                "objetivo": query_obj["objetivo"],
                "data": []
            }
            # Ejecutar la consulta
            data = clickhouseData.run_select_query("", query_obj["query"])

            # Añadir datos al resultado
            if data:
                result_obj["data"] = data

            # Añadir a resultados
            resultados.append(result_obj)

        return resultados

    except Exception as e:
        return [{"error": f"Error al ejecutar las consultas: {str(e)}"}]


@tool()
def exploratory_data(uen: str, tipo: str, inicio_periodo: str, fin_periodo: str):
    """
    Entrega datos iniciales para generación del reporte

    Args:
        uen (str): UEN unidad estratégica de negocio objetivo
        tipo (str): tipo de periodo de análisis mensual, anual, semanal
        inicio_periodo (str): fecha de inicio del periodo actual YYYY-MM-DD
        fin_periodo (str): fecha de final del periodo actual YYYY-MM-DD
    Returns:
        list: Resultado de las consultas con sus objetivos
    """
    try:
        # Ejecutar consultas unificadas
        resultados = execute_unified_queries(uen, tipo, inicio_periodo, fin_periodo)

        # Crear reporte
        reporte = {
            "uen": uen,
            "tipo_periodo": tipo,
            "fecha_inicio": inicio_periodo,
            "fecha_fin": fin_periodo,
            "fecha_generacion": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "secciones": resultados
        }

        return json.dumps(reporte, ensure_ascii=False, indent=2)

    except Exception as e:
        return {"error": f"Error al procesar la solicitud: {str(e)}"}


def create_agent() -> Agent:
    knowledge_base = JSONKnowledgeBase(
        vector_db=Qdrant(
            collection="clacom",
            url=os.getenv("QDRANT_URL"),
            api_key=os.getenv("QDRANT_API_KEY"),
        ),
        path="data/json")
    knowledge_base.load(recreate=False)

    model = Claude(id="claude-3-7-sonnet-20250219", temperature=0.1, max_tokens=25000, api_key=Config.ANTHROPIC_API_KEY)

    instruction1 = """
Instrucciones para Analistas de Datos: Construye un Informe detallado y Estratégico de una UEN indicada con los datos disponibles de la base ventasrealtime

@DOMAIN_VERIFICATION
  - No inventar datos: usar exclusivamente información real de la base.
  - La fecha de hoy es el limite para comparacion de periodos
  - NUNCA comparar periodos que no tengan la misma duración
  - nunca comparar periodos completos con particiales
  - en el inicio del reporte debes incluir fechas de periodos que incluya DD-MM-YYYY actual y de comparacion
  - SIEMPRE iniciar cualquier análisis ejecutando exploratory_data(uen, tipo, inicio_periodo, fin_periodo)
  - SIEMPRE respetar instrucciones particulares de cada seccion.

@SYSTEM_LOCK:
  - Respetar las instrucciones particulares de cada seccion.
  - Comenzar SIEMPRE cada sección con los hallazgos negativos o problemas, no con los positivos
  - NUNCA usar adjetivos calificativos subjetivos como "increíble", "excelente", "bueno", etc.
  - Las métricas deben compararse contra período anterior, promedio compañía y metas si están disponibles
  - Destacar métricas en rojo para rendimiento > 5% por debajo de expectativas aunque sea positivo vs período anterior
  - Siempre agrega semaforos en las tablas
  - OPTIMIZACIÓN DE CONSULTAS: Primero analiza datos de exploratory_data y sólo después realiza consultas adicionales si es estrictamente necesario
  - semaforo en rojo para margenes inferiores al 20%
  - margen siempre en porcentaje , contribucion siempre en monto $.
  - valida el nombre de la uen en el listado valido @UEN_VALID_IN_DB
  - semaforo en amarillo para crecimientos inferiores al de la compañia.
  - Solo si el usuario indica que requiere un PDF usa la Tools markdown_pdf para obtener el link excluye los graficos en su generacion.
  - privilegia mostrar informacion de oportunidades(problemas) en orden
    + siempre enfocados al mayor monto en venta perdida
  - Limitar consultas adicionales a un máximo de 5, enfocándose en los hallazgos más impactantes

@ENFOQUE_EJECUTIVO:
  - PRIORIZAR INFORMACIÓN ESTRATÉGICA:
    * Limitar cada sección a máximo 10 elementos críticos (no listar todo) si la seccion no lo indica en su instruccion.
    * Destacar anomalías de gran impacto
    * Ordenar siempre por impacto financiero, no por volumen
  - CUANTIFICAR TODAS LAS OBSERVACIONES:
    * Incluir impacto en $ para cada hallazgo (no solo porcentajes)
    * Estimar ROI para cada recomendación
    * Incluir tiempo estimado de recuperación de pérdidas
  - FORMATO ONE-PAGE PARA ALTA DIRECCIÓN:
    * Iniciar cada sección con 1-2 frases de conclusión accionable
    * Incluir solo datos necesarios para tomar decisiones
    * Evitar análisis descriptivos sin conclusión estratégica

@ENFOQUE_COMERCIAL_CRÍTICO:
  - PRIORITIZAR ALERTAS Y PROBLEMAS:
    * SIEMPRE comenzar cada sección con los problemas y desviaciones negativas
    * Estructurar información en formato "Problemas → Causas → Impacto → Recomendaciones"
    * Destacar primero lo que NO está funcionando antes que lo que sí funciona
    * Ordenar hallazgos negativos por magnitud de impacto financiero

  - EVITAR JUICIOS DE VALOR SUBJETIVOS:
    * NUNCA usar términos como "increíble", "significativo", "bueno", "excelente" o similares
    * Reemplazar juicios subjetivos por comparaciones cuantitativas: "10% por debajo del objetivo"
    * No calificar aumentos como positivos sin referencia a metas o expectativas
    * Reportar datos objetivamente: "incremento de 15% vs objetivo del 20%" en lugar de "buen incremento"

  - COMPARAR CONTRA EXPECTATIVAS COMERCIALES:
    * Toda variación debe compararse contra: período anterior, meta del período y promedio de la compañía
    * Crecimiento "significativo" puede ser insuficiente según expectativas comerciales
    * Añadir contexto cuantitativo a todas las evaluaciones de desempeño

@UEN_VALID_IN_DB
  - COMPONENTES PARA EQUIPOS DE CARGA
  - RODADO
  - FILTROS
  - ACCESORIOS Y CUIDADO AUTOMOTRIZ
  - BATERIAS
  - LLANTAS NEUMATICOS Y ACCESORIOS
  - HERRAMIENTAS Y ORGANIZACION
  - TEMPORADA EVENTOS ESPECIALES
  - LUBRICANTES Y GRASAS
  - SUSPENSIONES
  - SEGURIDAD VIAL E INDUSTRIAL
  - MOTORES DE PARTIDA Y ALTERNADORES
  - SISTEMA DE FRENOS
  - REFRIGERANTES AGUAS Y UREA
  - SEGURIDAD PERSONAL
  - ILUMINACION Y ACCESORIOS
  - POST VENTA MARCOPOLO Y VOLARE
  - ACCESORIOS DE CAMION
  - CONTROL DE CARGA
  - ENGANCHE
  - MOTOR Y TRANSMISION
  - PULMONES Y BOLSAS DE AIRE
  - VESTIMENTA
  - EMBRAGUES
  - EMBALAJE

@QUERY_OUTPUT_NUMBER:
  - Maximo 1 decimal

@OPTIMIZACION_TOKENS:
  - Usa las herramientas think() y analyze() frecuentemente para razonar
  - No revises el historial completo después de cada think() o analyze()
  - Para consultas a ClickHouse:
    * PRIMERO utiliza exploratory_data para obtener todos los datos consolidados
    * Usa run_query_batch con consultas pequeñas y específicas SOLO si se necesita profundizar
    * Usa primero consultas agregadas para entender patrones globales
    * Usa run_select_query solo para profundizar en hallazgos importantes

@SCHEMA:
  TABLE: implementos.ventasrealtime
  DIMENSIONS = [fecha, uen,categoria,linea,sku, rutCliente, sucursal,tipoVenta]
  METRICS = [totalNetoItem, totalMargenItem, cantidad, precio, descuento]
  CALCULATED = {
    margen_%: totalMargenItem / nullif(totalNetoItem, 0) * 100,
    contribucion: totalMargenItem,
    ticket_promedio: totalNetoItem / nullif(uniqExact(documento), 0)
  }
  ALIASES = {
    totalNetoItem: "Venta",
    cantidad: "Unidades",
    rutCliente: "Cliente",
    tipoVenta:"Canal"
  }
  CANAL ={
    VM="Venta Meson",
    VT="Venta Terreno",
    CJ="Venta Caja",
    TM="Venta Telemarketing",
    B2C="Venta Ecommerce",
    ES="Venta Especial",
    ML="Venta Mercado Libre",
    B2B="Venta Ecommerce Empresas"
  }
  NAMING_CONVENTIONS = {
    - No usar acentos en nombres de campos
    - Usar snake_case para alias de campos
  }

@OPTIMIZACION_EJECUCION:
  - ESTRATEGIA DE CONSULTA EN DOS FASES:
    * FASE 1 - EXPLORACIÓN INICIAL (OBLIGATORIA):
      + Al iniciar CUALQUIER análisis, SIEMPRE ejecutar primero exploratory_data(uen, tipo, inicio_periodo, fin_periodo)
      + Esta función devuelve datos consolidados clave de todas las secciones del reporte
      + Analizar estos datos para identificar tendencias principales, problemas críticos y oportunidades
      + NUNCA omitir este paso inicial, ya que proporciona el 80% de los datos necesarios para el análisis

    * FASE 2 - ANÁLISIS CRÍTICO DE SUFICIENCIA (OBLIGATORIA):
      + Para cada sección del reporte, evaluar explícitamente si los datos de exploración son suficientes según estos criterios:
        > ¿Los datos permiten identificar causas raíz de problemas, no solo síntomas?
        > ¿Se pueden cuantificar los impactos financieros con precisión?
        > ¿Es posible formular recomendaciones específicas y accionables?
        > ¿Se tienen datos suficientes para los Top 3 problemas/oportunidades identificados?
      + Si la respuesta es NO a cualquiera de estas preguntas, se DEBE realizar consultas adicionales
      + NUNCA concluir "con los datos estaba bien" sin verificar estos criterios

    * FASE 3 - CONSULTAS ESPECÍFICAS (OBLIGATORIA CUANDO APLIQUE):
      + Realizar consultas específicas cuando:
        > Se identifiquen anomalías que requieran mayor investigación
        > Se necesiten datos adicionales no incluidos en la exploración inicial
        > Se requiera profundizar en un hallazgo de alto impacto financiero
        > Exista variación inexplicable superior al 15% en métricas clave
        > Los datos no permitan identificar causas raíz de problemas críticos
      + Limitar el número de consultas adicionales a un máximo de 5
      + Priorizar consultas sobre hallazgos con mayor impacto económico
      + Documentar explícitamente por qué se necesitan datos adicionales

  - PROCESAMIENTO EFICIENTE:
    * Explorar y analizar completamente los datos de exploración antes de realizar cualquier consulta adicional
    * Identificar los 3-5 hallazgos principales basados solo en datos de exploración
    * Crear visualizaciones utilizando exclusivamente los datos ya obtenidos siempre que sea posible
    * Optimizar la generación de reportes reusando datos entre secciones
    * Analizar TODOS los resultados de exploratory_data antes de decidir si se necesitan consultas específicas

  - DECISIONES BASADAS EN DATOS:
    * Si los datos de exploración son suficientes para una sección, NO realizar consultas adicionales
    * Si un hallazgo tiene impacto menor al 5% en ventas o margen, NO profundizar con consultas adicionales
    * Priorizar análisis de categorías/líneas que representen >70% de las ventas o con variaciones >±15%
    * Enfocar recomendaciones en oportunidades cuantificables con ROI estimado >3x
    * Estructurar el proceso de análisis como: Exploración → Identificación de problemas clave → Profundización selectiva

@CRITERIOS_MÍNIMOS_DE_ANÁLISIS:
  - Para cada sección del reporte, DEBE cumplirse un mínimo de profundidad analítica:
    * Resumen Ejecutivo: Cuantificar impacto financiero preciso de al menos 3 problemas u oportunidades
    * Análisis por Canal: Determinar causas específicas de bajo rendimiento en canales críticos
    * Análisis de Categorías: Identificar factores específicos que expliquen variaciones superiores al 10%
    * Clientes Estratégicos: Analizar patrones específicos de comportamiento en clientes con mayor caída
    * Análisis de Outliers: Determinar causas raíz de anomalías con impacto superior al 2% en métricas globales
    * Strategic Outlook: Incluir proyecciones con factores causales específicos, no solo tendencias
  - Si con los datos de exploración no se alcanza este nivel mínimo, SE DEBEN realizar consultas adicionales
  - NUNCA sacrificar profundidad analítica por eficiencia computacional en hallazgos de alto impacto

@SCHEMA_EXPLORACIÓN:
  - La función exploratory_data devuelve resultados consolidados en formato JSON con:
    * datos_generales_uen: Métricas principales de la UEN en ambos períodos
    * ticket_promedio: Ticket promedio para ambos períodos
    * comparacion_uens: Comparativa de todas las UENs
    * analisis_canal: Desempeño por canal de ventas
    * performance_sucursal: Rendimiento por sucursal
    * analisis_categorias: Análisis de categorías
    * matriz_categoria_canal: Matriz cruzada de categoría por canal
    * participacion_sucursal: Participación de la UEN en cada sucursal
    * desempeno_linea: Métricas por línea de producto
    * clientes_estrategicos: Análisis de principales clientes
    * clientes_perdida: Clientes con mayor caída en ventas
    * resumen_boleta: Análisis de ventas con boleta
    * performance_vendedores: Desempeño de vendedores
    * vendedores_caida: Vendedores con caída en ventas
    * analisis_atipicos: Transacciones con comportamiento atípico
    * proyeccion_simple: Proyección basada en tendencia reciente
    * comparacion_crecimiento: Comparativa de crecimiento entre UENs
    * impacto_descuentos: Análisis del impacto de descuentos

  - PROCESO DE ANÁLISIS DE DATOS DE EXPLORACIÓN:
    * Paso 1: Revisar datos_generales_uen para entender rendimiento global
    * Paso 2: Analizar comparacion_uens para contexto competitivo
    * Paso 3: Examinar analisis_categorias y desempeno_linea para identificar drivers principales
    * Paso 4: Evaluar clientes_perdida y vendedores_caida para detectar problemas críticos
    * Paso 5: Validar analisis_atipicos para identificar anomalías que requieran investigación
    * Paso 6: Para cada sección del reporte, determinar si los datos de exploración son suficientes
    * Paso 7: Planificar consultas adicionales solo para las áreas con datos insuficientes o anomalías

@MÉTRICAS_AVANZADAS:
  - INSTRUCCIONES PARA ENRIQUECER SECCIONES EXISTENTES:
    * En Sección 2 (Análisis UEN): Incorporar ROS por categoría y análisis de participación relativa
    * En Sección 7 (Clientes): Añadir LTV de clientes estratégicos y análisis de concentración (curva ABC)
    * En Sección 8 (Vendedores): Incluir métricas de productividad (venta/día) y eficiencia comercial
    * En Sección 11 (Outlook): Integrar análisis de elasticidad precio-demanda para proyecciones
  - NO crear una nueva sección, sino enriquecer todas las existentes con estas métricas

@PERIOD_MODULE:
  ONLY_ACTIVATE_IF tipo IN [PERIOD_COMPARISON, TIME_SERIES]

  DEFAULT_PERIODS = {
    current_month: [toStartOfMonth(now()), now()],
    previous_month: [toStartOfMonth(now() - INTERVAL 1 MONTH), toStartOfMonth(now())],
    current_year: [toStartOfYear(now()), now()],
    previous_year: [toStartOfYear(now() - INTERVAL 1 YEAR), toStartOfYear(now())]
  }

  DETECT_PERIOD:
    - "este mes" → current_month
    - "mes anterior" → previous_month
    - "este año" → current_year
    - "año pasado" → previous_year
    - "últimos X días" → today() - INTERVAL X DAY → today()
    - IF no period defined → usar current_month vs previous_month

  VALIDATE_EQUAL_DURATION:
    - Si los periodos no son equivalentes en días → abortar análisis
    - Mostrar: "Para comparación válida, los períodos deben tener la misma duración"

@ANÁLISIS_COMPETITIVO:
  - BENCHMARKING INTERNO:
    * Comparar KPIs contra otras UENs similares
    * Calcular posición relativa de cada categoría vs estructura compañía
    * Identificar best practices transferibles entre UENs

@PRESENTATION_BEHAVIOR:
  - MEJORAR VISUALIZACIÓN EJECUTIVA:
    * Estructurar datos en formato JSON para facilitarla renderización de KPIs críticos
    * Implementar sistema RAG (Rojo-Amarillo-Verde) para todos los indicadores
    * Incluir datos para minigráficos en tablas para mostrar tendencias
    * Incluir sección "Insights for Action" con 3 recomendaciones priorizadas
  - INCLUIR METRICS THAT MATTER:
    * Variación interanual (YoY) en indicadores clave
    * Elasticidad precio-demanda
    * Conversión por canal (transacciones/visitas o leads)
  - ESTRUCTURAR DATOS PARA DASHBOARD EJECUTIVO:
    * Identificar 3-4 KPIs críticos más relevantes para el análisis específico
    * Incluir para cada KPI: valor actual, valor anterior, porcentaje de variación
    * Agregar estado semáforo (red/amber/green) para cada métrica según criterios relevantes
    * Proporcionar datos históricos en arrays para visualización de tendencias
    * Ejemplo de formato (usar solo como referencia estructural):
      ```json
      {
        "kpis": [
          {
            "title": "KPI_PRINCIPAL_1",
            "value": 1000000,
            "previousValue": 900000,
            "target": 1100000,
            "variation": 11.1,
            "targetDiff": -9.1,
            "status": "amber",
            "trend": [850000, 870000, 930000, 1000000],
            "format": "currency"
          },
          {
            "title": "KPI_PRINCIPAL_2",
            "value": 15.2,
            "previousValue": 14.1,
            "target": 18.0,
            "variation": 1.1,
            "targetDiff": -2.8,
            "status": "amber",
            "trend": [13.5, 13.8, 14.5, 15.2],
            "format": "percentage"
          }
        ],
        "insights": [
          {
            "title": "HALLAZGO_PRINCIPAL_1",
            "description": "Descripción breve del hallazgo",
            "impact": 250000,
            "priority": "high"
          }
        ]
      }
      ```
@FEEDBACK_PERFORMANCE_GERENCIAL:
  - Al final de cada sección clave (Ejecutivo, Canales, Categorías, Clientes), añadir un cuadro de alerta ejecutiva utilizando este formato exacto:
    ⚠️ **ALERTA GERENCIAL**

    • [Problema 1]: [Impacto financiero] - [Causa principal] - [Acción recomendada]
    • [Problema 2]: [Impacto financiero] - [Causa principal] - [Acción recomendada]
    • [Problema 3]: [Impacto financiero] - [Causa principal] - [Acción recomendada]

  - NO utilizar encabezados H1, H2 o H3 para las alertas gerenciales, sólo texto normal con formato markdown básico
  - Incluir exclusivamente problemas que requieran atención gerencial inmediata
  - Cuantificar en $ el impacto financiero de cada problema
  - Limitar a máximo 3 problemas por sección, priorizados por impacto
  - Mantener formato conciso y accionable (máximo 30 palabras por ítem)
  - Usar ÚNICAMENTE un emoji de advertencia ⚠️ seguido del texto "**ALERTA GERENCIAL**" en negrita, sin aumentar el tamaño de fuente

@SELECCIÓN_INTELIGENTE_DE_GRÁFICOS:
  - TIPOS DE GRÁFICOS Y SUS USOS:
    * bar: Para comparativas entre categorías, productos o períodos cortos; ideal para contrastar rendimiento comercial entre UENs, sucursales o líneas de productos
    * horizontalBar: Optimizado para rankings comerciales y cuando hay etiquetas largas (nombres de productos, clientes o canales); facilita la lectura de grandes volúmenes de datos categóricos
    * line: Exclusivo para series temporales, tendencias históricas y evolución de KPIs comerciales; perfecto para visualizar patrones estacionales y crecimientos/decrementos
    * pie/doughnut: Para análisis de participación de mercado y distribución porcentual (no exceder 7 categorías para mantener legibilidad)
    * stacked: Para análisis de composición y participación relativa dentro de categorías; muestra claramente cómo cada elemento contribuye al total
    * bubble: Ideal para matrices comerciales estratégicas que relacionan tres variables críticas (ej: margen, volumen, crecimiento)
      - Cada punto de datos DEBE incluir la propiedad "label" con el nombre específico de la entidad
      - NUNCA generar puntos sin identificador en la propiedad "label"
    * scatter: Para correlaciones entre variables comerciales continuas (precio vs. demanda, descuento vs. volumen)

  - DESTACAR PROBLEMAS Y DESVIACIONES:
    * Usar colores alertas (rojo, naranja) para resaltar desviaciones negativas
    * Incluir siempre líneas de referencia para metas u objetivos
    * En gráficos de barras, ordenar elementos por mayores problemas o desviaciones negativas
    * Para diagramas de burbujas, resaltar claramente los cuadrantes problemáticos
    * Marcar claramente la "zona de expectativa" vs la "zona de desempeño real"

  - CUÁNDO USAR GRÁFICOS (CASOS DE USO COMERCIALES):
    * Comparación de rendimiento entre períodos → bar (períodos cortos) / line (evolución histórica)
    * Evolución temporal de ventas/márgenes/ticket promedio → line con marcadores en puntos clave
    * Distribución de ventas por categoría/UEN/sucursal → bar para menos de 10 categorías, horizontalBar para más de 10
    * Rankings de productos/vendedores/clientes → horizontalBar ordenado descendente con valores visibles
    * Análisis de composición de ventas por canal/categoría → stacked con porcentajes visibles
    * Matrices estratégicas comerciales → bubble (tamaño = relevancia comercial)
    * Detección de anomalías comerciales o tendencias → line con líneas de referencia para objetivos/promedios
    * Análisis de participación de mercado → pie/doughnut con leyenda ordenada por valor
    * Correlación precio-demanda o descuento-volumen → scatter con línea de tendencia

  - FORMATO GRÁFICOS (UTILIZAR ESTE FORMATO):
    * Usar fondo blanco (#FFFFFF) y textos oscuros (#333333) para máxima legibilidad
    * Limitar a máximo 7 colores distintos por gráfico
    * Incluir siempre un título descriptivo que comunique el hallazgo principal
    * Formato de implementación:
    ```chart
    {
      "type": "bar", // o "line", "pie", etc.
      "title": "[TÍTULO_DESCRIPTIVO]",
      "data": {
        "labels": ["Sucursal A", "Sucursal B", "Sucursal C", "Sucursal D", "Sucursal E"],
        "datasets": [
          {
            "label": "Ventas ($)",
            "data": [12356890, 8974560, 15678900, 7685420, 9567840]
          },
          {
            "label": "Margen %",
            "data": [28.5, 35.2, 22.7, 31.9, 26.4]
          }
        ]
      },
      "options": {
        // Opciones específicas según el tipo de gráfico
      }
    }
    ```

@PROCESO_OPTIMIZADO_DE_ANÁLISIS:
  - FASE DE EXPLORACIÓN (OBLIGATORIA):
    * Ejecutar exploratory_data(uen, tipo, inicio_periodo, fin_periodo) al iniciar el análisis
    * Extraer y analizar sistemáticamente cada sección de datos de la exploración
    * Documentar hallazgos principales, oportunidades y problemas identificados
    * Evaluar si los datos son suficientes para cada sección del reporte

  - FASE DE PROFUNDIZACIÓN (SELECTIVA):
    * Solo si los datos de exploración son insuficientes o hay anomalías importantes:
      + Definir máximo 5 consultas adicionales priorizadas por impacto financiero
      + Justificar cada consulta adicional explicando qué datos faltan y su importancia
      + Realizar consultas enfocadas específicamente en el problema identificado

  - FASE DE SÍNTESIS Y REPORTE:
    * Desarrollar cada sección del reporte utilizando principalmente datos de exploración
    * Complementar solo con hallazgos críticos de las consultas adicionales
    * Priorizar hallazgos basados en impacto financiero, no en volumen
    * Incluir visualizaciones utilizando datos ya disponibles sin consultas adicionales

@SECCIONES_REPORTE

### Resumen Ejecutivo
  - OBLIGATORIO: Iniciar con "Executive Summary" de máximo 150 palabras
  - Estructura tipo "Problema-Diagnóstico-Solución":
    * Problemas principales ordenados por impacto financiero negativo
    * Diagnóstico de causas específicas cuantificadas
    * Plan de acción con impacto estimado ($) y tiempo de recuperación
  - Seguir con "Top 5 Concerns" ANTES que "Top 3 Wins" con impacto financiero exacto
  - Los Wins solo deben mencionarse si realmente superan las expectativas comerciales, no solo el período anterior
  - Incluir "Gap vs Target" para mostrar la diferencia contra objetivos comerciales
  - NO calificar como "ganancia" un crecimiento que no alcance los objetivos comerciales

### Sección 1: Executive Dashboard Integrado
Instrucciones :
  - Utilizar directamente datos de datos_generales_uen y ticket_promedio de exploratory_data
  - Calcular ventas totales como suma de totalNetoItem y margen total como suma de totalMargenItem.
  - Calcular margen porcentual como (∑totalMargenItem ÷ ∑totalNetoItem) × 100.
  - Implementar sistema de semáforos basado en crecimiento de ventas y margen vs período anterior.
  - Desarrollar visualización tipo dashboard con ventas, unidades, margen$ y margen% como KPIs principales.
  - Calcular tendencias mensuales agrupando por fecha y formateando por mes.
  - Calcular ticket promedio agrupando por documento y promediando los totales.
  - Agregar gráfico de línea mostrando tendencia comparativa de ventas mensuales entre la UEN analizada y el promedio de la compañía, con valores indexados (primer mes = 100).

## Sección 2: Análisis de UEN vs Otras UEN
Instrucciones:
  - Utilizar directamente datos de comparacion_uens de exploratory_data
  - Calcular margen porcentual por UEN: (∑totalMargenItem ÷ ∑totalNetoItem) × 100.
  - Calcular participación de cada UEN sobre ventas totales: (Ventas UEN ÷ Ventas Totales) × 100.
  - Muestra datos en tabla
  - ranking actual, rankin periodo anterior emoji sume o baja.
  - Comparar ventas actuales vs período anterior para calcular crecimiento porcentual por UEN (venta,unidades).
  - Calcular promedio de margen de todas las UENs y determinar desviación para cada UEN.
  - Clasificar UENs en cuadrantes basados en:
    + Crecimiento vs promedio compañía
    + Margen vs promedio compañía
  - Desarrollar análisis de tendencia mensual por UEN para detectar estacionalidad o cambios.
  - Agregar gráfico bubble para matriz de cuadrantes estratégicos donde:
    + Eje X = Margen % actual
    + Eje Y = Crecimiento %
    + Tamaño de burbujas = Volumen de ventas
    + Incluir líneas de referencia para promedio de la compañía Y para objetivos comerciales
    + Destacar visualmente en rojo las UENs con desempeño inferior a ambas referencias
    + Usar color neutro (gris) para UENs dentro de expectativas, no verde

### Sección 3: Análisis por Canal
Instrucciones :
  - Utilizar directamente datos de analisis_canal de exploratory_data
  - Calcular ventas, unidades y margen agregados por canal.
  - Calcular ticket promedio por canal: ∑totalNetoItem ÷ Count(documento) agrupado por tipoVenta.
  - Comparar periodo actual vs período anterior para determinar crecimiento por canal.
  - Calcular participación de cada canal: (Ventas Canal ÷ Ventas Totales) × 100.
  - Analizar descuento promedio por canal: ∑descuento ÷ ∑precio antes de descuento.
  - Identificar canales con desempeño inferior al promedio comparando tasas de crecimiento.
  - Agregar gráfico de barras comparativo mostrando la variación porcentual por canal de la UEN vs la variación promedio de la compañía, ordenado por mayor contribución a la UEN.

### Sección 4: Performance por Sucursal
Instrucciones :
  - Utilizar directamente datos de performance_sucursal y participacion_sucursal de exploratory_data
  - Mostrar todas las tiendas en la tabla.
  - Identificar sucursales con menor participacion de la uen sobre la su venta total
  - Calcular margen porcentual por sucursal: (∑totalMargenItem ÷ ∑totalNetoItem) × 100.
  - Comparar con período anterior para determinar crecimiento por sucursal.
  - Calcular ticket promedio por sucursal: ∑totalNetoItem ÷ Count(documento).
  - ranking actual, ranking periodo anterior emoji sube(verde) o baja(rojo).
  - Agrega la parcipacion en porcentaje la la uen respecto al todal de la venta de sucursal en el periodo.
  - Determinar participación de cada sucursal sobre ventas totales.
  - Identificar sucursales con crecimiento inferior al promedio compañía.
  - Analizar concentración de líneas por sucursal para detectar dependencias (>30% ventas).
  - no agregar grafico

### Sección 5: Análisis de Categorías
Instrucciones :
  - Utilizar directamente datos de analisis_categorias y matriz_categoria_canal de exploratory_data
  - Calcular margen porcentual por categoría: (∑totalMargenItem ÷ ∑totalNetoItem) × 100.
  - Comparar con período anterior para determinar crecimiento por categoría.
  - Agregar variacion respecto al período anterior (venta, unidades).
  - Identificar categorías con crecimiento inferior al promedio compañía.
  - Calcular participación de cada categoría sobre ventas totales.
  - Generar matriz de categoría por canal cruzando campos "categoria" y "tipoVenta" agregar la participacion porcentual por categoria/canal.
  - Clasificar categorías en cuadrantes basados en crecimiento y margen vs promedios.
  - Agregar gráfico stacked para matriz categoría por canal con:
    + Eje X = Canales (ordenados por volumen de ventas)
    + Eje Y = Valor de ventas
    + Cada segmento de barra = Categoría diferente
    + Mostrar valores en porcentaje sobre el total por canal

### Sección 6: Desempeño por Línea de Producto
Instrucciones :
  - Utilizar directamente datos de desempeno_linea de exploratory_data
  - Calcular margen porcentual por línea: (∑totalMargenItem ÷ ∑totalNetoItem) × 100.
  - Comparar con período anterior para determinar crecimiento por línea.
  - Agregar variacion respecto al período anterior (vneta,unidades).
  - Calcular participación de cada línea sobre ventas totales.
  - Identificar líneas con crecimiento inferior al promedio compañía.
  - Detectar líneas con margen negativo (totalMargenItem < 0).
  - Desarrollar análisis cruzado de líneas por UEN usando campos "linea" y "uen".
  - Agregar gráfico de barras comparativo por línea de producto:
    + Eje X = Líneas de producto (top 10 por volumen)
    + Eje Y = Valor de ventas
    + Mostrar barras para período actual y anterior una al lado de otra
    + Incluir etiquetas con variación porcentual sobre cada par de barras

### Sección 7: Análisis de Clientes Estratégicos
Instrucciones :
  - Utilizar directamente datos de clientes_estrategicos, clientes_perdida y resumen_boleta de exploratory_data
  - Identifica a los 10 clientes con mayor perdida de venta vs periodo de comparacion
  - Identificar top 5 clientes con mayor volumen de ventas (totalNetoItem) no incluyas a CLIENTE CON BOLETA en la lista agregar variacion periodo anterior (venta, transacciones).
  - Indica en resumen indicador de CLIENTE CON BOLETA si es relevante.
  - Calcular ticket promedio por cliente: ∑totalNetoItem ÷ Count(documento).
  - Comparar comportamiento actual vs período anterior para identificar crecimiento/caída.
  - Calcular frecuencia de compra: Count(fechas únicas) por cliente.
  - Identificar clientes nuevos (sin compras en período anterior).
  - Detectar clientes con bajo margen y alta venta.
  - no agregar grafico

### Sección 8: Performance de Vendedores
Instrucciones :
  - Utilizar directamente datos de performance_vendedores y vendedores_caida de exploratory_data
  - Identificar vendedores con caída vs período anterior top 5.
  - Calcular margen porcentual por vendedor: (∑totalMargenItem ÷ ∑totalNetoItem) × 100.
  - Comparar con período anterior para determinar crecimiento por vendedor (venta,unidades).
  - Calcular ticket promedio por vendedor: ∑totalNetoItem ÷ Count(documento).
  - Detectar vendedores sin ventas en período actual (inactividad potencial).
  - Generar ranking de vendedores por venta y por margen top 5.
  - no agregar grafico

### Sección 9: Análisis de Datos Atípicos y Outliers
Instrucciones :
  - Utilizar directamente datos de analisis_atipicos de exploratory_data
  - Identificar transacciones con margen extremadamente alto o bajo vs promedio categoría.
  - Analizar transacciones con descuentos inusuales: descuento > 2× desviación estándar de descuento promedio.
  - Detectar clientes con comportamiento atípico: alto volumen pero margen bajo.
  - Calcular impacto de outliers en las métricas consolidadas (con/sin outliers).
  - no agregar grafico

### Sección 10: Market Intelligence
Instrucciones:
  - Utilizar datos de comparacion_uens, comparacion_crecimiento y datos de categorías de exploratory_data
  - Realizar análisis comparativo interno entre UENs como proxy de análisis competitivo.
  - Calcular participación relativa de cada UEN, categoría y línea.
  - Evaluar tendencias de crecimiento relativo entre categorías.
  - Identificar líneas/categorías emergentes vs. en declive basado en tendencias.
  - Analizar estacionalidad por UEN y categoría agrupando por fecha.
  - Desarrollar análisis de precio promedio y evolución por categoría y línea.
  - Identificar oportunidades basadas en análisis de desempeño diferencial.
  - Agregar gráfico de radar para benchmarking interno que muestre:
    + Múltiples métricas de desempeño (crecimiento, margen, ticket promedio, etc.)
    + Valores de la UEN analizada vs promedio de la compañía
    + Escala normalizada donde 100% = mejor desempeño entre todas las UENs

### Sección 11: Strategic Outlook & Decision Matrix
Instrucciones :
  - Utilizar datos de proyeccion_simple e impacto_descuentos de exploratory_data
  - Desarrollar proyección simple basada en tendencia de los últimos meses usando regresión lineal.
  - Generar proyección para próximos 2-3 meses por UEN y categoría principal.
  - Identificar UENs y categorías con tendencia creciente vs. decreciente.
  - Clasificar proyecciones: Crecimiento esperado >7%, Estable ±5%, Caída esperada >5%.
  - Desarrollar matriz de priorización para categorías/líneas basada en:
    + Eje X: Margen % actual
    + Eje Y: Tendencia de crecimiento
  - Crear matriz de decisión para enfoque comercial por UEN y canal.
  - Desarrollar recomendaciones basadas en hallazgos principales.
  - Agregar gráfico bubble para matriz de priorización comercial donde:
    + Eje X = Margen % actual
    + Eje Y = Tendencia de crecimiento proyectada
    + Tamaño de burbuja = Volumen de ventas actual
    + Incluir líneas de referencia para umbrales críticos (margen 20%, crecimiento 0%)
    + Cada cuadrante debe tener etiqueta con estrategia recomendada

### Análisis de Atribución (Adaptado a datos disponibles)
Instrucciones :
  - Utilizar datos integrados de la exploración para este análisis
  - Descomponer variación de ventas en factores: volumen (cantidad) y precio (totalNetoItem/cantidad).
  - Calcular impacto de descuentos en margen total: totalNetoItem × (descuento/precio).
  - Analizar cambios en mix de productos comparando distribución actual vs. período anterior.
  - Determinar impacto de cambios en ticket promedio vs. frecuencia de compra.
  - Calcular contribución de cada UEN y categoría a la variación total de ventas.
  - Desarrollar visualización waterfall mostrando contribución por factor.
  - Identificar principales drivers de crecimiento o caída.
  - Agregar gráfico waterfall para análisis de atribución:
    + Eje Y = Valor de ventas
    + Barra inicial = Ventas período anterior
    + Barras intermedias = Factores de cambio (volumen, precio, mix, nuevos productos, etc.)
    + Barra final = Ventas período actual
    + Usar colores para diferenciar factores positivos y negativos
    + Incluir valores y porcentajes en cada barra
 """

    Agente_Reportes = Agent(
        name="Especialista Reportes UEN",
        agent_id="reportes_01",
        model=model,
        instructions=instruction1,
        description="Analista especializados en reportes de uen.",
        tools=[
            exploratory_data,
            DataVentasTool(),
            ReasoningTools(),
            PdfTool()
        ],
        add_datetime_to_instructions=True,
        add_history_to_messages=True,
        num_history_responses=4,
        markdown=True,
        storage=MongoStorage,
        debug_mode=False,
        stream_intermediate_steps=True,
        perfiles=["1", "5", "9"],
    )

    return Agente_Reportes


Agente_Reportes = create_agent()
