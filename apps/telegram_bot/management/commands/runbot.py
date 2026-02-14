import os
import logging
from django.core.management.base import BaseCommand
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler
from telegram.constants import ParseMode

# Importamos el handler que acabamos de crear
from apps.telegram_bot.onboarding import onboarding_handler
from apps.telegram_bot.admin_handler import admin_approval_handler, rejection_handler
from apps.telegram_bot.profile_handler import (
    profile_conv_handler,
    show_config_menu,
    show_profiles_menu,
    show_main_menu,  # Importante para el comando /menu
)
from apps.telegram_bot.config_handler import show_global_config, config_conv_handler
from apps.telegram_bot.sizes_handler import (
    show_sizes_menu,
    toggle_size_status,
    sizes_conv_handler,
)

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

        # 1. Admin Approval (Prioridad Alta)
        application.add_handler(admin_approval_handler)
        application.add_handler(rejection_handler)

        # 2. Perfiles (Prioridad Alta - Conversation)
        application.add_handler(profile_conv_handler)

        application.add_handler(config_conv_handler)
        application.add_handler(sizes_conv_handler)

        # 3. Onboarding
        application.add_handler(onboarding_handler)

        # 4. Navegación General (Prioridad Baja)
        application.add_handler(CommandHandler("menu", show_main_menu))
        application.add_handler(
            CallbackQueryHandler(show_main_menu, pattern="^main_menu$")
        )
        application.add_handler(
            CallbackQueryHandler(show_config_menu, pattern="^menu_config$")
        )
        application.add_handler(
            CallbackQueryHandler(show_profiles_menu, pattern="^config_profiles$")
        )
        application.add_handler(
            CallbackQueryHandler(show_global_config, pattern="^config_globals$")
        )
        # Entrar al menú tallas
        application.add_handler(
            CallbackQueryHandler(show_sizes_menu, pattern="^manage_sizes$")
        )
        # Activar/Desactivar
        application.add_handler(
            CallbackQueryHandler(toggle_size_status, pattern=r"^toggle_size_")
        )

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
