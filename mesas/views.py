from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, ProtectedError, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from cuentas.decorators import rol_requerido
from cuentas.models import Rol
from cuentas.views import texto_error

from . import services
from .forms import AsignacionForm, ConceptoForm, GenerarTurnosForm, JuegoForm, MesaForm, TurnoForm
from .models import AsignacionMesa, Juego, Mesa, Turno

admin_requerido = rol_requerido(Rol.ADMINISTRADOR)


def _guardar(request, form, mensaje, destino, titulo, volver, **destino_kwargs):
    """Patrón común de crear/editar con ModelForm (valida clean() y constraints del modelo)."""
    if request.method == 'POST' and form.is_valid():
        objeto = form.save()
        messages.success(request, mensaje)
        return redirect(destino, **{k: getattr(objeto, v) for k, v in destino_kwargs.items()})
    return render(request, 'form.html', {'titulo': titulo, 'form': form, 'volver': volver})


def _eliminar(request, objeto, volver, descripcion):
    if request.method == 'POST':
        try:
            objeto.delete()
            messages.success(request, f'{descripcion} eliminado(a).')
        except ProtectedError:
            messages.error(request, f'No se puede eliminar {descripcion}: tiene registros asociados.')
        return redirect(volver)
    return render(request, 'confirmar.html', {
        'titulo': f'Eliminar {descripcion}', 'mensaje': f'¿Confirma que desea eliminar {objeto}?', 'volver': volver,
    })


# ---------------------------------------------------------------- juegos

@admin_requerido
def juegos_lista(request):
    juegos = Juego.objects.annotate(num_mesas=Count('mesas', distinct=True),
                                    num_empleados=Count('competencias', distinct=True))
    return render(request, 'mesas/juegos_lista.html', {'juegos': juegos})


@admin_requerido
def juego_crear(request):
    return _guardar(request, JuegoForm(request.POST or None), 'Juego creado.', 'mesas:juegos',
                    'Nuevo juego', 'mesas:juegos')


@admin_requerido
def juego_editar(request, pk):
    juego = get_object_or_404(Juego, pk=pk)
    return _guardar(request, JuegoForm(request.POST or None, instance=juego), 'Juego actualizado.',
                    'mesas:juegos', f'Editar {juego}', 'mesas:juegos')


@admin_requerido
def juego_eliminar(request, pk):
    return _eliminar(request, get_object_or_404(Juego, pk=pk), 'mesas:juegos', 'el juego')


# ---------------------------------------------------------------- mesas (caso de uso 3.1)

@admin_requerido
def mesas_lista(request):
    mesas = Mesa.objects.select_related('juego').annotate(
        num_rondas=Count('rondas', distinct=True),
        abiertas=Count('rondas', filter=Q(rondas__hora_cierre__isnull=True), distinct=True),
    )
    vigentes = {m.pk: services.asignacion_vigente(m) for m in mesas}
    filas = [(m, vigentes[m.pk]) for m in mesas]
    return render(request, 'mesas/mesas_lista.html', {'filas': filas})


@admin_requerido
def mesa_crear(request):
    return _guardar(request, MesaForm(request.POST or None), 'Mesa creada.', 'mesas:mesas',
                    'Nueva mesa', 'mesas:mesas')


@admin_requerido
def mesa_editar(request, pk):
    mesa = get_object_or_404(Mesa, pk=pk)
    return _guardar(request, MesaForm(request.POST or None, instance=mesa), 'Mesa actualizada.',
                    'mesas:mesas', f'Editar {mesa}', 'mesas:mesas')


@admin_requerido
def mesa_eliminar(request, pk):
    return _eliminar(request, get_object_or_404(Mesa, pk=pk), 'mesas:mesas', 'la mesa')


# ---------------------------------------------------------------- turnos

@admin_requerido
def turnos_lista(request):
    turnos = Turno.objects.annotate(num_asignaciones=Count('asignaciones'))[:200]
    return render(request, 'mesas/turnos_lista.html', {'turnos': turnos, 'ahora': timezone.localtime()})


@admin_requerido
def turno_crear(request):
    return _guardar(request, TurnoForm(request.POST or None, initial={'fecha': timezone.localdate()}),
                    'Turno creado.', 'mesas:turno_detalle', 'Nuevo turno', 'mesas:turnos', pk='pk')


@admin_requerido
def turno_generar(request):
    form = GenerarTurnosForm(request.POST or None, initial={'fecha': timezone.localdate()})
    if request.method == 'POST' and form.is_valid():
        try:
            creados = services.generar_turnos(**form.cleaned_data)
        except ValidationError as e:
            form.add_error(None, e)
        else:
            messages.success(request, f'Se crearon {len(creados)} turnos.')
            return redirect('mesas:turnos')
    return render(request, 'form.html', {
        'titulo': 'Definir los turnos de un día', 'form': form, 'volver': 'mesas:turnos',
        'ayuda': 'Crea turnos consecutivos con la duración indicada entre el inicio y el fin de la jornada.',
    })


