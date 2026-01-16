# 📘 Bono Nutrición – Expediente API (MIS)

Backend del **Sistema MIS – Bono Nutrición** para la gestión de **Expedientes Electrónicos**, cargas masivas **SESAN**, validación, normalización de datos y control documental.

Desarrollado con **FastAPI + SQLAlchemy + PostgreSQL**, siguiendo una arquitectura modular y reutilizable para integración con frontend y BPM.

---

## 🧱 Arquitectura General

```
bono-nutricion-expediente-api/
├── app/
│   ├── core/          # Configuración, DB, settings
│   ├── models/        # Modelos SQLAlchemy
│   ├── schemas/       # Schemas Pydantic
│   ├── routers/       # Endpoints (expedientes, sesan, etc.)
│   └── main.py        # Entrada FastAPI
├── .venv/             # Entorno virtual (NO se sube)
├── .gitignore
├── README.md
└── requirements.txt
```

---

## 🚀 Tecnologías

- Python 3.10+
- FastAPI
- SQLAlchemy 2.x
- PostgreSQL
- psycopg v3
- Pydantic v2
- openpyxl (procesamiento Excel SESAN)
- Uvicorn

---

## ⚙️ Requisitos Previos

- Python instalado y agregado al PATH
- PostgreSQL activo
- Base de datos creada (ej. `mis_bono_nutricion`)
- Git

---

## 🔧 Instalación (Local)

### 1️⃣ Clonar el repositorio

```bash
git clone https://github.com/<org-o-usuario>/bono-nutricion-expediente-api.git
cd bono-nutricion-expediente-api
```

---

### 2️⃣ Crear entorno virtual

**Windows (CMD / PowerShell):**
```cmd
python -m venv .venv
.venv\Scripts\activate
```

**Linux / Mac:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

### 3️⃣ Instalar dependencias

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

### 4️⃣ Variables de entorno

Crear un archivo `.env` en la raíz del proyecto:

```env
DATABASE_URL=postgresql+psycopg://usuario:password@localhost:5432/mis_bono_nutricion
```

⚠️ El archivo `.env` **NO debe subirse** al repositorio.

---

### 5️⃣ Ejecutar la API

```bash
uvicorn app.main:app --reload
```

---

## 📖 Documentación

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

---

## 🧩 Funcionalidades

- Expediente electrónico
- Info general 1:1
- Documentos y anexos
- Carga masiva SESAN
- Procesamiento por batch y por fila
- Validaciones y auditoría
- Base para integración BPM

---

## 📌 Proyecto

Sistema **MIS – Bono Nutrición (MIDES / CESAN)**  
Uso institucional.
