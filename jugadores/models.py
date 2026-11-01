from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from cuentas.models import Persona


class EstadoCuenta(models.TextChoices):
    ACTIVO = 'Activo'
    SUSPENDIDO = 'Suspendido'
    INVESTIGACION = 'Investigación'


class Jugador(models.Model):
    persona = models.OneToOneField(
        Persona, primary_key=True, on_delete=models.PROTECT, db_column='id_persona', related_name='jugador',
    )
    codigo_cliente = models.CharField(max_length=20, unique=True)
    edad = models.PositiveSmallIntegerField()
    saldo_fichas = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estado = models.CharField(max_length=20, choices=EstadoCuenta.choices, default=EstadoCuenta.ACTIVO)
    # NULL con estado Suspendido = suspensión sin plazo (deuda de empleado, RN-29)
    suspendido_hasta = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'jugador'
        ordering = ['codigo_cliente']
        constraints = [
            models.CheckConstraint(
                condition=Q(edad__gte=settings.CASINO_EDAD_MINIMA), name='jugador_mayor_de_edad',
                violation_error_message='El jugador debe ser mayor de edad (RN-03).',
            ),
            models.CheckConstraint(
                condition=Q(saldo_fichas__gte=0), name='jugador_saldo_no_negativo',
                violation_error_message='El saldo no puede ser negativo.',
            ),
            models.CheckConstraint(
                condition=Q(estado__in=[e.value for e in EstadoCuenta]), name='jugador_estado_valido',
            ),
        ]

    def __str__(self):
        return f'{self.codigo_cliente} · {self.persona.nombre_completo}'

    @property
    def es_empleado(self):
        return self.persona.es_empleado

    @property
    def puede_apostar(self):
        return self.estado == EstadoCuenta.ACTIVO


class TipoMovimiento(models.TextChoices):
    CONSIGNACION = 'Consignacion', 'Consignación'
    RETIRO = 'Retiro', 'Retiro'


class EstadoMovimiento(models.TextChoices):
    PENDIENTE = 'Pendiente'
    APROBADO = 'Aprobado'
    RECHAZADO = 'Rechazado'


class Movimiento(models.Model):
    """Consignaciones y retiros (caso de uso 3.6). Tabla agregada al modelo base."""
    Tipo = TipoMovimiento
    Estado = EstadoMovimiento

    id_movimiento = models.AutoField(primary_key=True)
    jugador = models.ForeignKey(Jugador, on_delete=models.PROTECT, db_column='id_jugador', related_name='movimientos')
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    fecha = models.DateTimeField(default=timezone.now)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.APROBADO)
    observacion = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'movimiento'
        ordering = ['-fecha']
        constraints = [
            models.CheckConstraint(condition=Q(monto__gt=0), name='movimiento_monto_positivo'),
            models.CheckConstraint(condition=Q(tipo__in=TipoMovimiento.values), name='movimiento_tipo_valido'),
            models.CheckConstraint(condition=Q(estado__in=EstadoMovimiento.values), name='movimiento_estado_valido'),
        ]

    def __str__(self):
        return f'{self.get_tipo_display()} {self.monto} · {self.jugador.codigo_cliente}'


class Configuracion(models.Model):
    UMBRAL_PERDIDA_DIARIA = 'umbral_perdida_diaria'

    clave = models.CharField(max_length=50, primary_key=True)
    valor = models.CharField(max_length=100)

    class Meta:
        db_table = 'configuracion'

    def __str__(self):
        return f'{self.clave} = {self.valor}'

    @classmethod
    def umbral_perdida_diaria(cls):
        fila = cls.objects.filter(clave=cls.UMBRAL_PERDIDA_DIARIA).first()
        return Decimal(fila.valor if fila else settings.CASINO_UMBRAL_PERDIDA_DEFECTO)


class HistorialEstado(models.Model):
    jugador = models.ForeignKey(Jugador, on_delete=models.CASCADE, db_column='id_jugador', related_name='historial_estados')
    estado_anterior = models.CharField(max_length=20, choices=EstadoCuenta.choices)
    estado_nuevo = models.CharField(max_length=20, choices=EstadoCuenta.choices)
    motivo = models.CharField(max_length=200)
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'historial_estado'
        ordering = ['-fecha']

    def __str__(self):
        return f'{self.jugador.codigo_cliente}: {self.estado_anterior} → {self.estado_nuevo}'


class Notificacion(models.Model):
    persona = models.ForeignKey(Persona, on_delete=models.CASCADE, db_column='id_persona', related_name='notificaciones')
    mensaje = models.CharField(max_length=300)
    fecha = models.DateTimeField(default=timezone.now)
    leida = models.BooleanField(default=False)

    class Meta:
        db_table = 'notificacion'
        ordering = ['leida', '-fecha']

    def __str__(self):
        return self.mensaje
