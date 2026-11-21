"""Geometria: distâncias em metros, coordenadas baricêntricas e chaves de vértice."""
from math import hypot, tanh

M_LAT = 110540.0


def dist_m(a, b, m_lon):
    return hypot((a[0] - b[0]) * m_lon, (a[1] - b[1]) * M_LAT)


def segment_distance(point, a, b, m_lon):
    vx, vy = (b[0] - a[0]) * m_lon, (b[1] - a[1]) * M_LAT
    den = vx * vx + vy * vy
    if den == 0:
        return dist_m(point, a, m_lon)
    px, py = (point[0] - a[0]) * m_lon, (point[1] - a[1]) * M_LAT
    t = max(0.0, min(1.0, (px * vx + py * vy) / den))
    return dist_m(point, (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])), m_lon)


def profile_of(name, steepness):
    if name and "tanh" in name:
        def tanh_profile(x):
            return (tanh((x - 0.5) * steepness) / tanh(0.5 * steepness) + 1) / 2
        return tanh_profile
    if name == "spline":
        return lambda x: 3 * x * x - 2 * x * x * x
    return lambda x: x


def barycentric(point, a, b, c):
    den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(den) < 1e-18:
        return (1.0, 0.0, 0.0)
    w0 = ((b[1] - c[1]) * (point[0] - c[0]) + (c[0] - b[0]) * (point[1] - c[1])) / den
    w1 = ((c[1] - a[1]) * (point[0] - c[0]) + (a[0] - c[0]) * (point[1] - c[1])) / den
    w2 = 1.0 - w0 - w1
    return (w0, w1, w2)


def surface_parts(geom):
    if geom.is_empty:
        return
    kind = geom.geom_type
    if kind == "Polygon":
        if geom.area > 1e-14:
            yield geom
    elif kind in ("MultiPolygon", "GeometryCollection"):
        for part in geom.geoms:
            yield from surface_parts(part)


def signed_area(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def interpolate_vertex(point, verts):
    weights = barycentric(point, verts[0], verts[1], verts[2])
    extras = []
    width = len(verts[0]) - 2
    for index in range(width):
        extras.append(sum(weights[n] * verts[n][2 + index] for n in range(3)))
    return (point[0], point[1], *extras)


def format_vertex(vertex, z_value):
    lon, lat = vertex[0], vertex[1]
    tail = " ".join("%.9f" % value for value in vertex[3:])
    return "PATCH_VERTEX %.9f %.9f %.3f %s\n" % (lon, lat, z_value, tail)


def vertex_key(vertex):
    return (round(vertex[0], 8), round(vertex[1], 8))


def edge_key(a, b):
    ka = vertex_key(a)
    kb = vertex_key(b)
    return (ka, kb) if ka <= kb else (kb, ka)
