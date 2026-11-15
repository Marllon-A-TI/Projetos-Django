from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    SetPasswordForm,
    UserCreationForm,
    UsernameField,
)
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction

from core.forms import BootstrapFormMixin

from .models import GRUPO_ADMINISTRADOR, GRUPOS

User = get_user_model()


def _grupos_disponiveis():
    return Group.objects.filter(name__in=GRUPOS).order_by("name")


def _aplicar_grupo(usuario, grupo):
    """
    Define o perfil (grupo) do usuário. Somente administradores acessam
    o /admin do Django (is_staff).
    """
    usuario.groups.set([grupo])
    deve_ser_staff = grupo.name == GRUPO_ADMINISTRADOR or usuario.is_superuser
    if usuario.is_staff != deve_ser_staff:
        usuario.is_staff = deve_ser_staff
        usuario.save(update_fields=["is_staff"])


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    username = UsernameField(
        label="Usuário",
        widget=forms.TextInput(
            attrs={"autofocus": True, "autocomplete": "username"}
        ),
    )
    password = forms.CharField(
        label="Senha",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    error_messages = {
        "invalid_login": "Usuário ou senha incorretos. Verifique e tente novamente.",
        "inactive": "Este usuário está inativo.",
    }


class UsuarioCriarForm(BootstrapFormMixin, UserCreationForm):
    grupo = forms.ModelChoiceField(
        label="Perfil de acesso",
        queryset=Group.objects.none(),
        empty_label="Selecione o perfil",
    )

    field_order = [
        "username",
        "first_name",
        "last_name",
        "email",
        "grupo",
        "password1",
        "password2",
        "is_active",
    ]

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["grupo"].queryset = _grupos_disponiveis()
        self.fields["first_name"].required = True

    @transaction.atomic
    def save(self, commit=True):
        usuario = super().save(commit=False)
        if commit:
            usuario.save()
            _aplicar_grupo(usuario, self.cleaned_data["grupo"])
        return usuario


class UsuarioEditarForm(BootstrapFormMixin, forms.ModelForm):
    grupo = forms.ModelChoiceField(
        label="Perfil de acesso",
        queryset=Group.objects.none(),
        empty_label="Selecione o perfil",
    )

    field_order = [
        "username",
        "first_name",
        "last_name",
        "email",
        "grupo",
        "is_active",
    ]

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "is_active")

    def __init__(self, *args, usuario_logado=None, **kwargs):
        self.usuario_logado = usuario_logado
        super().__init__(*args, **kwargs)
        self.fields["grupo"].queryset = _grupos_disponiveis()
        self.fields["first_name"].required = True

        if self.instance.pk and not self.is_bound:
            atual = self.instance.groups.filter(name__in=GRUPOS).first()
            if atual:
                self.initial["grupo"] = atual.pk

    def clean(self):
        dados = super().clean()
        grupo = dados.get("grupo")
        ativo = dados.get("is_active")
        if grupo is None or ativo is None or not self.instance.pk:
            return dados

        era_admin_ativo = (
            self.instance.is_active
            and self.instance.groups.filter(name=GRUPO_ADMINISTRADOR).exists()
        )
        deixa_de_ser_admin_ativo = (not ativo) or grupo.name != GRUPO_ADMINISTRADOR

        if era_admin_ativo and deixa_de_ser_admin_ativo:
            if self.usuario_logado and self.instance.pk == self.usuario_logado.pk:
                raise ValidationError(
                    "Você não pode desativar nem rebaixar o seu próprio usuário."
                )

            outros_admins = (
                User.objects.filter(is_active=True, groups__name=GRUPO_ADMINISTRADOR)
                .exclude(pk=self.instance.pk)
                .exists()
            )
            if not outros_admins:
                raise ValidationError(
                    "Deve existir pelo menos um administrador ativo no sistema."
                )

        return dados

    @transaction.atomic
    def save(self, commit=True):
        usuario = super().save(commit=commit)
        if commit:
            _aplicar_grupo(usuario, self.cleaned_data["grupo"])
        return usuario


class AlterarSenhaForm(BootstrapFormMixin, PasswordChangeForm):
    """O próprio usuário troca a sua senha (pede a senha atual)."""


class RedefinirSenhaForm(BootstrapFormMixin, SetPasswordForm):
    """O administrador define uma nova senha para outro usuário."""