from django.test import TestCase
from djangosms.core.testing import FormTestCase

class ParserTest(TestCase):
    @staticmethod
    def _birth(text):
        from ..forms import Birth
        return Birth().parse(text=text)

    def test_missing(self):
        from djangosms.core.router import FormatError
        self.assertRaises(FormatError, self._birth, "")
        self.assertRaises(FormatError, self._birth, "apio")
        self.assertRaises(FormatError, self._birth, "apio, f")

    def test_bad_location(self):
        from djangosms.core.router import FormatError
        self.assertRaises(FormatError, self._birth, "api, f, bed")

    def test_birth(self):
        self.assertEqual(self._birth("Apio, female clinic"),
                         {'name': 'Apio', 'sex': 'F', 'place': 'CLINIC'})

class FormTest(FormTestCase):
    @classmethod
    def _birth(cls, **kwargs):
        from ..forms import Birth
        return cls.handle(Birth, **kwargs)

    def test_birth(self):
        self.register_default_user()
        self._birth(name="Apio", sex="F", place="CLINIC")
        from ..models import BirthReport
        self.assertEqual(BirthReport.objects.count(), 1)