@admin_requerido
def turno_editar(request, pk):
    turno = get_object_or_404(Turno, pk=pk)
    return _guardar(request, TurnoForm(request.POST or None, instance=turno), 'Turno actualizado.',
                    'mesas:turno_detalle', f'Editar turno {turno}', 'mesas:turnos', pk='pk')


@admin_requerido
def turno_eliminar(request, pk):
    return _eliminar(request, get_object_or_404(Turno, pk=pk), 'mesas:turnos', 'el turno')


@admin_requerido
def turno_detalle(request, pk):
    turno = get_object_or_404(Turno, pk=pk)
    asignaciones = turno.asignaciones.select_related('mesa__juego', 'crupier__persona', 'supervisor__persona')
    sin_asignar = Mesa.objects.exclude(asignaciones__turno=turno).select_related('juego')
    return render(request, 'mesas/turno_detalle.html', {
        'turno': turno, 'asignaciones': asignaciones, 'sin_asignar': sin_asignar,
    })


# ---------------------------------------------------------------- asignaciones

@admin_requerido
def asignacion_crear(request):
    inicial = {k: request.GET[k] for k in ('turno', 'mesa') if k in request.GET}
    form = AsignacionForm(request.POST or None, initial=inicial)
    return _guardar(request, form, 'Asignación registrada.', 'mesas:turno_detalle',
                    'Asignar crupier y supervisor a una mesa', 'mesas:turnos', pk='turno_id')


@admin_requerido
def asignacion_editar(request, pk):
    asignacion = get_object_or_404(AsignacionMesa, pk=pk)
    form = AsignacionForm(request.POST or None, instance=asignacion)
    return _guardar(request, form, 'Asignación actualizada.', 'mesas:turno_detalle',
                    f'Editar asignación {asignacion}', 'mesas:turnos', pk='turno_id')


@admin_requerido
def asignacion_eliminar(request, pk):
    return _eliminar(request, get_object_or_404(AsignacionMesa, pk=pk), 'mesas:turnos', 'la asignación')


# ---------------------------------------------------------------- supervisión (RN-11, RN-12)

def _resumen_asignacion(asignacion):
    """Rondas y totales de la mesa durante el turno: insumo para que el supervisor forme su criterio."""
    from juego.models import Ronda
    rondas = (Ronda.objects.filter(mesa=asignacion.mesa, hora_inicio__gte=asignacion.turno.inicio_dt,
                                   hora_inicio__lt=asignacion.turno.fin_dt)
              .annotate(apostado=Sum('apuestas__monto_apostado'), pagado=Sum('apuestas__premio'),
                        num_apuestas=Count('apuestas'))
              .order_by('numero'))
    apostado = sum((r.apostado or 0) for r in rondas)
    pagado = sum((r.pagado or 0) for r in rondas)
    return rondas, apostado, pagado


@rol_requerido(Rol.SUPERVISOR)
def supervision(request):
    supervisor = getattr(request.user.persona, 'empleado', None) if request.user.persona_id else None
    if supervisor is None:
        messages.error(request, 'Su usuario no está vinculado a un empleado.')
        return redirect('inicio')
    asignaciones = (AsignacionMesa.objects.filter(supervisor=supervisor)
                    .select_related('turno', 'mesa__juego', 'crupier__persona')
                    .order_by('-turno__fecha', '-turno__hora_inicio'))[:100]
    return render(request, 'mesas/supervision.html', {'asignaciones': asignaciones})


@rol_requerido(Rol.SUPERVISOR)
def supervision_detalle(request, pk):
    asignacion = get_object_or_404(
        AsignacionMesa.objects.select_related('turno', 'mesa__juego', 'crupier__persona', 'supervisor__persona'),
        pk=pk, supervisor__persona=request.user.persona,
    )
    rondas, apostado, pagado = _resumen_asignacion(asignacion)
    form = ConceptoForm(request.POST or None, initial={'concepto': asignacion.concepto_supervisor})
    if request.method == 'POST' and form.is_valid():
        try:
            services.emitir_concepto(asignacion, asignacion.supervisor, form.cleaned_data['concepto'])
        except ValidationError as e:
            messages.error(request, texto_error(e))
        else:
            messages.success(request, 'Concepto registrado.')
        return redirect('mesas:supervision_detalle', pk=pk)
    return render(request, 'mesas/supervision_detalle.html', {
        'asignacion': asignacion, 'rondas': rondas, 'apostado': apostado, 'pagado': pagado, 'form': form,
    })
