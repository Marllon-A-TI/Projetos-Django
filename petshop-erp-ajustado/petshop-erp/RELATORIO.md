# Pet Shop ERP: diagnóstico, produção e Excel

Baseado na leitura do projeto real enviado (`petshop-erp.zip`). Nada foi inventado: onde algo não pôde ser verificado, está dito.

## 1. Diagnóstico da arquitetura

**Apps (8):** `core` (mixins, base de models, middleware de acesso, filtros), `accounts` (usuários e grupos), `produtos`, `estoque`, `vendas`, `financeiro`, `dashboard`, `logs`. Django 5.2, PostgreSQL via `psycopg 3`, `gunicorn`, `whitenoise`, `python-decouple`. Sem JavaScript de build: Bootstrap e Chart.js locais em `static/vendor`.

**Padrões em uso (todos devem ser preservados):**

- **Class Based Views** finas, com mixins de `core/mixins.py`; listagens com `FiltroListViewMixin` + um `FiltroForm` com método `filtrar()`.
- **Models-base** em `core/models.py`: `ModeloBase` (criado/atualizado), `ModeloProtegido` (não exclui), `ModeloImutavel` (não altera nem exclui; `update()` e `delete()` em lote bloqueados). Usados por `MovimentacaoEstoque`, `LogAcao`, `Venda`, `ItemVenda`, `FluxoCaixa`.
- **Regra de ouro do estoque:** `Produto.quantidade` não pode ser gravada por `save()` (levanta `EstoqueProtegidoError`); só `MovimentacaoEstoque.registrar()` altera o saldo, com `select_for_update`, histórico imutável e *constraints* no banco que garantem saldo consistente.
- **Serviços em classmethod** com `transaction.atomic` (`Venda.registrar_venda`, `MovimentacaoEstoque.registrar`) e módulo de serviços no dashboard.
- **Templates** com `base.html` (navbar Bootstrap, perfil decide o menu), parciais (`campo`, `form_corpo`, `filtro`, `paginacao`, `mensagens`) e filtros em `core_tags`.

**Permissões (3 camadas):** (1) `ControleAcessoMiddleware` define o perfil mínimo por app (`PERFIS_POR_APP`); (2) cada view usa `AdministradorRequiredMixin` ou `VendedorOuAdministradorRequiredMixin` (login → redireciona; sem perfil → 403); (3) os templates escondem o que o perfil não pode usar. Perfis = grupos `Administrador` e `Vendedor` (`accounts/models.py`, criados por `manage.py criar_grupos`); superusuário passa em tudo. Importante: o app `produtos` está liberado para Vendedor na camada 1, então **qualquer view nova de produtos que seja só de administrador precisa do mixin na própria view**.

**Logs:** `LogAcao` (imutável) guarda usuário, ação, IP, data e descrição. Gravação por `registrar_acao(request, acao, descricao)` ou `LogFormValidMixin` (grava na mesma transação do objeto). `AuditoriaMiddleware` calcula o IP (`CLIENT_IP_HEADER`), bloqueia excesso de logins errados (429) e audita POSTs do `/admin/`; sinais registram login/logout/falha. Há também log de aplicação em `var/log/petshop.log` com rotação.

## 2. Diagnóstico de Produtos

`Produto`: nome, código de barras, categoria, fornecedor, quantidade (protegida), estoque mínimo, preço de custo/venda (≥ 0 por constraint), ativo. Índices em nome, código e categoria. **O código de barras não é único no banco**; a unicidade é só validada no `ProdutoForm`.
CRUD: lista (filtros, paginação 25; vendedor só vê ativos e não vê custo), detalhe, criar/editar (só admin, com log; estoque inicial vira movimentação de ENTRADA), ativar/desativar, excluir (bloqueado se houver movimentações/vendas).

## 3. Diagnóstico da infraestrutura atual

Já existia e está bem feito: `deploy/` (Gunicorn em `127.0.0.1:8000`, serviço systemd, `atualizar.sh`, exemplo de Caddyfile e de `.env` de produção), `scripts/` (backup diário com `pg_dump`, retenção, restauração e teste de restauração), `settings.py` guiado por `.env` (DEBUG falso por padrão, HSTS, cookies seguros, proxy). **Então a hospedagem não exige mudança de código.**

**O que o projeto não tinha:** nenhuma parte de Excel. O módulo de produtos terminava no CRUD, o `LogAcao` não tinha ações de importação/exportação e o `openpyxl` não estava no `requirements.txt`. Tudo isso foi criado agora, reaproveitando `ModeloImutavel`, `registrar_acao`, os mixins de perfil, `BootstrapFormMixin` e os parciais de template existentes.

## 4. Plano de hospedagem

