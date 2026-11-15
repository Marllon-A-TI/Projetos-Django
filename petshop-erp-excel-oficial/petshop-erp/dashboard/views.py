from django.views.generic import TemplateView

from core.mixins import AdministradorRequiredMixin

from .services import montar_dashboard


class DashboardView(AdministradorRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update(montar_dashboard())
        return contexto