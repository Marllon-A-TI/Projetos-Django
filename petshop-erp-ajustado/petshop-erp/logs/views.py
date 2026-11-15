from django.views.generic import ListView

from core.mixins import AdministradorRequiredMixin, FiltroListViewMixin

from .forms import LogAcaoFiltroForm
from .models import LogAcao


class LogAcaoListView(AdministradorRequiredMixin, FiltroListViewMixin, ListView):
    model = LogAcao
    queryset = LogAcao.objects.select_related("usuario")
    template_name = "logs/logacao_list.html"
    context_object_name = "registros"
    paginate_by = 50
    filtro_form_class = LogAcaoFiltroForm