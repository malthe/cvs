from django.test import TestCase
from .base import Scenario

class ParserTest(TestCase):
    @staticmethod
    def _cure(text):
        from ..forms import Cure
        return Cure().parse(text=text)

    def test_empty(self):
        from djangosms.core.router import FormatError
        self.assertRaises(FormatError, self._cure, "")

    def test_single(self):
        self.assertEqual(self._cure("abc123")['ids'],
                         ['ABC123'])

    def test_multiple(self):
        self.assertEqual(self._cure("abc123 def456")['ids'],
                         ['ABC123', 'DEF456'])

class RequestTest(Scenario):
    @classmethod
    def _cure(cls, **kwargs):
        from ..forms import Cure
        return cls.handle(Cure, **kwargs)

    def test_not_exist(self):
        self.register_default_user()
        request = self._cure(ids=["TRACK456"])
        self.assertTrue('TRACK456' in request.responses.get().text, request.responses.get().text)

    def test_not_found(self):
        self.register_default_user()
        request = self._cure(ids=["TRACK456"])
        from ..models import Case
        self.assertEqual(Case.objects.get().closed, None)
        self.assertTrue('TRACK456' in request.responses.get().text)

    def test_single_is_closed(self):
        self.register_default_user()
        self._cure(ids=["TRACK123"])
        from ..models import Case
        self.assertNotEqual(Case.objects.get().closed, None)

    def test_single_yields_two_responses(self):
        self.register_default_user()
        request = self._cure(ids=["TRACK123"])
        self.assertEqual(request.responses.count(), 2)

    def test_name_sex_age_unknown_patient(self):
        self.register_default_user()
        from datetime import timedelta
        request = self._cure(name="Jim", sex="M", age=timedelta(days=60))
        self.assertTrue('Jim' in request.responses.all()[0].text)

    def test_name_sex_age_known_patient(self):
        self.register_default_user()
        from datetime import datetime
        request = self._cure(uri="test://ann", name="Bob", sex="M", age=datetime(1980, 1, 1, 3, 42))
        from ..models import Case
        self.assertNotEqual(Case.objects.get().closed, None)
        self.assertTrue('Bob' in request.responses.all()[0].text)
