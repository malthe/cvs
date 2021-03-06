import datetime
import difflib
import itertools
import random

from picoparse import remaining
from picoparse import optional
from picoparse.text import whitespace

from djangosms.core import pico
from djangosms.core.router import Form
from djangosms.core.router import FormatError
from djangosms.reporter.models import Reporter
from djangosms.stats.models import Report
from djangosms.stats.models import Observation
from djangosms.stats.models import ObservationKind
from djangosms.stats.models import ReportKind

from django.db import IntegrityError
from django.conf import settings

from picoparse import choice
from picoparse import many
from picoparse import many1
from picoparse import one_of
from picoparse import partial
from picoparse import peek
from picoparse import tri

from .models import Facility
from .models import HealthRole
from .models import HealthReporter
from .models import ReportingPolicy
from .models import Case
from .models import Patient
from .models import BirthReport
from .models import NutritionReport

date = partial(pico.date, formats=settings.DATE_INPUT_FORMATS)

TRACKING_ID_LETTERS = tuple('ABCDEFGHJKLMPQRTUVXZ')

def generate_tracking_id():
    return '%2.d%s%s%2.d' % (
        random.randint(0, 99),
        random.choice(TRACKING_ID_LETTERS),
        random.choice(TRACKING_ID_LETTERS),
        random.randint(0, 99))


class Signup(Form):
    """Message to register as health worker or supervisor.

    Health workers:

      +<role> <facility_code> [, <location_name>]

    Supervisors:

      +<role> <facility_code>

    The token is the role keyword (see :class:`HealthRole`), while the
    code is an integer facility code.
    """

    @pico.wrap('text')
    def parse(self, keyword=None):
        roles = HealthRole.objects.all()
        by_keyword = dict((role.keyword, role) for role in roles)
        matches = difflib.get_close_matches(keyword.upper(), by_keyword)

        if not matches:
            raise FormatError(
                u"Did not understand the keyword: '%s'." % keyword)

        keyword = matches[0]
        result = {
            'role': by_keyword[keyword.upper()],
            }

        try:
            code = u"".join(pico.digits())
        except:
            raise FormatError(u"Expected an HMIS facility code (got: %s)." %
                             "".join(remaining()))

        try:
            facility = result['facility'] = Facility.objects.filter(code=code).get()
        except Facility.DoesNotExist:
            raise FormatError(u"No such HMIS facility code: %s." % code)

        whitespace()
        optional(pico.separator, None)

        # optionally provide a sub-village group
        name = "".join(remaining()).strip()
        if name:
            # get all (name, location) pairs of all child nodes of
            # groups that report to this facility
            policies = {}
            policy = None
            group = None

            for policy in facility.policies.all().select_related():
                policies[policy.group.name.upper()] = policy
                for descendant in policy.group.get_descendants():

                    try:
                        group_name = descendant.name.upper()
                        policies[group_name] = descendant.reporting_policy
                    except ReportingPolicy.DoesNotExist:
                        pass

            matches = difflib.get_close_matches(name.upper(), policies)
            if matches:
                name = matches[0]
                group = policies[name].group
            elif policy is not None:
                group = policy.group.add_child(
                    slug="added_by_user", name='"%s"' % name)
                facility.policies.create(group=group)

            result['group'] = group

        return result

    def handle(self, role=None, facility=None, group=None):
        reporter = Reporter.objects.get(pk=self.user.pk)
        try:
            reporter = HealthReporter.objects.get(pk=reporter.pk)
        except HealthReporter.DoesNotExist:
            reporter = HealthReporter(pk=reporter.pk, name=reporter.name)

            Report.from_observations(
                "registration", new_signup=1, group=group, source=self.request.message)

        reporter.facility = facility
        reporter.group = group
        reporter.save()

        health_roles = HealthRole.objects.all()

        for role_to_check in health_roles:
            if role_to_check in health_roles:
                reporter.roles.remove(role_to_check)

        reporter.roles.add(role)

        if group is not None:
            return "You have joined the system as %s reporting to %s in %s. " \
                   "Please resend if there is a mistake." % (
                role.name, facility.name, group.name)
        else:
            return "You have joined the system as %s reporting to %s. " \
                   "Please resend if there is a mistake." % (
                role.name, facility.name)

class Birth(Form):
    """Report a birth.

    Note that although this is not a complete birth registration form,
    we still enter a new patient record.

    Format::

      <name>, <sex> <location>

    We include ``name`` to corroborate the data. Location can one of:

    * At Home -- ``\"home\"``
    * Clinic -- ``\"clinic\"``
    * Health Facility -- ``\"facility\"``

    The last part of the form is forgiving in the sense that it just
    checks if any of these words occur in the remaining part of the
    message (until a punctuation).
    """

    @pico.wrap('text')
    def parse(cls):
        result = {}

        try:
            result['name'] = pico.name()
        except:
            raise FormatError(
                "Expected name (got: %s)." % "".join(remaining()))

        try:
            many1(partial(one_of, ' ,;'))
            result['sex'] = pico.one_of_strings(
                'male', 'female', 'm', 'f')[0].upper()
        except:
            raise FormatError(
                "Expected the infant's gender "
                "(\"male\", \"female\", or simply \"m\" or \"f\"), "
                "but received instead: %s." % "".join(remaining()))

        try:
            many1(partial(one_of, ' ,;'))
            words = pico.name().lower()
        except:
            raise FormatError(
                "Expected a location; "
                "either \"home\", \"clinic\" or \"facility\" "
                "(got: %s)." % "".join(remaining()))

        for word in words.split():
            matches = difflib.get_close_matches(
                word, ('home', 'clinic', 'facility'))
            if matches:
                result['place'] = matches[0].upper()
                break
        else:
            raise FormatError(
                "Did not understand the location: %s." % words)

        return result

    def handle(self, name=None, sex=None, place=None):
        Report.from_observations(slug='messages',
            source=self.request.message,messages_total_birth=1)
        
        birthdate = self.request.message.time

        patient = Patient(
            name=name, sex=sex, birthdate=birthdate,
            last_reported_on_by=self.user)
        patient.save()

        observations = {
            'birth_male' if sex == 'M' else 'birth_female': 1,
            "birth_at_%s" % place.lower(): 1,
            'birth_total': 1
            }

        Report.from_observations(
            "birth", source=self.request.message, **observations)

        birth = BirthReport(slug="birth", patient=patient,
                            place=place, source=self.request.message)
        birth.save()

        if place == 'CLINIC':
            birth_place = 'at a clinic'
        if place == 'FACILITY':
            birth_place = 'in a facility'
        if place == 'HOME':
            birth_place = 'at home'

        return "Thank you for registering the birth of %s. " \
               "We have recorded that the birth took place %s." % (
            patient.label, birth_place)

class PatientVisitation(Form):
    report_kind = None

    @pico.wrap('text')
    def parse(cls):
        result = {}

        try:
            identifiers = optional(tri(pico.ids), None)
            if identifiers:
                result['ids'] = [id.upper() for id in identifiers]
            else:
                result['name'] = pico.name()
        except:
            raise FormatError(
                "Expected a name, or a patient's health or tracking ID "
                "(got: %s)." % "".join(remaining()))

        if 'name' in result:
            try:
                many1(partial(one_of, ' ,;'))
                result['sex'] = pico.one_of_strings(
                    'male', 'female', 'm', 'f')[0].upper()
            except:
                raise FormatError(
                    "Expected the infant's gender "
                    "(\"male\", \"female\", or simply \"m\" or \"f\"), "
                    "but received instead: %s." % "".join(remaining()))
            try:
                pico.separator()
            except:
                raise FormatError("Expected age or birthdate of patient.")

            try:
                result['age'] = choice(*map(tri, (pico.date, pico.timedelta)))
            except:
                raise FormatError("Expected age or birthdate of patient, but "
                                 "received %s." % "".join(remaining()))

        return result

    def handle(self, ids=None, name=None, sex=None, age=None):
        if ids is not None:
            # this may be a tracking ids or a health ids; try both.
            cases = set(Case.objects.filter(tracking_id__in=ids).all())
            patients = set(Patient.objects.filter(health_id__in=ids).all())

            found = set([case.tracking_id for case in cases]) | \
                    set([case.health_id for case in patients])

            not_found = set(ids) - found

            if not_found:
                return "The id(s) %s do not exist. " \
                       "Please correct and resend all."  % \
                       ", ".join(not_found)

            patients |= set(case.patient for case in cases)
            cases |= set(itertools.chain(*[
                patient.cases.all() for patient in patients]))

        else:
            if isinstance(age, datetime.timedelta):
                birthdate = self.request.message.time - age
            else:
                birthdate = age

            patient = Patient.identify(name, sex, birthdate, self.user)
            if patient is None:
                Report.from_observations(slug=self.report_kind, unregistered_patient=1)
                return self.handle_unregistered(name, sex, birthdate)

            cases = patient.cases.all()
            patients = [patient]

        notifications = {}
        for case in cases:
            # ``source`` is not a required field
            if case.report.source is None: # pragma: NOCOVER
                continue
            # check if we need to notify the original case reporter
            case_reported_by = case.report.source.user
            if  case_reported_by != self.user:
                notifications[case_reported_by.pk] = case.patient

        Report.from_observations(slug=self.report_kind, registered_patient=len(patients))
        return self.handle_registered(patients, cases, notifications)

