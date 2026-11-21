"""Otimização da malha cortada: junta pedaços planos, melhora ângulos e encaixa contornos."""
from collections import defaultdict
import threading
from math import cos, hypot, radians

import triangle
from shapely import constrained_delaunay_triangles
from shapely.errors import GEOSException
from shapely.geometry import LineString, MultiPoint, Point, Polygon
from shapely.ops import polygonize, snap, unary_union
from shapely.prepared import prep
from shapely.strtree import STRtree

from .dsf_io import read_batches
from .geo import edge_key, interpolate_vertex, signed_area, surface_parts, vertex_key

MIN_ANGLE = 25
SNAP_M = 1.5
_triangle_trava = threading.Lock()


def flat_level(tri):
    """Altura comum dos três vértices, em milímetros. None quando o triângulo inclina."""
    z = tri[0][2]
    if abs(tri[1][2] - z) > 1e-3 or abs(tri[2][2] - z) > 1e-3:
        return None
    return int(round(z * 1000.0))


def merge_flat(tris):
    """Junta os pedaços que estão na mesma altura. A borda de cada grupo fica igual."""
    groups = defaultdict(list)
    out = []
    for tri in tris:
        level = flat_level(tri)
        if level is None:
            out.append(tri)
        else:
            groups[level].append(tri)
    for group in groups.values():
        if len(group) < 3:
            out.extend(group)
            continue
        out.extend(merge_group(group))
    return out


def cdt_parts(shape):
    """Delaunay restrito do GEOS. None quando o GEOS falha (ex.: "Unable to find a convex corner")."""
    try:
        return list(surface_parts(constrained_delaunay_triangles(shape)))
    except GEOSException:
        return None


def quality_parts(face):
    """Triangle (Shewchuk) sem ponto novo na borda e sem limite de tamanho. Só cria ponto no meio para evitar ângulo fechado."""
    if face.is_empty or not face.is_valid or face.area <= 1e-16:
        return None
    ox, oy = face.bounds[0], face.bounds[1]
    m_lon = 111320.0 * cos(radians(oy))
    vertices = []
    segments = []
    holes = []
    for index, ring in enumerate([face.exterior, *face.interiors]):
        coords = list(ring.coords)[:-1]
        clean = []
        for x, y in coords:
            if not clean or (x, y) != clean[-1]:
                clean.append((x, y))
        if len(clean) > 1 and clean[0] == clean[-1]:
            clean.pop()
        if len(clean) < 3:
            return None
        start = len(vertices)
        for x, y in clean:
            vertices.append(((x - ox) * m_lon, (y - oy) * 111320.0))
        for n in range(len(clean)):
            segments.append((start + n, start + (n + 1) % len(clean)))
        if index > 0:
            inside = Polygon(ring).representative_point()
            holes.append(((inside.x - ox) * m_lon, (inside.y - oy) * 111320.0))
    for i, (x, y) in enumerate(vertices):
        for j in range(i):
            if hypot(x - vertices[j][0], y - vertices[j][1]) < 1e-3:
                return None
    for a, b in segments:
        if hypot(vertices[a][0] - vertices[b][0], vertices[a][1] - vertices[b][1]) < 1e-3:
            return None
    data = {"vertices": vertices, "segments": segments}
    if holes:
        data["holes"] = holes
    try:
        with _triangle_trava:
            result = triangle.triangulate(data, "pq%dYQ" % MIN_ANGLE)
    except Exception:
        return None
    if "triangles" not in result:
        return None
    pts = [(ox + x / m_lon, oy + y / 111320.0) for x, y in result["vertices"]]
    lookup = {
        (round(x, 8), round(y, 8)): (x, y)
        for ring in [face.exterior, *face.interiors]
        for x, y in ring.coords
    }
    pts = [lookup.get((round(x, 8), round(y, 8)), (x, y)) for x, y in pts]
    return [Polygon([pts[a], pts[b], pts[c]]) for a, b, c in result["triangles"]]


