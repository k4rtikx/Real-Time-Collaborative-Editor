"""
Unit tests for document permissions, services, and views.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.documents.models import Document, DocumentPermission
from apps.documents.permissions import get_user_role, has_edit_permission, has_view_permission
from apps.documents.services import create_document, share_document, revoke_permission

User = get_user_model()


class DocumentPermissionsTest(TestCase):
    """Test permission resolution functions."""

    def setUp(self):
        self.owner = User.objects.create_user("owner", "owner@example.com", "password123")
        self.editor = User.objects.create_user("editor", "editor@example.com", "password123")
        self.viewer = User.objects.create_user("viewer", "viewer@example.com", "password123")
        self.stranger = User.objects.create_user("stranger", "stranger@example.com", "password123")
        self.document = create_document(self.owner, title="Test Doc")
        share_document(self.owner, self.document, self.editor, "editor")
        share_document(self.owner, self.document, self.viewer, "viewer")

    def test_owner_role(self):
        self.assertEqual(get_user_role(self.owner, self.document), "owner")

    def test_editor_role(self):
        self.assertEqual(get_user_role(self.editor, self.document), "editor")

    def test_viewer_role(self):
        self.assertEqual(get_user_role(self.viewer, self.document), "viewer")

    def test_stranger_has_no_access(self):
        self.assertIsNone(get_user_role(self.stranger, self.document))

    def test_owner_can_edit(self):
        self.assertTrue(has_edit_permission(self.owner, self.document))

    def test_editor_can_edit(self):
        self.assertTrue(has_edit_permission(self.editor, self.document))

    def test_viewer_cannot_edit(self):
        self.assertFalse(has_edit_permission(self.viewer, self.document))

    def test_stranger_cannot_view(self):
        self.assertFalse(has_view_permission(self.stranger, self.document))


class DocumentServiceTest(TestCase):
    """Test document service functions."""

    def setUp(self):
        self.owner = User.objects.create_user("sowner", "sowner@example.com", "password123")
        self.other = User.objects.create_user("sother", "sother@example.com", "password123")
        self.document = create_document(self.owner, "Service Test Doc")

    def test_create_document_sets_owner(self):
        self.assertEqual(self.document.owner, self.owner)

    def test_create_document_has_uuid(self):
        self.assertIsNotNone(self.document.uuid)

    def test_share_creates_permission(self):
        share_document(self.owner, self.document, self.other, "editor")
        self.assertTrue(
            DocumentPermission.objects.filter(
                document=self.document, user=self.other, role="editor"
            ).exists()
        )

    def test_share_invalid_role_raises(self):
        with self.assertRaises(ValueError):
            share_document(self.owner, self.document, self.other, "superuser")

    def test_share_with_self_raises(self):
        with self.assertRaises(ValueError):
            share_document(self.owner, self.document, self.owner, "editor")

    def test_non_owner_cannot_share(self):
        with self.assertRaises(PermissionError):
            share_document(self.other, self.document, self.other, "editor")

    def test_revoke_permission(self):
        share_document(self.owner, self.document, self.other, "editor")
        revoke_permission(self.owner, self.document, self.other)
        self.assertFalse(
            DocumentPermission.objects.filter(
                document=self.document, user=self.other
            ).exists()
        )


class DocumentViewAuthTest(TestCase):
    """Test that views enforce authentication and authorization."""

    def setUp(self):
        self.owner = User.objects.create_user("vowner", "vowner@example.com", "password123")
        self.stranger = User.objects.create_user("vstranger", "vstranger@example.com", "password123")
        self.document = create_document(self.owner, "View Test Doc")

    def test_unauthenticated_redirected(self):
        client = Client()
        response = client.get(f"/documents/{self.document.uuid}/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_stranger_gets_403(self):
        client = Client()
        client.login(username="vstranger", password="password123")
        response = client.get(f"/documents/{self.document.uuid}/")
        self.assertEqual(response.status_code, 403)

    def test_owner_can_access(self):
        client = Client()
        client.login(username="vowner", password="password123")
        response = client.get(f"/documents/{self.document.uuid}/")
        self.assertEqual(response.status_code, 200)
