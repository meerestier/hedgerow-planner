import math
from qgis.core import (QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, 
                       QgsPointXY, QgsFields, QgsField, QgsWkbTypes, QgsMarkerSymbol, QgsCoordinateReferenceSystem)
from qgis.PyQt.QtCore import QVariant
from qgis.utils import iface

def calculate_angle(point1, point2):
    """Calculate angle in degrees between two points."""
    dx = point2.x() - point1.x()
    dy = point2.y() - point1.y()
    return math.degrees(math.atan2(dy, dx))

def generate_points(rows, row_spacing, plant_spacing):
    """Generate points based on hardcoded parameters."""
    line_layer = iface.activeLayer()

    if not isinstance(line_layer, QgsVectorLayer) or line_layer.geometryType() != QgsWkbTypes.LineGeometry:
        iface.messageBar().pushMessage("Error", "Please select a line layer.", level=3)
        return

    # Get CRS from the active layer
    crs = line_layer.crs().toWkt()

    point_layer = QgsVectorLayer(f'Point?crs={crs}', 'Hedgerow Points', 'memory')
    point_provider = point_layer.dataProvider()
    fields = QgsFields()
    fields.append(QgsField("id", QVariant.Int))
    fields.append(QgsField("type", QVariant.String))
    point_provider.addAttributes(fields)
    point_layer.updateFields()

    id_counter = 1
    for feature in line_layer.getFeatures():
        geom = feature.geometry()
        if geom.isMultipart():
            lines = geom.asMultiPolyline()
        else:
            lines = [geom.asPolyline()]

        for line in lines:
            line_length = geom.length()

            for row in range(rows):
                row_offset = row * row_spacing
                distance = 0

                while distance < line_length:
                    point_geom = geom.interpolate(distance)
                    point = point_geom.asPoint()

                    if distance + plant_spacing < line_length:
                        next_point_geom = geom.interpolate(distance + plant_spacing)
                        next_point = next_point_geom.asPoint()
                        offset_angle = calculate_angle(point, next_point) + 90
                    else:
                        offset_angle = 90  # Default angle for the last point

                    offset_x = row_offset * math.cos(math.radians(offset_angle))
                    offset_y = row_offset * math.sin(math.radians(offset_angle))
                    row_point = QgsPointXY(point.x() + offset_x, point.y() + offset_y)

                    feature = QgsFeature()
                    feature.setGeometry(QgsGeometry.fromPointXY(row_point))
                    feature.setAttributes([id_counter, "Type"])
                    point_provider.addFeature(feature)

                    distance += plant_spacing
                    id_counter += 1

    # Apply symbology
    symbol = QgsMarkerSymbol.createSimple({'name': 'circle', 'color': 'red', 'size': '3'})
    point_layer.renderer().setSymbol(symbol)

    QgsProject.instance().addMapLayer(point_layer)
    iface.messageBar().pushMessage("Success", "Hedgerow points created successfully.", level=0)

# Hardcoded parameters
rows = 7
row_spacing = 1.25
plant_spacing = 1.0

# Call the function
generate_points(rows, row_spacing, plant_spacing)
