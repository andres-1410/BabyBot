import logging
import csv
import io
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from asgiref.sync import sync_to_async
from django.utils import timezone

from apps.users.models import TelegramUser
from apps.profiles.models import Profile
from apps.nursery.models import DiaperLog

logger = logging.getLogger("apps.telegram_bot")

# Estados
WAITING_FOR_CSV = range(1)


# --- COMANDO DE INICIO ---
async def start_import_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Punto de entrada: /carga_masiva_panales
    Solo permite acceso al OWNER.
    """
    user = update.effective_user

    # 1. Verificación de Seguridad (Solo Owner)
    is_owner = await sync_to_async(
        TelegramUser.objects.filter(
            telegram_id=user.id, role=TelegramUser.Role.OWNER
        ).exists
    )()

    if not is_owner:
        await update.message.reply_text(
            "⛔ **Acceso Denegado:** Comando exclusivo para el Propietario."
        )
        return ConversationHandler.END

    # 2. Ofrecer Plantilla
    keyboard = [
        [
            InlineKeyboardButton(
                "📄 Descargar Plantilla CSV", callback_data="GET_TEMPLATE"
            )
        ],
        [InlineKeyboardButton("🚫 Cancelar", callback_data="CANCEL_IMPORT")],
    ]

    await update.message.reply_text(
        "📂 **Carga Masiva de Pañales**\n\n"
        "Este modo te permite subir un historial antiguo mediante un archivo CSV.\n\n"
        "1. Descarga la plantilla.\n"
        "2. Llénala con tus datos (Excel -> Guardar como CSV).\n"
        "3. **Envíame el archivo aquí.**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return WAITING_FOR_CSV


# --- DESCARGA DE PLANTILLA ---
async def send_csv_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera y envía un CSV de ejemplo en memoria"""
    query = update.callback_query
    await query.answer()

    # Creamos el CSV en memoria RAM
    output = io.StringIO()
    writer = csv.writer(output)
    # Encabezados
    writer.writerow(["perfil", "fecha", "hora", "talla", "tipo", "notas"])
    # Datos de ejemplo
    writer.writerow(["Ignacio", "03/02/2026", "14:30", "RN", "PEE", "Carga Inicial"])
    writer.writerow(["Ignacio", "03/02/2026", "18:00", "RN", "POO", ""])
    writer.writerow(["Ignacio", "03/02/2026", "18:00", "RN", "BOTH", ""])

    output.seek(0)
    # Convertimos a bytes para Telegram
    bytes_file = io.BytesIO(output.getvalue().encode("utf-8"))
    bytes_file.name = "plantilla_babybot.csv"

    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=bytes_file,
        caption="📄 Aquí tienes la plantilla. Llénala y envíame el archivo de vuelta.",
    )
    return WAITING_FOR_CSV


# --- PROCESAMIENTO DEL ARCHIVO ---
async def process_csv_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el archivo, lo lee y guarda en BD"""
    document = update.message.document

    # Validar extensión
    if not document.file_name.lower().endswith(".csv"):
        await update.message.reply_text("⚠️ Por favor envía un archivo **.csv**.")
        return WAITING_FOR_CSV

    status_msg = await update.message.reply_text("⏳ **Procesando archivo...**")

    try:
        # Descargar archivo a memoria
        file = await document.get_file()
        byte_array = await file.download_as_bytearray()

        # Decodificar
        content = byte_array.decode("utf-8")
        csv_file = io.StringIO(content)
        reader = csv.DictReader(csv_file)

        # Preparar datos auxiliares (Owner)
        owner = await sync_to_async(TelegramUser.objects.get)(
            telegram_id=update.effective_user.id
        )

        success_count = 0
        error_count = 0
        errors = []

        # Iterar filas
        for i, row in enumerate(reader, start=1):
            try:
                # 1. Buscar Perfil (Ignacio)
                profile_name = row.get("perfil", "").strip()
                profile = await sync_to_async(
                    lambda: Profile.objects.filter(name__iexact=profile_name).first()
                )()

                if not profile:
                    raise ValueError(f"Perfil '{profile_name}' no encontrado.")

                # 2. Parsear Fecha y Hora
                date_str = row.get("fecha", "").strip()
                time_str = row.get("hora", "").strip()
                dt_str = f"{date_str} {time_str}"

                dt_naive = datetime.strptime(dt_str, "%d/%m/%Y %H:%M")
                dt_aware = timezone.make_aware(
                    dt_naive, timezone.get_current_timezone()
                )

                # 3. Validar Tipos
                waste_map = {
                    "PEE": "PEE",
                    "POO": "POO",
                    "BOTH": "BOTH",
                    "PIPI": "PEE",
                    "PUPU": "POO",
                    "AMBOS": "BOTH",
                }
                waste_type = waste_map.get(row.get("tipo", "").upper(), "PEE")

                size_label = row.get("talla", "").upper()
                notes = row.get("notas", "")

                # 4. Crear Registro
                await sync_to_async(DiaperLog.objects.create)(
                    profile=profile,
                    reporter=owner,  # Se asigna al Owner como responsable del histórico
                    time=dt_aware,
                    waste_type=waste_type,
                    size_label=size_label,
                    notes=f"{notes} [Importado]",
                )
                success_count += 1

            except Exception as e:
                error_count += 1
                errors.append(f"Fila {i}: {str(e)}")

        # Reporte Final
        report = (
            f"✅ **Importación Finalizada**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📥 Procesados: {success_count}\n"
            f"⚠️ Errores: {error_count}\n"
        )

        if errors:
            # Mostrar primeros 3 errores si los hay
            report += "\n**Detalle de Errores (Primeros 3):**\n" + "\n".join(errors[:3])

        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=status_msg.message_id,
            text=report,
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"Error importando CSV: {e}")
        await update.message.reply_text(
            "❌ Ocurrió un error crítico leyendo el archivo. Revisa el formato."
        )

    return ConversationHandler.END


async def cancel_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🚫 Importación cancelada.")
    return ConversationHandler.END


# --- DEFINICIÓN HANDLER ---
import_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("carga_masiva_panales", start_import_command)],
    states={
        WAITING_FOR_CSV: [
            MessageHandler(filters.Document.FileExtension("csv"), process_csv_upload),
            CallbackQueryHandler(send_csv_template, pattern="^GET_TEMPLATE$"),
            CallbackQueryHandler(cancel_import, pattern="^CANCEL_IMPORT$"),
        ]
    },
    fallbacks=[CommandHandler("cancel", cancel_import)],
)
