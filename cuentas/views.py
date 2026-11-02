import hmac
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from jugadores import services as jugadores_services
from jugadores.models import EstadoCuenta, Jugador, Movimiento

from . import services
from .backends import SESION_NONCE, SESION_USUARIO
from .decorators import SESION_ROL, rol_requerido
from .forms import EmpleadoCrearForm, EmpleadoEditarForm, HabilitarJugadorForm, RegistroJugadorForm
from .models import Empleado, Rol, Usuario, generar_salt

SESION_SALT_REGISTRO = 'zk_salt_registro'

PANEL_POR_ROL = {
    Rol.ADMINISTRADOR: 'cuentas:panel_admin',
    Rol.SUPERVISOR: 'mesas:supervision',
    Rol.CRUPIER: 'juego:mis_mesas',
    Rol.JUGADOR: 'jugadores:panel',
}


def texto_error(error):
    return ' '.join(error.messages) if isinstance(error, ValidationError) else str(error)


def _salt_registro(request, renovar=False):
    """Salt generado por el servidor para un nuevo usuario; el navegador calcula SHA256(salt + password)."""
    if renovar or SESION_SALT_REGISTRO not in request.session:
        request.session[SESION_SALT_REGISTRO] = generar_salt()
    return request.session[SESION_SALT_REGISTRO]


# ---------------------------------------------------------------- autenticación Zero Knowledge

@login_required
def inicio(request):
    roles = request.user.roles
    if not roles:
        messages.warning(request, 'Su usuario no tiene roles asignados.')
        return render(request, 'base.html')
    rol = request.session.get(SESION_ROL)
    if rol not in roles:
        rol = request.session[SESION_ROL] = roles[0]
    return redirect(PANEL_POR_ROL[rol])


@require_POST
def desafio(request):
    """Paso 1 del login: devuelve el salt del usuario y un nonce aleatorio de un solo uso."""
    username = request.POST.get('username', '').strip()
    usuario = Usuario.objects.filter(username=username).first()
    if usuario:
        salt = usuario.salt
    else:
        # Salt ficticio pero estable: no revela si el usuario existe.
        salt = hmac.new(settings.SECRET_KEY.encode(), username.encode(), 'sha256').hexdigest()[:32]
    nonce = secrets.token_hex(32)
    request.session[SESION_NONCE] = nonce
    request.session[SESION_USUARIO] = username
    return JsonResponse({'salt': salt, 'nonce': nonce})


def login_view(request):
    """Paso 2 del login: recibe R = SHA256(H + nonce); nunca la contraseña."""
    if request.user.is_authenticated:
        return redirect('inicio')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        usuario = authenticate(request, username=username, respuesta=request.POST.get('respuesta', ''))
        if usuario:
            login(request, usuario)
            roles = usuario.roles
            request.session[SESION_ROL] = roles[0] if roles else None
            messages.success(request, f'Bienvenido(a), {usuario.nombre_visible}.')
            siguiente = request.GET.get('next', '')
            if url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}):
                return redirect(siguiente)
            return redirect('inicio')
        messages.error(request, 'Usuario o contraseña incorrectos.')
    return render(request, 'cuentas/login.html')


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, 'Sesión cerrada.')
    return redirect('cuentas:login')


def registro(request):
    """Registro público de jugadores (RN-01, RN-02, RN-03)."""
    form = RegistroJugadorForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        datos = form.cleaned_data
        try:
            jugadores_services.registrar_jugador(
                username=datos['username'], documento=datos['documento'],
                nombre_completo=datos['nombre_completo'], salt=_salt_registro(request),
                password_hash=datos['password_hash'], codigo_cliente=datos['codigo_cliente'],
                edad=datos['edad'], saldo_inicial=datos['saldo_inicial'] or 0,
            )
        except ValidationError as e:
            form.add_error(None, e)
        else:
            request.session.pop(SESION_SALT_REGISTRO, None)
            messages.success(request, 'Registro exitoso. Ya puede iniciar sesión.')
            return redirect('cuentas:login')
    return render(request, 'cuentas/registro.html', {'form': form, 'salt': _salt_registro(request)})


@login_required
def cambiar_rol(request, rol):
    if rol in request.user.roles:
        request.session[SESION_ROL] = rol
        messages.info(request, f'Ahora está usando el sistema como {rol}.')
    else:
        messages.error(request, 'No tiene ese rol.')
    return redirect('inicio')


# ---------------------------------------------------------------- panel del administrador

