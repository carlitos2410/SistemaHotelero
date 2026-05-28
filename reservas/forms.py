from django import forms
from django.forms import formset_factory
from django.utils import timezone
from .models import Acompanante, Reserva, Huesped
from habitaciones.models import Habitacion


class HuespedForm(forms.ModelForm):
    class Meta:
        model = Huesped
        fields = ['tipo_doc', 'num_doc', 'nombres', 'apellidos', 'email', 'telefono', 'nacionalidad']
        widgets = {
            'tipo_doc': forms.Select(attrs={'class': 'form-select'}),
            'num_doc': forms.TextInput(attrs={'class': 'form-control'}),
            'nombres': forms.TextInput(attrs={'class': 'form-control'}),
            'apellidos': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control'}),
            'nacionalidad': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_num_doc(self):
        return self.cleaned_data['num_doc']

    def validate_unique(self):
        pass


class ReservaForm(forms.ModelForm):
    class Meta:
        model = Reserva
        fields = ['habitacion', 'fecha_entrada', 'fecha_salida', 'num_adultos', 'estado', 'origen']
        widgets = {
            'habitacion': forms.HiddenInput(),
            'fecha_entrada': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'readonly': 'readonly'}),
            'fecha_salida': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'readonly': 'readonly'}),
            'num_adultos': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'estado': forms.Select(attrs={'class': 'form-select'}),
            'origen': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        habitacion_id = kwargs.pop('habitacion_id', None)
        super().__init__(*args, **kwargs)

        hoy = timezone.localdate().strftime('%Y-%m-%d')
        self.fields['fecha_entrada'].widget.attrs['min'] = hoy
        self.fields['fecha_salida'].widget.attrs['min'] = hoy

        if habitacion_id:
            self.fields['habitacion'].queryset = Habitacion.objects.filter(id=habitacion_id)
        else:
            self.fields['habitacion'].queryset = Habitacion.objects.all()

    def clean(self):
        cleaned_data = super().clean()
        fecha_entrada = cleaned_data.get('fecha_entrada')
        fecha_salida = cleaned_data.get('fecha_salida')
        habitacion = cleaned_data.get('habitacion')
        num_adultos = cleaned_data.get('num_adultos')

        hoy = timezone.localdate()

        if fecha_entrada and fecha_entrada < hoy:
            self.add_error('fecha_entrada', 'No se puede reservar para una fecha anterior a hoy.')

        if fecha_salida and fecha_salida < hoy:
            self.add_error('fecha_salida', 'La fecha de salida no puede ser anterior a hoy.')

        if fecha_entrada and fecha_salida and fecha_salida <= fecha_entrada:
            self.add_error('fecha_salida', 'La fecha de salida debe ser posterior a la fecha de entrada.')

        if habitacion and num_adultos and num_adultos > habitacion.tipo.capacidad:
            self.add_error(
                'num_adultos',
                f'La habitacion permite maximo {habitacion.tipo.capacidad} persona(s).'
            )

        return cleaned_data


class ReservaFiltroForm(forms.Form):
    ESTANCIA_CHOICES = [
        ('', 'Todos'),
        ('SIN_CHECKIN', 'Sin check-in'),
        ('CHECKIN_NORMAL', 'Check-in normal'),
        ('CHECKIN_ANTICIPADO', 'Check-in anticipado'),
        ('CHECKOUT_NORMAL', 'Check-out normal'),
        ('CHECKOUT_TARDIO', 'Check-out tardio'),
    ]

    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Huesped, documento, habitacion u origen',
        })
    )
    estado = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos los estados')] + Reserva.ESTADO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    fecha_desde = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    fecha_hasta = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    estancia = forms.ChoiceField(
        required=False,
        choices=ESTANCIA_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class ClienteFiltroForm(forms.Form):
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nombre, apellido, documento, email o telefono',
        })
    )


class CheckinDirectoForm(forms.Form):
    tipo_doc = forms.ChoiceField(
        choices=Huesped.TIPO_DOC_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    num_doc = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    nombres = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    apellidos = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    telefono = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    nacionalidad = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    habitacion = forms.ModelChoiceField(
        queryset=Habitacion.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    fecha_salida = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    num_adultos = forms.IntegerField(
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1'})
    )
    origen = forms.CharField(
        required=False,
        initial='Walk-in',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoy = timezone.localdate()
        self.fields['fecha_salida'].widget.attrs['min'] = hoy.strftime('%Y-%m-%d')
        self.fields['habitacion'].queryset = Habitacion.objects.select_related('hotel', 'tipo').filter(
            estado='DISPONIBLE'
        ).order_by('piso', 'numero')

    def clean_fecha_salida(self):
        fecha_salida = self.cleaned_data['fecha_salida']
        hoy = timezone.localdate()

        if fecha_salida <= hoy:
            raise forms.ValidationError('La fecha de salida debe ser posterior a hoy.')

        return fecha_salida

    def clean(self):
        cleaned_data = super().clean()
        habitacion = cleaned_data.get('habitacion')
        num_adultos = cleaned_data.get('num_adultos')

        if habitacion and num_adultos and num_adultos > habitacion.tipo.capacidad:
            self.add_error(
                'num_adultos',
                f'La habitacion permite maximo {habitacion.tipo.capacidad} persona(s).'
            )

        return cleaned_data


class AcompananteForm(forms.ModelForm):
    class Meta:
        model = Acompanante
        fields = ['tipo_doc', 'num_doc', 'nombres', 'apellidos', 'nacionalidad', 'parentesco']
        widgets = {
            'tipo_doc': forms.Select(attrs={'class': 'form-select'}),
            'num_doc': forms.TextInput(attrs={'class': 'form-control'}),
            'nombres': forms.TextInput(attrs={'class': 'form-control'}),
            'apellidos': forms.TextInput(attrs={'class': 'form-control'}),
            'nacionalidad': forms.TextInput(attrs={'class': 'form-control'}),
            'parentesco': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        tiene_datos = any(
            cleaned_data.get(campo)
            for campo in ['num_doc', 'nombres', 'apellidos', 'nacionalidad', 'parentesco']
        )

        if tiene_datos:
            for campo in ['tipo_doc', 'num_doc', 'nombres', 'apellidos']:
                if not cleaned_data.get(campo):
                    self.add_error(campo, 'Este dato es obligatorio para registrar acompanante.')

        return cleaned_data


AcompananteFormSet = formset_factory(AcompananteForm, extra=3, can_delete=True)
