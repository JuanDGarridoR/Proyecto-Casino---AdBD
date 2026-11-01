from django import forms

from cuentas.forms import EstiloBootstrapMixin
from cuentas.models import Empleado

from .models import AsignacionMesa, Juego, Mesa, Turno


class JuegoForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Juego
        fields = ['tipo_juego', 'registro_detallado']


class MesaForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Mesa
        fields = ['juego', 'monto_minimo', 'monto_maximo']


class TurnoForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Turno
        fields = ['fecha', 'hora_inicio', 'hora_fin']
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'hora_inicio': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'hora_fin': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
        }


class GenerarTurnosForm(EstiloBootstrapMixin, forms.Form):
    fecha = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    hora_inicio = forms.TimeField(label='Inicio de la jornada', widget=forms.TimeInput(attrs={'type': 'time'}))
    hora_fin = forms.TimeField(label='Fin de la jornada', widget=forms.TimeInput(attrs={'type': 'time'}))
    duracion_minutos = forms.IntegerField(label='Duración de cada turno (minutos)', min_value=1, max_value=120,
                                          initial=120, help_text='Máximo 120 minutos (RN-10).')


class AsignacionForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = AsignacionMesa
        fields = ['turno', 'mesa', 'crupier', 'supervisor']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        empleados = Empleado.objects.select_related('persona').prefetch_related('competencias__juego')
        self.fields['crupier'].queryset = empleados.filter(cargo=Empleado.Cargo.CRUPIER)
        self.fields['supervisor'].queryset = empleados.filter(cargo=Empleado.Cargo.SUPERVISOR)
        etiqueta = lambda e: (f'{e.persona.nombre_completo} — conoce: '
                              f'{", ".join(c.juego.tipo_juego for c in e.competencias.all()) or "ninguno"}')
        self.fields['crupier'].label_from_instance = etiqueta
        self.fields['supervisor'].label_from_instance = etiqueta
        self.fields['mesa'].queryset = Mesa.objects.select_related('juego')


class ConceptoForm(EstiloBootstrapMixin, forms.Form):
    concepto = forms.ChoiceField(label='Concepto del trabajo del crupier', choices=AsignacionMesa.Concepto.choices)
