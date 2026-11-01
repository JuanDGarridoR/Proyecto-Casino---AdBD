from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from cuentas.decorators import rol_requerido
from cuentas.models import Rol
from cuentas.views import texto_error
from jugadores.models import Jugador
from mesas.models import Mesa
from mesas.services import asignacion_vigente, asignaciones_del_dia

from . import services
from .forms import ApuestaEditarForm, ApuestaForm, ApuestasAlResultadoFormSet, CerrarRondaForm
from .models import Apuesta, Ronda

crupier_requerido = rol_requerido(Rol.CRUPIER)
CERO = Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))


def _crupier(request):
    persona = request.user.persona
    return getattr(persona, 'empleado', None) if persona else None


def _sugerencias(juego):
    return services.SUGERENCIAS.get(services.clave_juego(juego), [])


@crupier_requerido
def mis_mesas(request):
    crupier = _crupier(request)
    if crupier is None:
        messages.error(request, 'Su usuario no está vinculado a un empleado.')
        return redirect('inicio')
    asignaciones = list(asignaciones_del_dia(crupier=crupier))
    vigente = next((a for a in asignaciones if a.turno.en_curso), None)
    return render(request, 'juego/mis_mesas.html', {'asignaciones': asignaciones, 'vigente': vigente})


@crupier_requerido
def panel_mesa(request, pk):
    mesa = get_object_or_404(Mesa.objects.select_related('juego'), pk=pk)
    asignacion = asignacion_vigente(mesa)
    es_mi_turno = asignacion is not None and asignacion.crupier_id == getattr(_crupier(request), 'pk', None)
    ronda = mesa.rondas.filter(hora_cierre__isnull=True).first()
    apuestas = ronda.apuestas.select_related('jugador__persona') if ronda else []
    contexto = {
        'mesa': mesa, 'asignacion': asignacion, 'es_mi_turno': es_mi_turno, 'ronda': ronda, 'apuestas': apuestas,
        'form_apuesta': ApuestaForm(), 'form_cerrar': CerrarRondaForm(),
        'sugerencias': _sugerencias(mesa.juego),
        'historial': mesa.rondas.filter(hora_cierre__isnull=False).annotate(
            num_apuestas=Count('apuestas'), apostado=Sum('apuestas__monto_apostado'),
            pagado=Sum('apuestas__premio'))[:15],
    }
    return render(request, 'juego/panel_mesa.html', contexto)


@crupier_requerido
@require_POST
def abrir_ronda(request, pk):
    mesa = get_object_or_404(Mesa, pk=pk)
    try:
        ronda = services.abrir_ronda(mesa, _crupier(request))
        messages.success(request, f'Ronda #{ronda.numero} abierta.')
    except ValidationError as e:
        messages.error(request, texto_error(e))
    return redirect('juego:panel_mesa', pk=pk)


@crupier_requerido
@require_POST
def ronda_eliminar(request, pk):
    ronda = get_object_or_404(Ronda, pk=pk)
    try:
        services.eliminar_ronda(ronda, _crupier(request))
        messages.success(request, 'Ronda eliminada.')
    except ValidationError as e:
        messages.error(request, texto_error(e))
    return redirect('juego:panel_mesa', pk=ronda.mesa_id)


@crupier_requerido
@require_POST
def registrar_apuesta(request, pk):
    ronda = get_object_or_404(Ronda, pk=pk)
    form = ApuestaForm(request.POST)
    if form.is_valid():
        d = form.cleaned_data
        try:
            apuesta = services.registrar_apuesta(ronda, d['jugador'], d['tipo_apuesta'], d['monto_apostado'],
                                                 d['factor_pago'], _crupier(request))
            messages.success(request, f'Apuesta registrada: {apuesta}.')
        except ValidationError as e:
            messages.error(request, texto_error(e))
    else:
        messages.error(request, 'Datos de la apuesta inválidos: ' + '; '.join(
            f'{campo}: {" ".join(errs)}' for campo, errs in form.errors.items()))
    return redirect('juego:panel_mesa', pk=ronda.mesa_id)


@crupier_requerido
def apuesta_editar(request, pk):
    apuesta = get_object_or_404(Apuesta.objects.select_related('ronda__mesa__juego', 'jugador__persona'), pk=pk)
    form = ApuestaEditarForm(request.POST or None, initial={
        'tipo_apuesta': apuesta.tipo_apuesta, 'monto_apostado': apuesta.monto_apostado,
        'factor_pago': apuesta.factor_pago,
    })
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        try:
            services.modificar_apuesta(apuesta, d['tipo_apuesta'], d['monto_apostado'], d['factor_pago'],
                                       _crupier(request))
        except ValidationError as e:
            form.add_error(None, e)
        else:
            messages.success(request, 'Apuesta modificada.')
            return redirect('juego:panel_mesa', pk=apuesta.ronda.mesa_id)
    return render(request, 'form.html', {
        'titulo': f'Modificar apuesta de {apuesta.jugador}', 'form': form,
        'volver_url': redirect('juego:panel_mesa', pk=apuesta.ronda.mesa_id).url,
        'sugerencias': _sugerencias(apuesta.ronda.mesa.juego),
    })


