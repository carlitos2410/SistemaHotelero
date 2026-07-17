from django.core.paginator import Paginator


def paginar_queryset(request, queryset, por_pagina=25):
    """Pagina un queryset y conserva todos los filtros salvo el número de página."""
    pagina = Paginator(queryset, por_pagina).get_page(request.GET.get('page'))
    parametros = request.GET.copy()
    parametros.pop('page', None)
    return pagina, parametros.urlencode()
