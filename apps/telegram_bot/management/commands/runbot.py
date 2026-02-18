import os
import logging
from datetime import time
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
from apps.telegram_bot.notifications_handler import (
    show_users_for_notifications,
    show_user_preferences,
    toggle_notification_setting,
)
from apps.telegram_bot.nursery_handler import diaper_conv_handler, restock_conv_handler
from apps.telegram_bot.lactation_handler import lactation_conv_handler
from apps.telegram_bot.health_handler import (
    show_health_menu,
    treatment_conv,
    appointment_conv,
    daily_appointment_check,
    handle_dose_action,
    results_conv,
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
        application.add_handler(diaper_conv_handler)
        application.add_handler(restock_conv_handler)
        application.add_handler(lactation_conv_handler)
        application.add_handler(profile_conv_handler)
        application.add_handler(config_conv_handler)
        application.add_handler(sizes_conv_handler)
        application.add_handler(treatment_conv)
        application.add_handler(appointment_conv)
        application.add_handler(results_conv)

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
        # Lista usuarios
        application.add_handler(
            CallbackQueryHandler(
                show_users_for_notifications, pattern="^config_notifications$"
            )
        )
        # Ver panel usuario
        application.add_handler(
            CallbackQueryHandler(show_user_preferences, pattern=r"^config_notif_user_")
        )
        # Switch ON/OFF
        application.add_handler(
            CallbackQueryHandler(toggle_notification_setting, pattern=r"^toggle_notif_")
        )
        application.add_handler(
            CallbackQueryHandler(show_health_menu, pattern="^menu_health$")
        )
        application.add_handler(
            CallbackQueryHandler(handle_dose_action, pattern=r"^DOSE_")
        )

        self.stdout.write(
            self.style.SUCCESS("🤖 BabyBot escuchando (Timeouts extendidos)...")
        )

        # Programar revisión de citas todos los días a las 8:00 AM hora local
        # time(8, 0) creará un objeto hora. El JobQueue usa la timezone del bot (definida en Defaults o system)
        # Como definimos TIME_ZONE en settings pero no pasamos defaults al JobQueue,
        # es mejor pasar la hora directa.

        job_queue = application.job_queue
        # job_queue.run_daily(
        #     daily_appointment_check, time=time(hour=12, minute=0, second=0)
        # )
        job_queue.run_once(daily_appointment_check, when=30)
        self.stdout.write(
            self.style.SUCCESS(
                "⏰ Tarea de prueba programada para ejecutarse en 30s..."
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                "🤖 BabyBot escuchando... (Alertas de Citas programadas 8:00 AM VET)"
            )
        )

        # Iniciar loop
        # allowed_updates=Update.ALL_TYPES asegura que reciba todo
        application.run_polling(poll_interval=1.0)

        async def error_handler(self, update, context):
            """Captura errores silenciosos y los manda al log"""
            logger.error(msg="Excepción en el bot:", exc_info=context.error)
            print(f"🔴 Error capturado: {context.error}")
