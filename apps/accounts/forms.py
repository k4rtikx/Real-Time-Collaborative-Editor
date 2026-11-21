"""Account registration and authentication forms."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

User = get_user_model()

_INPUT_ATTRS = {"class": "form-control"}
_PASSWORD_ATTRS = {"class": "form-control", "autocomplete": "new-password"}


class RegistrationForm(UserCreationForm):
    """User registration form with optional email field."""

    email = forms.EmailField(
        required=False,
        help_text="Optional.",
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "you@example.com"}),
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update(_PASSWORD_ATTRS)
        self.fields["password2"].widget.attrs.update({"class": "form-control"})
        # Strip help text noise from password fields
        self.fields["password1"].help_text = ""
        self.fields["password2"].help_text = ""

    def clean_email(self) -> str:
        email = self.cleaned_data.get("email", "").lower().strip()
        if email and User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email address already exists.")
        return email

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        user.email = self.cleaned_data.get("email", "")
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    """Login form — thin wrapper for consistent error messaging."""

    error_messages = {
        "invalid_login": "Invalid username or password.",
        "inactive": "This account is inactive.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({
            "class": "form-control",
            "autofocus": True,
        })
        self.fields["password"].widget.attrs.update({
            "class": "form-control",
            "autocomplete": "current-password",
        })
