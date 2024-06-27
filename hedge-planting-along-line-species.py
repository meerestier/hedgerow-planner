"""
Dieses Skript führt die folgenden Schritte aus:

1. Imports und Funktionen:
    - Importiert notwendige Module und Funktionen aus QGIS und PyQt.
    - Definiert die Funktion `calculate_angle`, um den Winkel zwischen zwei Punkten zu berechnen.

2. Generierung der Punkte (generate_points Funktion):
    - Überprüft, ob die aktive Schicht eine Linienvektorschicht ist.
    - Erstellt eine neue Punktschicht mit den entsprechenden Attributfeldern (`id`, `type`, `species`, `row`).
    - Iteriert über die Features der Linienvektorschicht und generiert Punkte entlang der Linien basierend auf festgelegten Abständen (`row_spacing`, `plant_spacing`).
    - Berechnet die Position der Punkte und weist den Typ `shrub` den äußeren Reihen (erster und letzter) und `unassigned` den inneren Reihen zu.
    - Fügt die generierten Punkte der Punktschicht hinzu.
    - Fügt die Punktschicht zum Projekt hinzu.

3. Zuordnung der Arten zu Punkten (attribute_species_to_points Funktion):
    - Trennt die Arten in `trees` und `shrubs` basierend auf der `species_distribution` Liste.
    - Berechnet die Anzahl der Punkte pro Art basierend auf den Prozentsätzen.
    - Erstellt erweiterte Listen von `trees` und `shrubs` basierend auf den berechneten Punktzahlen und mischt sie zufällig.
    - Kategorisiert die Punkte in `edge_points` (äußere Reihen) und `inner_points` (innere Reihen).
    - Fügt das `species` Feld zur Punktschicht hinzu, falls es noch nicht vorhanden ist.
    - Beginnt die Bearbeitung der Punktschicht.
    - Weist die `shrubs` den äußeren Punkten (`edge_points`) zu.
    - Weist die `trees` und verbleibenden `shrubs` den inneren Punkten (`inner_points`) zu und mischt sie zufällig.
    - Beendet die Bearbeitung der Punktschicht und zählt die Anzahl der Punkte für jede Art.
    - Setzt die Symbologie basierend auf dem Typ (`tree` oder `shrub`) mit unterschiedlichen Farben.
"""

import math
import random
from qgis.core import (QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, 
                       QgsPointXY, QgsFields, QgsField, QgsWkbTypes, QgsMarkerSymbol, QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsCoordinateReferenceSystem)
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
    fields.append(QgsField("species", QVariant.String))
    fields.append(QgsField("row", QVariant.Int))
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

                    type_value = "shrub" if row == 0 or row == rows - 1 else "unassigned"
                    feature = QgsFeature()
                    feature.setGeometry(QgsGeometry.fromPointXY(row_point))
                    feature.setAttributes([id_counter, type_value, None, row])
                    point_provider.addFeature(feature)

                    distance += plant_spacing
                    id_counter += 1

    QgsProject.instance().addMapLayer(point_layer)
    iface.messageBar().pushMessage("Success", "Hedgerow points created successfully.", level=0)

