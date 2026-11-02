from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from cuentas.models import Empleado


class Juego(models.Model):
    id_juego = models.AutoField(primary_key=True)
    tipo_juego = models.CharField(max_length=50, unique=True)
    registro_detallado = models.BooleanField(
        help_text='Si está activo, las apuestas se registran antes del resultado.',
    )

    class Meta:
        db_table = 'juego'
        ordering = ['tipo_juego']

    def __str__(self):
        return self.tipo_juego


class Mesa(models.Model):
    id_mesa = models.AutoField(primary_key=True)
    juego = models.ForeignKey(Juego, on_delete=models.PROTECT, db_column='id_juego', related_name='mesas')
    monto_minimo = models.DecimalField(max_digits=12, decimal_places=2)
    monto_maximo = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = 'mesa'
        ordering = ['id_mesa']
        constraints = [
            models.CheckConstraint(
                condition=Q(monto_minimo__gt=0) & Q(monto_minimo__lte=F('monto_maximo')),
                name='mesa_montos_validos',
                violation_error_message='El monto mínimo debe ser positivo y no superar al máximo.',
            ),
        ]

    def __str__(self):
        return f'Mesa {self.id_mesa} · {self.juego}'


class Competencia(models.Model):
    """Juegos que conoce cada empleado (RN-14). PK compuesta lógica → UniqueConstraint."""
    empleado = models.ForeignKey(
        Empleado, on_delete=models.CASCADE, db_column='id_empleado', related_name='competencias',
    )
    juego = models.ForeignKey(Juego, on_delete=models.PROTECT, db_column='id_juego', related_name='competencias')

    class Meta:
        db_table = 'competencia'
        constraints = [
            models.UniqueConstraint(fields=['empleado', 'juego'], name='competencia_pk'),
        ]

    def __str__(self):
        return f'{self.empleado} conoce {self.juego}'


class Turno(models.Model):
    DURACION_MAXIMA = timedelta(hours=2)  # RN-10

    id_turno = models.AutoField(primary_key=True)
    fecha = models.DateField()
    # Supuesto del modelo: el turno no cruza medianoche.
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()

    class Meta:
        db_table = 'turno'
        ordering = ['-fecha', 'hora_inicio']
        constraints = [
            models.CheckConstraint(
                condition=Q(hora_fin__gt=F('hora_inicio')),
                name='turno_fin_posterior_inicio',
                violation_error_message='La hora de fin debe ser posterior a la de inicio.',
            ),
        ]

    def __str__(self):
        return f'{self.fecha:%Y-%m-%d} {self.hora_inicio:%H:%M}–{self.hora_fin:%H:%M}'

    @property
    def duracion(self):
        return datetime.combine(self.fecha, self.hora_fin) - datetime.combine(self.fecha, self.hora_inicio)

    @property
    def inicio_dt(self):
        return timezone.make_aware(datetime.combine(self.fecha, self.hora_inicio))

    @property
    def fin_dt(self):
        return timezone.make_aware(datetime.combine(self.fecha, self.hora_fin))

    @property
    def en_curso(self):
        return self.inicio_dt <= timezone.now() < self.fin_dt

    @property
    def finalizado(self):
        return timezone.now() >= self.fin_dt

    def clean(self):
        if not (self.fecha and self.hora_inicio and self.hora_fin):
            return
        if self.hora_fin <= self.hora_inicio:
            raise ValidationError('La hora de fin debe ser posterior a la de inicio (el turno no cruza medianoche).')
        if self.duracion > self.DURACION_MAXIMA:
            raise ValidationError('Un turno no puede durar más de 2 horas.')
        solapados = Turno.objects.filter(
            fecha=self.fecha, hora_inicio__lt=self.hora_fin, hora_fin__gt=self.hora_inicio,
        ).exclude(pk=self.pk)
        if solapados.exists():
            raise ValidationError(f'El turno se solapa con otro turno del mismo día: {solapados.first()}.')


class ConceptoSupervisor(models.TextChoices):  # RN-12
    GANANCIAS = 'Genera ganancias'
    PERDIDAS = 'Genera pérdidas'
    FRAUDE = 'Sospecha de fraude'
    NEUTRO = 'Comportamiento neutro'


class AsignacionMesa(models.Model):
    Concepto = ConceptoSupervisor

    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, db_column='id_mesa', related_name='asignaciones')
    turno = models.ForeignKey(Turno, on_delete=models.PROTECT, db_column='id_turno', related_name='asignaciones')
    crupier = models.ForeignKey(
        Empleado, on_delete=models.PROTECT, db_column='id_crupier', related_name='asignaciones_como_crupier',
    )
    supervisor = models.ForeignKey(
        Empleado, on_delete=models.PROTECT, db_column='id_supervisor', related_name='asignaciones_como_supervisor',
    )
    concepto_supervisor = models.CharField(max_length=30, choices=Concepto.choices, null=True, blank=True)

    class Meta:
        db_table = 'asignacion_mesa'
        ordering = ['turno__fecha', 'turno__hora_inicio', 'mesa_id']
        constraints = [
            models.UniqueConstraint(
                fields=['mesa', 'turno'], name='asignacion_mesa_pk',
                violation_error_message='La mesa ya tiene una asignación en ese turno.',
            ),
            models.UniqueConstraint(
                fields=['crupier', 'turno'], name='asignacion_crupier_turno_unico',
                violation_error_message='El crupier ya atiende otra mesa en ese turno.',
            ),
            models.CheckConstraint(
                condition=~Q(crupier=F('supervisor')), name='asignacion_crupier_distinto_supervisor',
                violation_error_message='El crupier y el supervisor deben ser personas distintas.',
            ),
            models.CheckConstraint(
                condition=Q(concepto_supervisor__isnull=True) | Q(concepto_supervisor__in=ConceptoSupervisor.values),
                name='asignacion_concepto_valido',
            ),
        ]

    def __str__(self):
        return f'{self.mesa} · {self.turno}'

    def clean(self):
        errores = {}
        if self.crupier_id and self.crupier.cargo != Empleado.Cargo.CRUPIER:
            errores['crupier'] = 'El empleado seleccionado no tiene cargo de Crupier.'
        if self.supervisor_id and self.supervisor.cargo != Empleado.Cargo.SUPERVISOR:
            errores['supervisor'] = 'El empleado seleccionado no tiene cargo de Supervisor.'
        if self.mesa_id:
            juego = self.mesa.juego
            # RN-15: solo personal que conoce el juego de la mesa
            if self.crupier_id and 'crupier' not in errores and not self.crupier.conoce(juego):
                errores['crupier'] = f'El crupier no conoce el juego {juego}.'
            if self.supervisor_id and 'supervisor' not in errores and not self.supervisor.conoce(juego):
                errores['supervisor'] = f'El supervisor no conoce el juego {juego}.'
            # RN-09: un crupier no repite mesa en la misma jornada
            if self.crupier_id and self.turno_id and 'crupier' not in errores:
                repetida = AsignacionMesa.objects.filter(
                    crupier_id=self.crupier_id, mesa_id=self.mesa_id, turno__fecha=self.turno.fecha,
                ).exclude(pk=self.pk)
                if repetida.exists():
                    errores['crupier'] = (
                        f'El crupier ya atendió esta mesa el {self.turno.fecha:%Y-%m-%d} '
                        f'(turno {repetida.first().turno}); no puede repetir mesa en la jornada.'
                    )
        if errores:
            raise ValidationError(errores)
