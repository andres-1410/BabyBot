# 👶 BabyBot - Sistema de Gestión Familiar (ERP)

BabyBot es un sistema integral de gestión familiar diseñado bajo el patrón de arquitectura **SRP (Single Responsibility Principle)** usando **Django** y la API de **Telegram**. Permite llevar un registro detallado y colaborativo del cuidado del bebé y la salud familiar.

## 🚀 Características Principales (Fase 1)

El sistema opera mediante una interfaz de Chatbot en Telegram con persistencia en base de datos SQL.

### 🏛️ Módulos del Sistema

1.  **Users & Onboarding:** Gestión de roles (Owner/Admin), control de acceso y asignación de apodos familiares (ej. "Papá", "Mamá").
2.  **Profiles:** Gestión de múltiples perfiles (Bebés y Adultos).
3.  **Core Config:** Configuración dinámica de intervalos de lactancia, umbrales de alerta de stock y tallas de pañales.
4.  **Nursery (Pañales):** Registro de cambios, control de inventario en tiempo real y alertas de stock bajo. Soporte para zonas horarias.
5.  **Lactancia:** Cronómetro de tomas, registro manual y cálculo automático de la próxima toma.
6.  **Health (Salud):** * Gestión de Tratamientos con cálculo de dosis.
    * **Alertas Globales (Broadcast):** Notificaciones de seguridad a todos los cuidadores para evitar sobredosis.
    * Agenda de Citas Médicas con recordatorios (1 semana, 1 día, hoy).
    * Registro de resultados de control (Peso, Talla, Cefálico).
7.  **Reports:** Resúmenes diarios inteligentes y proyección de eventos ("¿Qué sigue?") adaptados según el perfil (Bebé vs. Adulto).

## 🛠️ Tecnologías

* **Python 3.9+**
* **Django 4.x:** ORM, Gestión de Modelos y Señales.
* **Python-Telegram-Bot:** Manejo de handlers, JobQueue y Async/Await.
* **PostgreSQL / SQLite:** Base de datos relacional.
* **Asgiref:** Puente entre Django síncrono y Telegram asíncrono.

## 📦 Instalación y Despliegue Local

1.  **Clonar el repositorio:**
    ```bash
    git clone [https://github.com/tu-usuario/babybot.git](https://github.com/tu-usuario/babybot.git)
    cd babybot
    ```

2.  **Crear entorno virtual:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Instalar dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configurar Variables de Entorno (.env):**
    Crea un archivo `.env` en la raíz:
    ```env
    TELEGRAM_TOKEN=tu_token_aqui
    SECRET_KEY=tu_django_secret
    DEBUG=True
    ALLOWED_HOSTS=*
    TIME_ZONE=America/Caracas
    ```

5.  **Migrar Base de Datos:**
    ```bash
    python manage.py migrate
    ```

6.  **Ejecutar el Bot:**
    ```bash
    python manage.py runbot
    ```

## 🛡️ Arquitectura y Seguridad

* **Zero-Inference:** No se asumen datos, todo se valida contra la BD.
* **Timezone Aware:** Manejo estricto de zonas horarias (VET) para registros históricos precisos.
* **JobQueue Persistence:** Las alertas se recalculan dinámicamente para asegurar consistencia.

---
*Desarrollado como proyecto personal de gestión familiar.*