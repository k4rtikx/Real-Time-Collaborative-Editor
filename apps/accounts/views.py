"""Account views — registration, login, logout."""
import logging

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import LoginForm, RegistrationForm

logger = logging.getLogger(__name__)


@require_http_methods(["GET", "POST"])
def register_view(request):
    """User registration view."""
    if request.user.is_authenticated:
        return redirect("documents:list")

    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            logger.info("User registered and logged in", extra={"user_id": user.id})
            return redirect("documents:list")
    else:
        form = RegistrationForm()

    return render(request, "accounts/register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def login_view(request):
    """User login view."""
    if request.user.is_authenticated:
        return redirect("documents:list")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = request.GET.get("next", "/documents/")
            logger.info("User logged in", extra={"user_id": user.id})
            return redirect(next_url)
        else:
            # Log failed attempt without exposing the attempted password
            logger.warning(
                "Failed login attempt",
                extra={"username": request.POST.get("username", "")[:50]},
            )
    else:
        form = LoginForm(request)

    return render(request, "accounts/login.html", {"form": form})


@require_http_methods(["POST"])
@login_required
def logout_view(request):
    """User logout view — POST only to prevent CSRF-based logout."""
    user_id = request.user.id
    logout(request)
    logger.info("User logged out", extra={"user_id": user_id})
    return redirect("/")