@crupier_requerido
def apuesta_anular(request, pk):
    apuesta = get_object_or_404(Apuesta.objects.select_related('ronda'), pk=pk)
    volver = redirect('juego:panel_mesa', pk=apuesta.ronda.mesa_id)
    if request.method == 'POST':
        try:
            services.anular_apuesta(apuesta, _crupier(request))
            messages.success(request, 'Apuesta anulada y monto devuelto al jugador.')
        except ValidationError as e:
            messages.error(request, texto_error(e))
        return volver
    return render(request, 'confirmar.html', {
        'titulo': 'Anular apuesta', 'mensaje': f'¿Anular la apuesta {apuesta}? El monto se devuelve al jugador.',
        'volver_url': volver.url,
    })


@crupier_requerido
def cerrar_ronda(request, pk):
    ronda = get_object_or_404(Ronda.objects.select_related('mesa__juego'), pk=pk)
    sin_detalle = not ronda.mesa.juego.registro_detallado
    form = CerrarRondaForm(request.POST or None)
    formset = ApuestasAlResultadoFormSet(request.POST or None, prefix='ap') if sin_detalle else None
    if request.method == 'POST' and form.is_valid() and (formset is None or formset.is_valid()):
        apuestas = []
        if formset is not None:
            apuestas = [f.cleaned_data for f in formset if f.cleaned_data.get('jugador')]
        try:
            ronda = services.cerrar_ronda(ronda, form.cleaned_data['resultado'], _crupier(request), apuestas)
        except ValidationError as e:
            messages.error(request, texto_error(e))
        else:
            ganadas = ronda.apuestas.filter(estado=Apuesta.Estado.GANADA).count()
            messages.success(request, f'Ronda #{ronda.numero} cerrada con resultado "{ronda.resultado}". '
                                      f'{ganadas} apuesta(s) ganadora(s) de {ronda.apuestas.count()}.')
            return redirect('juego:ronda_detalle', pk=ronda.pk)
    return render(request, 'juego/cerrar_ronda.html', {
        'ronda': ronda, 'form': form, 'formset': formset, 'sin_detalle': sin_detalle,
        'apuestas': ronda.apuestas.select_related('jugador__persona'),
        'sugerencias': _sugerencias(ronda.mesa.juego),
    })


@rol_requerido(Rol.CRUPIER, Rol.ADMINISTRADOR, Rol.SUPERVISOR)
def ronda_detalle(request, pk):
    ronda = get_object_or_404(Ronda.objects.select_related('mesa__juego'), pk=pk)
    apuestas = ronda.apuestas.select_related('jugador__persona')
    totales = apuestas.aggregate(apostado=Sum('monto_apostado'), pagado=Sum('premio'),
                                 perdido=Sum('monto_apostado', filter=Q(estado=Apuesta.Estado.PERDIDA)))
    return render(request, 'juego/ronda_detalle.html', {'ronda': ronda, 'apuestas': apuestas, 'totales': totales})


@rol_requerido(Rol.ADMINISTRADOR)
def reporte_ganancias(request):
    """Caso de uso 3.4: ganancias del casino y de los jugadores."""
    try:
        dias = max(1, min(365, int(request.GET.get('dias', 30))))
    except ValueError:
        dias = 30
    desde = timezone.now() - timedelta(days=dias)
    cerradas = Apuesta.objects.exclude(estado=Apuesta.Estado.PENDIENTE).filter(ronda__hora_cierre__gte=desde)
    perdidas = Q(estado=Apuesta.Estado.PERDIDA)
    por_mesa = (cerradas.values('ronda__mesa__id_mesa', 'ronda__mesa__juego__tipo_juego')
                .annotate(apostado=Sum('monto_apostado'), pagado=Coalesce(Sum('premio'), CERO),
                          retenido=Coalesce(Sum('monto_apostado', filter=perdidas), CERO),
                          num=Count('id_apuesta'))
                .order_by('ronda__mesa__id_mesa'))
    por_dia = (cerradas.annotate(dia=TruncDate('ronda__hora_cierre'))
               .values('dia')
               .annotate(pagado=Coalesce(Sum('premio'), CERO),
                         retenido=Coalesce(Sum('monto_apostado', filter=perdidas), CERO))
               .order_by('-dia'))
    en_periodo = Q(apuestas__ronda__hora_cierre__gte=desde)
    por_jugador = (Jugador.objects.select_related('persona')
                   .annotate(ganado=Coalesce(Sum('apuestas__premio', filter=en_periodo), CERO),
                             perdido=Coalesce(Sum('apuestas__monto_apostado',
                                                  filter=en_periodo & Q(apuestas__estado=Apuesta.Estado.PERDIDA)), CERO))
                   .order_by('codigo_cliente'))
    for fila in por_mesa:
        fila['utilidad'] = fila['retenido'] - fila['pagado']
    for fila in por_dia:
        fila['utilidad'] = fila['retenido'] - fila['pagado']
    for j in por_jugador:
        j.neto = j.ganado - j.perdido
    total_retenido = sum(f['retenido'] for f in por_mesa)
    total_pagado = sum(f['pagado'] for f in por_mesa)
    return render(request, 'juego/reporte_ganancias.html', {
        'por_mesa': por_mesa, 'por_dia': por_dia, 'por_jugador': por_jugador, 'dias': dias,
        'opciones_dias': [1, 7, 30, 90, 365],
        'total_retenido': total_retenido, 'total_pagado': total_pagado,
        'utilidad': total_retenido - total_pagado,
    })
