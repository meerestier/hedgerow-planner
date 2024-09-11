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

def attribute_species_to_points(point_layer, species_distribution, tree_percentage, shrub_percentage, rows):
    """
    Attribute species to points based on a distribution table, avoiding edge rows for trees.
    
    :param point_layer: The layer containing the points.
    :param species_distribution: List of dictionaries with species and type.
    :param tree_percentage: Percentage of points to be assigned to trees.
    :param shrub_percentage: Percentage of points to be assigned to shrubs.
    :param rows: Number of rows in the planting scheme.
    """
    # Extract trees and shrubs from species_distribution
    tree_species = [species["species"] for species in species_distribution if species["type"] == "tree"]
    shrub_species = [species["species"] for species in species_distribution if species["type"] == "shrub"]

    # Calculate number of points per type based on percentage
    total_points = point_layer.featureCount()
    tree_points_count = int(total_points * (tree_percentage / 100))
    shrub_points_count = int(total_points * (shrub_percentage / 100))

    # Expand tree and shrub lists based on the calculated points
    tree_list = [species for species in tree_species for _ in range(int(tree_points_count / len(tree_species)))]
    shrub_list = [species for species in shrub_species for _ in range(int(shrub_points_count / len(shrub_species)))]

    # Shuffle species lists to randomly distribute them
    random.shuffle(tree_list)
    random.shuffle(shrub_list)

    # Get the point layer and categorize points by row
    edge_points = []
    inner_points = []
    
    for feature in point_layer.getFeatures():
        row = feature['row']
        if row == 0 or row == rows - 1:
            edge_points.append(feature.id())
        else:
            inner_points.append(feature.id())

    # Update features with species attributes
    point_layer.startEditing()

    # Assign shrubs to edge points
    for feature_id, species in zip(edge_points, shrub_list[:len(edge_points)]):
        feature = point_layer.getFeature(feature_id)
        feature.setAttribute('species', species)
        feature.setAttribute('type', 'shrub')
        point_layer.updateFeature(feature)

    # Assign trees and remaining shrubs to inner points
    all_inner_species = tree_list + shrub_list[len(edge_points):]
    random.shuffle(all_inner_species)

    for feature_id, species in zip(inner_points, all_inner_species):
        feature = point_layer.getFeature(feature_id)
        feature.setAttribute('species', species)
        feature.setAttribute('type', 'tree' if species in tree_species else 'shrub')
        point_layer.updateFeature(feature)

    point_layer.commitChanges()

    # Assign random species to points with NULL species
    random_species = tree_species + shrub_species
    random.shuffle(random_species)

    point_layer.startEditing()
    for feature in point_layer.getFeatures():
        if feature['species'] is None or feature['type'] is None:
            species = random.choice(random_species)
            feature.setAttribute('species', species)
            feature.setAttribute('type', 'tree' if species in tree_species else 'shrub')
            point_layer.updateFeature(feature)
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

    return species_count

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

# Call the function to attribute species to points and get the species count
species_count = attribute_species_to_points(point_layer, species_distribution, tree_percentage, shrub_percentage, rows)

# Create polygons around groups of points and include species counts
create_group_polygons(point_layer)

# Create a summary table with the total counts of all species
create_species_summary_table(species_count)
