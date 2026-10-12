from shapely.geometry import box
from shapely.ops import unary_union

from app.seed import data, sample_geo


def test_kmc_has_144_non_overlapping_wards_tiling_the_municipality():
    wards = sample_geo.kmc_ward_polygons()
    assert len(wards) == sample_geo.KMC_WARD_COUNT
    kmc = box(*sample_geo.KMC_BBOX)
    assert unary_union(wards).symmetric_difference(kmc).area < 1e-12
    total = sum(w.area for w in wards)
    assert abs(total - kmc.area) < 1e-12  # no overlaps


def test_hierarchy_nesting():
    assert box(*sample_geo.KOLKATA_DISTRICT_BBOX).contains(box(*sample_geo.KMC_BBOX))
    assert box(*sample_geo.HOWRAH_DISTRICT_BBOX).contains(box(*sample_geo.HMC_BBOX))
    for bbox in (
        sample_geo.KOLKATA_DISTRICT_BBOX,
        sample_geo.HOWRAH_DISTRICT_BBOX,
        sample_geo.NORTH_24_PGS_BBOX,
        sample_geo.SOUTH_24_PGS_BBOX,
    ):
        assert box(*sample_geo.WEST_BENGAL_BBOX).contains(box(*bbox))


def test_sample_districts_do_not_overlap():
    boxes = [
        box(*b)
        for b in (
            sample_geo.KOLKATA_DISTRICT_BBOX,
            sample_geo.HOWRAH_DISTRICT_BBOX,
            sample_geo.NORTH_24_PGS_BBOX,
            sample_geo.SOUTH_24_PGS_BBOX,
        )
    ]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            assert a.intersection(b).area == 0


def test_west_bengal_has_23_districts_and_categories_have_full_sla():
    assert len(data.WEST_BENGAL_DISTRICTS) == 23
    for category in data.CATEGORIES:
        assert set(category["sla"]) == {"1", "2", "3", "4", "5"}
        # Higher severity must never get a longer deadline.
        hours = [category["sla"][str(s)] for s in range(1, 6)]
        assert hours == sorted(hours, reverse=True)
