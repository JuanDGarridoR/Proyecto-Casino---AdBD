"""
Rondas y apuestas: registro con validaciones (RN-17 a RN-21, RN-24) y
procesamiento automático del resultado (RN-22, RN-23) con evaluación de suspensiones.
"""
import re
import unicodedata
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Max
from django.utils import timezone

from jugadores.models import EstadoCuenta, Jugador
from jugadores.services import actualizar_estado, evaluar_estado
from mesas.models import Mesa
from mesas.services import asignacion_vigente

from .models import Apuesta, Ronda

ROJOS_RULETA = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

# Sugerencias de tipos de apuesta (datalist en el formulario) y su factor de pago habitual.
SUGERENCIAS = {
    'ruleta': [('Pleno 17', 35), ('Rojo', 1), ('Negro', 1), ('Par', 1), ('Impar', 1), ('Falta (1-18)', 1),
               ('Pasa (19-36)', 1), ('Primera docena', 2), ('Segunda docena', 2), ('Tercera docena', 2)],
    'blackjack': [('Asiento 1', 1), ('Asiento 2', 1), ('Asiento 3', 1), ('Blackjack asiento 1', 1.5),
                  ('Seguro', 2), ('Empate', 1)],
    'poker': [('Mano J-0001', 1), ('Bote', 1)],
}


# ---------------------------------------------------------------- comparación de resultados

def normalizar(texto):
    texto = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode()
    texto = re.sub(r'[()]', ' ', texto.lower())
    return re.sub(r'\s+', ' ', texto).strip()


def clave_juego(juego):
    return normalizar(juego.tipo_juego).split(' ')[0]


