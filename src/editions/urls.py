from django.urls import path

from editions import views

urlpatterns = [
    path("document/<int:number>/freeze/", views.freeze, name="document_freeze"),
    path(
        "document/<int:number>/make-canonical/",
        views.make_canonical,
        name="document_make_canonical",
    ),
]
