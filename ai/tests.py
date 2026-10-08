from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from pydantic import BaseModel

from ai.providers import get_ai_provider


class AIProviderConfigurationTests(SimpleTestCase):
    @override_settings(AI_PROVIDER="mock")
    def test_mock_provider_is_not_used_as_a_fallback(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "Use 'openai' or 'openai_compatible'",
        ):
            get_ai_provider()

    @override_settings(AI_PROVIDER="openai", AI_API_KEY="", OPENAI_API_KEY="")
    def test_openai_requires_an_api_key(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "Set AI_API_KEY"):
            get_ai_provider()

    @override_settings(
        AI_PROVIDER="openai",
        AI_API_KEY="",
        OPENAI_API_KEY="openai-key",
    )
    @patch("apps.ai.providers.ChatOpenAI")
    def test_openai_uses_the_existing_api_key_setting(self, chat_openai):
        get_ai_provider()

        chat_openai.assert_called_once_with(
            model="gpt-4o-mini",
            temperature=0.2,
            api_key="openai-key",
        )

    @override_settings(
        AI_PROVIDER="openai_compatible",
        DEFAULT_LLM_MODEL="deepseek-chat",
        AI_API_KEY="provider-key",
        AI_BASE_URL="https://api.deepseek.com/v1",
        OPENAI_API_KEY="embedding-key",
    )
    @patch("apps.ai.providers.ChatOpenAI")
    def test_openai_compatible_provider_uses_configured_model_and_endpoint(
        self,
        chat_openai,
    ):
        get_ai_provider()

        chat_openai.assert_called_once_with(
            model="deepseek-chat",
            temperature=0.2,
            api_key="provider-key",
            base_url="https://api.deepseek.com/v1",
        )

    @override_settings(
        AI_PROVIDER="openai_compatible",
        AI_API_KEY="provider-key",
        AI_BASE_URL="https://api.deepseek.com/v1",
    )
    @patch("apps.ai.providers.ChatOpenAI")
    def test_openai_compatible_provider_uses_function_calling_for_structured_output(
        self,
        chat_openai,
    ):
        class ResponseSchema(BaseModel):
            response: str

        expected = ResponseSchema(response="OK")
        chat_openai.return_value.with_structured_output.return_value.invoke.return_value = (
            expected
        )
        provider = get_ai_provider()

        result = provider.generate_structured("prompt", ResponseSchema)

        self.assertEqual(result, expected)
        chat_openai.return_value.with_structured_output.assert_called_once_with(
            ResponseSchema,
            method="function_calling",
        )