@rol_requerido(Rol.ADMINISTRADOR)
def panel_admin(request):
    from juego.models import Apuesta, Ronda
    from mesas.models import Mesa
    from mesas.services import asignaciones_del_dia
    hoy = timezone.localdate()
    contexto = {
        'total_mesas': Mesa.objects.count(),
        'total_empleados': Empleado.objects.count(),
        'total_jugadores': Jugador.objects.count(),
        'suspendidos': Jugador.objects.filter(estado=EstadoCuenta.SUSPENDIDO).select_related('persona'),
        'investigacion': Jugador.objects.filter(estado=EstadoCuenta.INVESTIGACION).select_related('persona'),
        'movimientos_pendientes': Movimiento.objects.filter(estado=Movimiento.Estado.PENDIENTE).count(),
        'rondas_abiertas': Ronda.objects.filter(hora_cierre__isnull=True).select_related('mesa__juego'),
        'asignaciones_hoy': asignaciones_del_dia(fecha=hoy),
        'apostado_total': Apuesta.objects.aggregate(s=Sum('monto_apostado'))['s'] or 0,
    }
    return render(request, 'cuentas/panel_admin.html', contexto)


# ---------------------------------------------------------------- gestión de empleados

@rol_requerido(Rol.ADMINISTRADOR)
def empleados_lista(request):
    empleados = (Empleado.objects.select_related('persona__usuario', 'persona__jugador')
                 .prefetch_related('competencias__juego'))
    return render(request, 'cuentas/empleados_lista.html', {'empleados': empleados})


@rol_requerido(Rol.ADMINISTRADOR)
def empleado_crear(request):
    form = EmpleadoCrearForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        datos_jugador = None
        if d['tambien_jugador']:
            datos_jugador = {'codigo_cliente': d['codigo_cliente'], 'edad': d['edad'],
                             'saldo_inicial': d['saldo_inicial'] or 0}
        try:
            empleado = services.crear_empleado(
                username=d['username'], documento=d['documento'], nombre_completo=d['nombre_completo'],
                salt=_salt_registro(request), password_hash=d['password_hash'], cargo=d['cargo'],
                salario=d['salario'], juegos=d['juegos'], datos_jugador=datos_jugador,
            )
        except ValidationError as e:
            form.add_error(None, e)
        else:
            request.session.pop(SESION_SALT_REGISTRO, None)
            messages.success(request, f'Empleado {empleado} registrado.')
            return redirect('cuentas:empleados')
    return render(request, 'cuentas/empleado_crear.html', {'form': form, 'salt': _salt_registro(request)})


@rol_requerido(Rol.ADMINISTRADOR)
def empleado_editar(request, pk):
    empleado = get_object_or_404(Empleado.objects.select_related('persona'), pk=pk)
    usuario = getattr(empleado.persona, 'usuario', None)
    inicial = {
        'nombre_completo': empleado.persona.nombre_completo, 'cargo': empleado.cargo,
        'salario': empleado.salario, 'juegos': [c.juego for c in empleado.competencias.all()],
        'activo': usuario.is_active if usuario else False,
    }
    form = EmpleadoEditarForm(request.POST or None, initial=inicial)
    if request.method == 'POST' and form.is_valid():
        try:
            services.actualizar_empleado(empleado, **form.cleaned_data)
        except ValidationError as e:
            form.add_error(None, e)
        else:
            messages.success(request, 'Empleado actualizado.')
            return redirect('cuentas:empleados')
    return render(request, 'form.html', {
        'titulo': f'Editar empleado: {empleado.persona.nombre_completo}', 'form': form,
        'volver': 'cuentas:empleados',
    })


@rol_requerido(Rol.ADMINISTRADOR)
def empleado_eliminar(request, pk):
    empleado = get_object_or_404(Empleado, pk=pk)
    if request.method == 'POST':
        try:
            services.eliminar_empleado(empleado)
        except ValidationError as e:
            messages.error(request, texto_error(e))
        else:
            messages.success(request, 'Empleado eliminado.')
        return redirect('cuentas:empleados')
    return render(request, 'confirmar.html', {
        'titulo': 'Eliminar empleado',
        'mensaje': f'¿Eliminar a {empleado}? Solo es posible si no tiene asignaciones.',
        'volver': 'cuentas:empleados',
    })


@rol_requerido(Rol.ADMINISTRADOR)
def empleado_habilitar_jugador(request, pk):
    empleado = get_object_or_404(Empleado.objects.select_related('persona'), pk=pk)
    form = HabilitarJugadorForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            jugadores_services.habilitar_empleado_como_jugador(empleado, **form.cleaned_data)
        except ValidationError as e:
            form.add_error(None, e)
        else:
            messages.success(request, f'{empleado.persona.nombre_completo} ahora también puede jugar.')
            return redirect('cuentas:empleados')
    return render(request, 'form.html', {
        'titulo': f'Registrar a {empleado.persona.nombre_completo} como jugador', 'form': form,
        'volver': 'cuentas:empleados',
    })
