
from django.contrib import admin
from django.urls import path,include,re_path
from django.conf import settings
from django.conf.urls.static import static
from microfinance import views as microview


urlpatterns = [
   # path('', views.dashboard,name="dashboard"),
    path('', include('microfinance.urls')),
    path('', include('microfinance.urls')),
    path('admin/', admin.site.urls),
    re_path(r'^accounts/', include('accounts.urls')),

]
urlpatterns = urlpatterns + static(settings.MEDIA_URL,document_root=settings.MEDIA_ROOT) 