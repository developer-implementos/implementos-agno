from pydantic import BaseModel


class UsuarioAX(BaseModel):
    codUsuario: int
    codEmpleado: int
    usuario: str
    nombre: str
    codSucursal: str
    rut: str
    codBodega: str
    codPerfil: int
    nombreSucursal: str
    email: str
    movil: str
    bodegas: list[str]
    vendedorRecid: int

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }
