from django import forms
from django.utils import timezone


class DisponibilidadForm(forms.Form):
    fecha_entrada = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    fecha_salida = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    num_personas = forms.IntegerField(
        label='Personas',
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        hoy = timezone.localdate().strftime('%Y-%m-%d')
        self.fields['fecha_entrada'].widget.attrs['min'] = hoy
        self.fields['fecha_salida'].widget.attrs['min'] = hoy

    def clean(self):
        cleaned_data = super().clean()
        fecha_entrada = cleaned_data.get('fecha_entrada')
        fecha_salida = cleaned_data.get('fecha_salida')
        num_personas = cleaned_data.get('num_personas')

        hoy = timezone.localdate()

        if fecha_entrada and fecha_entrada < hoy:
            self.add_error('fecha_entrada', 'No puedes consultar disponibilidad para una fecha anterior a hoy.')

        if fecha_salida and fecha_salida < hoy:
            self.add_error('fecha_salida', 'La fecha de salida no puede ser anterior a hoy.')

        if fecha_entrada and fecha_salida and fecha_salida <= fecha_entrada:
            self.add_error('fecha_salida', 'La fecha de salida debe ser posterior a la fecha de entrada.')

        if num_personas and num_personas < 1:
            self.add_error('num_personas', 'Debe ingresar al menos una persona.')

        return cleaned_data
