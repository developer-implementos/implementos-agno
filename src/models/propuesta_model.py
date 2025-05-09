from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime


class PropuestasClientesRequest(BaseModel):
    """Equivalente a la interfaz PropuestasClientesRequest"""
    rut: str
    page: int
    limit: int
    sort: str  # folio|-1

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class ObtenerProductosPropuestaRequest(BaseModel):
    """Equivalente a la interfaz ObtenerProductosPropuestaRequest"""
    rut: str
    sucursal: str
    limite: int
    uensOptions: str  # BATERIAS,AGROINSUMOS
    originOptions: str  # RECOMMENDED,STOPPED_PURCHASING,VEHICLE_FLEET
    marcaFlota: str
    modeloFlota: str
    tipoFlota: str
    additionalOptions: str  # INCLUDE_MATRIX

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class Image(BaseModel):
    """Equivalente a la interfaz Image"""
    img_150: List[str] = Field(alias="150")
    img_250: List[str] = Field(alias="250")
    img_450: List[str] = Field(alias="450")
    img_600: List[str] = Field(alias="600")
    img_1000: List[str] = Field(alias="1000")
    img_2000: List[str] = Field(alias="2000")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class Atributo(BaseModel):
    """Equivalente a la interfaz Atributo"""
    nombre: str
    valor: str

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class Filtro(BaseModel):
    """Equivalente a la interfaz Filtro"""
    nombre: str
    valor: str
    orden: int

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class Matriz(BaseModel):
    """Equivalente a la interfaz Matriz"""
    sku: str

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class Stock(BaseModel):
    """Equivalente a la interfaz Stock"""
    cantidad: int
    id: str
    tienda: str

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class Precio(BaseModel):
    """Equivalente a la interfaz Precio"""
    precio: float
    precioComun: float
    precioEscala: float
    precioCliente: Optional[float] = None  # Modificado: ahora es opcional

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class ArticuloFull(BaseModel):
    """Equivalente a la interfaz ArticuloFull"""
    _id: str
    sku: str
    categoria: str
    estado: str
    fabricante: str
    linea: str
    marca: str
    nombre: str
    numero_parte: str
    uen: str
    descripcion: str
    visible: int
    images: List[Image]
    cyberMonday: int
    calidad: int
    estadoPuntaje: int
    popularidad: Optional[int] = None
    peso: float
    atributos: List[Atributo]
    filtros: List[Filtro] = Field(default_factory=list)  # Modificado: ahora tiene valor por defecto
    matriz: List[Matriz]
    lineSlug: str
    precio: Precio
    stock: List[Stock]
    stockTienda: int
    stockCD1: int
    stockCD5: int
    stockVentaVerde: int
    origenPropuesta: str
    cyber: Optional[int] = None
    assortment: Optional[int] = None

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class ProductoPropuestaItem(BaseModel):
    """Equivalente a la interfaz ProductoPropuestaItem"""
    uen: str
    articulos: List[ArticuloFull]

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class ObtenerProductosPropuestaResponse(BaseModel):
    """Equivalente a la interfaz ObtenerProductosPropuestaResponse"""
    error: bool
    msg: str
    data: List[ProductoPropuestaItem]
    cantidad: int
    cantidadMatriz: int
    segmento: Optional[str] = None

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class Sucursal(BaseModel):
    """Equivalente a la interfaz Sucursal"""
    codigo: str
    nombre: str

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class Cliente(BaseModel):
    """Equivalente a la interfaz Cliente"""
    rut: str
    nombre: str

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class Vendedor(BaseModel):
    """Equivalente a la interfaz Vendedor"""
    rut: str
    nombre: str
    codUsuario: int
    codEmpleado: int
    cuenta: str
    email: str

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class Articulo(BaseModel):
    """Equivalente a la interfaz Articulo"""
    precio: Precio
    estado: str
    nombre: str
    sku: str
    cantidad: int
    origenPropuesta: str

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class Log(BaseModel):
    """Equivalente a la interfaz Log"""
    _id: str
    comentario: str
    fecha: str
    usuario: str

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class GeneraPropuestaRequest(BaseModel):
    """Equivalente a la interfaz GeneraPropuestaRequest"""
    tipo: str
    tipoEntrega: str
    sucursal: Sucursal
    cliente: Cliente
    vendedor: Vendedor
    articulos: List[Articulo]

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class GenerarCatalogoPropuestaRequest(BaseModel):
    """Equivalente a la interfaz GenerarCatalogoPropuestaRequest"""
    folio: int

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class GenerarCatalogoPropuestaItem(BaseModel):
    """Equivalente a la interfaz GenerarCatalogoPropuestaItem"""
    url: str
    urlPortada: str

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class GenerarCatalogoPropuestaResponse(BaseModel):
    """Equivalente a la interfaz GenerarCatalogoPropuestaResponse"""
    error: bool
    msg: str
    data: Optional[GenerarCatalogoPropuestaItem] = None

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class PropuestaCliente(BaseModel):
    """Equivalente a la interfaz PropuestaCliente"""
    sucursal: Sucursal
    cliente: Cliente
    vendedor: Vendedor
    estado: str
    tipoEntrega: str
    _id: str
    folio: int
    tipo: str
    articulos: List[Articulo]
    valorTotal: float
    logs: List[Log]
    eliminados: List[Any]
    createdAt: str
    updatedAt: str
    __v: int

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class PropuestasClientesResponse(BaseModel):
    """Equivalente a la interfaz PropuestasClientesResponse"""
    error: bool
    msg: str
    total: int
    found: int
    page: int
    firstPage: int
    lastPage: int
    data: List[PropuestaCliente]

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class ObtenerPropuestaClienteRequest(BaseModel):
    """Equivalente a la interfaz ObtenerPropuestaClienteRequest"""
    folio: int

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class PropuestaClienteResponse(BaseModel):
    """Equivalente a la interfaz PropuestaClienteResponse"""
    error: bool
    msg: str
    data: PropuestaCliente

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }
