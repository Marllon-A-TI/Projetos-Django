# Pet Shop ERP

Sistema web de gestão para pet shop, feito em Django e PostgreSQL. Neste projeto reuni em um só lugar o que um pequeno comércio precisa controlar no dia a dia: produtos, estoque, vendas, contas a pagar e a receber, caixa, indicadores e histórico de quem fez o quê.

É o meu projeto pessoal mais completo até agora.

## O que aprendi com este projeto

Esta é a parte do projeto que mais me ensinou. O que eu levo daqui:

- **Regra de negócio fica no modelo, não só na tela.** O saldo de estoque de um produto não pode ser alterado direto: só muda por uma movimentação (entrada, saída, ajuste ou venda). Se alguém tentar gravar o saldo por fora, o sistema levanta um erro. Entendi que proteger o dado no modelo vale mais do que esconder um botão.
- **Histórico que não se altera.** Movimentações de estoque, itens de venda, lançamentos do caixa e logs não podem ser editados nem excluídos. Para corrigir um erro eu lanço um novo registro, como numa contabilidade.
- **Transação: tudo ou nada.** Registrar uma venda cria a venda e os itens, baixa o estoque, calcula o total e lança a entrada no caixa. Usei `transaction.atomic` para que um erro em qualquer etapa desfaça tudo, sem deixar dados pela metade.
- **Permissão em camadas.** O acesso é controlado por um middleware (regra por app), por mixins nas views e pelo que aparece no menu e nas telas. Aprendi que não basta uma camada: se uma view nova esquece a proteção, a outra segura.
- **Validar antes de gravar.** Na importação de produtos por Excel, valido a planilha inteira antes de mexer no banco. Se uma linha tiver erro, nada é gravado e o sistema mostra a lista de erros.
- **Segurança básica de um sistema real.** Segredos em variáveis de ambiente (`.env`, com `python-decouple`), bloqueio de tentativas de login (5 falhas por usuário ou 20 por IP em 15 minutos) e auditoria das ações.
- **Testes automatizados com `TestCase`.** Escrevi testes para o app de produtos (18 testes: importação, exportação e controle de acesso). Aprendi o valor deles e também o que ainda falta: os outros apps não têm testes.
- **Backup e restauração do PostgreSQL** com scripts, incluindo um que testa a restauração.
- **Organização em apps pequenos**, cada um com uma responsabilidade, e a lógica de cálculo do dashboard separada das views em `services.py`.

## Funcionalidades

| App | O que faz | Quem acessa |
|---|---|---|
| `produtos` | Cadastro, edição, ativação e listagem com filtros e paginação. Bloqueia a exclusão de produto com movimentações ou vendas. Importa e exporta planilha Excel | Administrador e Vendedor (o preço de custo só aparece para o Administrador) |
| `estoque` | Registro de movimentações (entrada, saída, ajuste e venda) e consulta do histórico | Administrador |
| `vendas` | Registro de venda com vários itens, baixa automática do estoque e lançamento no caixa | Administrador e Vendedor |
| `financeiro` | Contas a pagar e a receber (com baixa, cancelamento e exclusão) e fluxo de caixa | Administrador |
| `dashboard` | Indicadores (produtos, estoque baixo, vendas e faturamento do dia, mês e ano, contas atrasadas, saldo do caixa) e gráficos | Administrador |
| `logs` | Histórico de ações dos usuários (login, falhas de login, alterações) e bloqueio de tentativas repetidas | Administrador |
| `accounts` | Login, troca de senha e cadastro de usuários, com os perfis Administrador e Vendedor | Administrador (usuários) |
| `core` | Modelos-base (protegido e imutável), mixins de permissão e middleware de acesso | Interno |

### Importação por Excel

A chave de ligação é o código de barras (ou o nome exato, se a linha não tiver código). Produto existente tem preço e estoque atualizados só nos campos que a planilha informar: célula em branco não apaga nada. O estoque nunca é gravado direto, sempre por uma movimentação (ajuste para o valor da planilha, ou entrada para produto novo).

## Tecnologias

Python, Django 5.2, PostgreSQL (psycopg 3), Gunicorn, WhiteNoise, python-decouple, dj-database-url e openpyxl. Front-end com templates Django, Bootstrap e gráficos no dashboard.

## Como executar

Requisitos: Python 3 e PostgreSQL instalados.

**1. Baixar o projeto e criar o ambiente virtual**

```bash
git clone https://github.com/Marllon-A-TI/Petshop-ERP.git
cd Petshop-ERP
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**2. Criar o banco no PostgreSQL**

```sql
CREATE USER petshop WITH PASSWORD 'escolha-uma-senha';
CREATE DATABASE petshop OWNER petshop;
```

**3. Criar o arquivo `.env` na raiz do projeto** (ele não vai para o Git):

```
DJANGO_SECRET_KEY=troque-por-uma-chave-gerada
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000
DJANGO_TIME_ZONE=America/Sao_Paulo

DB_NAME=petshop
DB_USER=petshop
DB_PASSWORD=a-mesma-senha-do-passo-2
DB_HOST=localhost
DB_PORT=5432

DJANGO_BEHIND_PROXY=False
DJANGO_SECURE_SSL_REDIRECT=False
DJANGO_HSTS_SECONDS=0
DJANGO_COOKIES_SECURE=False
CLIENT_IP_HEADER=REMOTE_ADDR
```

Para gerar uma chave secreta nova:

```bash
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

**4. Criar as tabelas, os perfis e o primeiro usuário**

```bash
python manage.py migrate
python manage.py criar_grupos
python manage.py createsuperuser
python manage.py runserver
```

Abra `http://127.0.0.1:8000`. O superusuário tem acesso de Administrador. Para criar um Vendedor, entre como Administrador e use o cadastro de usuários.

## Testes

```bash
python manage.py test produtos
```

Os testes usam o PostgreSQL do `.env` (o Django cria e apaga um banco de teste). Hoje cobrem o app `produtos`. Escrever testes para estoque, vendas, financeiro e permissões é o meu próximo passo.

## Backup

A pasta `scripts/` tem os scripts de backup do PostgreSQL, o agendamento diário, a restauração e um teste de restauração. O passo a passo está em `scripts/backup_restauracao.md`.

## Próximos passos

- [ ] Testes para estoque, vendas, financeiro e permissões
- [ ] Cancelamento de venda
- [ ] Prints das telas neste README
- [ ] Documentar o deploy

## Autor

Marllon Araújo, estudante de Ciência da Computação. [GitHub](https://github.com/Marllon-A-TI) · marllon.araujo.ti@gmail.com
