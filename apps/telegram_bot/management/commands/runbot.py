import os
import logging
from django.core.management.base import BaseCommand
from telegram.ext import ApplicationBuilder, Defaults
from telegram.constants import ParseMode

# Importamos el handler que acabamos de crear
from apps.telegram_bot.onboarding import onboarding_handler
from apps.telegram_bot.admin_handler import admin_approval_handler, rejection_handler

logger = logging.getLogger("django")


class Command(BaseCommand):
    help = "Ejecuta BabyBot (Polling)"

    def handle(self, *args, **options):
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            self.stdout.write(
                self.style.ERROR("Error: TELEGRAM_TOKEN no encontrado en .env")
            )
            return

        #   --- CORRECCIÓN TÉCNICA PARA VENEZUELA/LATENCIA ---
        # Aumentamos los tiempos de espera a 30 segundos para evitar el ReadTimeout
        application = (
            ApplicationBuilder()
            .token(token)
            .read_timeout(30)
            .write_timeout(30)
            .connect_timeout(30)
            .pool_timeout(30)
            .build()
        )

        # REGISTRO DE HANDLERS (Orden Importante)

        # 1. Admin Approval (Tiene prioridad alta porque captura callbacks específicos)
        application.add_handler(admin_approval_handler)
        application.add_handler(rejection_handler)

        # Registrar el manejador de Onboarding (Módulo 1)
        application.add_handler(onboarding_handler)

        self.stdout.write(
            self.style.SUCCESS("🤖 BabyBot escuchando (Timeouts extendidos)...")
        )

        # Iniciar loop
        # allowed_updates=Update.ALL_TYPES asegura que reciba todo
        application.run_polling(poll_interval=1.0)

        async def error_handler(self, update, context):
            """Captura errores silenciosos y los manda al log"""
            logger.error(msg="Excepción en el bot:", exc_info=context.error)
            print(f"🔴 Error capturado: {context.error}")
