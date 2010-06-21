import csv
import sys
import pyproj
import traceback
import collections

from django.core.management.base import BaseCommand
from django.template.defaultfilters import slugify as _slugify

from djangosms.stats.models import Group
from djangosms.stats.models import GroupKind

from cvs.models import Facility
from cvs.models import ReportingPolicy

wgs84 = pyproj.Proj(proj='latlong', datum='WGS84')
utm33 = pyproj.Proj(proj='utm', zone='33')

Entry = collections.namedtuple("Entry", "code, name, level, itp_otc_status, distribution_day, iycf, x, y, reports_to, district, county, sub_county, parish, village, sub_village, household, house_holds, population, needed_vhts, trained_vhts, vhts_to_be_trained")

def slugify(string):
    return _slugify(string).replace('-', '')

class Command(BaseCommand):
    args = 'path'
    help = 'Imports the specified .cvs file'

    def handle(self, path, **options):
        groups = Group.objects.count()
        facilities = Facility.objects.count()
        print >> sys.stderr, "%d existing groups." % groups
        print >> sys.stderr, "%d existing facilities." % facilities

        reader = csv.reader(open(path), delimiter=',', quotechar='"')

        _k_country = GroupKind.objects.get(name='Country')
        _k_district = GroupKind.objects.get(slug="district")
        _k_county = GroupKind.objects.get(slug="county")
        _k_sub_county = GroupKind.objects.get(slug="sub_county")
        _k_parish = GroupKind.objects.get(slug="parish")
        _k_village = GroupKind.objects.get(slug="village")
        _k_sub_village = GroupKind.objects.get(slug="sub_village")

        try:
            root = Group.objects.get(name="Uganda", kind=_k_country)
        except Group.DoesNotExist:
            root = Group.add_root(name="Uganda", kind=_k_country)

        reader.next()

        # read all entries
        entries = []
        for line in reader:
            line.extend(
                [""]*(21-len(line)))

            try:
                entry = Entry(*line)
            except Exception, exc:
                print >> sys.stderr, traceback.format_exc(exc)
            else:
                entries.append(entry)

        # read all facilities
        facility_entries = {}
        for entry in entries:
            if entry.name and entry.level:
                name = slugify(entry.name)
                level = slugify(entry.level)
                facility_entries[name, level] = entry

        created = {}
        def get_or_create(entry):
            try:
                return Facility.objects.get(code=entry.code)
            except Facility.DoesNotExist:
                pass

            parent = None

            if entry.reports_to:
                name, level = entry.reports_to.rsplit(' ', 1)

                parent = created.get((name, level))
                if parent is None:
                    try:
                        parent_entry = facility_entries[slugify(name), slugify(level)]
                    except KeyError:
                        raise KeyError("Facility not found: '%s %s'." % (name, level))

                    try:
                        parent = created[name, level] = get_or_create(parent_entry)
                    except RuntimeError:
                        raise RuntimeError(
                            "Recursive definition: %s %s => %s %s." % (
                                entry.code, entry.name,
                                parent_entry.code, parent_entry.name))

                create = Facility.objects.get(pk=parent.pk).add_child
            else:
                create = Facility.add_root

            if entry.x and entry.y:
                transformed = pyproj.transform(
                    utm33, wgs84, float(entry.x), float(entry.y))
                longitude, latitude = map(str, transformed)
            else:
                longitude, latitude = None, None

            level = entry.level.replace(' ', '')
            slug = level.lower()
            try:
                kind = GroupKind.objects.get(slug=slug)
            except GroupKind.DoesNotExist:
                raise GroupKind.DoesNotExist(slug)

            facility = create(
                name=entry.name,
                code=entry.code,
                kind=kind,
                longitude=longitude,
                latitude=latitude,
                )

            facility = Facility.objects.get(pk=facility.pk)
            return facility

        facility = None
        for entry in entries:
            # update locations
            locations = ((entry.district, _k_district),
                         (entry.county, _k_county),
                         (entry.sub_county, _k_sub_county),
                         (entry.parish, _k_parish),
                         (entry.village, _k_village),
                         (entry.sub_village, _k_sub_village))

            if entry.code:
                try:
                    facility = get_or_create(entry)
                except RuntimeError, error:
                    print >> sys.stderr, "Warning: %s" % error
                    continue
            elif facility is None:
                continue

            parent = root
            for placename, kind in locations:
                if not placename.strip():
                    break

                kwargs = dict(name=placename, kind=kind)
                try:
                    inst = Group.objects.get(**kwargs)
                except Group.DoesNotExist:
                    inst = parent.add_child(**kwargs)
                    ReportingPolicy(group=inst, report_to=facility).save()

                parent = Group.objects.get(pk=inst.pk)

        print >> sys.stderr, "%d groups (locations) added." % (
            Group.objects.count() - groups)
        print >> sys.stderr, "%d facilities added." % (
            Facility.objects.count() - facilities)
