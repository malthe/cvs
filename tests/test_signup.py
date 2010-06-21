from django.test import TestCase
from djangosms.core.testing import FormTestCase

class SignupTestCase(TestCase):
    def bootstrap(self):
        from cvs.models import HealthRole
        self.role = HealthRole(slug="test", keyword="TEST", name="Test")
        self.role.save()

        from djangosms.stats.models import Group
        from djangosms.stats.models import GroupKind
        kind = GroupKind(slug="test")
        kind.save()

        from cvs.models import Facility
        facility = Facility.add_root(kind=kind, code='1234')

        from cvs.models import ReportingPolicy
        root = Group.add_root(kind=kind, name="root")
        root = root.get()

        location = root.add_child(
            kind=kind, name='test')
        location = location.get()
        ReportingPolicy(group=location, report_to=facility).save()

        # various child locations for testing
        self.group1 = location.add_child(kind=kind, name='child1')
        ReportingPolicy(group=self.group1).save()
        self.group2 = location.add_child(kind=kind, name='child2')
        ReportingPolicy(group=self.group2).save()
        self.group3 = location.add_child(kind=kind, name='other')
        ReportingPolicy(group=self.group3).save()

        location = location.get()

        self.group = location
        self.facility = facility

class ParserTest(SignupTestCase):
    @staticmethod
    def _signup(text, keyword="test"):
        from ..forms import Signup
        return Signup().parse(keyword=keyword, text=text)

    def test_code(self):
        self.bootstrap()
        self.assertEquals(
            self._signup("1234"),
            {'role': self.role, 'facility': self.facility})
        self.assertEquals(
            self._signup("1234", keyword="t est"),
            {'role': self.role, 'facility': self.facility})

    def test_no_code(self):
        self.bootstrap()
        from djangosms.core.router import FormatError
        self.assertRaises(FormatError, self._signup, "")

    def test_wrong_code(self):
        self.bootstrap()
        from djangosms.core.router import FormatError
        self.assertRaises(FormatError, self._signup, "5678")

    def test_code_and_reporting_location(self):
        self.bootstrap()
        self.assertEquals(
            self._signup("1234, test"),
            {'role': self.role,
             'facility': self.facility,
             'group': self.group,
             })

    def test_code_and_reporting_location_fuzzy_matching(self):
        self.bootstrap()
        self.assertEquals(
            self._signup("1234, test1"),
            {'role': self.role,
             'facility': self.facility,
             'group': self.group,
             })

    def test_code_and_child_location(self):
        self.bootstrap()
        self.assertEquals(
            self._signup("1234, other"),
            {'role': self.role,
             'facility': self.facility,
             'group': self.group3,
             })

    def test_code_and_unknown_location(self):
        self.bootstrap()
        data = self._signup("1234, different")

        from djangosms.stats.models import Group
        group = Group.objects.get(kind__slug="added_by_user")

        self.assertEquals(
            data,
            {'role': self.role,
             'facility': self.facility,
             'group': group,
             })

class FormTest(SignupTestCase, FormTestCase):
    @staticmethod
    def _register(uri="test://ann", name="Ann"):
        from djangosms.reporter.models import Reporter
        return Reporter.from_uri(uri, name=name)

    @classmethod
    def _signup(cls, **kwargs):
        kwargs.setdefault("uri", "test://ann")
        from ..forms import Signup
        return cls.handle(Signup, **kwargs)

    def test_signup(self):
        self.bootstrap()
        self._register()
        request = self._signup(role=self.role, facility=self.facility, group=self.group)

        from djangosms.reporter.models import Reporter
        reporter = Reporter.objects.get()

        self.assertEqual(reporter.pk, request.message.connection.user.pk)

        from cvs.models import HealthReporter
        reporter = HealthReporter.objects.get()

        self.assertEqual(reporter.group, self.group)
        self.assertEqual(reporter.facility, self.facility)

