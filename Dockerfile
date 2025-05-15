# Primera etapa: construcción
FROM python:3.13.3-slim-bullseye AS builder

WORKDIR /app

# Instalar solo las dependencias necesarias para compilar
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copiar solo los archivos necesarios para la instalación
COPY requirements.txt .
COPY libs/ ./libs/

# Crear un entorno virtual y preparar los paquetes
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Crear versión modificada de requirements.txt sin pywin32
RUN grep -v "pywin32" requirements.txt > requirements.linux.txt

# Instalar dependencias
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.linux.txt && \
    find /opt/venv -name "*.pyc" -delete && \
    find /opt/venv -name "__pycache__" -delete

# Segunda etapa: imagen final
FROM python:3.13.3-slim-bullseye

WORKDIR /app

# Copiar el entorno virtual desde la etapa de construcción
COPY --from=builder /opt/venv /opt/venv

# Hacer que el entorno virtual sea accesible
ENV PATH="/opt/venv/bin:$PATH"

# Copiar resto de archivos de la aplicación
COPY . /app/

# Exponer puerto
EXPOSE 7777

# Comando para iniciar la API
CMD ["python", "playground.py"]