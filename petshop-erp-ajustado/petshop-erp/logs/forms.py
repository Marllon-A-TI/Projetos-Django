from django import forms

from core.forms import PeriodoForm, UsuarioChoiceField

from .models import LogAcao


class LogAcaoFiltroForm(PeriodoForm):
    usuario = UsuarioChoiceField(required=False, empty_label="Todos")
    acao = forms.ChoiceField(
        label="Ação", required=False, choices=[("", "Todas")] + LogAcao.Acao.choices
    )
    ip = forms.CharField(label="IP", required=False)
    q = forms.CharField(label="Descrição contém", required=False)

    field_order = ["usuario", "acao", "ip", "q", "data_inicial", "data_final"]

    def filtrar(self, queryset):
        if not self.is_valid():
            return queryset

        dados = self.cleaned_data
        if dados.get("usuario"):
            queryset = queryset.filter(usuario=dados["usuario"])
        if dados.get("acao"):
            queryset = queryset.filter(acao=dados["acao"])
        if dados.get("ip"):
            queryset = queryset.filter(ip=dados["ip"])
        if dados.get("q"):
            queryset = queryset.filter(descricao__icontains=dados["q"])

        return self.filtrar_periodo(queryset, "data__date")