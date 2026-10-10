from django.urls import path

from .views import (
    document_list,
    library_upload,
    process_document_view,
    reprocess_document,
    upload_document,
)

urlpatterns = [
    path("", document_list, name="document_list"),
    path("upload/", upload_document, name="document_upload"),
    path("library/upload/", library_upload, name="document_library_upload"),
    path("<uuid:document_id>/process/", process_document_view, name="document_process"),
    path("<uuid:document_id>/reprocess/", reprocess_document, name="document_reprocess"),
]