class Death(PatientVisitation):
    """Report a death.

    Format::

      <name>, <sex>, <age>
      [<health_id>]+
      [<tracking_id>]+

    """

    report_kind = "death"

    def handle_unregistered(self, name, sex, birthdate):
        Report.from_observations(slug='messages',
            source=self.request.message,messages_total_death=1)
        
        is_male = bool(sex == 'M')

        Report.from_observations(
            "death", source=self.request.message,
            death_male=is_male, death_female=not is_male)

        age = self.request.message.time - birthdate
        days = age.days
        if (days < 1826): # it's a child death if 5 years or under
            observations = {'death_under_five_total':1}
            if (days < 28):
                observations['death_under_month'] = 1
            elif (days < 90):
                observations['death_one_three_month'] = 1
            elif (days < 365):
                observations['death_three_twelve_month'] = 1
            else:
                observations['death_one_five_year'] = 1
            Report.from_observations("death", self.request.message, **observations)

        return u"We have recorded the death of %s." % \
               Patient(name=name, sex=sex, birthdate=birthdate).label

    def handle_registered(self, patients, cases, notifications):
        Report.from_observations(slug='messages',
            source=self.request.message,messages_total_death=1)
        
        death_male = 0
        death_female = 0

        for patient in patients:
            patient.deathdate = self.request.message.time
            patient.save()

            if patient.sex == 'M':
                death_male += 1
            else:
                death_female += 1
            
            age = self.request.message.time - patient.birthdate
            days = age.days
            if (days < 1826): # it's a child death if 5 years or under
                observations = {'death_under_five_total':1}
                if (days < 28):
                    observations['death_under_month'] = 1
                elif (days < 90):
                    observations['death_one_three_month'] = 1
                elif (days < 365):
                    observations['death_three_twelve_month'] = 1
                else:
                    observations['death_one_five_year'] = 1
                Report.from_observations("death", self.request.message, **observations)
                
                Report.from_observations("muac", self.request.message, muac_deaths=1)

        for case in cases:
            case.closed = self.request.message.time
            case.save()

        Report.from_observations(
            "death", source=self.request.message,
            death_male=death_male,
            death_female=death_female)

        Report.from_observations(
            "patient", source=self.request.message,
            closing_of_case=len(cases))

        for pk, patient in notifications.items():
            reporter = Reporter.objects.get(pk=pk)
            self.request.respond(
                reporter.most_recent_connection,
                u"This is to inform you that "
                "Your patient, %s, has died." % patient.label,)

        return "Thank you for reporting the death of %s; " \
               "we have closed %d open case(s)." % (
            ", ".join(patient.label for patient in patients),
            len(cases))

class Cure(PatientVisitation):
    """Mark a case as closed due to curing.

    Format::

      [<tracking_id>]+

    Separate multiple entries with space and/or comma. Tracking IDs
    are case-insensitive.
    """

    report_kind = "cure"

    def handle_unregistered(self, name, sex, birthdate):
        Report.from_observations(slug='messages',group=None,
            source=self.request.message,messages_total_cure=1)
        
        return u"We have recorded the curing of %s." % \
               Patient(name=name, sex=sex, birthdate=birthdate).label

    def handle_registered(self, patients, cases, notifications):
        Report.from_observations(slug='messages',group=None,
            source=self.request.message,messages_total_cure=1)
      
        for case in cases:
            case.closed = self.request.message.time
            case.save()

        Report.from_observations(
            "patient", source=self.request.message,
            closing_of_case=len(cases))

        Report.from_observations('muac', source=self.request.message,
            group=None, muac_cures=1)
        
        for pk, patient in notifications.items():
            reporter = Reporter.objects.get(pk=pk)

            self.request.respond(
                reporter.most_recent_connection,
                u"This is to inform you that "
                "Your patient, %s, has been cured." % patient.label)

        return "Thank you for reporting the curing of %s; " \
               "we have closed %d open case(s)." % (
            ", ".join(patient.label for patient in patients),
            len(cases))