def triangulate_face(face):
    """Triângulos da face, ou None quando nem o Triangle nem o GEOS conseguem."""
    pieces = quality_parts(face)
    if pieces:
        total = sum(piece.area for piece in pieces)
        if abs(total - face.area) <= face.area * 1e-6:
            return pieces
    return cdt_parts(face)


def merge_group(group):
    points = {}
    counts = defaultdict(int)
    for tri in group:
        for vertex in tri:
            points[vertex_key(vertex)] = vertex
        for n in range(3):
            counts[edge_key(tri[n], tri[(n + 1) % 3])] += 1
    border = [LineString([a, b]) for (a, b), used in counts.items() if used == 1]
    if not border:
        return group
    shapes = [Polygon([(v[0], v[1]) for v in tri]) for tri in group]
    area = unary_union(shapes)
    inside = prep(area.buffer(1e-10))
    tree = STRtree(shapes)
    sign = signed_area(group[0][0], group[0][1], group[0][2])
    level = group[0][0][2]

    def locate(x, y):
        for index in tree.query(Point(x, y), predicate="intersects"):
            base = group[int(index)]
            made_vertex = interpolate_vertex((x, y), base)
            return (made_vertex[0], made_vertex[1], level, *made_vertex[3:])
        return None

    made = []
    for face in polygonize(unary_union(border)):
        if face.area <= 0 or not inside.covers(face.representative_point()):
            continue
        smalls = triangulate_face(face)
        if smalls is None:
            return group
        for small in smalls:
            ring = list(small.exterior.coords)[:3]
            keys = [(round(x, 8), round(y, 8)) for x, y in ring]
            for key, (x, y) in zip(keys, ring):
                if key not in points:
                    found = locate(x, y)
                    if found is None:
                        return group
                    points[key] = found
            tri = [points[key] for key in keys]
            if sign * signed_area(tri[0], tri[1], tri[2]) < 0:
                tri = [tri[0], tri[2], tri[1]]
            made.append(tuple(tri))
    if not made:
        return group
    total = sum(abs(signed_area(t[0], t[1], t[2])) for t in made)
    if abs(total - area.area * 2.0) > area.area * 2e-4:
        return group
    return made


def mesh_points_near(src, bounds, pad):
    """Vértices da malha original dentro da caixa, sem repetir."""
    minx, miny, maxx, maxy = bounds
    seen = set()
    for _line, batch in read_batches(src):
        if batch is None:
            continue
        for vertex in batch:
            if minx - pad <= vertex[0] <= maxx + pad and miny - pad <= vertex[1] <= maxy + pad:
                seen.add((vertex[0], vertex[1]))
    return list(seen)


def snap_to_mesh(shape, tree, points, tol):
    """Encaixa o contorno nos vértices da malha a até tol. Devolve o original se o encaixe estragar a forma."""
    near = tree.query(shape.boundary.buffer(tol))
    if len(near) == 0:
        return shape
    ref = MultiPoint([points[int(index)] for index in near])
    moved = snap(shape, ref, tol)
    if not moved.is_valid:
        moved = moved.buffer(0)
    if moved.is_empty or abs(moved.area - shape.area) > shape.area * 0.01:
        return shape
    return moved


def snap_layers(src, layers, blend_m, log):
    """Contornos dos polígonos e da faixa encaixados nos vértices da malha a até SNAP_M."""
    tol = SNAP_M / 111320.0
    union = unary_union([polygon for polygon, _spec in layers])
    bounds = union.buffer(blend_m / 111320.0).bounds
    points = mesh_points_near(src, bounds, 0.002)
    if not points:
        return layers, union.buffer(blend_m / 111320.0)
    tree = STRtree([Point(p) for p in points])
    snapped = [(snap_to_mesh(polygon, tree, points, tol), spec) for polygon, spec in layers]
    region = unary_union([polygon for polygon, _spec in snapped]).buffer(blend_m / 111320.0)
    region = snap_to_mesh(region, tree, points, tol)
    log("contornos encaixados na malha (ate %.1f m)" % SNAP_M)
    return snapped, region
