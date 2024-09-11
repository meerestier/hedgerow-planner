import math
import random
from qgis.core import (QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsFields, QgsField, QgsWkbTypes, QgsMarkerSymbol, QgsCategorizedSymbolRenderer, QgsRendererCategory)
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
    fields.append(QgsField("gatter", QVariant.Int))
    point_provider.addAttributes(fields)
    point_layer.updateFields()

    id_counter = 1
    gatter_counter = 1
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
                        previous_point_geom = geom.interpolate(distance - plant_spacing)
                        previous_point = previous_point_geom.asPoint()
                        offset_angle = calculate_angle(previous_point, point) + 90

                    offset_x = row_offset * math.cos(math.radians(offset_angle))
                    offset_y = row_offset * math.sin(math.radians(offset_angle))
                    row_point = QgsPointXY(point.x() + offset_x, point.y() + offset_y)

                    type_value = "shrub" if row == 0 or row == rows - 1 else "unassigned"
                    feature = QgsFeature()
                    feature.setGeometry(QgsGeometry.fromPointXY(row_point))
                    feature.setAttributes([id_counter, type_value, None, row, gatter_counter])
                    point_provider.addFeature(feature)

                    distance += plant_spacing
                    id_counter += 1
            gatter_counter += 1

    QgsProject.instance().addMapLayer(point_layer)
    iface.messageBar().pushMessage("Success", "Hedgerow points created successfully.", level=0)
    return point_layer

