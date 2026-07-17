from django import forms
from django.utils import timezone


class ReporteFiltroForm(forms.Form):
    fecha_desde = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    fecha_hasta = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )

    def clean(self):
        cleaned_data = super().clean()
        fecha_desde = cleaned_data.get('fecha_desde')
        fecha_hasta = cleaned_data.get('fecha_hasta')

        if fecha_desde and fecha_hasta and fecha_hasta < fecha_desde:
            self.add_error('fecha_hasta', 'La fecha final no puede ser anterior a la fecha inicial.')

        return cleaned_data

    def obtener_rango(self):
        hoy = timezone.localdate()
        fecha_desde = self.cleaned_data.get('fecha_desde') or hoy.replace(day=1)
        fecha_hasta = self.cleaned_data.get('fecha_hasta') or hoy
        return fecha_desde, fecha_hasta
