from django.conf.urls.defaults import *
from django.contrib import admin

from djangosms.core.views import incoming
from djangosms.ui.urls import urlpatterns as ui_urls

admin.autodiscover()

urlpatterns = patterns(
    '',
    (r'^admin/', include(admin.site.urls)),
    (r'^incoming/', incoming),
    ) + \
    ui_urls
