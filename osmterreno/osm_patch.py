"""Leitura do .patch.osm e altura do OSM em cada ponto."""
import xml.etree.ElementTree as ET

from shapely.geometry import Point, Polygon

from .geo import profile_of, segment_distance

BLEND_M = 70.0
SEA_M = 0.0


def load_patch(path):
    root = ET.parse(path).getroot()
    nodes = {
        n.get("id"): (float(n.get("lon")), float(n.get("lat")))
        for n in root.findall("node")
    }
    flats, ramps = [], []
    lons, lats = [], []
    for way in root.findall("way"):
        refs = [nd.get("ref") for nd in way.findall("nd")]
        tags = {t.get("k"): t.get("v") for t in way.findall("tag")}
        if len(refs) < 4 or refs[0] != refs[-1]:
            continue
        ring = [nodes[r] for r in refs]
        lons.extend(p[0] for p in ring)
        lats.extend(p[1] for p in ring)
        polygon = Polygon(ring)
        if not polygon.is_valid or polygon.is_empty:
            polygon = polygon.buffer(0)
        if polygon.is_empty:
            continue
        if "altitude" in tags:
            flats.append((polygon, float(tags["altitude"])))
        elif "altitude_high" in tags and len(refs) == 5:
            steep = float(tags.get("steepness", "2"))
            ramps.append(
                (
                    polygon,
                    ring[0],
                    ring[3],
                    ring[1],
                    ring[2],
                    float(tags["altitude_high"]),
                    float(tags["altitude_low"]),
                    profile_of(tags.get("profile"), steep),
                )
            )
    if not lons:
        raise ValueError("o OSM nao tem poligonos de altitude")
    return flats, ramps, (min(lons), min(lats), max(lons), max(lats))


def layers_of(flats, ramps):
    layers = [(poly, ("flat", alt)) for poly, alt in flats]
    layers += [
        (poly, ("ramp", h0, h1, l0, l1, high, low, profile))
        for poly, h0, h1, l0, l1, high, low, profile in ramps
    ]
    return layers


def spec_height(lon, lat, spec, m_lon):
    if spec[0] == "flat":
        return spec[1]
    _, h0, h1, l0, l1, high, low, profile = spec
    d_high = segment_distance((lon, lat), h0, h1, m_lon)
    d_low = segment_distance((lon, lat), l0, l1, m_lon)
    span = d_high + d_low
    t = 0.0 if span == 0 else d_high / span
    return high - profile(t) * (high - low)


def altitude_at(lon, lat, layers, m_lon):
    """Altitude do OSM no ponto. None quando o ponto fica fora de todo poligono."""
    height_m = None
    point = Point(lon, lat)
    for polygon, spec in layers:
        if not polygon.covers(point):
            continue
        height_m = spec_height(lon, lat, spec, m_lon)
    return height_m


def height_on_mesh(lon, lat, layers, m_lon, dem_z, proteger_agua=True, blend_m=BLEND_M):
    """Dentro do polígono usa o OSM. Na faixa escolhida desce liso até o terreno.

    Dentro do polígono a altitude do OSM vale mesmo abaixo do mar.
    Fora dele, o mar fica com a malha original.
    """
    inside = altitude_at(lon, lat, layers, m_lon)
    if inside is not None:
        return inside
    if proteger_agua and dem_z <= SEA_M:
        return None
    point = Point(lon, lat)
    nearest = None
    nearest_m = None
    for polygon, spec in layers:
        dist_m = polygon.distance(point) * 111320.0
        if nearest_m is None or dist_m < nearest_m:
            nearest_m = dist_m
            nearest = (polygon, spec)
    if nearest is None or nearest_m is None or blend_m <= 0 or nearest_m >= blend_m:
        return dem_z
    border = nearest[0].exterior.interpolate(nearest[0].exterior.project(point))
    edge_z = spec_height(border.x, border.y, nearest[1], m_lon)
    t = nearest_m / blend_m
    t = t * t * (3.0 - 2.0 * t)
    return edge_z * (1.0 - t) + dem_z * t
