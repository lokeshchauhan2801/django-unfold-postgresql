from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse


class UserAuthApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(username="alice", email="alice@example.com", password="secret123")

    def test_signup_api_creates_user(self):
        response = self.client.post(
            reverse("auth-register"),
            {"username": "bob", "email": "bob@example.com", "password": "strongpass123"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertTrue(get_user_model().objects.filter(username="bob").exists())

    def test_login_api_authenticates_user(self):
        response = self.client.post(
            reverse("auth-login"),
            {"username": "alice", "password": "secret123"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_current_user_requires_login(self):
        response = self.client.get(reverse("current-user"))
        self.assertEqual(response.status_code, 401)
