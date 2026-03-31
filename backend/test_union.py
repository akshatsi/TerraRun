import sys
from shapely.geometry import LineString, Polygon, MultiPolygon, mapping, shape
from shapely.ops import unary_union

coords = [(40.7128, -74.0060), (40.7130, -74.0050)]
line = LineString(coords)
poly = line.buffer(0.00015)
geo = mapping(poly)
s = shape(geo)
shapes = [s]
print(type(shapes[0]))
print(shapes[0])
try:
    merged = unary_union(shapes)
    print("Success:", merged.geom_type)
except Exception as e:
    import traceback
    traceback.print_exc()
