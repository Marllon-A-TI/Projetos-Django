import zipfile

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from core.forms import BootstrapFormMixin
from estoque.models import MovimentacaoEstoque

from .models import Produto


class ProdutoSelect(forms.Select):
    """
    Select de produtos que expõe dados úteis ao JavaScript da tela de venda
    (preço de venda, estoque e código de barras). O preço de custo nunca
    é exposto.
    """

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        opcao = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs
        )
        produto = getattr(value, "instance", None)
        if produto is not None:
            preco = produto.preco_venda
            opcao["attrs"]["data-preco"] = f"{preco:.2f}" if preco is not None else ""
            opcao["attrs"]["data-estoque"] = str(produto.quantidade or 0)
            opcao["attrs"]["data-codigo"] = produto.codigo_barras or ""
        return opcao


class ProdutoChoiceField(forms.ModelChoiceField):
    """Seleção de produto. Por padrão lista apenas produtos ativos."""

    widget = ProdutoSelect

    def __init__(self, queryset=None, **kwargs):
        if queryset is None:
            queryset = Produto.objects.ativos().order_by("nome", "id")
        kwargs.setdefault("label", "Produto")
        kwargs.setdefault("empty_label", "Selecione um produto")
        super().__init__(queryset, **kwargs)

    def label_from_instance(self, obj):
        texto = obj.nome or f"Produto #{obj.pk}"
        if obj.codigo_barras:
            texto += f" [{obj.codigo_barras}]"
        return f"{texto} (estoque: {obj.quantidade or 0})"


class ProdutoForm(BootstrapFormMixin, forms.ModelForm):
    quantidade_inicial = forms.IntegerField(
        label="Estoque inicial",
        min_value=0,
        required=False,
        initial=0,
        help_text="Gera automaticamente uma movimentação de ENTRADA.",
    )

    class Meta:
        model = Produto
        fields = [
            "nome",
            "codigo_barras",
            "categoria",
            "fornecedor",
            "estoque_minimo",
            "preco_custo",
            "preco_venda",
            "ativo",
        ]
        widgets = {
            "nome": forms.TextInput(attrs={"autofocus": True}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        self.usuario = usuario
        super().__init__(*args, **kwargs)
        self.criando = self.instance.pk is None
        if not self.criando:
            # O estoque de um produto existente só muda por movimentação.
            del self.fields["quantidade_inicial"]

    def clean_codigo_barras(self):
        codigo = (self.cleaned_data.get("codigo_barras") or "").strip()
        if codigo:
            existente = (
                Produto.objects.filter(codigo_barras=codigo)
                .exclude(pk=self.instance.pk)
                .first()
            )
            if existente:
                raise ValidationError(
                    f"Já existe um produto com este código de barras: {existente}."
                )
        return codigo

    def clean_quantidade_inicial(self):
        quantidade = self.cleaned_data.get("quantidade_inicial") or 0
        if quantidade > 0 and self.usuario is None:
            raise ValidationError(
                "Não foi possível identificar o usuário responsável pelo estoque."
            )
        return quantidade

    @transaction.atomic
    def save(self, commit=True):
        produto = super().save(commit=commit)
        if commit and self.criando:
            quantidade = self.cleaned_data.get("quantidade_inicial") or 0
            if quantidade > 0:
                MovimentacaoEstoque.registrar(
                    produto=produto,
                    tipo=MovimentacaoEstoque.Tipo.ENTRADA,
                    quantidade=quantidade,
                    usuario=self.usuario,
                    observacao="Estoque inicial",
                )
        return produto


class ProdutoFiltroForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(
        label="Buscar",
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "Nome ou código de barras"}
        ),
    )
    categoria = forms.CharField(label="Categoria", required=False)
    fornecedor = forms.CharField(label="Fornecedor", required=False)
    situacao = forms.ChoiceField(
        label="Situação",
        required=False,
        choices=[("", "Todos"), ("ativos", "Ativos"), ("inativos", "Inativos")],
    )
    estoque_baixo = forms.BooleanField(
        label="Somente estoque baixo", required=False
    )

    def filtrar(self, queryset):
        if not self.is_valid():
            return queryset

        dados = self.cleaned_data

        termo = dados.get("q")
        if termo:
            queryset = queryset.filter(
                Q(nome__icontains=termo) | Q(codigo_barras__icontains=termo)
            )

        if dados.get("categoria"):
            queryset = queryset.filter(categoria__icontains=dados["categoria"])

        if dados.get("fornecedor"):
            queryset = queryset.filter(fornecedor__icontains=dados["fornecedor"])

        if dados.get("situacao") == "ativos":
            queryset = queryset.filter(ativo=True)
        elif dados.get("situacao") == "inativos":
            queryset = queryset.filter(ativo=False)

        if dados.get("estoque_baixo"):
            queryset = queryset.estoque_baixo()

        return queryset


class ImportarProdutosForm(BootstrapFormMixin, forms.Form):
    """Upload da planilha. A leitura e a validação das linhas ficam em excel.py."""

    TAMANHO_MAXIMO = 5 * 1024 * 1024  # 5 MB
    DESCOMPACTADO_MAXIMO = 100 * 1024 * 1024  # protege contra "zip bomb"

    arquivo = forms.FileField(
        label="Planilha Excel (.xlsx)",
        widget=forms.FileInput(attrs={"accept": ".xlsx"}),
        help_text="Arquivo .xlsx de até 5 MB. A primeira aba é a lida.",
    )

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]

        if not arquivo.name.lower().endswith(".xlsx"):
            raise ValidationError("Envie um arquivo no formato .xlsx.")
        if arquivo.size > self.TAMANHO_MAXIMO:
            raise ValidationError("O arquivo passa de 5 MB. Divida em arquivos menores.")

        try:
            with zipfile.ZipFile(arquivo) as pacote:
                nomes = pacote.namelist()
                descompactado = sum(item.file_size for item in pacote.infolist())
        except zipfile.BadZipFile:
            raise ValidationError(
                "O arquivo não é uma planilha .xlsx válida."
            ) from None
        finally:
            arquivo.seek(0)

        if "xl/workbook.xml" not in nomes:
            raise ValidationError("O arquivo não é uma planilha .xlsx válida.")
        if descompactado > self.DESCOMPACTADO_MAXIMO:
            raise ValidationError("A planilha é grande demais para ser importada.")
        return arquivo
