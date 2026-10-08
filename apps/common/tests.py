from django.test import SimpleTestCase

from apps.common.admin_dashboard import admin_dashboard


class AdminDashboardTests(SimpleTestCase):
    def test_dashboard_contains_only_configured_models(self):
        context = {
            "app_list": [
                {
                    "app_label": "companies",
                    "models": [
                        {"object_name": "Company"},
                        {"object_name": "CompanyMembership"},
                    ],
                },
                {
                    "app_label": "token_blacklist",
                    "models": [{"object_name": "OutstandingToken"}],
                },
            ],
        }

        result = admin_dashboard(None, context)

        self.assertEqual(
            [
                (app["app_label"], [model["object_name"] for model in app["models"]])
                for app in result["app_list"]
            ],
            [
                ("companies", ["Company", "CompanyMembership"]),
            ],
        )
