from datetime import timedelta
from django.utils import timezone
from asgiref.sync import sync_to_async
from apps.nursery.models import DiaperLog, DiaperInventory
from apps.core_config.models import DiaperSize
from apps.core_config.utils import (
    get_setting,
    KEY_DIAPER_THRESHOLD,
    DEFAULT_DIAPER_THRESHOLD,
)
from apps.profiles.models import Profile
from apps.nursery.models import FeedingLog
from apps.core_config.utils import (
    get_setting,
    KEY_LACTATION_INTERVAL,
    DEFAULT_LACTATION_INTERVAL,
)


async def registrar_uso_panal(
    profile_id, size_label, waste_type, reporter_user, timestamp=None
):
    """
    1. Crea el Log.
    2. Descuenta Inventario.
    3. Retorna (Log, Alerta_Stock_Bajo?)
    """
    if not timestamp:
        timestamp = timezone.now()

    # 1. Obtener Perfil y Talla
    profile = await sync_to_async(Profile.objects.get)(id=profile_id)
    # Buscamos la talla por etiqueta (ej "RN")
    size_obj = await sync_to_async(DiaperSize.objects.get)(label=size_label)

    # 2. Crear Log
    log = await sync_to_async(DiaperLog.objects.create)(
        profile=profile,
        reporter=reporter_user,
        time=timestamp,
        waste_type=waste_type,
        size_label=size_label,
    )

    # 3. Descontar Inventario
    # Buscamos o creamos el inventario para esa talla
    inventory, created = await sync_to_async(DiaperInventory.objects.get_or_create)(
        size=size_obj, defaults={"quantity": 0}
    )

    if inventory.quantity > 0:
        inventory.quantity -= 1
        await sync_to_async(inventory.save)()

    current_stock = inventory.quantity

    # 4. Verificar Umbral
    threshold_str = await get_setting(KEY_DIAPER_THRESHOLD, DEFAULT_DIAPER_THRESHOLD)
    threshold = int(threshold_str)

    trigger_alert = False
    if current_stock <= threshold:
        trigger_alert = True

    return log, current_stock, trigger_alert


async def registrar_lactancia(
    profile_id, start_time, end_time, reporter_user, observation=""
):
    """
    1. Guarda el registro.
    2. Calcula la próxima toma sumando el intervalo global a la hora de FIN.
    """
    profile = await sync_to_async(Profile.objects.get)(id=profile_id)

    # 1. Guardar Log
    log = await sync_to_async(FeedingLog.objects.create)(
        profile=profile,
        reporter=reporter_user,
        start_time=start_time,
        end_time=end_time,
        observation=observation,
    )

    # 2. Calcular Próxima Toma
    # Obtenemos el intervalo (String "3.0" -> Float 3.0)
    interval_str = await get_setting(KEY_LACTATION_INTERVAL, DEFAULT_LACTATION_INTERVAL)
    interval_hours = float(interval_str)

    # La próxima toma se calcula desde que TERMINÓ de comer
    next_feeding_time = end_time + timedelta(hours=interval_hours)

    return log, next_feeding_time
