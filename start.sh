#!/usr/bin/env bash
# Si falla algo, detener todo
set -o errexit

# 1. Aplicar migraciones (por seguridad, cada vez que arranque)
python manage.py migrate

# 2. Arrancar el Bot en SEGUNDO PLANO (fíjate en el '&' al final)
# Esto permite que el script siga ejecutándose hacia abajo sin bloquearse aquí
echo "🤖 Iniciando BabyBot..."
python manage.py runbot &

# 3. Arrancar el Servidor Web (Django Admin) en PRIMER PLANO
# Esto es lo que mantiene a Render feliz escuchando el puerto HTTP
echo "🌍 Iniciando Servidor Web..."
gunicorn config.wsgi:application
