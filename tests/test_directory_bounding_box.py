import math

from app.directory.matching import EARTH_RADIUS_KM, bounding_box
from app.directory.models import GeoPoint


def _destination(start: GeoPoint, bearing_degrees: float, km: float) -> GeoPoint:
    d = km / EARTH_RADIUS_KM
    lat1, lng1, bearing = math.radians(start.lat), math.radians(start.lng), math.radians(bearing_degrees)
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(bearing))
    lng2 = lng1 + math.atan2(
        math.sin(bearing) * math.sin(d) * math.cos(lat1), math.cos(d) - math.sin(lat1) * math.sin(lat2)
    )
    return GeoPoint(math.degrees(lat2), math.degrees(lng2))


def test_every_point_on_the_radius_lies_inside_the_box():
    for centre in (GeoPoint(17.43, 78.41), GeoPoint(-33.86, 151.21), GeoPoint(64.0, -21.9)):
        for radius in (1, 10, 50):
            min_lat, max_lat, min_lng, max_lng = bounding_box(centre, radius)
            for bearing in range(0, 360, 5):
                edge = _destination(centre, bearing, radius)
                assert min_lat <= edge.lat <= max_lat
                assert min_lng <= edge.lng <= max_lng


def test_a_box_near_a_pole_has_no_longitude_bounds():
    _, max_lat, min_lng, max_lng = bounding_box(GeoPoint(89.9, 10.0), 50)

    assert max_lat > 90
    assert min_lng is None and max_lng is None


def test_a_box_across_the_antimeridian_has_no_longitude_bounds():
    _, _, min_lng, max_lng = bounding_box(GeoPoint(-17.0, 179.95), 50)

    assert min_lng is None and max_lng is None
