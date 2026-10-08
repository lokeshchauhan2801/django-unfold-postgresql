from rest_framework.routers import DefaultRouter

from .views import DocumentChunkViewSet, DocumentViewSet, QueueMessageViewSet

router = DefaultRouter()
router.register("documents", DocumentViewSet, basename="scrapper-document")
router.register("document-chunks", DocumentChunkViewSet, basename="scrapper-document-chunk")
router.register("queue-messages", QueueMessageViewSet, basename="scrapper-queue-message")

urlpatterns = router.urls