Ver **`deploy/ORACLE_CLOUD.md`** (passo a passo, firewall, Caddy/Nginx, SSL, backup, custos, limites). Resumo: uma VM Ampere A1 (1 OCPU/6 GB) com Ubuntu 24.04, PostgreSQL local, Gunicorn, Caddy; custo R$ 0 (domínio opcional). Dois alertas: o Always Free hoje é **2 OCPU/12 GB** (não 4/24) e instâncias ociosas podem ser recuperadas, por isso o **backup externo é obrigatório**.

## 5. Alterações necessárias para produção

Nenhuma no código. Só configuração no `.env` (modelo em `deploy/env.producao.exemplo`): `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, nova `DJANGO_SECRET_KEY`, `DJANGO_ADMIN_URL`, `CLIENT_IP_HEADER=HTTP_X_FORWARDED_FOR`, cookies seguros e SSL redirect ligados.

## 6. Importar Excel (implementado)

Menu **Produtos → Importar Excel** (somente Administrador). Fluxo: upload → validações do arquivo (extensão, 5 MB, é um zip `.xlsx` real, tamanho descompactado) → leitura em modo *read-only* linha a linha → validação de **todas** as linhas → só então grava, em uma `transaction.atomic`.

- **Chave:** código de barras; na linha sem código, o nome (exato). **Nenhuma coluna é obrigatória**, mas cada linha precisa de código ou nome. **Colunas aceitas:** Código de barras, Nome, Estoque, Preço de venda, Categoria, Fornecedor, Estoque mínimo, Preço de custo, Ativo. Cabeçalhos aceitam variações sem acento (ex.: "EAN", "Quantidade", "Preço", "Nome do produto"). Célula em branco não altera produto existente.
- **Valida:** colunas ausentes/duplicadas, vazios, tipos, negativos, casas decimais, tamanhos de texto, duplicidade na planilha, duplicidade no cadastro, limite de 20.000 linhas. Mostra até 100 erros com o número da linha; qualquer erro = nada é gravado.
- **Produto existente:** atualiza preço de venda, preço de custo (se informado) e estoque; **preserva** nome, categoria, fornecedor, estoque mínimo e situação.
- **Produto novo:** criado com `bulk_create`.
- **Estoque respeita a regra do projeto:** nada de `save()` em `quantidade`. Existente recebe movimentação **AJUSTE** (a planilha vira o saldo contado); novo recebe **ENTRADA**. Isso é feito por `MovimentacaoEstoque.registrar_lote()` (novo, em lote: `select_for_update` + `bulk_create` + `bulk_update`), então o histórico e as constraints continuam valendo.
- **Log:** uma ação `IMPORTACAO` com arquivo e contagens, gravada na mesma transação.
- **Desempenho:** a leitura/validação de 20.000 linhas levou ~1 s no teste; consultas em lotes de 2.000, gravação em lotes de 1.000.

## 7. Exportar Excel (implementado)

Menu **Produtos → Exportar Excel**: download imediato (GET), todos os produtos (inclusive inativos), as 9 colunas do model, em ordem de nome. Só Administrador (inclui preço de custo). Textos gravados como texto (zeros à esquerda preservados e **sem execução de fórmulas** se o nome começar com `=`, `+`, `-`, `@`). Cabeçalho `Cache-Control: no-store`. Gera log `EXPORTACAO`. O arquivo exportado é o modelo da importação (exportar → editar → importar funciona).

## 8. Arquivos alterados

| Arquivo | Mudança |
|---|---|
| `requirements.txt` | `+ openpyxl>=3.1,<4.0` (única dependência nova) |
| `logs/models.py` | `+ IMPORTACAO`, `+ EXPORTACAO` em `LogAcao.Acao` |
| `logs/migrations/0003_alter_logacao_acao.py` | **novo**: só atualiza as `choices` (sem alterar tabelas); rode `migrate` |
| `estoque/models.py` | `+ MovimentacaoEstoque.registrar_lote()` e `import timezone` |
| `produtos/excel.py` | **novo**: lê/valida/gera XLSX (só openpyxl, sem Django, sem banco) |
| `produtos/importacao.py` | **novo**: grava a importação (atômica, em lote, via movimentações) |
| `templates/produtos/produto_importar.html` | **novo**: tela de importação (layout padrão do projeto) |
| `produtos/forms.py` | `+ ImportarProdutosForm` |
| `produtos/views.py` | `+ ProdutoImportarView`, `+ ProdutoExportarView` |
| `produtos/urls.py` | `+ importar/`, `+ exportar/` |
| `templates/base.html` | "Produtos" vira dropdown (só administrador) |
| `produtos/tests.py` | 11 testes novos |
| `deploy/ORACLE_CLOUD.md`, `RELATORIO.md` | documentação |

O diff exato está em `alteracoes.patch` (a nova migração, `excel.py`, `importacao.py` e o template aparecem como arquivos novos).

## 9. Novas URLs, forms, views, templates e menu

- URLs: `produtos:importar` (`/produtos/importar/`), `produtos:exportar` (`/produtos/exportar/`).
- Form: `ImportarProdutosForm` (um campo de arquivo). Views: `ProdutoImportarView` (FormView), `ProdutoExportarView` (View GET).
- Template novo: `produto_importar.html` (usa `form_corpo`, `campo` e `mensagens` existentes). Menu: dropdown Produtos → Lista / Importar Excel / Exportar Excel.

## 10. Como testar localmente

1. `pip install -r requirements.txt` (traz o `openpyxl`) e `python manage.py check`.
2. `python manage.py test produtos` (precisa do PostgreSQL do `.env`; o Django cria e apaga um banco de teste).
3. Manual: entre como Administrador → Produtos → **Exportar Excel** → abra, altere preço/estoque de uma linha, acrescente uma linha nova → **Importar Excel** → confira a mensagem, a lista, a tela de Estoque (movimentações "Importação Excel") e Logs.
4. Planilha com erro (estoque negativo, código repetido, coluna faltando): deve mostrar a lista de erros e não gravar nada.
5. Entre como Vendedor: o menu não mostra as opções e as URLs devolvem 403.

## 11. Como testar em produção

Checklist da seção 10 de `deploy/ORACLE_CLOUD.md`. Antes da primeira importação real, rode `./scripts/backup_db.sh` e importe primeiro uma planilha pequena.

## 12. Segurança (verificado em `settings.py`)

| Item | Situação | Ajuste |
|---|---|---|
| `DEBUG` | padrão `False`; o `.env` enviado tem `True` (desenvolvimento) | `False` em produção |
| `ALLOWED_HOSTS` / CSRF | lidos do `.env`; `.env` enviado só tem localhost | colocar o domínio e `CSRF_TRUSTED_ORIGINS` com `https://` |
| Sessão | 8 h, `HttpOnly`, `SameSite=Lax`, cookie seguro se não for DEBUG | manter |
| HTTPS/HSTS/proxy | `SECURE_PROXY_SSL_HEADER`, SSL redirect e HSTS por `.env` | HSTS 3600 → 1 ano depois de validar |
| Upload | não há `MEDIA`; planilha é lida em memória/temporário e descartada | 5 MB (form) + 6 MB (Caddy) + proteção contra zip bomb |
| Permissões | importar/exportar só Administrador (view + teste) | — |
| Admin | URL configurável (`DJANGO_ADMIN_URL`) | trocar o padrão |

