"""
Unit and integration tests for the accounts app.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class RegistrationFormTest(TestCase):
    """Test user registration validation."""

    def test_valid_registration(self):
        """Valid registration creates a user and logs them in."""
        client = Client()
        response = client.post(
            reverse("accounts:register"),
            {
                "username": "testuser",
                "email": "test@example.com",
                "password1": "strongpassword123",
                "password2": "strongpassword123",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="testuser").exists())

    def test_duplicate_username_rejected(self):
        """Registration with an existing username returns form error."""
        User.objects.create_user("existing", "e@example.com", "password123")
        client = Client()
        response = client.post(
            reverse("accounts:register"),
            {
                "username": "existing",
                "email": "new@example.com",
                "password1": "strongpassword123",
                "password2": "strongpassword123",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="new@example.com").exists())

    def test_weak_password_rejected(self):
        """Short password fails validation."""
        client = Client()
        response = client.post(
            reverse("accounts:register"),
            {
                "username": "newuser",
                "email": "new@example.com",
                "password1": "short",
                "password2": "short",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newuser").exists())


class LoginViewTest(TestCase):
    """Test user login."""

    def setUp(self):
        self.user = User.objects.create_user("loginuser", "login@example.com", "testpassword123")

    def test_valid_login(self):
        """Valid credentials log the user in."""
        client = Client()
        response = client.post(
            reverse("accounts:login"),
            {"username": "loginuser", "password": "testpassword123"},
        )
        self.assertEqual(response.status_code, 302)

    def test_invalid_password(self):
        """Wrong password returns 200 (re-renders form)."""
        client = Client()
        response = client.post(
            reverse("accounts:login"),
            {"username": "loginuser", "password": "wrongpassword"},
        )
        self.assertEqual(response.status_code, 200)

    def test_unauthenticated_redirected_to_login(self):
        """Unauthenticated access to /documents/ redirects to login."""
        client = Client()
        response = client.get("/documents/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])


class LogoutViewTest(TestCase):
    """Test user logout."""

    def setUp(self):
        self.user = User.objects.create_user("logoutuser", "logout@example.com", "testpassword123")

    def test_logout_destroys_session(self):
        """POST to logout destroys session and redirects."""
        client = Client()
        client.login(username="logoutuser", password="testpassword123")
        response = client.post(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)
        # Subsequent request should redirect to login
        response = client.get("/documents/")
        self.assertEqual(response.status_code, 302)

    def test_logout_requires_post(self):
        """GET to logout is rejected (405)."""
        client = Client()
        client.login(username="logoutuser", password="testpassword123")
        response = client.get(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 405)
