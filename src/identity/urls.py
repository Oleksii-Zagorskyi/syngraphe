from django.urls import path

from identity.views import setup, signin

urlpatterns = [
    path("setup/", setup.setup, name="setup"),
    path("signin/", signin.signin, name="signin"),
    path("signout/", signin.signout, name="signout"),
]
