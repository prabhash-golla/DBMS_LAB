from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PostViewSet

# Initialize DefaultRouter
post_router = DefaultRouter()
post_router.register(r'posts', PostViewSet)  # Register viewset

# Define urlpatterns
urlpatterns = [
    path('', include(post_router.urls)),  # Include router-generated URLs
]
