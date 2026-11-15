from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Sum
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import TemplateView

from vendas.models import Venda

from .mixins import eh_administrador


class HomeView(LoginRequiredMixin, TemplateView):
    """
    Página inicial após o login.
    Administrador vai direto ao dashboard; vendedor vê atalhos e o resumo
    das próprias vendas do dia.
    """

    template_name = "core/home.html"

    def get(self, request, *args, **kwargs):
        if eh_administrador(request.user):
            return redirect("dashboard:index")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        resumo = Venda.objects.filter(
            vendedor=self.request.user, data=timezone.localdate()
        ).aggregate(quantidade=Count("id"), total=Sum("valor_total"))
        contexto["vendas_hoje"] = resumo["quantidade"] or 0
        contexto["faturamento_hoje"] = resumo["total"] or Decimal("0.00")
        return contexto