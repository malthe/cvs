from django.test import TestCase
from djangosms.core.testing import FormTestCase

class ParserTest(TestCase):
    @staticmethod
    def _muac(text):
        from ..forms import Muac
        return Muac().parse(text=text)

    @property
    def _datetime(self):
        from datetime import datetime
        return datetime

    @property
    def _timedelta(self):
        from datetime import timedelta
        return timedelta

    def test_empty(self):
        from djangosms.core.router import FormatError
        self.assertRaises(FormatError, self._muac, "")

    def test_oedema_no_comma(self):
        self.assertEqual(self._muac("okumu john ,m, 2yr red oe"), {
            'name': 'okumu john',
            'sex': 'M',
            'age': self._timedelta(days=2*365),
            'oedema': True,
            'category': u'R',
            })

    def test_health_id(self):
        self.assertEqual(self._muac("abc1, red"), {
            'health_id': 'abc1',
            'category': u'R',
            })

    def test_all_uppercase(self):
        self.assertEqual(self._muac("JOE, M, 2 Years, RED"), {
            'name': 'JOE',
            'sex': 'M',
            'age': self._timedelta(days=2*365),
            'category': u'R',
            })

    def test_sex_spelled_out(self):
        self.assertEqual(self._muac("JOE, Male, 2 Years, RED"), {
            'name': 'JOE',
            'sex': 'M',
            'age': self._timedelta(days=2*365),
            'category': u'R',
            })

    def test_health_id_first(self):
        self.assertEqual(self._muac("abc1 red"), {
            'health_id': 'abc1',
            'category': u'R',
            })

    def test_health_id_without_reading(self):
        from djangosms.core.router import FormatError
        self.assertRaises(FormatError, self._muac, "abc1")

    def test_health_id_with_measurement(self):
        self.assertEqual(self._muac("abc1, 140"), {
            'health_id': 'abc1',
            'reading': 140,
            })

    def test_health_id_with_implict_cm_measurement(self):
        self.assertEqual(self._muac("abc1, 14"), {
            'health_id': 'abc1',
            'reading': 140,
            })

    def test_health_id_with_measurement_in_mm(self):
        self.assertEqual(self._muac("abc1, 140mm"), {
            'health_id': 'abc1',
            'reading': 140,
            })

    def test_health_id_with_measurement_in_cm(self):
        self.assertEqual(self._muac("abc1, 14cm"), {
            'health_id': 'abc1',
            'reading': 140,
            })

    def test_missing_information(self):
        from djangosms.core.router import FormatError
        self.assertRaises(FormatError, self._muac, "foo")
        self.assertRaises(FormatError, self._muac, "foo, m")
        self.assertRaises(FormatError, self._muac, "foo, m, 16y")

    def test_name_sex_age(self):
        self.assertEqual(self._muac("foo, m, 6 days, red"), {
            'name': 'foo',
            'sex': u'M',
            'age': self._timedelta(6),
            'category': u'R',
            })

    def test_name_sex_age_as_date(self):
        self.assertEqual(self._muac("foo, m, 12/31/1999, red"), {
            'name': 'foo',
            'sex': u'M',
            'age': self._datetime(1999, 12, 31),
            'category': u'R',
            })

    def test_name_sex_wrong_date(self):
        from djangosms.core.router import FormatError
        try:
            self._muac("foo, m, 31/12/1999, red")
        except FormatError, error:
            self.assertTrue('31/12/1999' in error.text, error.text)
        else: # pragma: NOCOVER
            self.fail()

    def test_name_sex_age_with_sex_female(self):
        self.assertEqual(self._muac("foo, f, 6 days, red"), {
            'name': 'foo',
            'sex': u'F',
            'age': self._timedelta(days=6),
            'category': u'R',
            })

    def test_name_sex_age_with_age_unit(self):
        self.assertEqual(self._muac("foo, m, 6 years, red"), {
            'name': 'foo',
            'sex': u'M',
            'age': self._timedelta(days=6*365),
            'category': u'R',
            })

        self.assertEqual(self._muac("foo, m, 6 months, red"), {
            'name': 'foo',
            'sex': u'M',
            'age': self._timedelta(days=6*30),
            'category': u'R',
            })

        self.assertEqual(self._muac("foo, m, 6 weeks, red"), {
            'name': 'foo',
            'sex': u'M',
            'age': self._timedelta(days=6*7),
            'category': u'R',
            })

    def test_health_id_with_oedema(self):
        self.assertEqual(self._muac("abc1, red, oedema"), {
            'health_id': 'abc1',
            'category': 'R',
            'oedema': True,
            })

    def test_health_id_with_something_else(self):
        from djangosms.core.router import FormatError
        self.assertRaises(FormatError, self._muac, "abc1, red, something")

    def test_health_id_with_oe(self):
        self.assertEqual(self._muac("abc1, red, oe"), {
            'health_id': 'abc1',
            'category': 'R',
            'oedema': True,
            })

