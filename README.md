# 📘 Bono Nutrición – Expediente API (MIS)

Backend del **Sistema MIS – Bono Nutrición** para la gestión de **Expedientes Electrónicos**, cargas masivas **SESAN**, validación, normalización de datos y control documental.

El sistema sigue una **Arquitectura de Despliegue Híbrida**:

- **Aplicación:** Contenerizada (Docker) para garantizar consistencia entre entornos.
- **Datos:** Persistencia en Infraestructura Institucional (Base de Datos PostgreSQL MIDES).

---

## 🧱 Estructura del Proyecto

```text
bono-nutricion-expediente-api/
├── app/               # Código fuente del Backend (FastAPI)
├── .env.example       # Plantilla de variables de entorno (¡Vital para despliegue!)
├── Dockerfile         # Definición de la imagen (Python 3.11 Slim Bookworm)
├── docker-compose.yml # Orquestación del servicio API
├── README.md
└── requirements.txt




## 🧱 Arquitectura General

```

bono-nutricion-expediente-api/
├── app/
│ ├── core/ # Configuración, DB, settings
│ ├── models/ # Modelos SQLAlchemy
│ ├── schemas/ # Schemas Pydantic
│ ├── routers/ # Endpoints (expedientes, sesan, etc.)
│ └── main.py # Entrada FastAPI
├── .venv/ # Entorno virtual (NO se sube)
├── .gitignore
├── README.md
└── requirements.txt

````

---

## 🚀 Tecnologías

- Lenguaje: Python 3.11
- Framework: FastAPI
- Base de Datos: PostgreSQL (Conexión externa)
- Driver: psycopg v3 + SQLAlchemy 2.x
- Infraestructura: Docker & Docker Compose
- Servidor: Uvicorn

---

## ⚙️ Requisitos de Infraestructura
Para el despliegue en servidores MIDES, se requiere:

- Docker Engine y Docker Compose instalados.
- Conectividad de Red: El servidor Docker debe tener acceso (salida) a la IP y Puerto del servidor de Base de Datos.
- Base de datos creada (ej. `mis_bono_nutricion`)
- Credenciales: Usuario y contraseña de base de datos autorizados.

---

## 🔧 Instalación (Local)

### 1️⃣ Clonar el repositorio

```bash
git clone https://github.com/<org-o-usuario>/bono-nutricion-expediente-api.git
cd bono-nutricion-expediente-api
````

---

🐳 Despliegue con Docker (Método Principal)
Siga estos pasos para levantar el servicio en el entorno de servidor (QA/Producción).

1️⃣ Configuración de Variables (.env)
El repositorio incluye un archivo .env.example. Genere el archivo de configuración real:

cp .env.example .env

✅ USE la IP REAL del servidor de base de datos (ej. 192.168.X.X o 145.32.X.X).

# Ejemplo en .env:

DATABASE_URL=postgresql+psycopg://usuario_mides:password_seguro@145.xx.xx.230:5433/MIS

2️⃣ Levantar el Servicio
Ejecute el siguiente comando para compilar la imagen y levantar el contenedor en segundo plano:

docker compose up --build -d

3️⃣ Comandos de Gestión y Monitoreo
Verificar estado:

docker ps

Ver logs en tiempo real (Auditoría):

docker logs -f mis_bono_api

## 📖 Documentación

Una vez iniciado el servicio, la documentación interactiva está disponible en:

- Swagger UI: http://SERVER_IP:8000/docs

- ReDoc: http://SERVER_IP:8000/redoc

Endpoints de Verificación:

- GET /docs (Estado del servidor web - Código 200)

- GET /health (Si está implementado - Health Check)

- GET /catalogos/departamentos (Prueba de conexión a Base de Datos)

---

## 🧩 Funcionalidades

- Expediente electrónico (Ciclo de vida completo).

- Carga masiva SESAN (Procesamiento Excel validado).

- Validaciones de negocio y auditoría.

- Integración nativa con Frontend y BPM.

---

## 📌 Proyecto

Sistema **MIS – Bono Nutrición (MIDES / CESAN)**  
Uso institucional.
