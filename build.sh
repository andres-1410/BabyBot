#!/usr/bin/env bash
# Salir si ocurre un error
set -o errexit

# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Recopilar archivos estáticos (Necesario en Django para el panel de Admin)
python manage.py collectstatic --no-input

# 3. Aplicar las migraciones a la base de datos PostgreSQL de Render
python manage.py migrate

# NUEVO: Crear superusuario automáticamente si no existe
echo "Verificando/Creando Superusuario..."
python manage.py createsuperuser --noinput || true