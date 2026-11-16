‼️ Projeto de Django feito junto com o professor Otávio Miranda, através de seu curso na plataforma digital 'Udemy'.

‼️O código acompanha as aulas.

Objetivo:
* Curso_Agenda/Agenda de contatos: contatos com categoria, foto e dono (usuário), com formulários de contato e de usuário.

Tecnologia: 
* Django 4.2 & SQLite

Aprendizado:

* URLs, views, templates, herança de templates, partials, arquivos estáticos, banco de dados, models, forms e autenticação.

Como rodar o projeto:


cd Curso_Agenda             # entrar na pasta do projeto

python -m venv venv        # criar ambiente virtual

source venv/bin/activate   # Windows: venv\Scripts\activate  - # ativar ambiente

pip install -r requirements.txt  # instalar dependências

cp .env.example .env       # defina DJANGO_SECRET_KEY

python manage.py migrate
python manage.py runserver

O .env não vai para o Git. O .env.example tem só DJANGO_SECRET_KEY=troque-por-uma-chave-gerada.
