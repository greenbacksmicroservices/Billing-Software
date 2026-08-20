from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect

urlpatterns = [
    # Built-in Django Admin (mounted at alternative route)
    path('django-admin/', admin.site.urls),
    
    # Root redirects to login by default
    path('', lambda r: redirect('login')),
    
    # Include all billing & SaaS admin routes
    path('', include('billing.urls')),
]

# Static & Media routing for development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
