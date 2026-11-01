from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cuentas.decorators import rol_requerido
from cuentas.models import Empleado, Rol
from cuentas.views import texto_error

from . import services
from .forms import MovimientoAdminForm, ObservacionForm, SolicitudMovimientoForm, UmbralForm
from .models import Configuracion, EstadoCuenta, Jugador, Movimiento, Notificacion

jugador_requerido = rol_requerido(Rol.JUGADOR)
admin_requerido = rol_requerido(Rol.ADMINISTRADOR)


def _jugador_actual(request):
    return get_object_or_404(Jugador.objects.select_related('persona'), persona_id=request.user.persona_id)


def _contexto_historial(jugador):
    """Funcionalidad adicional 3: historial completo del cliente."""
    from juego.models import Apuesta
    perdido, ganado = services.totales_juego(jugador)
    empleado = Empleado.objects.filter(persona_id=jugador.pk).first()
    contexto = {
        'jugador': jugador,
        'apuestas': Apuesta.objects.filter(jugador=jugador).select_related('ronda__mesa__juego')
                    .order_by('-ronda__hora_inicio')[:200],
        'movimientos': jugador.movimientos.all()[:200],
        'estados': jugador.historial_estados.all()[:200],
        'perdido': perdido, 'ganado': ganado, 'neto': ganado - perdido,
        'perdidas_hoy': services.perdidas_del_dia(jugador),
        'umbral': Configuracion.umbral_perdida_diaria(),
        'empleado': empleado,
    }
    if empleado:
        contexto['deuda_empleado'] = services.deuda_empleado(jugador)
        contexto['limite_deuda'] = empleado.salario * 2
        contexto['ganancias_empleado'] = services.ganancias_netas_empleado(jugador)
    return contexto


# ---------------------------------------------------------------- vistas del jugador

@jugador_requerido
def panel(request):
    jugador = services.actualizar_estado(_jugador_actual(request).pk)
    contexto = _contexto_historial(jugador)
    contexto['apuestas'] = contexto['apuestas'][:10]
    contexto['notificaciones'] = jugador.persona.notificaciones.filter(leida=False)[:5]
    return render(request, 'jugadores/panel.html', contexto)


@jugador_requerido
def pausa(request):
    jugador = _jugador_actual(request)
    if request.method == 'POST':
        try:
            services.solicitar_pausa(jugador)
            messages.success(request, 'Su cuenta quedó suspendida por 24 horas. Puede seguir consultando su saldo.')
        except ValidationError as e:
            messages.error(request, texto_error(e))
        return redirect('jugadores:panel')
    return render(request, 'confirmar.html', {
        'titulo': 'Solicitar pausa voluntaria (autoexclusión)',
        'mensaje': 'Su cuenta pasará a estado Suspendido y no podrá apostar en ninguna mesa durante las '
                   'siguientes 24 horas. Esta acción no se puede deshacer.',
        'volver': 'jugadores:panel', 'boton': 'Confirmar pausa', 'boton_clase': 'warning',
    })


@jugador_requerido
def mis_movimientos(request):
    jugador = _jugador_actual(request)
    form = SolicitudMovimientoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            services.solicitar_movimiento(jugador, **form.cleaned_data)
        except ValidationError as e:
            form.add_error(None, e)
        else:
            messages.success(request, 'Solicitud registrada; queda pendiente de aprobación por la caja.')
            return redirect('jugadores:mis_movimientos')
    return render(request, 'jugadores/mis_movimientos.html', {
        'jugador': jugador, 'form': form, 'movimientos': jugador.movimientos.all(),
    })


@jugador_requerido
@require_POST
def cancelar_movimiento(request, pk):
    movimiento = get_object_or_404(Movimiento, pk=pk, jugador__persona_id=request.user.persona_id)
    try:
        services.eliminar_movimiento(movimiento)
        messages.success(request, 'Solicitud cancelada.')
    except ValidationError as e:
        messages.error(request, texto_error(e))
    return redirect('jugadores:mis_movimientos')


@jugador_requerido
def mi_historial(request):
    jugador = services.actualizar_estado(_jugador_actual(request).pk)
    return render(request, 'jugadores/historial.html', _contexto_historial(jugador))


@login_required
def notificaciones(request):
    lista = Notificacion.objects.filter(persona_id=request.user.persona_id)
    if request.method == 'POST':
        lista.filter(leida=False).update(leida=True)
        messages.info(request, 'Notificaciones marcadas como leídas.')
        return redirect('jugadores:notificaciones')
    return render(request, 'jugadores/notificaciones.html', {'notificaciones': lista[:100]})


# ---------------------------------------------------------------- vistas del administrador