class Otp(PatientVisitation):
    """Mark a case as seen in outpatient therapeutic program care.

    Format::

      [<tracking_id>]+

    Separate multiple entries with space and/or comma. Tracking IDs
    are case-insensitive.
    """

    report_kind = "otp"

    def handle_unregistered(self, name, sex, birthdate):
        return u"We have recorded the OTP visit of %s." % \
               Patient(name=name, sex=sex, birthdate=birthdate).label

    def handle_registered(self, patients, cases, notifications):
        for pk, patient in notifications.items():
            reporter = Reporter.objects.get(pk=pk)
            self.request.respond(
                reporter.most_recent_connection,
                u"This is to inform you that " \
                "Your patient, %s, has received OTP treatment." % patient.label)

        return "Thank you for reporting the OTP treatment of %s." % \
               ", ".join(patient.label for patient in patients)


class Itp(PatientVisitation):
    """Mark a case as seen in outpatient therapeutic program care.

    Format::

      [<tracking_id>]+

    Separate multiple entries with space and/or comma. Tracking IDs
    are case-insensitive.
    """

    report_kind = "itp"

    def handle_unregistered(self, name, sex, birthdate):
        return u"We have recorded the ITP visit of %s." % \
               Patient(name=name, sex=sex, birthdate=birthdate).label

    def handle_registered(self, patients, cases, notifications):
        for pk, patient in notifications.items():
            reporter = Reporter.objects.get(pk=pk)
            self.request.respond(
                reporter.most_recent_connection,
                u"This is to inform you that " \
                "Your patient, %s, has received ITP treatment." % patient.label)

        return "Thank you for reporting the ITP treatment of %s." % \
               ", ".join(patient.label for patient in patients)

class Observations(Form):
    """Form to allow multiple observation input.

    This form supports the following observation groups:

    * Epidemiology
    * Domestic Health

    Regular reports should come in with the format::

      [<total>, ]? [<code> <integer_value>]*

    For each entry, the value for ``code`` must map (via the keyword)
    to an observation kind, e.g. for an epidemiological report on
    malaria, ``\"MA\"`` would map to the observation kind
    ``\"epi_ma\"``.

    Only decimal values allowed; negative values are disallowed.

    Example input for 12 cases of malaria and 4 tuberculous cases::

      +EPI MA 12, TB 4

    The reports are confirmed in the reply, along with percentage or
    absolute change (whichever is applicable depending on whether this
    or the previous value is zero) on consecutive reporting.

    Example output::

      You reported malaria 12 (+5) and tuberculosis 4 (+23%).

    All aggregates are entered into the database as separate
    objects. To group aggregates based on reports, filter by reporter
    and group by time.
    """

    ALIASES = {
        'epi_dy': 'epi_bd',
        }

    KEYWORDS = {
        'epi': 'epidemiological_observations',
        'epid': 'epidemiological_observations',
        'home': 'observations_at_home',
        }

    @pico.wrap('text')
    def parse(cls, keyword=None, keywords=None):
        if keywords is None:
            keywords = cls.KEYWORDS

        slug = keywords[keyword.lower()]
        kind = ReportKind.objects.get(slug=slug)

        observations = {}
        result = {
            'observations': observations,
            'kind': kind,
            }

        total = "".join(optional(pico.digits, ()))
        if total:
            result['total'] = int(total)
            many1(partial(one_of, ' ,;'))

        kinds = ObservationKind.objects.filter(slug__startswith="%s_" % slug).all()
        observation_kinds = dict((kind.slug, kind) for kind in kinds)
        codes = [kind.abbr for kind in kinds if kind.abbr]

        # we allow both the observation kinds and any aliases
        allowed_codes = tuple(codes) + tuple(cls.ALIASES)

        while peek():
            # look up observation kinds that double as user input
            # for the aggregate codes
            try:
                code = "".join(pico.one_of_strings(*allowed_codes)).lower()
            except:
                raise FormatError(
                    "Expected an indicator code "
                    "such as %s (got: %s)." % (
                        " or ".join(map(unicode.upper, codes[:2])),
                        "".join(remaining()).strip() or u"nothing"))

            # rewrite alias if required, then look up kind
            munged= "%s_%s" % (slug, code)
            munged = cls.ALIASES.get(munged, munged)
            kind = observation_kinds[munged]

            # guard against duplicate entries
            if kind.slug in observations:
                raise FormatError("Duplicate value for %s." % code)

            whitespace()

            try:
                minus = optional(partial(one_of, '-'), '')
                value = int("".join([minus]+pico.digits()))
            except:
                raise FormatError("Expected a value for %s." % code)

            if value < 0:
                raise FormatError("Got %d for %s. You must "
                                  "report a positive value." % (
                    value, kind.name))

            observations[kind.slug] = value
            many(partial(one_of, ' ,;.'))

        return result

    def handle(self, kind=None, total=None, observations={}):
        if kind.slug == 'epidemiological_observations':
            Report.from_observations(slug='messages',group=None,
                source=self.request.message,messages_total_epi=1)
        elif kind.slug == 'observations_at_home': 
            Report.from_observations(slug='messages',
                source=self.request.message,messages_total_house=1)       
        
        if not observations:
            return u"Please include one or more reports."

        # determine whether there's any previous reports for this user
        previous_reports = Report.objects.filter(
            kind=kind, source__connection__user=self.user).all()
        if previous_reports:
            previous = previous_reports[0]
        else:
            previous = None

        # create new report to contain these observations
        report = Report(kind=kind, source=self.request.message)
        report.save()

        # if the report kind has support for an observation total,
        # we add it to the report
        if total is not None:
            try:
                total_kind = ObservationKind.objects\
                            .get(group=kind, slug__endswith="_total")
                report.observations.create(kind=total_kind, value=total)
            except ObservationKind.DoesNotExist:
                pass

        # we keep running tally of stats to generate message reply
        # item by item
        stats = []

        for slug, value in sorted(observations.items()):
            kind = ObservationKind.objects.get(slug=slug)
            stat = "%s %d" % (kind.name.lower(), value)

            previous_value = None
            if previous is not None:
                try:
                    previous_observation = previous.observations.get(kind=kind)
                except Observation.DoesNotExist: # pragma: NOCOVER
                    pass
                else:
                    previous_value = previous_observation.value

            if previous_value is not None:
                if value > 0 and previous_value > 0:
                    ratio = 100 * (float(value)/float(previous_value) - 1)
                    r = "%1.f%%" % abs(ratio)
                else:
                    ratio = value-int(previous_value)
                    r = str(abs(ratio))
                if ratio > 0:
                    r = "+" + r
                else:
                    r = "-" + r
                stat += " (%s)" % r

            report.observations.create(kind=kind, value=value)
            stats.append(stat)

        separator = [", "] * len(stats)
        if len(stats) > 1:
            separator[-2] = " and "
        separator[-1] = ""

        return u"You reported %s." % "".join(
            itertools.chain(*zip(stats, separator)))

