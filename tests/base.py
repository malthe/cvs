from djangosms.core.testing import FormTestCase

class Scenario(FormTestCase):
    def setUp(self):
        super(Scenario, self).setUp()

        from djangosms.reporter.models import Reporter
        reporter = Reporter.from_uri("test://ann", name="Ann")

        from datetime import datetime
        from ..models import Patient
        from ..models import Report
        from ..models import Case

        from djangosms.stats.models import ReportKind
        ReportKind(slug="test", name="Test report").save()

        from djangosms.core.models import Request
        from djangosms.core.models import Incoming

        message = Incoming.from_uri("test://ann")
        request = Request(message=message)
        request.save()

        report = Report(slug="test", source=message)
        report.save()

        patient = Patient(
            health_id="bob123",
            name="Bob",
            sex="M",
            birthdate=datetime(1980, 1, 1, 3, 42),
            last_reported_on_by=reporter,
            )
        patient.save()

        case = Case(
            patient=patient,
            report=report,
            tracking_id="TRACK123",
            )

        case.save()

