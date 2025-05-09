from etl.etl_log import log_message
from etl.qdrant_etl_canales_venta import etl_carga_canales_venta
from etl.qdrant_etl_clientes import etl_carga_clientes
from etl.qdrant_etl_sucursales import etl_carga_sucursales


def etl_qdrant_carga():
    log_message("inicio etl qdrant carga")
    # etl_carga_sucursales()
    # etl_carga_canales_venta()
    # etl_carga_clientes()
    log_message("fin etl qdrant carga")

etl_qdrant_carga()
