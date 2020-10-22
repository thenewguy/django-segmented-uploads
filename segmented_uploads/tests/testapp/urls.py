from django.urls import path

from . import views


urlpatterns = [
    path('', views.AuthorCreate.as_view(), name='author-create'),
    path('author/<pk>/', views.AuthorUpdate.as_view(), name='author-update'),
]
