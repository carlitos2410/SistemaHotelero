from django import forms

from hoteles.models import Hotel


class ReporteFiltroForm(forms.Form):
    fecha_desde = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label='Fecha desde',
    )
    fecha_hasta = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label='Fecha hasta',
    )
    hotel = forms.ModelChoiceField(
        required=False,
        queryset=Hotel.objects.filter(activo=True).order_by('nombre'),
        empty_label='Todos los hoteles',
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Hotel',
    )
    TIPO_REPORTE_CHOICES = [
        ('', 'Todos'),
        ('OCUPACION', 'Ocupacion'),
        ('INGRESOS', 'Ingresos'),
        ('RESERVAS', 'Reservas'),
    ]
    tipo = forms.ChoiceField(
        required=False,
        choices=TIPO_REPORTE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Tipo de reporte',
    )
