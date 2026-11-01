import hashlib
import secrets

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models import Q


class Rol(models.TextChoices):
    """Roles del sistema. Se materializan como Groups de django.contrib.auth."""
    ADMINISTRADOR = 'Administrador'
    SUPERVISOR = 'Supervisor'
    CRUPIER = 'Crupier'
    JUGADOR = 'Jugador'


def generar_salt():
    return secrets.token_hex(16)


def sha256_hex(texto):
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()


class Persona(models.Model):
    id_persona = models.AutoField(primary_key=True)
    documento = models.CharField(max_length=20, unique=True)
    nombre_completo = models.CharField(max_length=100)

    class Meta:
        db_table = 'persona'
        ordering = ['nombre_completo']

    def __str__(self):
        return f'{self.nombre_completo} ({self.documento})'

    @property
    def es_empleado(self):
        return hasattr(self, 'empleado')

    @property
    def es_jugador(self):
        return hasattr(self, 'jugador')


class UsuarioManager(BaseUserManager):
    def create_user(self, username, password=None, **extra):
        usuario = self.model(username=username, **extra)
        # La columna `password` de Django queda sin uso: la credencial vive en salt/password_hash.
        usuario.set_unusable_password()
        if password:
            # Solo para `seed` y `createsuperuser` (consola local): la contraseña no viaja por la red.
            usuario.establecer_password_plano(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, username, password=None, **extra):
        extra.setdefault('is_staff', True)
        extra.setdefault('is_superuser', True)
        return self.create_user(username, password, **extra)


class Usuario(AbstractBaseUser, PermissionsMixin):
    """
    Credenciales Zero Knowledge: se guarda salt y H = SHA256(salt + password),
    calculado en el navegador. La contraseña en claro nunca llega al servidor.
    """
    id_usuario = models.AutoField(primary_key=True)
    username = models.CharField(max_length=50, unique=True)
    persona = models.OneToOneField(
        Persona, null=True, blank=True, on_delete=models.PROTECT,
        db_column='id_persona', related_name='usuario',
    )
    salt = models.CharField(max_length=32)
    password_hash = models.CharField(max_length=64)
    is_active = models.BooleanField('activo', default=True, db_column='activo')
    is_staff = models.BooleanField(default=False)

    objects = UsuarioManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []

    class Meta:
        db_table = 'usuario'
        constraints = [
            models.CheckConstraint(
                condition=Q(password_hash__regex=r'^[0-9a-f]{64}$'),
                name='usuario_password_hash_sha256',
            ),
        ]

    def __str__(self):
        return self.username

    def establecer_hash(self, salt, password_hash):
        self.salt = salt
        self.password_hash = password_hash

    def establecer_password_plano(self, password):
        salt = generar_salt()
        self.establecer_hash(salt, sha256_hex(salt + password))

    @property
    def roles(self):
        """Roles del usuario en orden de prioridad."""
        nombres = set(self.groups.values_list('name', flat=True))
        if self.is_superuser:
            nombres.add(Rol.ADMINISTRADOR)
        return [r.value for r in Rol if r.value in nombres]

    def tiene_rol(self, rol):
        return rol in self.roles

    @property
    def nombre_visible(self):
        return self.persona.nombre_completo if self.persona_id else self.username


class CargoEmpleado(models.TextChoices):
    ADMINISTRADOR = 'Administrador'
    SUPERVISOR = 'Supervisor'
    CRUPIER = 'Crupier'


class Empleado(models.Model):
    Cargo = CargoEmpleado

    persona = models.OneToOneField(
        Persona, primary_key=True, on_delete=models.PROTECT,
        db_column='id_persona', related_name='empleado',
    )
    cargo = models.CharField(max_length=50, choices=Cargo.choices)
    salario = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = 'empleado'
        ordering = ['persona__nombre_completo']
        constraints = [
            models.CheckConstraint(condition=Q(salario__gt=0), name='empleado_salario_positivo'),
            models.CheckConstraint(
                condition=Q(cargo__in=CargoEmpleado.values), name='empleado_cargo_valido',
            ),
        ]

    def __str__(self):
        return f'{self.persona.nombre_completo} · {self.cargo}'

    def conoce(self, juego):
        return self.competencias.filter(juego=juego).exists()
