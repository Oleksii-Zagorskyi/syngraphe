from django.urls import path

from documents import views

urlpatterns = [
    path("document/new/", views.create, name="document_create"),
    path("folder/<int:number>/", views.folder, name="folder"),
    path("document/<int:number>/", views.page, name="document"),
    path("document/<int:number>/info/", views.page, name="document_info"),
]
