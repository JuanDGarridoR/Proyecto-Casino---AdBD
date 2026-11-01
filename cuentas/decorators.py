from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

SESION_ROL = 'rol_activo'


def rol_requerido(*roles):
    """
    Restringe la vista a usuarios que tengan alguno de los roles indicados.
    Si el usuario tiene el rol pero está en otro contexto, se cambia el rol activo
    (caso de un empleado que también es jugador).
    """
    def decorador(vista):
        @wraps(vista)
        @login_required
        def envoltura(request, *args, **kwargs):
            roles_usuario = request.user.roles
            permitidos = [r for r in roles_usuario if r in roles]
            if not permitidos:
                messages.error(request, 'No tiene permiso para acceder a esa funcionalidad.')
                return redirect('inicio')
            if request.session.get(SESION_ROL) not in permitidos:
                request.session[SESION_ROL] = permitidos[0]
            return vista(request, *args, **kwargs)
        return envoltura
    return decorador
