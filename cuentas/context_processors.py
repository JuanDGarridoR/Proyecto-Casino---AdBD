from .decorators import SESION_ROL


def navegacion(request):
    """Expone el rol activo y los roles del usuario para armar el menú de base.html."""
    usuario = getattr(request, 'user', None)
    if not usuario or not usuario.is_authenticated:
        return {}
    roles = usuario.roles
    rol_activo = request.session.get(SESION_ROL)
    if rol_activo not in roles:
        rol_activo = roles[0] if roles else None
    no_leidas = 0
    if usuario.persona_id:
        no_leidas = usuario.persona.notificaciones.filter(leida=False).count()
    return {
        'rol_activo': rol_activo,
        'roles_usuario': roles,
        'notificaciones_no_leidas': no_leidas,
    }