class Muac(Form):
    """Middle upper arm circumference measurement.

    Formats::

      +MUAC <name>, <sex>, <age>, <reading> [,oedema]
      +MUAC <health_id>, <reading> [,oedema]
      <health_id> +MUAC <reading> [,oedema]

    Note that a patient id must contain one or more digits (to
    distinguish a name from a patient id).

    Oedema may be specified as \"oedema\" or simply \"oe\".

    Reading is one of (case-insensitive):

    - ``\"red\"`` (or ``\"r\"``)
    - ``\"yellow\"`` (or ``\"y\"``)
    - ``\"green\"`` (or ``\"g\"``)

    Or, alternatively the reading may be a floating point number,
    e.g. ``\"114 mm\"`` (unit optional).
    values > 30, otherwise *cm* is assumed). While such a value will
    be translated into one of the readings above, the given number is
    still recorded.

    Both yellow and red categories result in a referral. Included in
    the reply is then a tracking ID which is used in other commands to
    follow up on the referral.
    """

    @staticmethod
    def get_reading_in_mm(reading):
        if reading > 30:
            return reading
        return reading*10

    @pico.wrap('text')
    def parse(self, health_id=None):
        result = {}

        if health_id is None:
            try:
                part = optional(tri(pico.identifier), None)
                if part is not None:
                    health_id = "".join(part)
                else:
                    result['name'] = pico.name()
            except:
                raise FormatError("Expected a patient id or name.")

        if 'name' in result:
            try:
                pico.separator()
                result['sex'] = pico.one_of_strings(
                    'male', 'female', 'm', 'f')[0].upper()
            except:
                raise FormatError(
                    "Expected either M or F " \
                    "to indicate the patient's gender (got: %s)." %
                    "".join(remaining()))

            try:
                pico.separator()
            except:
                raise FormatError("Expected age or birthdate of patient.")

            try:
                result['age'] = choice(*map(tri, (pico.date, pico.timedelta)))
            except:
                raise FormatError("Expected age or birthdate of patient, but "
                                 "received %s." % "".join(
                                      remaining()).split(',')[0])

        if health_id is not None:
            result['health_id'] = health_id

        try:
            whitespace()
            optional(pico.separator, None)
            reading = choice(
                partial(pico.one_of_strings,
                        'red', 'green', 'yellow', 'r', 'g', 'y'), pico.digits)

            try:
                reading = int("".join(reading))
            except:
                result['category'] = reading[0].upper()
            else:
                whitespace()
                unit = optional(partial(pico.one_of_strings, 'mm', 'cm'), None)
                if unit is None:
                    reading = self.get_reading_in_mm(reading)
                elif "".join(unit) == 'cm':
                    reading = reading * 10
                result['reading'] = reading
        except:
            raise FormatError(
                "Expected MUAC reading (either green, yellow or red), but "
                "received %s." % "".join(remaining()))

        if optional(partial(choice, tri(pico.separator), tri(whitespace)), None):
            if optional(partial(
                pico.one_of_strings, 'oedema', 'odema', 'oe'), None):
                result['oedema'] = True
            elif peek():
                raise FormatError(
                    "Specify \"oedema\"  or \"oe\" if the patient shows "
                    "signs of oedema, otherwise leave empty (got: %s)." % \
                    "".join(remaining()))

        return result

    def handle(self, health_id=None, name=None, sex=None,
               age=None, category=None, reading=None, oedema=False):
        user = Reporter.objects.get(pk=self.request.message.user.pk)
        Report.from_observations(
            slug='messages',
            source=self.request.message,messages_total_muac=1)

        for role in user.roles.all():
            if role.slug in ('vht', 'pvht'):
                Report.from_observations(
                    'muac', source=self.request.message, vht_cases=1)
            elif role.slug in ('hno', 'hso'):
                Report.from_observations(
                    'muac', source=self.request.message, facility_cases=1)

        if health_id is None:
            if isinstance(age, datetime.timedelta):
                birthdate = self.request.message.time - age
            else:
                birthdate = age

            # attempt to identify the patient using the information
            patient = Patient.identify(name, sex, birthdate, self.user)

            # if we fail to identify the patient, we create a new record
            if patient is None:
                patient = Patient(
                    name=name, sex=sex, birthdate=birthdate,
                    last_reported_on_by=self.user)
                patient.save()
        else:
            try:
                patient = Patient.objects.filter(health_id=health_id).get()
            except Patient.DoesNotExist:
                return u"Patient not found: %s." % health_id

        if category is None and reading is not None:
            if reading > 125:
                category = 'G'
            elif reading < 114:
                category = 'R'
            else:
                category = 'Y'

        report = NutritionReport(
            slug="muac",
            reading=reading,
            category=category,
            patient=patient,
            oedema=oedema,
            source=self.request.message)

        report.save()

        report.observations.create(slug="oedema", value=int(oedema))
        report.observations.create(
            slug="age",
            value=(self.request.message.time-patient.birthdate).days)
        if not oedema:
            report.observations.create(
                slug={'G': 'green_muac',
                      'Y': 'yellow_muac',
                      'R': 'red_muac'}[category],
                      value=1)
        else:
            report.observations.create(
                slug={'G': 'green_muac_oedema',
                      'Y': 'yellow_muac_oedema',
                      'R': 'red_muac_oedema'}[category],
                      value=1)            

        pronoun = 'his' if patient.sex == 'M' else 'her'

        if category != 'G' or oedema:
            Report.from_observations('muac', group=None,
                source=self.request.message, muac_referrals=1)
            case = Case(patient=patient, report=report)
            while case.id is None:
                try:
                    tracking_id = generate_tracking_id()
                    case.tracking_id = tracking_id
                    case.save()
                except IntegrityError: # pragma: NOCOVER
                    pass

            Report.from_observations(slug="patient", opening_of_case=1)

            if category == 'Y':
                severity = "Risk of"
            else:
                severity = "Severe Acute"

            if oedema:
                possibly_oedema = "(with oedema)"
            else:
                possibly_oedema = ""

            return "%s has been identified with " \
                   "%s Malnutrition%s. %s Case Number %s." % (
                patient.label, severity, possibly_oedema, pronoun.capitalize(),
                tracking_id)

        return "Thank you for reporting your measurement of " \
                "%s. %s reading is normal (green)." % (
            patient.label, pronoun.capitalize())
