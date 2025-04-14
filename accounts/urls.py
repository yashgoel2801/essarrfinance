from django.urls import path,re_path as url
from .import views

app_name ='accounts'


urlpatterns = [
    url(r'^login/$',views.login_view,name="login"),
    url(r'^logout/$',views.logout_view,name="logout"),    
]