"""
Testes da importação/exportação Excel de produtos.

Rodar:  python manage.py test produtos
(precisa do PostgreSQL configurado no .env; o Django cria um banco de teste).
"""

from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from accounts.models import GRUPO_ADMINISTRADOR, GRUPO_VENDEDOR
from estoque.models import MovimentacaoEstoque
from logs.models import LogAcao

from .models import Produto

CABECALHO = ["Código de barras", "Nome", "Estoque", "Preço de venda", "Preço de custo"]


def planilha(linhas, nome="produtos.xlsx"):
    pasta = Workbook()
    folha = pasta.active
    for linha in linhas:
        folha.append(linha)
    saida = BytesIO()
    pasta.save(saida)
    return SimpleUploadedFile(
        nome,
        saida.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@override_settings(
    SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False
)
class BaseTeste(TestCase):
    @classmethod
    def setUpTestData(cls):
        admin_grupo = Group.objects.create(name=GRUPO_ADMINISTRADOR)
        vend_grupo = Group.objects.create(name=GRUPO_VENDEDOR)
        cls.admin = User.objects.create_user("admin", password="x-12345678")
        cls.admin.groups.add(admin_grupo)
        cls.vendedor = User.objects.create_user("vend", password="x-12345678")
        cls.vendedor.groups.add(vend_grupo)

    def setUp(self):
        self.client.force_login(self.admin)


class ImportarProdutosTests(BaseTeste):
    url = reverse("produtos:importar")

    def test_cria_produto_novo_com_estoque_inicial(self):
        resposta = self.client.post(
            self.url,
            {"arquivo": planilha([CABECALHO, ["123", "Ração", 10, "19,90", "12,00"]])},
        )
        self.assertRedirects(resposta, reverse("produtos:list"))
        produto = Produto.objects.get(codigo_barras="123")
        self.assertEqual(produto.quantidade, 10)
        self.assertEqual(produto.preco_venda, Decimal("19.90"))
        movimento = produto.movimentacoes.get()
        self.assertEqual(movimento.tipo, MovimentacaoEstoque.Tipo.ENTRADA)
        self.assertEqual(movimento.usuario, self.admin)
        self.assertTrue(LogAcao.objects.filter(acao=LogAcao.Acao.IMPORTACAO).exists())

    def test_atualiza_preco_e_estoque_e_preserva_demais_campos(self):
        produto = Produto.objects.create(
            nome="Nome original",
            codigo_barras="123",
            categoria="Cães",
            fornecedor="Forn",
            estoque_minimo=3,
            preco_venda=Decimal("10"),
        )
        MovimentacaoEstoque.registrar(
            produto=produto,
            tipo=MovimentacaoEstoque.Tipo.ENTRADA,
            quantidade=5,
            usuario=self.admin,
        )
        self.client.post(
            self.url,
            {"arquivo": planilha([CABECALHO, ["123", "Nome da planilha", 8, 25, None]])},
        )
        produto.refresh_from_db()
        self.assertEqual(produto.quantidade, 8)
        self.assertEqual(produto.preco_venda, Decimal("25.00"))
        self.assertEqual(produto.nome, "Nome original")
        self.assertEqual(produto.categoria, "Cães")
        self.assertEqual(produto.estoque_minimo, 3)
        ultimo = produto.movimentacoes.first()
        self.assertEqual(ultimo.tipo, MovimentacaoEstoque.Tipo.AJUSTE)
        self.assertEqual((ultimo.quantidade_anterior, ultimo.quantidade_nova), (5, 8))

    def test_erro_em_uma_linha_nao_grava_nada(self):
        resposta = self.client.post(
            self.url,
            {
                "arquivo": planilha(
                    [CABECALHO, ["1", "Ok", 1, 1, None], ["2", "Ruim", -3, 1, None]]
                )
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Nada foi importado")
        self.assertEqual(Produto.objects.count(), 0)

    def test_codigo_duplicado_no_cadastro_bloqueia_tudo(self):
        Produto.objects.create(nome="A", codigo_barras="9")
        Produto.objects.create(nome="B", codigo_barras="9")
        resposta = self.client.post(
            self.url,
            {"arquivo": planilha([CABECALHO, ["9", "X", 1, 1, None], ["8", "Y", 1, 1, None]])},
        )
        self.assertContains(resposta, "Corrija o cadastro")
        self.assertFalse(Produto.objects.filter(codigo_barras="8").exists())

    def test_rejeita_arquivo_que_nao_e_xlsx(self):
        resposta = self.client.post(
            self.url, {"arquivo": SimpleUploadedFile("x.xlsx", b"texto qualquer")}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Produto.objects.count(), 0)

    def test_importa_varios_produtos(self):
        linhas = [CABECALHO] + [[str(i), f"P{i}", i % 7, 10, None] for i in range(1, 1501)]
        self.client.post(self.url, {"arquivo": planilha(linhas)})
        self.assertEqual(Produto.objects.count(), 1500)

    # --- Colunas opcionais: planilha só com nome, células em branco ---------

    def test_importa_planilha_so_com_nome(self):
        resposta = self.client.post(
            self.url,
            {
                "arquivo": planilha(
                    [
                        ["NOME DO PRODUTO"],
                        [None],
                        ["Ração A 10kg"],
                        ["Ração B 15kg "],
                        [None],
                        ["Ração A 10kg"],  # repetida e idêntica: ignorada
                    ]
                )
            },
        )
        self.assertRedirects(resposta, reverse("produtos:list"))
        self.assertEqual(Produto.objects.count(), 2)
        produto = Produto.objects.get(nome="Ração A 10kg")
        self.assertEqual(produto.codigo_barras, "")
        self.assertIsNone(produto.preco_venda)
        self.assertEqual(produto.quantidade, 0)
        self.assertFalse(produto.movimentacoes.exists())
        self.assertTrue(Produto.objects.filter(nome="Ração B 15kg").exists())

    def test_importar_so_nomes_de_novo_nao_duplica(self):
        arquivo = [["Nome"], ["Ração A"], ["Ração B"]]
        self.client.post(self.url, {"arquivo": planilha(arquivo)})
        resposta = self.client.post(self.url, {"arquivo": planilha(arquivo)}, follow=True)
        self.assertContains(resposta, "2 sem alteração")
        self.assertEqual(Produto.objects.count(), 2)

    def test_celula_em_branco_nao_apaga_preco_nem_estoque(self):
        produto = Produto.objects.create(
            nome="Ração", codigo_barras="123", preco_venda=Decimal("10")
        )
        MovimentacaoEstoque.registrar(
            produto=produto,
            tipo=MovimentacaoEstoque.Tipo.ENTRADA,
            quantidade=5,
            usuario=self.admin,
        )
        resposta = self.client.post(
            self.url,
            {
                "arquivo": planilha(
                    [["Código de barras", "Nome", "Estoque", "Preço de venda"], ["123", "Ração", None, None]]
                )
            },
            follow=True,
        )
        self.assertContains(resposta, "1 sem alteração")
        produto.refresh_from_db()
        self.assertEqual(produto.quantidade, 5)
        self.assertEqual(produto.preco_venda, Decimal("10.00"))
        self.assertEqual(produto.movimentacoes.count(), 1)

    def test_linha_sem_codigo_atualiza_produto_pelo_nome(self):
        produto = Produto.objects.create(nome="Ração", preco_venda=Decimal("10"))
        self.client.post(
            self.url,
            {"arquivo": planilha([["Nome", "Preço de venda"], ["Ração", "12,50"]])},
        )
        self.assertEqual(Produto.objects.count(), 1)
        produto.refresh_from_db()
        self.assertEqual(produto.preco_venda, Decimal("12.50"))

    def test_linha_sem_codigo_nem_nome_da_erro(self):
        resposta = self.client.post(
            self.url, {"arquivo": planilha([["Nome", "Estoque"], [None, 3]])}
        )
        self.assertContains(resposta, "o código de barras ou o nome")
        self.assertEqual(Produto.objects.count(), 0)

    def test_nome_repetido_sem_codigo_com_dados_diferentes_bloqueia(self):
        resposta = self.client.post(
            self.url,
            {"arquivo": planilha([["Nome", "Estoque"], ["Ração", 1], ["Ração", 2]])},
        )
        self.assertContains(resposta, "nome repetido")
        self.assertEqual(Produto.objects.count(), 0)

    def test_planilha_sem_nenhuma_coluna_reconhecida(self):
        resposta = self.client.post(
            self.url, {"arquivo": planilha([["Foo", "Bar"], ["a", "b"]])}
        )
        self.assertContains(resposta, "Nenhuma coluna reconhecida")
        self.assertEqual(Produto.objects.count(), 0)

    def test_vendedor_nao_acessa(self):
        self.client.force_login(self.vendedor)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        resposta = self.client.post(
            self.url, {"arquivo": planilha([CABECALHO, ["1", "A", 1, 1, None]])}
        )
        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(Produto.objects.count(), 0)

    def test_anonimo_vai_para_o_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)


class ExportarProdutosTests(BaseTeste):
    url = reverse("produtos:exportar")

    def test_baixa_xlsx_com_todos_os_produtos_inclusive_inativos(self):
        Produto.objects.create(
            nome="Ativo", codigo_barras="001", preco_custo=Decimal("5"), preco_venda=Decimal("9")
        )
        Produto.objects.create(nome="Inativo", codigo_barras="002", ativo=False)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("attachment", resposta["Content-Disposition"])
        folha = load_workbook(BytesIO(resposta.content))["Produtos"]
        codigos = [linha[0] for linha in folha.iter_rows(min_row=2, values_only=True)]
        self.assertEqual(sorted(codigos), ["001", "002"])
        self.assertTrue(LogAcao.objects.filter(acao=LogAcao.Acao.EXPORTACAO).exists())

    def test_vendedor_nao_exporta(self):
        self.client.force_login(self.vendedor)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_exportar_e_importar_de_volta_nao_altera_nada(self):
        produto = Produto.objects.create(
            nome="Ração", codigo_barras="0042", preco_venda=Decimal("9.90")
        )
        MovimentacaoEstoque.registrar(
            produto=produto,
            tipo=MovimentacaoEstoque.Tipo.ENTRADA,
            quantidade=4,
            usuario=self.admin,
        )
        conteudo = self.client.get(self.url).content
        resposta = self.client.post(
            reverse("produtos:importar"),
            {"arquivo": SimpleUploadedFile("volta.xlsx", conteudo)},
            follow=True,
        )
        self.assertContains(resposta, "1 sem alteração")
        self.assertEqual(produto.movimentacoes.count(), 1)  # nenhum ajuste novo