**Atenção ao `.env` dentro do zip:** o arquivo foi enviado junto com o projeto. Não li nem repeti os valores, mas por ele ter circulado, recomendo gerar uma nova `DJANGO_SECRET_KEY` e uma nova senha de banco para produção (a nuvem terá as suas de qualquer forma) e nunca versionar o `.env` (já está no `.gitignore`).

## 13. Riscos

- **Os testes Django novos não foram executados.** O ambiente de análise não tinha Django nem rede para instalá-lo. O que foi realmente executado: compilação de todos os arquivos alterados e testes do `excel.py` (leitura, erros, ida e volta, proteção contra fórmula, 20.000 linhas, limites). `registrar_lote`, form e views foram revisados contra o código existente, mas rode `python manage.py test produtos` antes de confiar.
- **Código de barras não é único no banco:** se o cadastro tiver códigos repetidos, a importação recusa as linhas afetadas e pede correção (comportamento intencional e seguro).
- **Importação por AJUSTE sobrescreve o saldo** com o valor da planilha. Se houver vendas entre exportar e importar, o saldo volta ao valor antigo. Oriente: importe logo após exportar, ou use a importação como "contagem de estoque".
- Preços/estoque com formato de texto incomum (ex.: "1,5 mil") são recusados com mensagem, não adivinhados.
- Oracle: recuperação de instância ociosa, falta de capacidade A1 e limite de 2 OCPU/12 GB (detalhes no runbook).
- Operação síncrona: 20.000 linhas ficam bem abaixo do `timeout` de 60 s do Gunicorn, mas arquivos muito maiores precisariam de fila (não recomendado agora).

## 14. Melhorias futuras (em ordem de valor)

1. Tornar `codigo_barras` único no banco (índice único parcial para não vazios) depois de limpar duplicidades.
2. Pré-visualização ("vai criar X, atualizar Y") com confirmação antes de gravar.
3. Botão "Baixar modelo vazio" e coluna `Ação` (ex.: ENTRADA em vez de AJUSTE).
4. Exportar respeitando os filtros da lista; exportar movimentações e vendas.
5. Monitoramento externo gratuito (UptimeRobot) e alerta de falha de backup por e-mail.
6. CI simples (GitHub Actions) rodando `manage.py test` a cada commit.
