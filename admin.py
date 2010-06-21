from django.contrib import admin
from . import models

admin.site.register(models.ReportingPolicy)
admin.site.register(models.Facility)
admin.site.register(models.HealthRole)
admin.site.register(models.HealthReporter)
