from django.urls import path
from . import views

urlpatterns = [
    path('', views.CompanyListCreateView.as_view(), name='company-list'),
    path('<uuid:pk>/', views.CompanyDetailView.as_view(), name='company-detail'),
    path('me/', views.MyCompaniesView.as_view(), name='my-companies'),
]
