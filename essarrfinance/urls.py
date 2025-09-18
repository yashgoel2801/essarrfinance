from django.contrib import admin
from django.urls import path,include,re_path
from django.conf import settings
from django.conf.urls.static import static
from microfinance import views as microview


urlpatterns = [
   # path('', views.dashboard,name="dashboard"),
    path('v2/', include('microfinance.urls')),
    path('v2/admin/', admin.site.urls),
    re_path(r'^v2/accounts/', include('accounts.urls')),

]
urlpatterns = urlpatterns + static(settings.MEDIA_URL,document_root=settings.MEDIA_ROOT) 