import re

from django import forms
from django.conf import settings

from mesas.models import Juego

from .models import Empleado, Persona, Usuario


class CasillasMultiples(forms.CheckboxSelectMultiple):
    """Casillas múltiples cuya clase CSS va solo en cada casilla, no en el contenedor."""

    def get_context(self, name, value, attrs):
        contexto = super().get_context(name, value, attrs)
        contexto['widget']['attrs'].pop('class', None)
        return contexto


class EstiloBootstrapMixin:
    """Agrega las clases de Bootstrap a los widgets de cualquier formulario."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            widget = campo.widget
            if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                clase = 'form-check-input'
            elif isinstance(widget, forms.Select):
                clase = 'form-select'
            else:
                clase = 'form-control'
            widget.attrs.setdefault('class', clase)


class HashZeroKnowledgeMixin(forms.Form):
    """
    Campo oculto con H = SHA256(salt + password) calculado en el navegador (static/js/zk.js).
    La contraseña en claro está en inputs SIN atributo `name`, así que nunca se envía.
    """
    password_hash = forms.CharField(widget=forms.HiddenInput, required=True)

    def clean_password_hash(self):
        valor = self.cleaned_data['password_hash'].lower()
        if not re.fullmatch(r'[0-9a-f]{64}', valor):
            raise forms.ValidationError('No se pudo procesar la contraseña. ¿Tiene JavaScript habilitado?')
        return valor


class DatosPersonaMixin(forms.Form):
    username = forms.CharField(label='Usuario', max_length=50)
    documento = forms.CharField(label='Documento de identidad', max_length=20)
    nombre_completo = forms.CharField(label='Nombre completo', max_length=100)

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if Usuario.objects.filter(username=username).exists():
            raise forms.ValidationError('Ese nombre de usuario ya existe.')
        return username

    def clean_documento(self):
        documento = self.cleaned_data['documento'].strip()
        if Persona.objects.filter(documento=documento).exists():
            raise forms.ValidationError('Ya existe una persona con ese documento.')
        return documento


def validar_codigo_cliente(codigo):
    from jugadores.models import Jugador
    codigo = codigo.strip().upper()
    if Jugador.objects.filter(codigo_cliente=codigo).exists():
        raise forms.ValidationError('Ese código de cliente ya está registrado.')
    return codigo


def validar_edad(edad):
    if edad is not None and edad < settings.CASINO_EDAD_MINIMA:
        raise forms.ValidationError(
            f'No se permite el registro de menores de edad (mínimo {settings.CASINO_EDAD_MINIMA} años).'
        )
    return edad


class RegistroJugadorForm(EstiloBootstrapMixin, DatosPersonaMixin, HashZeroKnowledgeMixin):
    codigo_cliente = forms.CharField(label='Código de cliente', max_length=20)
    edad = forms.IntegerField(label='Edad', min_value=0, max_value=120)
    saldo_inicial = forms.DecimalField(label='Saldo inicial en fichas', min_value=0, max_digits=12,
                                       decimal_places=2, initial=0)

    field_order = ['username', 'documento', 'nombre_completo', 'codigo_cliente', 'edad', 'saldo_inicial']

    def clean_codigo_cliente(self):
        return validar_codigo_cliente(self.cleaned_data['codigo_cliente'])

    def clean_edad(self):
        return validar_edad(self.cleaned_data['edad'])


class EmpleadoCrearForm(EstiloBootstrapMixin, DatosPersonaMixin, HashZeroKnowledgeMixin):
    cargo = forms.ChoiceField(choices=Empleado.Cargo.choices)
    salario = forms.DecimalField(min_value=1, max_digits=12, decimal_places=2)
    juegos = forms.ModelMultipleChoiceField(
        label='Juegos que conoce', queryset=Juego.objects.all(), required=False,
        widget=CasillasMultiples,
    )
    tambien_jugador = forms.BooleanField(label='También juega como cliente', required=False)
    codigo_cliente = forms.CharField(label='Código de cliente', max_length=20, required=False)
    edad = forms.IntegerField(label='Edad', required=False, min_value=0, max_value=120)
    saldo_inicial = forms.DecimalField(label='Saldo inicial en fichas', required=False, min_value=0,
                                       max_digits=12, decimal_places=2)

    def clean(self):
        datos = super().clean()
        if datos.get('tambien_jugador'):
            if not datos.get('codigo_cliente'):
                self.add_error('codigo_cliente', 'Requerido si el empleado también juega.')
            else:
                try:
                    datos['codigo_cliente'] = validar_codigo_cliente(datos['codigo_cliente'])
                except forms.ValidationError as e:
                    self.add_error('codigo_cliente', e)
            if datos.get('edad') is None:
                self.add_error('edad', 'Requerido si el empleado también juega.')
            else:
                try:
                    validar_edad(datos['edad'])
                except forms.ValidationError as e:
                    self.add_error('edad', e)
        return datos


class EmpleadoEditarForm(EstiloBootstrapMixin, forms.Form):
    nombre_completo = forms.CharField(label='Nombre completo', max_length=100)
    cargo = forms.ChoiceField(choices=Empleado.Cargo.choices)
    salario = forms.DecimalField(min_value=1, max_digits=12, decimal_places=2)
    juegos = forms.ModelMultipleChoiceField(
        label='Juegos que conoce', queryset=Juego.objects.all(), required=False,
        widget=CasillasMultiples,
    )
    activo = forms.BooleanField(label='Usuario activo (puede iniciar sesión)', required=False)


class HabilitarJugadorForm(EstiloBootstrapMixin, forms.Form):
    codigo_cliente = forms.CharField(label='Código de cliente', max_length=20)
    edad = forms.IntegerField(label='Edad', min_value=0, max_value=120)
    saldo_inicial = forms.DecimalField(label='Saldo inicial en fichas', min_value=0, max_digits=12,
                                       decimal_places=2, initial=0)

    def clean_codigo_cliente(self):
        return validar_codigo_cliente(self.cleaned_data['codigo_cliente'])

    def clean_edad(self):
        return validar_edad(self.cleaned_data['edad'])