@admin_requerido
def jugadores_lista(request):
    estado = request.GET.get('estado', '')
    jugadores = Jugador.objects.select_related('persona__empleado')
    if estado in EstadoCuenta.values:
        jugadores = jugadores.filter(estado=estado)
    return render(request, 'jugadores/jugadores_lista.html', {
        'jugadores': jugadores, 'estado': estado, 'estados': EstadoCuenta.values,
    })


@admin_requerido
def jugador_historial(request, pk):
    jugador = services.actualizar_estado(get_object_or_404(Jugador, pk=pk).pk)
    contexto = _contexto_historial(jugador)
    contexto['vista_admin'] = True
    return render(request, 'jugadores/historial.html', contexto)


@admin_requerido
def cerrar_investigacion(request, pk):
    jugador = get_object_or_404(Jugador.objects.select_related('persona'), pk=pk)
    form = ObservacionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            jugador = services.cerrar_investigacion(jugador, form.cleaned_data['observacion'])
            messages.success(request, f'Investigación cerrada. Estado actual: {jugador.estado}.')
        except ValidationError as e:
            messages.error(request, texto_error(e))
        return redirect('jugadores:historial', pk=pk)
    return render(request, 'form.html', {
        'titulo': f'Cerrar investigación de {jugador}', 'form': form, 'volver': 'jugadores:lista',
        'ayuda': 'Al cerrar la investigación el empleado vuelve a estar Activo y sus ganancias se cuentan '
                 'de nuevo desde cero (RN-30).',
    })


@admin_requerido
def movimientos(request):
    pendientes = Movimiento.objects.filter(estado=Movimiento.Estado.PENDIENTE).select_related('jugador__persona')
    recientes = Movimiento.objects.exclude(estado=Movimiento.Estado.PENDIENTE).select_related('jugador__persona')[:100]
    return render(request, 'jugadores/movimientos_admin.html', {'pendientes': pendientes, 'recientes': recientes})


@admin_requerido
def movimiento_nuevo(request):
    form = MovimientoAdminForm(request.POST or None, initial={'jugador': request.GET.get('jugador')})
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        try:
            services.registrar_movimiento(d['jugador'], d['tipo'], d['monto'], d['observacion'])
        except ValidationError as e:
            form.add_error(None, e)
        else:
            messages.success(request, 'Movimiento registrado y aplicado al saldo.')
            return redirect('jugadores:movimientos')
    return render(request, 'form.html', {'titulo': 'Registrar consignación o retiro', 'form': form,
                                         'volver': 'jugadores:movimientos'})


@admin_requerido
def movimiento_editar(request, pk):
    movimiento = get_object_or_404(Movimiento.objects.select_related('jugador'), pk=pk)
    form = SolicitudMovimientoForm(request.POST or None, initial={
        'tipo': movimiento.tipo, 'monto': movimiento.monto, 'observacion': movimiento.observacion,
    })
    if request.method == 'POST' and form.is_valid():
        try:
            services.modificar_movimiento(movimiento, **form.cleaned_data)
        except ValidationError as e:
            form.add_error(None, e)
        else:
            messages.success(request, 'Solicitud modificada.')
            return redirect('jugadores:movimientos')
    return render(request, 'form.html', {'titulo': f'Modificar solicitud de {movimiento.jugador}', 'form': form,
                                         'volver': 'jugadores:movimientos'})


@admin_requerido
@require_POST
def movimiento_accion(request, pk, accion):
    movimiento = get_object_or_404(Movimiento, pk=pk)
    acciones = {
        'aprobar': (services.aprobar_movimiento, 'Movimiento aprobado y aplicado al saldo.'),
        'rechazar': (services.rechazar_movimiento, 'Movimiento rechazado.'),
        'eliminar': (services.eliminar_movimiento, 'Solicitud eliminada.'),
    }
    if accion not in acciones:
        return redirect('jugadores:movimientos')
    funcion, mensaje = acciones[accion]
    try:
        funcion(movimiento)
        messages.success(request, mensaje)
    except ValidationError as e:
        messages.error(request, texto_error(e))
    return redirect('jugadores:movimientos')


@admin_requerido
def configuracion(request):
    form = UmbralForm(request.POST or None, initial={'umbral': Configuracion.umbral_perdida_diaria()})
    if request.method == 'POST' and form.is_valid():
        Configuracion.objects.update_or_create(
            clave=Configuracion.UMBRAL_PERDIDA_DIARIA, defaults={'valor': str(form.cleaned_data['umbral'])},
        )
        messages.success(request, 'Umbral diario de pérdidas actualizado.')
        return redirect('jugadores:configuracion')
    return render(request, 'form.html', {'titulo': 'Configuración: umbral diario de pérdidas', 'form': form,
                                         'volver': 'cuentas:panel_admin'})
