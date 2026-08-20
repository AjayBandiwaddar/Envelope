from django.urls import path

from .views import AuthorizeView

urlpatterns = [
    path("authorize/", AuthorizeView.as_view(), name="authorize"),
]