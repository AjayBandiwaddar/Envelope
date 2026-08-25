from django.urls import path
from .views import checkout_view

urlpatterns = [
    path("<str:order_id>/", checkout_view, name="checkout"),
]