def _expansion_ruleta(numero):
    """Todo lo que gana cuando sale `numero` en la ruleta."""
    ganan = {f'{numero}', f'numero {numero}', f'pleno {numero}', f'pleno al {numero}'}
    if numero == 0:
        return ganan | {'cero', 'verde'}
    color = 'rojo' if numero in ROJOS_RULETA else 'negro'
    paridad = 'par' if numero % 2 == 0 else 'impar'
    mitad = 'falta 1-18' if numero <= 18 else 'pasa 19-36'
    docena = ['primera docena', 'segunda docena', 'tercera docena'][(numero - 1) // 12]
    ganan |= {color, f'color {color}', paridad, f'numero {paridad}', mitad, mitad.split(' ')[0], docena}
    return ganan


def resultados_ganadores(juego, resultado):
    """
    El resultado se ingresa como texto; varias opciones ganadoras se separan con comas
    (ej. "Asiento 1, Asiento 3"). En la ruleta basta con el número: se deducen color,
    paridad, mitad y docena. Una apuesta gana si su tipo (normalizado) está en el conjunto.
    """
    partes = {normalizar(p) for p in re.split(r'[,;]', resultado or '') if p.strip()}
    if clave_juego(juego) == 'ruleta':
        for parte in list(partes):
            encontrado = re.fullmatch(r'(?:numero |pleno )?(\d{1,2})', parte)
            if encontrado and 0 <= int(encontrado.group(1)) <= 36:
                partes |= _expansion_ruleta(int(encontrado.group(1)))
    return partes


# ---------------------------------------------------------------- autorizaciones

def verificar_crupier_en_turno(crupier, mesa):
    """El crupier solo opera la mesa que tiene asignada en el turno en curso."""
    asignacion = asignacion_vigente(mesa)
    if asignacion is None:
        raise ValidationError(f'{mesa} no tiene crupier asignado en el turno actual.')
    if crupier is not None and asignacion.crupier_id != crupier.pk:
        raise ValidationError(f'Usted no es el crupier asignado a {mesa} en el turno actual.')
    return asignacion


def _validar_apuesta(ronda, jugador, monto, factor, *, permitir_sin_detalle=False):
    mesa = ronda.mesa
    if not ronda.abierta:
        raise ValidationError('La ronda ya está cerrada; no admite apuestas.')
    if not mesa.juego.registro_detallado and not permitir_sin_detalle:
        raise ValidationError(
            f'{mesa.juego} no permite registro detallado: las apuestas se registran al evidenciarse el resultado (RN-24).'
        )
    if jugador.estado != EstadoCuenta.ACTIVO:
        raise ValidationError(f'El jugador {jugador.codigo_cliente} está en estado {jugador.estado} y no puede apostar.')
    if monto is None or not (mesa.monto_minimo <= monto <= mesa.monto_maximo):
        raise ValidationError(
            f'El monto debe estar entre {mesa.monto_minimo:,.2f} y {mesa.monto_maximo:,.2f} (RN-20).'
        )
    if factor is None or factor <= 0:
        raise ValidationError('El factor de pago debe ser positivo.')
    if jugador.saldo_fichas < monto:
        raise ValidationError(
            f'Saldo insuficiente: {jugador.codigo_cliente} tiene {jugador.saldo_fichas:,.2f} fichas (RN-21).'
        )


# ---------------------------------------------------------------- rondas

@transaction.atomic
def abrir_ronda(mesa, crupier):
    mesa = Mesa.objects.select_for_update().get(pk=mesa.pk)
    verificar_crupier_en_turno(crupier, mesa)
    if mesa.rondas.filter(hora_cierre__isnull=True).exists():
        raise ValidationError('La mesa ya tiene una ronda abierta.')
    numero = (mesa.rondas.aggregate(m=Max('numero'))['m'] or 0) + 1
    return Ronda.objects.create(mesa=mesa, numero=numero, hora_inicio=timezone.now())


@transaction.atomic
def eliminar_ronda(ronda, crupier):
    ronda = Ronda.objects.select_for_update().get(pk=ronda.pk)
    verificar_crupier_en_turno(crupier, ronda.mesa)
    if not ronda.abierta or ronda.apuestas.exists():
        raise ValidationError('Solo se puede eliminar una ronda abierta y sin apuestas.')
    ronda.delete()


def _crear_apuesta(ronda, jugador_id, tipo, monto, factor, *, permitir_sin_detalle=False):
    jugador = Jugador.objects.select_for_update().get(pk=jugador_id)
    _validar_apuesta(ronda, jugador, monto, factor, permitir_sin_detalle=permitir_sin_detalle)
    # El monto se descuenta al registrar la apuesta, en la misma transacción (RN-21).
    Jugador.objects.filter(pk=jugador.pk).update(saldo_fichas=F('saldo_fichas') - monto)
    apuesta = Apuesta(jugador=jugador, ronda=ronda, tipo_apuesta=tipo.strip(), monto_apostado=monto, factor_pago=factor)
    apuesta.full_clean()
    apuesta.save()
    return apuesta


def registrar_apuesta(ronda, jugador, tipo, monto, factor, crupier):
    """RN-17..RN-21: registro detallado de una apuesta en una ronda abierta."""
    # Primero se actualiza el estado (vencimiento de suspensiones) en su propia transacción.
    actualizar_estado(jugador.pk)
    with transaction.atomic():
        ronda = Ronda.objects.select_for_update().select_related('mesa__juego').get(pk=ronda.pk)
        verificar_crupier_en_turno(crupier, ronda.mesa)
        return _crear_apuesta(ronda, jugador.pk, tipo, monto, factor)


def modificar_apuesta(apuesta, tipo, monto, factor, crupier):
    actualizar_estado(apuesta.jugador_id)
    with transaction.atomic():
        apuesta = Apuesta.objects.select_for_update().select_related('ronda__mesa__juego').get(pk=apuesta.pk)
        verificar_crupier_en_turno(crupier, apuesta.ronda.mesa)
        if apuesta.estado != Apuesta.Estado.PENDIENTE:
            raise ValidationError('Solo se pueden modificar apuestas pendientes.')
        jugador = Jugador.objects.select_for_update().get(pk=apuesta.jugador_id)
        # Se devuelve el monto anterior y se valida la apuesta como si fuera nueva.
        jugador.saldo_fichas += apuesta.monto_apostado
        _validar_apuesta(apuesta.ronda, jugador, monto, factor)
        Jugador.objects.filter(pk=jugador.pk).update(
            saldo_fichas=F('saldo_fichas') + apuesta.monto_apostado - monto,
        )
        apuesta.tipo_apuesta, apuesta.monto_apostado, apuesta.factor_pago = tipo.strip(), monto, factor
        apuesta.full_clean()
        apuesta.save()
        return apuesta


@transaction.atomic
def anular_apuesta(apuesta, crupier):
    apuesta = Apuesta.objects.select_for_update().select_related('ronda__mesa').get(pk=apuesta.pk)
    verificar_crupier_en_turno(crupier, apuesta.ronda.mesa)
    if apuesta.estado != Apuesta.Estado.PENDIENTE or not apuesta.ronda.abierta:
        raise ValidationError('Solo se pueden anular apuestas pendientes de una ronda abierta.')
    Jugador.objects.filter(pk=apuesta.jugador_id).update(saldo_fichas=F('saldo_fichas') + apuesta.monto_apostado)
    apuesta.delete()


def cerrar_ronda(ronda, resultado, crupier, apuestas_al_resultado=()):
    """
    RN-18/22/23: el crupier ingresa el resultado y el sistema procesa todas las apuestas.
    `apuestas_al_resultado`: para juegos sin registro detallado (RN-24), lista de dicts
    {jugador, tipo_apuesta, monto_apostado, factor_pago} que se registran al evidenciarse el resultado.
    """
    resultado = (resultado or '').strip()
    if not resultado:
        raise ValidationError('Debe ingresar el resultado ganador.')
    for datos in apuestas_al_resultado:
        actualizar_estado(datos['jugador'].pk)

    with transaction.atomic():
        ronda = Ronda.objects.select_for_update().select_related('mesa__juego').get(pk=ronda.pk)
        verificar_crupier_en_turno(crupier, ronda.mesa)
        if not ronda.abierta:
            raise ValidationError('La ronda ya fue cerrada.')
        juego = ronda.mesa.juego
        if apuestas_al_resultado and juego.registro_detallado:
            raise ValidationError('En juegos con registro detallado las apuestas se registran durante la ronda.')
        for datos in apuestas_al_resultado:
            _crear_apuesta(ronda, datos['jugador'].pk, datos['tipo_apuesta'], datos['monto_apostado'],
                           datos['factor_pago'], permitir_sin_detalle=True)

        ronda.resultado = resultado[:100]
        ronda.hora_cierre = timezone.now()
        ronda.save(update_fields=['resultado', 'hora_cierre'])

        ganadores = resultados_ganadores(juego, resultado)
        afectados = set()
        for apuesta in ronda.apuestas.select_for_update():
            if normalizar(apuesta.tipo_apuesta) in ganadores:
                apuesta.estado = Apuesta.Estado.GANADA
                apuesta.premio = (apuesta.monto_apostado * apuesta.factor_pago).quantize(Decimal('0.01'))
                # Se acredita inmediatamente el premio más la devolución del monto apostado (RN-22).
                Jugador.objects.filter(pk=apuesta.jugador_id).update(
                    saldo_fichas=F('saldo_fichas') + apuesta.premio + apuesta.monto_apostado,
                )
            else:
                # El monto (ya descontado al apostar) se consolida a favor del casino (RN-23).
                apuesta.estado = Apuesta.Estado.PERDIDA
                apuesta.premio = Decimal('0')
            apuesta.save(update_fields=['estado', 'premio'])
            afectados.add(apuesta.jugador_id)

        # Evaluación automática de suspensiones con los nuevos acumulados (3.5).
        for jugador in Jugador.objects.select_for_update().filter(pk__in=afectados):
            evaluar_estado(jugador)
        return ronda
