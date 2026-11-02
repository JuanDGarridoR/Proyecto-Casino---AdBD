from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import AsignacionMesa, Turno


def asignacion_vigente(mesa, momento=None):
    """Asignación (crupier + supervisor) de la mesa en el turno que está corriendo ahora."""
    momento = timezone.localtime(momento or timezone.now())
    return (AsignacionMesa.objects
            .select_related('turno', 'crupier__persona', 'supervisor__persona', 'mesa__juego')
            .filter(mesa=mesa, turno__fecha=momento.date(),
                    turno__hora_inicio__lte=momento.time(), turno__hora_fin__gt=momento.time())
            .first())


def asignaciones_del_dia(*, crupier=None, supervisor=None, fecha=None):
    fecha = fecha or timezone.localdate()
    qs = AsignacionMesa.objects.select_related('turno', 'mesa__juego', 'crupier__persona', 'supervisor__persona')
    if crupier:
        qs = qs.filter(crupier=crupier)
    if supervisor:
        qs = qs.filter(supervisor=supervisor)
    return qs.filter(turno__fecha=fecha).order_by('turno__hora_inicio', 'mesa_id')


@transaction.atomic
def generar_turnos(fecha, hora_inicio, hora_fin, duracion_minutos):
    """Define la duración de los turnos de un día creando turnos consecutivos (RN-10: máx. 2 h)."""
    duracion = timedelta(minutes=duracion_minutos)
    if duracion <= timedelta(0) or duracion > Turno.DURACION_MAXIMA:
        raise ValidationError('La duración del turno debe estar entre 1 y 120 minutos.')
    actual = datetime.combine(fecha, hora_inicio)
    limite = datetime.combine(fecha, hora_fin)
    if limite <= actual:
        raise ValidationError('La hora final de la jornada debe ser posterior a la inicial.')
    creados = []
    while actual < limite:
        fin = min(actual + duracion, limite)
        turno = Turno(fecha=fecha, hora_inicio=actual.time(), hora_fin=fin.time())
        turno.full_clean()  # valida duración y solapamiento con turnos existentes
        turno.save()
        creados.append(turno)
        actual = fin
    return creados


@transaction.atomic
def emitir_concepto(asignacion, supervisor, concepto):
    """RN-12/RN-13: concepto subjetivo del supervisor al final del turno."""
    asignacion = AsignacionMesa.objects.select_for_update().select_related('turno').get(pk=asignacion.pk)
    if asignacion.supervisor_id != supervisor.pk:
        raise ValidationError('Solo el supervisor asignado a la mesa puede emitir el concepto.')
    if not asignacion.turno.finalizado:
        raise ValidationError('El concepto se emite al final del turno; este turno aún no ha terminado.')
    if concepto not in AsignacionMesa.Concepto.values:
        raise ValidationError('Concepto no válido.')
    asignacion.concepto_supervisor = concepto
    asignacion.save(update_fields=['concepto_supervisor'])
    return asignacion