def attribute_species_to_points_with_clusters(point_layer, species_distribution, tree_percentage, shrub_percentage, rows, min_cluster_size=3, max_cluster_size=5):
    """
    Attribute species to points with clustering of shrubs, ensuring all points are assigned a species.
    Each shrub cluster is assigned a unique cluster ID, and plants in the same cluster are of the same species.
    
    :param point_layer: The layer containing the points.
    :param species_distribution: List of dictionaries with species and type.
    :param tree_percentage: Percentage of points to be assigned to trees.
    :param shrub_percentage: Percentage of points to be assigned to shrubs.
    :param rows: Number of rows in the planting scheme.
    :param min_cluster_size: Minimum number of plants in a cluster (same species).
    :param max_cluster_size: Maximum number of plants in a cluster (same species).
    """
    # Prüfe und füge die Felder 'species', 'type' und 'cluster_id' hinzu, falls nicht vorhanden
    fields = point_layer.fields()
    if fields.indexOf('species') == -1:
        point_layer.dataProvider().addAttributes([QgsField('species', QVariant.String)])
    if fields.indexOf('type') == -1:
        point_layer.dataProvider().addAttributes([QgsField('type', QVariant.String)])
    if fields.indexOf('cluster_id') == -1:
        point_layer.dataProvider().addAttributes([QgsField('cluster_id', QVariant.Int)])
    point_layer.updateFields()
    
    # Extrahiere Bäume und Sträucher aus der Verteilung
    tree_species = [species["species"] for species in species_distribution if species["type"] == "tree"]
    shrub_species = [species["species"] for species in species_distribution if species["type"] == "shrub"]
    
    # Berechne die Anzahl der Punkte pro Typ basierend auf dem Prozentsatz
    total_points = point_layer.featureCount()
    tree_points_count = int(total_points * (tree_percentage / 100))
    shrub_points_count = int(total_points * (shrub_percentage / 100))
    
    # Liste der Baum- und Straucharten erstellen
    tree_list = [species for species in tree_species for _ in range(tree_points_count // len(tree_species))]
    shrub_list = [species for species in shrub_species for _ in range(shrub_points_count // len(shrub_species))]
    
    # Artenlisten mischen für zufällige Verteilung
    random.shuffle(tree_list)
    random.shuffle(shrub_list)
    
    # Alle Punkte des Layers sammeln
    all_points = [feature.id() for feature in point_layer.getFeatures()]
    
    # Punkte-Cluster erstellen und Arten zuweisen
    point_layer.startEditing()
    
    current_shrub_index = 0
    cluster_id = 1  # Eindeutige Cluster-ID für jeden Cluster
    
    for i in range(0, len(all_points), min_cluster_size):
        cluster_size = random.randint(min_cluster_size, max_cluster_size)
        cluster_points = all_points[i:i + cluster_size]
        
        # Wähle eine Art für den gesamten Cluster
        shrub_species_for_cluster = shrub_list[current_shrub_index % len(shrub_list)]
        
        for feature_id in cluster_points:
            feature = point_layer.getFeature(feature_id)
            feature.setAttribute('species', shrub_species_for_cluster)
            feature.setAttribute('type', 'shrub')
            feature.setAttribute('cluster_id', cluster_id)  # Weisen Sie eine Cluster-ID für die Visualisierung zu
            point_layer.updateFeature(feature)
    
        current_shrub_index += 1
        cluster_id += 1  # Inkrementieren der Cluster-ID für die nächste Gruppe
    
    # Restliche Punkte zufällig Bäumen zuweisen
    remaining_points = all_points[current_shrub_index:]
    random.shuffle(remaining_points)
    current_tree_index = 0
    
    for feature_id in remaining_points:
        feature = point_layer.getFeature(feature_id)
        tree = tree_list[current_tree_index % len(tree_list)]  # Zyklus durch Baumarten
        feature.setAttribute('species', tree)
        feature.setAttribute('type', 'tree')
        feature.setAttribute('cluster_id', 0)  # Bäume sind nicht Teil der Strauch-Cluster
        point_layer.updateFeature(feature)
        current_tree_index += 1
    
    # Änderungen übernehmen, um die zugewiesenen Arten zu speichern
    point_layer.commitChanges()
    
    # Symbologie basierend auf der Cluster-ID für Sträucher und einer Standardsymbolik für Bäume festlegen
    categories = []
    
    # Symbologie für Sträucher basierend auf der Cluster-ID (Farben variieren)
    for cluster_id in range(1, cluster_id):  # Unterschiedliche Symbole pro Cluster
        shrub_symbol = QgsMarkerSymbol.createSimple({'name': 'circle', 'color': f'hsl({(cluster_id * 30) % 360}, 100%, 50%)', 'size': '3'})
        categories.append(QgsRendererCategory(cluster_id, shrub_symbol, f'Cluster {cluster_id}'))
    
    

def create_group_polygons(point_layer):
    """Create polygons around groups of points along each line and calculate metrics."""
    polygon_layer = QgsVectorLayer('Polygon?crs=' + point_layer.crs().toWkt(), 'Group Polygons', 'memory')
    polygon_provider = polygon_layer.dataProvider()
    
    # Add 'area', 'zaunlänge', and species count fields to polygon layer
    fields = QgsFields()
    fields.append(QgsField('area', QVariant.Double))
    fields.append(QgsField('zaunlänge', QVariant.Double))
    unique_species = set()
    for feature in point_layer.getFeatures():
        unique_species.add(feature['species'])
    for species in unique_species:
        fields.append(QgsField(f'count_{species}', QVariant.Int))
    polygon_provider.addAttributes(fields)
    polygon_layer.updateFields()

    # Create polygons for each gatter group
    gatter_groups = {}
    species_counts = {species: {} for species in unique_species}
    for feature in point_layer.getFeatures():
        gatter_id = feature['gatter']
        species = feature['species']
        geom = feature.geometry()
        point = geom.asPoint()
        if gatter_id not in gatter_groups:
            gatter_groups[gatter_id] = []
            species_counts[gatter_id] = {species: 0 for species in unique_species}
        gatter_groups[gatter_id].append(point)
        species_counts[gatter_id][species] += 1

    for gatter_id, points in gatter_groups.items():
        convex_hull = QgsGeometry.fromMultiPointXY(points).convexHull()
        buffer_geom = convex_hull.buffer(2.0, 5)  # 1m buffer with 5 segments
        polygon_feature = QgsFeature()
        polygon_feature.setGeometry(buffer_geom)
        attributes = [buffer_geom.area(), buffer_geom.length()]
        attributes.extend([species_counts[gatter_id].get(species, 0) for species in unique_species])
        polygon_feature.setAttributes(attributes)
        polygon_provider.addFeature(polygon_feature)

    # Add polygon layer to the project
    QgsProject.instance().addMapLayer(polygon_layer)
    iface.messageBar().pushMessage("Success", "Group polygons created successfully.", level=0)

def create_species_summary_table(species_count):
    """Create a summary table with the total counts of all species."""
    table_layer = QgsVectorLayer('None', 'Species Summary', 'memory')
    table_provider = table_layer.dataProvider()
    
    fields = QgsFields()
    fields.append(QgsField('species', QVariant.String))
    fields.append(QgsField('count', QVariant.Int))
    table_provider.addAttributes(fields)
    table_layer.updateFields()

    for species, count in species_count.items():
        feature = QgsFeature()
        feature.setAttributes([species, count])
        table_provider.addFeature(feature)
    
    QgsProject.instance().addMapLayer(table_layer)
    iface.messageBar().pushMessage("Success", "Species summary table created successfully.", level=0)

# Hardcoded parameters for point generation
rows = 5
row_spacing = 1.25
plant_spacing = 1.0

# Example species distribution list with type and species
species_distribution = [
    {"species": "Quercus petraea", "type": "tree"},
    {"species": "Quercus robur", "type": "tree"},
    {"species": "Acer campestre", "type": "tree"},
    {"species": "Tilia platyphyllos", "type": "tree"},
    {"species": "Acer pseudoplatanus", "type": "tree"},
    {"species": "Sorbus aucuparia", "type": "tree"},
    {"species": "Tilia cordata", "type": "tree"},
    {"species": "Carpinus betulus", "type": "tree"},
    {"species": "Salix alba", "type": "tree"},
    {"species": "Prunus avium", "type": "tree"},
    {"species": "Ulmus laevis", "type": "tree"},
    {"species": "Betula pendula", "type": "tree"},
    {"species": "Malus sylvestris", "type": "tree"},
    {"species": "Rosa canina", "type": "shrub"},
    {"species": "Rosa rubinigosa", "type": "shrub"},
    {"species": "Rosa corymbifera", "type": "shrub"},
    {"species": "Crataegus monogyna", "type": "shrub"},
    {"species": "Crataegus laevigata", "type": "shrub"},
    {"species": "Viburnum opolus", "type": "shrub"},
    {"species": "Prunus padus", "type": "shrub"},
    {"species": "Sorbus torminalis", "type": "shrub"},
    {"species": "Rhamnus carthartica", "type": "shrub"},
    {"species": "Cornus sanguinea", "type": "shrub"},
    {"species": "Coryllus avellana", "type": "shrub"},
    {"species": "Sambucus nigra", "type": "shrub"},
    {"species": "Euonymus europaeus", "type": "shrub"},
    {"species": "Pyrus pyraster", "type": "shrub"},
    {"species": "Salix viminalis", "type": "shrub"},
    {"species": "Salix purpurea", "type": "shrub"},
    {"species": "Salix caprea", "type": "shrub"}
]

# Example percentage inputs for trees and shrubs
tree_percentage = 30
shrub_percentage = 70

# Call the function to generate points and return the point layer
point_layer = generate_points(rows, row_spacing, plant_spacing)

# Call the function to attribute species to points with clustering and get the species count
species_count = attribute_species_to_points_with_clusters(point_layer, species_distribution, tree_percentage, shrub_percentage, rows)

# Create polygons around groups of points and include species counts
create_group_polygons(point_layer)

# Create a summary table with the total counts of all species
create_species_summary_table(species_count)
