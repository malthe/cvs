from django.test import TestCase
from djangosms.core.testing import FormTestCase

class HealthTestCase(TestCase):
    def setUp(self):
        super(HealthTestCase, self).setUp()

        from djangosms.stats.models import ReportKind
        from djangosms.stats.models import ObservationKind

        kind, created = ReportKind.objects.get_or_create(
            slug="agg", name="Test aggregate observations")
        ObservationKind.objects.get_or_create(
            slug="agg_ma", group=kind, abbr='ma', name="malaria")
        ObservationKind.objects.get_or_create(
            slug="agg_bd", group=kind, abbr='bd', name="bloody diarrhea")
        ObservationKind.objects.get_or_create(
            slug="agg_tb", group=kind, abbr='tb', name="tuberculosis")
        ObservationKind.objects.get_or_create(
            slug="agg_total", group=kind, name="Total")

class ParserTest(HealthTestCase):
    @staticmethod
    def _parse(text):
        from ..forms import Observations
        return Observations().parse(
            text=text, keyword="agg", keywords={'agg': 'agg'})

    def test_missing_value(self):
        from djangosms.core.router import FormatError
        self.assertRaises(FormatError, self._parse, "")
        self.assertRaises(FormatError, self._parse, "ma")

    def test_duplicate(self):
        from djangosms.core.router import FormatError
        self.assertRaises(FormatError, self._parse, "ma 5 ma 10")

    def test_value(self):
        data = self._parse("MA 5")
        self.assertEqual(data['observations'], {'agg_ma': 5.0})

    def test_values_together(self):
        data = self._parse("MA5 BD1")
        self.assertEqual(data['observations'], {'agg_ma': 5.0, 'agg_bd': 1.0})

    def test_value_lowercase(self):
        data = self._parse("ma 5")
        self.assertEqual(data['observations'], {'agg_ma': 5.0})

    def test_value_with_total(self):
        data = self._parse("10, ma 5")
        self.assertEqual(data['observations'], {'agg_ma': 5.0})
        self.assertEqual(data['total'], 10)

    def test_negative_value(self):
        from djangosms.core.router import FormatError
        self.assertRaises(FormatError, self._parse, "MA -5")

    def test_values(self):
        data = self._parse("MA 5 TB 10")
        self.assertEqual(data['observations'], {'agg_ma': 5.0, 'agg_tb': 10.0})

    def test_values_with_comma(self):
        data = self._parse("MA 5, TB 10")
        self.assertEqual(data['observations'], {'agg_ma': 5.0, 'agg_tb': 10.0})

    def test_bad_indicator(self):
        from djangosms.core.router import FormatError
        self.assertRaises(FormatError, self._parse, "xx 5.0")

    def test_bad_value(self):
        from djangosms.core.router import FormatError
        self.assertRaises(FormatError, self._parse, "ma five")

class FormTest(HealthTestCase, FormTestCase):
    @classmethod
    def _observations(cls, **kwargs):
        from ..forms import Observations
        from djangosms.stats.models import ReportKind
        kind = ReportKind.objects.get(slug="agg")
        return cls.handle(Observations, kind=kind, **kwargs)

    def test_no_reports(self):
        self.register_default_user()
        from djangosms.stats.models import Report
        request = self._observations(observations={})
        self.assertEqual(Report.objects.count(), 0)
        self.assertEqual(request.responses.count(), 1)

    def test_single_report(self):
        self.register_default_user()
        request = self._observations(observations={'agg_ma': 5})
        from djangosms.stats.models import Report
        report = Report.objects.get(kind__slug="agg")
        self.assertEqual(report.observations.count(), 1)
        self.assertEqual(report.source.user, request.message.user)
        reply = request.responses.get()
        self.assertTrue('malaria 5' in reply.text)

    def test_with_total(self):
        self.register_default_user()
        request = self._observations(total=10, observations={'agg_ma': 5})
        from djangosms.stats.models import Report
        report = Report.objects.get(kind__slug="agg")
        self.assertEqual(report.observations.count(), 2)
        self.assertEqual(report.source.user, request.message.user)
        self.assertEqual(report.observations.get(
            kind__slug__endswith="_total").value, 10)
        reply = request.responses.get()
        self.assertTrue('malaria 5' in reply.text)

    def test_follow_up_reports(self):
        self.register_default_user()
        self._observations(observations={'agg_ma': 5})
        update1 = self._observations(observations={'agg_ma': 10})
        update2 = self._observations(observations={'agg_ma': 8})
        self.assertTrue('malaria 10 (+100%)' in update1.responses.get().text)
        self.assertTrue('malaria 8 (-20%)' in update2.responses.get().text)

    def test_follow_up_zero(self):
        self.register_default_user()
        self._observations(observations={'agg_ma': 5})
        update1 = self._observations(observations={'agg_ma': 0})
        update2 = self._observations(observations={'agg_ma': 10})
        self.assertTrue(
            'malaria 0 (-5)' in update1.responses.get().text, update1.responses.get().text)
        self.assertTrue(
            'malaria 10 (+10)' in update2.responses.get().text, update2.responses.get().text)

    def test_multiple_reports(self):
        self.register_default_user()
        request = self._observations(
            observations={'agg_ma': 5, 'agg_tb': 10, 'agg_bd': 2})
        from djangosms.stats.models import Report
        report = Report.objects.get(kind__slug="agg")
        self.assertEqual(report.observations.count(), 3)
        reply = request.responses.get()
        self.assertTrue(
            'bloody diarrhea 2, malaria 5 and tuberculosis 10' in reply.text,
            reply.text)
