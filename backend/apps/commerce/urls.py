from django.urls import path
from .views import (
    checkout_view,
    catalog_view,
    product_detail_view,
    start_purchase_view,
    payment_callback_view,
    payment_status_view,
    audit_trail_view,
    security_demo_view,
    concurrency_demo_view,
    start_concurrency_race_view,
    concurrency_race_status_view,
)

urlpatterns = [
    path("", catalog_view, name="catalog"),
    path("concurrency-demo/", concurrency_demo_view, name="concurrency-demo"),
    path("concurrency-demo/start/", start_concurrency_race_view, name="concurrency-demo-start"),
    path("concurrency-demo/status/<str:race_id>/", concurrency_race_status_view, name="concurrency-demo-status"),
    path("product/<str:product_id>/", product_detail_view, name="product-detail"),
    path("buy/<str:product_id>/", start_purchase_view, name="start-purchase"),
    path("checkout/<str:order_id>/", checkout_view, name="checkout"),
    path("checkout/<str:order_id>/callback/", payment_callback_view, name="payment-callback"),
    path("checkout/<str:order_id>/status/", payment_status_view, name="payment-status"),
    path("checkout/<str:intent_id>/audit/", audit_trail_view, name="audit-trail"),
    path("security-demo/", security_demo_view, name="security-demo"),
]