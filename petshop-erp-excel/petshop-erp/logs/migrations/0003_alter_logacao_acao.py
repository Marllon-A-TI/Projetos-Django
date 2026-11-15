from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('logs', '0002_alter_logacao_acao'),
    ]

    operations = [
        migrations.AlterField(
            model_name='logacao',
            name='acao',
            field=models.CharField(choices=[('CRIACAO', 'Criação'), ('EDICAO', 'Edição'), ('EXCLUSAO', 'Exclusão'), ('VENDA', 'Venda'), ('LOGIN', 'Login'), ('LOGOUT', 'Logout'), ('LOGIN_ERRO', 'Falha de login'), ('IMPORTACAO', 'Importação'), ('EXPORTACAO', 'Exportação')], max_length=10, verbose_name='ação'),
        ),
    ]
