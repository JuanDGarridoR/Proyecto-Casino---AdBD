from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction

from mesas.models import Competencia

from .models import Empleado, Persona, Rol, Usuario


def crear_persona_usuario(*, username, documento, nombre_completo, salt, password_hash):
    persona = Persona(documento=documento, nombre_completo=nombre_completo)
    persona.full_clean()
    persona.save()
    usuario = Usuario(username=username, persona=persona)
    usuario.set_unusable_password()
    usuario.establecer_hash(salt, password_hash)
    usuario.full_clean(exclude=['password'])
    usuario.save()
    return persona, usuario


def sincronizar_grupos(usuario):
    """Los Groups se derivan de los datos: cargo del empleado y existencia de fila jugador."""
    from jugadores.models import Jugador

    deseados = set()
    if usuario.persona_id:
        # Consultas directas (no la caché de relaciones inversas) para reflejar cambios recientes.
        cargo = Empleado.objects.filter(persona_id=usuario.persona_id).values_list('cargo', flat=True).first()
        if cargo:
            deseados.add(cargo)
        if Jugador.objects.filter(persona_id=usuario.persona_id).exists():
            deseados.add(Rol.JUGADOR.value)
    usuario.groups.set(Group.objects.filter(name__in=deseados))
    # Los administradores tienen acceso de apoyo al admin de Django.
    usuario.is_staff = Rol.ADMINISTRADOR.value in deseados or usuario.is_superuser
    usuario.save(update_fields=['is_staff'])


def _asignar_competencias(empleado, juegos):
    empleado.competencias.exclude(juego__in=juegos).delete()
    for juego in juegos:
        Competencia.objects.get_or_create(empleado=empleado, juego=juego)


@transaction.atomic
def crear_empleado(*, username, documento, nombre_completo, salt, password_hash, cargo, salario, juegos,
                   datos_jugador=None):
    persona, usuario = crear_persona_usuario(
        username=username, documento=documento, nombre_completo=nombre_completo,
        salt=salt, password_hash=password_hash,
    )
    empleado = Empleado(persona=persona, cargo=cargo, salario=salario)
    empleado.full_clean()
    empleado.save()
    _asignar_competencias(empleado, juegos)
    if datos_jugador:
        from jugadores.services import crear_jugador
        crear_jugador(persona, **datos_jugador)
    sincronizar_grupos(usuario)
    return empleado


@transaction.atomic
def actualizar_empleado(empleado, *, nombre_completo, cargo, salario, juegos, activo):
    persona = empleado.persona
    persona.nombre_completo = nombre_completo
    persona.save(update_fields=['nombre_completo'])
    empleado.cargo = cargo
    empleado.salario = salario
    empleado.full_clean()
    empleado.save()
    _asignar_competencias(empleado, juegos)
    if hasattr(persona, 'usuario'):
        persona.usuario.is_active = activo
        persona.usuario.save(update_fields=['is_active'])
        sincronizar_grupos(persona.usuario)
    return empleado


@transaction.atomic
def eliminar_empleado(empleado):
    """Solo se elimina un empleado sin asignaciones; si tiene historial se debe desactivar."""
    if empleado.asignaciones_como_crupier.exists() or empleado.asignaciones_como_supervisor.exists():
        raise ValidationError(
            'El empleado tiene asignaciones registradas; no se puede eliminar. Desactive su usuario en su lugar.'
        )
    persona = empleado.persona
    empleado.delete()  # las competencias se eliminan en cascada
    usuario = getattr(persona, 'usuario', None)
    if persona.es_jugador:
        if usuario:
            sincronizar_grupos(usuario)
        return
    if usuario:
        usuario.delete()
    persona.delete()
