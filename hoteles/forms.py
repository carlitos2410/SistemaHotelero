from django import forms

from .models import Hotel


class HotelForm(forms.ModelForm):
    class Meta:
        model = Hotel
        fields = ['nombre', 'ruc', 'direccion', 'estrellas', 'telefono', 'email', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'ruc': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '11'}),
            'direccion': forms.TextInput(attrs={'class': 'form-control'}),
            'estrellas': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '5'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class HotelFiltroForm(forms.Form):
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nombre, RUC o direccion',
        }),
    )
    estrellas = forms.ChoiceField(
        required=False,
        choices=[('', 'Todas')] + [(i, f'{i} estrella{"s" if i > 1 else ""}') for i in range(1, 6)],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
