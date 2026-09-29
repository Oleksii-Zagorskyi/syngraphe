from django.urls import path

from review.views import accept, pending

urlpatterns = [
    path("document/<int:number>/pending/", pending.page, name="document_pending"),
    path("document/<int:number>/pending/accept/", accept.accept, name="document_accept"),
]
