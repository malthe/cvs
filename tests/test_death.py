from django.test import TestCase
from .base import Scenario

class ParserTest(TestCase):
    @staticmethod
    def _death(text):
        from ..forms import Death
        return Death().parse(text=text)

    def test_missing(self):
        from djangosms.core.router import FormatError
        self.assertRaises(FormatError, self._death, "")
        self.assertRaises(FormatError, self._death, "apio")
        self.assertRaises(FormatError, self._death, "apio, f")
        self.assertRaises(FormatError, self._death, "apio, f, other")

    def test_id(self):
        self.assertEqual(self._death("abc123"), {'ids': ['ABC123']})

    def test_ids(self):
        self.assertEqual(self._death("123 12ab65"), {
            'ids': ['123', '12AB65']})

    def test_name_sex_age(self):
        from datetime import timedelta
        self.assertEqual(self._death("bob, m, 6y"), {
            'name': 'bob',
            'sex': 'M',
            'age': timedelta(6*365),})

class FormTest(Scenario):
    @classmethod
    def _death(cls, **kwargs):
        from ..forms import Death
        kwargs.setdefault("uri", "test://ann")
        return cls.handle(Death, **kwargs)

    def test_health_id(self):
        self.register_default_user()
        request = self._death(ids=['bob123'])
        from ..models import Case
        self.assertNotEqual(Case.objects.get().closed, None)
        from ..models import Patient
        self.assertNotEqual(Patient.objects.get().deathdate, None)
        self.assertTrue('Bob' in request.responses.all()[0].text)

    def test_case_id(self):
        self.register_default_user()
        request = self._death(ids=['TRACK123'])
        from ..models import Case
        self.assertNotEqual(Case.objects.get().closed, None)
        from ..models import Patient
        self.assertNotEqual(Patient.objects.get().deathdate, None)
        self.assertTrue('Bob' in request.responses.all()[0].text)

    def test_case_id_other(self):
        self.register_default_user()
        request = self._death(uri=self.default_uri, ids=['TRACK123'])
        self.assertEqual(request.responses.count(), 2)

    def test_case_id_not_exist(self):
        self.register_default_user()
        request = self._death(ids=['TRACK456'])
        self.assertTrue('TRACK456' in request.responses.get().text)

    def test_name_sex_age_unknown_patient(self):
        self.register_default_user()
        from datetime import timedelta
        request = self._death(name="Jim", sex="M", age=timedelta(days=60))
        self.assertTrue('Jim' in request.responses.all()[0].text)

    def test_name_sex_age_known_patient(self):
        self.register_default_user()
        from datetime import datetime
        request = self._death(name="Bob", sex="M", age=datetime(1980, 1, 1, 3, 42))
        from ..models import Case
        self.assertNotEqual(Case.objects.get().closed, None)
        from ..models import Patient
        self.assertNotEqual(Patient.objects.get().deathdate, None)
        self.assertTrue('Bob' in request.responses.all()[0].text)
