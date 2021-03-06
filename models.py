import datetime
import time
import difflib
import logging

from urllib2 import Request as HttpRequest
from urllib2 import urlopen
from urllib2 import HTTPError
from urllib import urlencode

from django.conf import settings
from django.db import models
from django.db.models import signals

from djangosms.reporter.models import Reporter
from djangosms.reporter.models import Role
from djangosms.stats.models import Report
from djangosms.stats.models import Group
from djangosms.stats.models import GroupKind
from djangosms.core.models import User
from djangosms.core.models import Request

from djangosms.ui.sandbox.views import graduate
from djangosms.ui.sandbox.views import GraduateFailed

from treebeard.mp_tree import MP_Node

GENDER_CHOICES = (
    ('M', 'Male'),
    ('F', 'Female'),
    )

BIRTH_PLACE_CHOICES = (
    ('HOME', 'Home'),
    ('CLINIC', 'Clinic'),
    ('FACILITY', 'Facility'),
    )

def on_graduate(sender=None, reporter=None, **kwargs):
    requests = []
    try:
        reg_req = Request.objects.filter(
            erroneous=False, route__slug='register', 
            message__connection__user__pk=reporter.pk).latest('message__time')
        try:
            signup_req = Request.objects.filter(
                erroneous=False, route__slug='signup',
                message__connection__user__pk=reporter.pk).latest('message__time')
        except Request.DoesNotExist:
            pass
        else:
            requests.append(signup_req)

    except Request.DoesNotExist:
        pass
    else:
        requests.append(reg_req)
                
    for request in requests:
        try:
            urlopen(HttpRequest(settings.LIVE_URL,
             urlencode({
                'from':request.message.connection,
                'receiver':'6767',
                'text':request.message.text,
                'timestamp':int(time.mktime(request.message.time.timetuple())),
                'username':settings.LIVE_USERNAME,
                'password':settings.LIVE_PASSWORD,
             })
             ))
        except HTTPError, exc:
            logging.warn(exc)
            raise GraduateFailed()

graduate.connect(on_graduate)

class Facility(MP_Node):
    """HMIS health facility."""

    name = models.CharField(max_length=50, db_index=True)
    kind = models.ForeignKey(GroupKind)
    latitude = models.DecimalField(decimal_places=12, max_digits=14, null=True)
    longitude = models.DecimalField(decimal_places=12, max_digits=14, null=True)
    code = models.CharField(max_length=50, blank=True, null=True)

class ReportingPolicy(models.Model):
    """Group reporting policy."""

    group = models.OneToOneField(Group, related_name="reporting_policy", null=True)
    report_to = models.ForeignKey(Facility, related_name="policies", null=True)

class HealthRole(Role):
    """Community health role."""

    keyword = models.SlugField(max_length=10)

class HealthReporter(Reporter):
    """A Reporter is someone who interacts with RapidSMS as a user of
    the system (as opposed to an administrator).

    Although not enforced, they will tend to register with the system
    via SMS.
    """

    facility = models.ForeignKey(Facility, null=True)

class Patient(models.Model):
    health_id = models.CharField(max_length=30, null=True)
    name = models.CharField(max_length=50)
    sex = models.CharField(max_length=1, choices=GENDER_CHOICES)
    birthdate = models.DateTimeField()
    deathdate = models.DateTimeField(null=True)
    last_reported_on_by = models.ForeignKey(User)

    @property
    def age(self):
        return datetime.datetime.now(tz=self.birthdate.tzinfo) - self.birthdate

    @property
    def label(self):
        noun = 'male' if self.sex == 'M' else 'female'

        days = self.age.days
        if days > 365:
            age_string = "aged %d" % (days // 365)
        elif days > 30:
            age_string = "(%d months old)" % (days // 30)
        else:
            age_string = "(infant)"

        return "%s, %s %s" % (self.name, noun, age_string)

    @classmethod
    def identify(cls, name, sex, birthdate, user):
        patients = Patient.objects.filter(
            last_reported_on_by=user,
            name__icontains=name).all()

        names = [patient.name for patient in patients]
        matches = difflib.get_close_matches(name, names)
        if not matches:
            return

        name = matches[0]

        # return first match
        for patient in patients:
            if patient.name == name:
                return patient

class Case(models.Model):
    patient = models.ForeignKey(Patient, related_name="cases")
    report = models.ForeignKey(Report, related_name="cases")
    tracking_id = models.CharField(max_length=20, unique=True)
    closed = models.DateTimeField(null=True)

class BirthReport(Report):
    patient = models.ForeignKey(Patient)
    place = models.CharField(max_length=25, choices=BIRTH_PLACE_CHOICES)

class NutritionReport(Report):
    patient = models.ForeignKey(Patient)
    category = models.CharField(max_length=1)
    reading = models.FloatField(null=True)
    oedema = models.BooleanField()

