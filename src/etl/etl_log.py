from datetime import datetime

def log_message(mensaje: str):
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{fecha_actual}]: " + mensaje)