class FormTest(FormTestCase):
    def register_default_user(self):
        user = super(FormTest, self).register_default_user()
        from djangosms.reporter.models import Reporter
        reporter = Reporter(pk=user.pk)
        reporter.save()
        return reporter

    def _create_patient(self):
        from djangosms.reporter.models import Reporter
        reporter = Reporter.objects.get()
        from cvs.models import Patient
        from datetime import datetime
        patient = self.patient = Patient(
            health_id="bob123",
            name="Bob Smith",
            sex='M',
            birthdate=datetime(1980, 1, 1, 3, 42),
            last_reported_on_by=reporter)
        patient.save()

    @classmethod
    def _muac(cls, **kwargs):
        from ..forms import Muac
        return cls.handle(Muac, **kwargs)

    def test_patient_green_reading(self):
        self.register_default_user()
        self._create_patient()
        request = self._muac(health_id='bob123', category='G')
        self.assertTrue('normal' in request.responses.get().text)

    def test_patient_yellow_reading(self):
        self.register_default_user()
        self._create_patient()
        request = self._muac(health_id='bob123', category='Y')
        self.assertTrue('risk' in request.responses.get().text.lower())
        from ..models import Case
        case = Case.objects.get()
        self.assertEqual(case.patient, self.patient)
        self.assertTrue(case.tracking_id in request.responses.get().text)

    def test_patient_red_reading(self):
        self.register_default_user()
        self._create_patient()
        request = self._muac(health_id='bob123', category='R')
        self.assertTrue('acute' in request.responses.get().text.lower())
        from ..models import Case
        case = Case.objects.get()
        self.assertEqual(case.patient, self.patient)
        self.assertTrue(case.tracking_id in request.responses.get().text)

    def test_patient_reading_categorization(self):
        self.register_default_user()
        self._create_patient()
        for reading, category in ((140, 'G'), (125, 'Y'), (110, 'R')):
            request = self._muac(health_id='bob123', reading=reading)
            from cvs.models import NutritionReport
            report = NutritionReport.objects.all()[0]
            self.assertEqual(report.category, category)
            self.assertEqual(report.source.pk, request.message.pk)

    def test_patient_age_is_datetime(self):
        self.register_default_user()
        from datetime import datetime
        age = datetime(1980, 1, 1, 3, 42)
        self._muac(name="Barbra Smith", age=age, sex='F', reading=140)
        from cvs.models import NutritionReport
        self.assertTrue(NutritionReport.objects.get().patient.birthdate, age)

    def test_patient_age_is_timedelta(self):
        self.register_default_user()
        from datetime import timedelta
        age = timedelta(days=60)
        self._muac(name="Barbra Smith", age=age, sex='F', reading=140)
        from cvs.models import NutritionReport
        self.assertTrue(NutritionReport.objects.get().patient.age, age)

    def test_patient_age_is_timedelta_and_less_than_a_month(self):
        self.register_default_user()
        from datetime import timedelta
        age = timedelta(days=29)
        request = self._muac(name="Barbra Smith", age=age, sex='F', reading=140)
        self.assertTrue('infant' in request.responses.get().text)

    def test_patient_not_found(self):
        from cvs.models import NutritionReport
        self.assertEqual(NutritionReport.objects.count(), 0)
        self.register_default_user()
        self._create_patient()
        request = self._muac(health_id='bob456', reading=140)
        self.assertEqual(NutritionReport.objects.count(), 0)
        self.assertTrue('bob456' in request.responses.get().text)

    def test_patient_is_identified(self):
        self.register_default_user()
        self._create_patient()
        self._muac(
            name="bob smith", age=self.patient.age, sex='M', reading=140)
        from cvs.models import NutritionReport
        self.assertEqual(NutritionReport.objects.count(), 1)
        self.assertEqual(NutritionReport.objects.get().patient, self.patient)

    def test_patient_reading_with_oedema(self):
        self.register_default_user()
        self._create_patient()
        request = self._muac(health_id='bob123', category='G', oedema=True)
        self.assertTrue('oedema' in request.responses.get().text.lower())

