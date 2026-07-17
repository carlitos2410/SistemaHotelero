from decimal import Decimal, ROUND_HALF_UP

from django import forms

from .models import Comprobante, ConfiguracionCobro, MetodoPago, ProductoServicio


def garantizar_metodos_pago():
    defaults = [
        ('Efectivo', 'EFECTIVO'),
        ('Tarjeta', 'TARJETA'),
        ('Billetera digital', 'BILLETERA'),
        ('Transferencia', 'TRANSFERENCIA'),
    ]
    for nombre, tipo in defaults:
        MetodoPago.objects.get_or_create(nombre=nombre, defaults={'tipo': tipo, 'activo': True})


class CargoHabitacionForm(forms.Form):
    producto_servicio = forms.ModelChoiceField(
        queryset=ProductoServicio.objects.none(),
        label='Producto o servicio',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    cantidad = forms.IntegerField(
        min_value=1,
        initial=1,
        label='Cantidad',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1'})
    )
    observacion = forms.CharField(
        required=False,
        label='Observacion',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Detalle opcional para el folio',
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['producto_servicio'].queryset = ProductoServicio.objects.filter(
            activo=True,
            precio__gt=0,
        ).order_by('categoria', 'nombre')


class ConfiguracionCobroForm(forms.ModelForm):
    class Meta:
        model = ConfiguracionCobro
        fields = [
            'porcentaje_garantia_reserva',
            'horas_plazo_pago_garantia',
            'porcentaje_igv',
            'porcentaje_early_checkin',
            'porcentaje_late_checkout',
            'porcentaje_penalidad_salida_anticipada',
            'horas_cancelacion_gratuita',
            'porcentaje_retencion_cancelacion_tardia',
        ]
        widgets = {
            'porcentaje_garantia_reserva': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0.01', 'max': '100', 'step': '0.01',
            }),
            'horas_plazo_pago_garantia': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '1', 'step': '1',
            }),
            'porcentaje_igv': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0', 'max': '100', 'step': '0.01',
            }),
            'porcentaje_early_checkin': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0', 'max': '100', 'step': '0.01',
            }),
            'porcentaje_late_checkout': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0', 'max': '100', 'step': '0.01',
            }),
            'porcentaje_penalidad_salida_anticipada': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '100',
                'step': '0.01',
            }),
            'horas_cancelacion_gratuita': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0', 'step': '1',
            }),
            'porcentaje_retencion_cancelacion_tardia': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0', 'max': '100', 'step': '0.01',
            }),
        }


class PagoForm(forms.Form):
    metodo_pago = forms.ModelChoiceField(
        queryset=MetodoPago.objects.none(),
        label='Metodo de pago',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    monto = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'})
    )
    numero_operacion = forms.CharField(
        required=False,
        label='Numero de operacion',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Voucher, operacion o referencia'})
    )
    tipo_comprobante = forms.ChoiceField(
        choices=Comprobante.TIPO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    cliente_documento = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'DNI o RUC'})
    )
    cliente_nombre = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre completo o razon social'})
    )
    cliente_direccion = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Direccion fiscal o domicilio'})
    )
    observacion = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nota interna de caja'})
    )

    def __init__(self, *args, **kwargs):
        self.folio = kwargs.pop('folio', None)
        self.reserva = kwargs.pop('reserva', None)
        if (self.folio is None) == (self.reserva is None):
            raise ValueError('Indica un folio o una reserva, pero no ambos.')
        super().__init__(*args, **kwargs)
        garantizar_metodos_pago()
        self.fields['metodo_pago'].queryset = MetodoPago.objects.filter(activo=True)
        self.saldo_maximo = self.folio.saldo_pendiente if self.folio else self.reserva.saldo_adelanto
        self.fields['monto'].initial = self.saldo_maximo

        huesped = self.folio.estancia.reserva.huesped if self.folio else self.reserva.huesped
        self.fields['cliente_documento'].initial = huesped.num_doc
        self.fields['cliente_nombre'].initial = f'{huesped.nombres} {huesped.apellidos}'

    def clean_monto(self):
        monto = self.cleaned_data['monto'].quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        if monto <= 0:
            raise forms.ValidationError('El monto debe ser mayor a cero.')
        if monto > self.saldo_maximo:
            raise forms.ValidationError(f'El monto no puede superar el saldo pendiente de S/ {self.saldo_maximo}.')

        return monto

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo_comprobante')
        metodo = cleaned_data.get('metodo_pago')

        if tipo == 'FACTURA':
            documento = cleaned_data.get('cliente_documento') or ''
            if len(documento) != 11 or not documento.isdigit():
                self.add_error('cliente_documento', 'Para factura ingresa un RUC valido de 11 digitos.')
            if not cleaned_data.get('cliente_nombre'):
                self.add_error('cliente_nombre', 'Ingresa la razon social para emitir factura.')

        if tipo == 'BOLETA':
            if not cleaned_data.get('cliente_documento'):
                self.add_error('cliente_documento', 'Ingresa el documento del cliente para la boleta.')
            if not cleaned_data.get('cliente_nombre'):
                self.add_error('cliente_nombre', 'Ingresa el nombre del cliente para la boleta.')

        if metodo and metodo.tipo != 'EFECTIVO' and not cleaned_data.get('numero_operacion'):
            self.add_error('numero_operacion', 'Ingresa el numero de operacion para pagos no efectivos.')

        return cleaned_data


class ReporteCajaFiltroForm(forms.Form):
    fecha_desde = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    fecha_hasta = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    metodo_pago = forms.ModelChoiceField(
        required=False,
        queryset=MetodoPago.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    tipo_comprobante = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos')] + Comprobante.TIPO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    estado = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos')] + Comprobante.ESTADO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        garantizar_metodos_pago()
        self.fields['metodo_pago'].queryset = MetodoPago.objects.filter(activo=True)
