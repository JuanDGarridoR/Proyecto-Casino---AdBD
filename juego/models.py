from django.db import models
from django.db.models import F, Q

from jugadores.models import Jugador
from mesas.models import Mesa


class Ronda(models.Model):
    id_ronda = models.AutoField(primary_key=True)
    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, db_column='id_mesa', related_name='rondas')
    numero = models.PositiveIntegerField()
    hora_inicio = models.DateTimeField()
    hora_cierre = models.DateTimeField(null=True, blank=True)  # NULL mientras está abierta
    resultado = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = 'ronda'
        ordering = ['-hora_inicio']
        constraints = [
            models.UniqueConstraint(fields=['mesa', 'numero'], name='ronda_numero_por_mesa'),
            models.UniqueConstraint(
                fields=['mesa'], condition=Q(hora_cierre__isnull=True), name='ronda_una_abierta_por_mesa',
                violation_error_message='La mesa ya tiene una ronda abierta.',
            ),
            models.CheckConstraint(
                condition=Q(hora_cierre__isnull=True) | Q(hora_cierre__gte=F('hora_inicio')),
                name='ronda_cierre_posterior_inicio',
            ),
        ]

    def __str__(self):
        return f'Ronda #{self.numero} · {self.mesa}'

    @property
    def abierta(self):
        return self.hora_cierre is None


class EstadoApuesta(models.TextChoices):
    PENDIENTE = 'Pendiente'
    GANADA = 'Ganada'
    PERDIDA = 'Perdida'


class Apuesta(models.Model):
    Estado = EstadoApuesta

    id_apuesta = models.AutoField(primary_key=True)
    jugador = models.ForeignKey(Jugador, on_delete=models.PROTECT, db_column='id_jugador', related_name='apuestas')
    ronda = models.ForeignKey(Ronda, on_delete=models.PROTECT, db_column='id_ronda', related_name='apuestas')
    tipo_apuesta = models.CharField(max_length=100)
    monto_apostado = models.DecimalField(max_digits=12, decimal_places=2)
    factor_pago = models.DecimalField(max_digits=8, decimal_places=2, help_text='Ej.: 35 para un pago 35:1.')
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE)
    # Ganancia neta = monto × factor. Al ganar se acredita premio + monto apostado (devolución).
    premio = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = 'apuesta'
        ordering = ['-id_apuesta']
        constraints = [
            models.CheckConstraint(condition=Q(monto_apostado__gt=0), name='apuesta_monto_positivo'),
            models.CheckConstraint(condition=Q(factor_pago__gt=0), name='apuesta_factor_positivo'),
            models.CheckConstraint(condition=Q(premio__gte=0), name='apuesta_premio_no_negativo'),
            models.CheckConstraint(
                condition=Q(estado__in=EstadoApuesta.values), name='apuesta_estado_valido',
            ),
        ]

    def __str__(self):
        return f'{self.tipo_apuesta} · {self.monto_apostado} · {self.jugador.codigo_cliente}'
