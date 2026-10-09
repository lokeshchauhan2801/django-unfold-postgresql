"""Mock LLM provider for local development and testing."""
from .interfaces import LLMProvider
from .factory import register_provider


@register_provider('mock')
class MockLLMProvider(LLMProvider):
    """Returns canned responses. No external calls. Free."""

    def get_chat_model(self, **kwargs):
        from langchain_core.language_models.fake import FakeListChatModel
        return FakeListChatModel(responses=['Mock AI response. Configure a real provider for actual responses.'])

    def get_embedding_model(self, **kwargs):
        from langchain_core.embeddings import FakeEmbeddings
        return FakeEmbeddings(size=1536)

    def get_provider_name(self) -> str:
        return 'Mock'
