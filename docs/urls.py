from django.urls import path

from .views import document_list, reprocess_document, upload_document

urlpatterns = [
    path("", document_list, name="document_list"),
    path("upload/", upload_document, name="document_upload"),
    path("<uuid:document_id>/reprocess/", reprocess_document, name="document_reprocess"),
]
