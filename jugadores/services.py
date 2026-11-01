"""
Reglas de negocio de la cuenta del jugador:
saldo, consignaciones/retiros, suspensiones (RN-25 a RN-30), historial y notificaciones.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from cuentas.models import Empleado

from .models import Configuracion, EstadoCuenta, HistorialEstado, Jugador, Movimiento, Notificacion

CERO = Decimal('0')
MOTIVO_CIERRE_INVESTIGACION = 'Cierre investigación'


# ---------------------------------------------------------------- registro

def crear_jugador(persona, *, codigo_cliente, edad, saldo_inicial=CERO):
    jugador = Jugador(persona=persona, codigo_cliente=codigo_cliente, edad=edad)
    jugador.full_clean()  # incluye CheckConstraint edad >= 18 (RN-03)
    jugador.save()
    if saldo_inicial and saldo_inicial > 0:
        registrar_movimiento(jugador, Movimiento.Tipo.CONSIGNACION, saldo_inicial, observacion='Saldo inicial')
        jugador.refresh_from_db()
    return jugador


@transaction.atomic
def registrar_jugador(*, username, documento, nombre_completo, salt, password_hash, codigo_cliente, edad,
                      saldo_inicial=CERO):
    """RN-01/RN-02: registro previo obligatorio con todos los datos del jugador."""
    from cuentas.services import crear_persona_usuario, sincronizar_grupos
    if edad < settings.CASINO_EDAD_MINIMA:
        raise ValidationError('No se permite el registro de menores de edad (RN-03).')
    persona, usuario = crear_persona_usuario(
        username=username, documento=documento, nombre_completo=nombre_completo,
        salt=salt, password_hash=password_hash,
    )
    jugador = crear_jugador(persona, codigo_cliente=codigo_cliente, edad=edad, saldo_inicial=saldo_inicial)
    sincronizar_grupos(usuario)
    return jugador


@transaction.atomic
def habilitar_empleado_como_jugador(empleado, *, codigo_cliente, edad, saldo_inicial=CERO):
    """RN-28: un empleado puede jugar como cliente; se le crea su fila en `jugador`."""
    from cuentas.services import sincronizar_grupos
    if hasattr(empleado.persona, 'jugador'):
        raise ValidationError('Este empleado ya está registrado como jugador.')
    jugador = crear_jugador(empleado.persona, codigo_cliente=codigo_cliente, edad=edad, saldo_inicial=saldo_inicial)
    if hasattr(empleado.persona, 'usuario'):
        sincronizar_grupos(empleado.persona.usuario)
    return jugador


# ---------------------------------------------------------------- notificaciones e historial

def notificar(persona, mensaje):
    return Notificacion.objects.create(persona=persona, mensaje=mensaje)


def _cambiar_estado(jugador, nuevo, motivo, hasta=None):
    anterior = jugador.estado
    jugador.estado = nuevo
    jugador.suspendido_hasta = hasta if nuevo == EstadoCuenta.SUSPENDIDO else None
    jugador.save(update_fields=['estado', 'suspendido_hasta'])
    HistorialEstado.objects.create(jugador=jugador, estado_anterior=anterior, estado_nuevo=nuevo, motivo=motivo)
    if nuevo == EstadoCuenta.SUSPENDIDO:
        plazo = f' hasta {timezone.localtime(hasta):%Y-%m-%d %H:%M}' if hasta else ' sin plazo fijo'
        notificar(jugador.persona, f'Su cuenta fue SUSPENDIDA{plazo}. Motivo: {motivo}.')
    elif nuevo == EstadoCuenta.INVESTIGACION:
        notificar(jugador.persona, f'Su cuenta pasó a INVESTIGACIÓN y no puede apostar. Motivo: {motivo}.')
    else:
        notificar(jugador.persona, f'Su cuenta está ACTIVA nuevamente. Motivo: {motivo}.')


# ---------------------------------------------------------------- métricas (insumo de 3.4 / 3.5)

def _rango_dia(dia):
    inicio = timezone.make_aware(datetime.combine(dia, time.min))
    return inicio, inicio + timedelta(days=1)


def _apuestas_cerradas(jugador, desde=None, hasta=None):
    from juego.models import Apuesta
    qs = Apuesta.objects.filter(jugador=jugador).exclude(estado=Apuesta.Estado.PENDIENTE)
    if desde:
        qs = qs.filter(ronda__hora_cierre__gte=desde)
    if hasta:
        qs = qs.filter(ronda__hora_cierre__lt=hasta)
    return qs


def totales_juego(jugador, desde=None, hasta=None):
    """Devuelve (perdido, ganado): suma de montos de apuestas perdidas y de premios de apuestas ganadas."""
    from juego.models import Apuesta
    qs = _apuestas_cerradas(jugador, desde, hasta)
    perdido = qs.filter(estado=Apuesta.Estado.PERDIDA).aggregate(s=Sum('monto_apostado'))['s'] or CERO
    ganado = qs.filter(estado=Apuesta.Estado.GANADA).aggregate(s=Sum('premio'))['s'] or CERO
    return perdido, ganado


def perdidas_del_dia(jugador, dia=None):
    """RN-25: pérdida diaria = suma bruta de montos de apuestas Perdidas cerradas ese día."""
    inicio, fin = _rango_dia(dia or timezone.localdate())
    return totales_juego(jugador, inicio, fin)[0]


def deuda_empleado(jugador):
    """
    RN-29: pérdidas netas (perdido − ganado) en la ventana móvil configurada (30 días).
    Al salir de la ventana las pérdidas antiguas, la deuda baja y el empleado se reactiva solo.
    """
    desde = timezone.now() - timedelta(days=settings.CASINO_VENTANA_DEUDA_EMPLEADO_DIAS)
    perdido, ganado = totales_juego(jugador, desde)
    return max(CERO, perdido - ganado)


def ganancias_netas_empleado(jugador):
    """RN-30: ganancias netas (ganado − perdido) desde el último cierre de investigación."""
    ultimo_cierre = jugador.historial_estados.filter(
        motivo__startswith=MOTIVO_CIERRE_INVESTIGACION,
    ).order_by('-fecha').values_list('fecha', flat=True).first()
    perdido, ganado = totales_juego(jugador, ultimo_cierre)
    return max(CERO, ganado - perdido)


# ---------------------------------------------------------------- evaluación automática de estado

def evaluar_estado(jugador):
    """
    Aplica las reglas de autoexclusión y prevención de riesgo. Debe llamarse:
    al cerrar una ronda, antes de cada apuesta, al aprobar movimientos y al cargar el panel del jugador.
    """
    ahora = timezone.now()
    if (jugador.estado == EstadoCuenta.SUSPENDIDO and jugador.suspendido_hasta
            and jugador.suspendido_hasta <= ahora):
        _cambiar_estado(jugador, EstadoCuenta.ACTIVO, 'Fin de la suspensión de 24 horas')

    if jugador.estado == EstadoCuenta.INVESTIGACION:
        return jugador  # solo se cierra manualmente (RN-30)

    empleado = Empleado.objects.filter(persona_id=jugador.pk).first()
    if empleado:
        ganancias = ganancias_netas_empleado(jugador)
        if ganancias > empleado.salario:
            _cambiar_estado(jugador, EstadoCuenta.INVESTIGACION,
                            f'Empleado con ganancias ({ganancias:,.0f}) superiores a 1 salario (RN-30)')
            return jugador
        deuda = deuda_empleado(jugador)
        limite = empleado.salario * 2
        if deuda > limite and jugador.estado == EstadoCuenta.ACTIVO:
            _cambiar_estado(jugador, EstadoCuenta.SUSPENDIDO,
                            f'Empleado con pérdidas ({deuda:,.0f}) superiores a 2 salarios (RN-29)')
            return jugador
        if (jugador.estado == EstadoCuenta.SUSPENDIDO and jugador.suspendido_hasta is None
                and deuda <= limite):
            _cambiar_estado(jugador, EstadoCuenta.ACTIVO, 'La deuda del empleado bajó del límite de 2 salarios')

    if jugador.estado == EstadoCuenta.ACTIVO:
        perdidas = perdidas_del_dia(jugador)
        umbral = Configuracion.umbral_perdida_diaria()
        if perdidas > umbral:
            _cambiar_estado(
                jugador, EstadoCuenta.SUSPENDIDO,
                f'Pérdidas del día ({perdidas:,.0f}) superiores al umbral ({umbral:,.0f}) (RN-25)',
                hasta=ahora + timedelta(hours=settings.CASINO_HORAS_SUSPENSION),
            )
    return jugador


def actualizar_estado(jugador_id):
    """Evalúa el estado en su propia transacción (se confirma aunque luego falle la operación)."""
    with transaction.atomic():
        jugador = Jugador.objects.select_for_update().get(pk=jugador_id)
        return evaluar_estado(jugador)


@transaction.atomic
def solicitar_pausa(jugador):
    """RN-26: pausa voluntaria → Suspendido 24 h."""
    jugador = Jugador.objects.select_for_update().get(pk=jugador.pk)
    if jugador.estado != EstadoCuenta.ACTIVO:
        raise ValidationError(f'La cuenta ya está en estado {jugador.estado}.')
    _cambiar_estado(jugador, EstadoCuenta.SUSPENDIDO, 'Autoexclusión voluntaria solicitada por el jugador (RN-26)',
                    hasta=timezone.now() + timedelta(hours=settings.CASINO_HORAS_SUSPENSION))
    return jugador


@transaction.atomic
def cerrar_investigacion(jugador, observacion=''):
    """RN-30: cierre manual de la investigación por un administrador."""
    jugador = Jugador.objects.select_for_update().get(pk=jugador.pk)
    if jugador.estado != EstadoCuenta.INVESTIGACION:
        raise ValidationError('El jugador no está en investigación.')
    motivo = MOTIVO_CIERRE_INVESTIGACION + (f': {observacion}' if observacion else '')
    _cambiar_estado(jugador, EstadoCuenta.ACTIVO, motivo[:200])
    return evaluar_estado(jugador)


# ---------------------------------------------------------------- consignaciones y retiros (3.6)

def _aplicar_movimiento(jugador, tipo, monto):
    """Actualiza el saldo; el retiro no puede superar el saldo disponible."""
    if tipo == Movimiento.Tipo.RETIRO:
        if monto > jugador.saldo_fichas:
            raise ValidationError(f'Saldo insuficiente: disponible {jugador.saldo_fichas:,.2f}, retiro {monto:,.2f}.')
        Jugador.objects.filter(pk=jugador.pk).update(saldo_fichas=F('saldo_fichas') - monto)
    else:
        Jugador.objects.filter(pk=jugador.pk).update(saldo_fichas=F('saldo_fichas') + monto)
    jugador.refresh_from_db(fields=['saldo_fichas'])


@transaction.atomic
def registrar_movimiento(jugador, tipo, monto, observacion=''):
    """Registro directo (administrador): se aplica de inmediato."""
    jugador = Jugador.objects.select_for_update().get(pk=jugador.pk)
    if monto is None or monto <= 0:
        raise ValidationError('El monto debe ser positivo.')
    _aplicar_movimiento(jugador, tipo, monto)
    movimiento = Movimiento.objects.create(jugador=jugador, tipo=tipo, monto=monto,
                                           estado=Movimiento.Estado.APROBADO, observacion=observacion)
    evaluar_estado(jugador)
    return movimiento


@transaction.atomic
def solicitar_movimiento(jugador, tipo, monto, observacion=''):
    """Solicitud del jugador: queda Pendiente hasta que un administrador la apruebe."""
    jugador = Jugador.objects.select_for_update().get(pk=jugador.pk)
    if monto is None or monto <= 0:
        raise ValidationError('El monto debe ser positivo.')
    if tipo == Movimiento.Tipo.RETIRO:
        comprometido = jugador.movimientos.filter(
            tipo=Movimiento.Tipo.RETIRO, estado=Movimiento.Estado.PENDIENTE,
        ).aggregate(s=Sum('monto'))['s'] or CERO
        if monto + comprometido > jugador.saldo_fichas:
            raise ValidationError(
                f'El retiro supera el saldo disponible ({jugador.saldo_fichas - comprometido:,.2f} '
                'descontando retiros pendientes).'
            )
    return Movimiento.objects.create(jugador=jugador, tipo=tipo, monto=monto,
                                     estado=Movimiento.Estado.PENDIENTE, observacion=observacion)


def _movimiento_pendiente(movimiento):
    movimiento = Movimiento.objects.select_for_update().get(pk=movimiento.pk)
    if movimiento.estado != Movimiento.Estado.PENDIENTE:
        raise ValidationError('Solo se pueden modificar movimientos pendientes.')
    return movimiento


@transaction.atomic
def aprobar_movimiento(movimiento):
    movimiento = _movimiento_pendiente(movimiento)
    jugador = Jugador.objects.select_for_update().get(pk=movimiento.jugador_id)
    _aplicar_movimiento(jugador, movimiento.tipo, movimiento.monto)
    movimiento.estado = Movimiento.Estado.APROBADO
    movimiento.save(update_fields=['estado'])
    notificar(jugador.persona, f'Su {movimiento.get_tipo_display().lower()} por {movimiento.monto:,.2f} fue aprobada.')
    evaluar_estado(jugador)
    return movimiento


@transaction.atomic
def rechazar_movimiento(movimiento, observacion=''):
    movimiento = _movimiento_pendiente(movimiento)
    movimiento.estado = Movimiento.Estado.RECHAZADO
    movimiento.observacion = observacion[:200] or movimiento.observacion
    movimiento.save(update_fields=['estado', 'observacion'])
    notificar(movimiento.jugador.persona,
              f'Su {movimiento.get_tipo_display().lower()} por {movimiento.monto:,.2f} fue rechazada.')
    return movimiento


@transaction.atomic
def modificar_movimiento(movimiento, tipo, monto, observacion=''):
    movimiento = _movimiento_pendiente(movimiento)
    if monto is None or monto <= 0:
        raise ValidationError('El monto debe ser positivo.')
    movimiento.tipo, movimiento.monto, movimiento.observacion = tipo, monto, observacion
    movimiento.save()
    return movimiento


@transaction.atomic
def eliminar_movimiento(movimiento):
    _movimiento_pendiente(movimiento).delete()