def attribute_species_to_points(species_distribution, rows):
    """
    Attribute species to points based on a distribution table, avoiding edge rows for trees.
    
    :param species_distribution: List of dictionaries with species, type, and their area percentages.
    :param rows: Number of rows in the planting scheme.
    """
    # Extract trees and shrubs from species_distribution
    tree_list = [species["species"] for species in species_distribution if species["type"] == "tree"]
    shrub_list = [species["species"] for species in species_distribution if species["type"] == "shrub"]

    # Calculate number of points per species based on percentage
    point_layer = QgsProject.instance().mapLayersByName('Hedgerow Points')[0]
    total_points = point_layer.featureCount()
    species_points = {}
    for species in species_distribution:
        species_points[species["species"]] = int(total_points * (species["percentage"] / 100))

    # Expand tree and shrub lists based on the calculated points
    expanded_tree_list = [species for species in tree_list for _ in range(species_points.get(species, 0))]
    expanded_shrub_list = [species for species in shrub_list for _ in range(species_points.get(species, 0))]

    # Shuffle species lists to randomly distribute them
    random.shuffle(expanded_tree_list)
    random.shuffle(expanded_shrub_list)

    # Get the point layer and categorize points by row
    edge_points = []
    inner_points = []
    
    for feature in point_layer.getFeatures():
        row = feature['row']
        if row == 0 or row == rows - 1:
            edge_points.append(feature.id())
        else:
            inner_points.append(feature.id())

    # Add new field for species if not already present
    if 'species' not in point_layer.fields().names():
        point_provider = point_layer.dataProvider()
        point_provider.addAttributes([QgsField('species', QVariant.String)])
        point_layer.updateFields()

    # Update features with species attributes
    point_layer.startEditing()

    # Assign shrubs to edge points
    for feature_id, species in zip(edge_points, expanded_shrub_list):
        feature = point_layer.getFeature(feature_id)
        feature.setAttribute('species', species)
        feature.setAttribute('type', 'shrub')
        point_layer.updateFeature(feature)

    # Assign trees and remaining shrubs to inner points
    remaining_inner_points = inner_points[:]
    all_inner_species = expanded_tree_list + expanded_shrub_list[len(edge_points):]
    random.shuffle(all_inner_species)

    for feature_id, species in zip(inner_points, all_inner_species):
        feature = point_layer.getFeature(feature_id)
        feature.setAttribute('species', species)
        feature.setAttribute('type', 'tree' if species in tree_list else 'shrub')
        point_layer.updateFeature(feature)
        remaining_inner_points.remove(feature_id)

    point_layer.commitChanges()

    # Count the number of each species
    species_count = {species["species"]: 0 for species in species_distribution}
    for feature in point_layer.getFeatures():
        species = feature['species']
        if species in species_count:
            species_count[species] += 1

    # Output the species count
    for species, count in species_count.items():
        print(f"{species}: {count} Punkte")
    
    # Set symbology based on type
    categories = []
    tree_symbol = QgsMarkerSymbol.createSimple({'name': 'circle', 'color': 'green', 'size': '3'})
    shrub_symbol = QgsMarkerSymbol.createSimple({'name': 'circle', 'color': 'blue', 'size': '3'})
    
    categories.append(QgsRendererCategory('tree', tree_symbol, 'Tree'))
    categories.append(QgsRendererCategory('shrub', shrub_symbol, 'Shrub'))
    
    renderer = QgsCategorizedSymbolRenderer('type', categories)
    point_layer.setRenderer(renderer)

    iface.messageBar().pushMessage("Success", "Species attributes added to hedgerow points.", level=0)

# Hardcoded parameters for point generation
rows = 7
row_spacing = 1.25
plant_spacing = 1.0

# Example species distribution list with type and percentage
species_distribution = [
    {"species": "Quercus petraea", "type": "tree", "percentage": 10},
    {"species": "Quercus robur", "type": "tree", "percentage": 10},
    {"species": "Acer campestre", "type": "tree", "percentage": 5},
    {"species": "Tilia platyphyllos", "type": "tree", "percentage": 5},
    {"species": "Acer pseudoplatanus", "type": "tree", "percentage": 5},
    {"species": "Sorbus aucuparia", "type": "tree", "percentage": 5},
    {"species": "Tilia cordata", "type": "tree", "percentage": 5},
    {"species": "Carpinus betulus", "type": "tree", "percentage": 5},
    {"species": "Salix alba", "type": "tree", "percentage": 5},
    {"species": "Prunus avium", "type": "tree", "percentage": 5},
    {"species": "Ulmus laevis", "type": "tree", "percentage": 5},
    {"species": "Sand-Birke", "type": "tree", "percentage": 5},
    {"species": "Malus sylvestris", "type": "tree", "percentage": 5},
    {"species": "Rosa canina", "type": "shrub", "percentage": 3},
    {"species": "Rosa rubinigosa", "type": "shrub", "percentage": 3},
    {"species": "Rosa corymbifera", "type": "shrub", "percentage": 3},
    {"species": "Crataegus monogyna", "type": "shrub", "percentage": 3},
    {"species": "Crataegus laevigata", "type": "shrub", "percentage": 3},
    {"species": "Viburnum opolus", "type": "shrub", "percentage": 3},
    {"species": "Prunus padus", "type": "shrub", "percentage": 3},
    {"species": "Sorbus torminalis", "type": "shrub", "percentage": 3},
    {"species": "Rhamnus carthartica", "type": "shrub", "percentage": 3},
    {"species": "Cornus sanguinea", "type": "shrub", "percentage": 3},
    {"species": "Coryllus avellana", "type": "shrub", "percentage": 3},
    {"species": "Sambucus nigra", "type": "shrub", "percentage": 3},
    {"species": "Euonymus europaeus", "type": "shrub", "percentage": 3},
    {"species": "Pyrus pyraster", "type": "shrub", "percentage": 3},
    {"species": "Salix viminalis", "type": "shrub", "percentage": 3},
    {"species": "Salix purpurea", "type": "shrub", "percentage": 3},
    {"species": "Salix caprea", "type": "shrub", "percentage": 3}
]

# Call the function to generate points
generate_points(rows, row_spacing, plant_spacing)

# Call the function to attribute species to points
attribute_species_to_points(species_distribution, rows)
