import math
import random
from qgis.core import (QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsFields, QgsField, QgsWkbTypes, QgsMarkerSymbol, QgsCategorizedSymbolRenderer, QgsRendererCategory)
from qgis.PyQt.QtCore import QVariant
from qgis.utils import iface
from datetime import datetime

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
    fields_to_add = [QgsField('species', QVariant.String), QgsField('type', QVariant.String), QgsField('cluster_id', QVariant.Int)]
    point_layer.dataProvider().addAttributes([f for f in fields_to_add if point_layer.fields().indexOf(f.name()) == -1])
    point_layer.updateFields()

    tree_species = [species["species"] for species in species_distribution if species["type"] == "tree"]
    shrub_species = [species["species"] for species in species_distribution if species["type"] == "shrub"]

    total_points = point_layer.featureCount()
    tree_points_count = int(total_points * (tree_percentage / 100))
    shrub_points_count = total_points - tree_points_count

    tree_list = [species for species in tree_species for _ in range(tree_points_count // len(tree_species) + 1)]
    shrub_list = [species for species in shrub_species for _ in range(shrub_points_count // len(shrub_species) + 1)]

    random.shuffle(tree_list)
    random.shuffle(shrub_list)

    gatter_groups = {}
    for feature in point_layer.getFeatures():
        gatter_id = feature['gatter']
        gatter_groups.setdefault(gatter_id, []).append(feature.id())

    point_layer.startEditing()
    
    global_cluster_id = 1
    tree_count = 0
    shrub_count = 0
    
    # Calculate trees per gatter
    gatter_count = len(gatter_groups)
    trees_per_gatter = tree_points_count // gatter_count
    extra_trees = tree_points_count % gatter_count

    def assign_shrub_cluster(points, start_index):
        nonlocal shrub_count, global_cluster_id
        cluster_size = min(random.randint(min_cluster_size, max_cluster_size), len(points) - start_index)
        shrub_species_for_cluster = shrub_list[shrub_count % len(shrub_list)]
        for i in range(start_index, start_index + cluster_size):
            feature = point_layer.getFeature(points[i])
            feature.setAttribute('species', shrub_species_for_cluster)
            feature.setAttribute('type', 'shrub')
            feature.setAttribute('cluster_id', global_cluster_id)
            point_layer.updateFeature(feature)
            shrub_count += 1
        global_cluster_id += 1
        return cluster_size

    for gatter_id, point_ids in gatter_groups.items():
        points_by_row = {}
        for pid in point_ids:
            feature = point_layer.getFeature(pid)
            row = feature['row']
            points_by_row.setdefault(row, []).append(pid)

        # Determine number of trees for this gatter
        gatter_tree_count = trees_per_gatter + (1 if extra_trees > 0 else 0)
        extra_trees = max(0, extra_trees - 1)
        
        # Assign plants row by row
        for row in range(rows):
            row_points = points_by_row.get(row, [])
            random.shuffle(row_points)
            i = 0
            while i < len(row_points):
                if row == 0 or row == rows - 1 or tree_count >= tree_points_count:
                    # Assign shrubs to outer rows and when tree quota is met
                    i += assign_shrub_cluster(row_points, i)
                else:
                    # Assign trees to inner rows
                    if gatter_tree_count > 0:
                        feature = point_layer.getFeature(row_points[i])
                        tree = tree_list[tree_count % len(tree_list)]
                        feature.setAttribute('species', tree)
                        feature.setAttribute('type', 'tree')
                        feature.setAttribute('cluster_id', 0)
                        point_layer.updateFeature(feature)
                        tree_count += 1
                        gatter_tree_count -= 1
                        i += 1
                    else:
                        # Assign shrubs when tree quota for this gatter is met
                        i += assign_shrub_cluster(row_points, i)

    point_layer.commitChanges()

    # Create a more robust symbology
    categories = []
    for species in set(shrub_species + tree_species):
        for plant_type in ['shrub', 'tree']:
            symbol = QgsMarkerSymbol.createSimple({
                'name': 'circle' if plant_type == 'shrub' else 'triangle',
                'color': random_color_for_species(species),
                'size': '3',
                'outline_style': 'solid',
                'outline_color': 'black',
                'outline_width': '0.2'
            })
            categories.append(QgsRendererCategory(f"{species}_{plant_type}", symbol, f"{species} ({plant_type})"))

    renderer = QgsCategorizedSymbolRenderer("species || '_' || type", categories)
    point_layer.setRenderer(renderer)

    return point_layer

def random_color_for_species(species_name):
    """Generate a random color for a given species."""
    random.seed(hash(species_name))
    return f'#{random.randint(0, 255):02x}{random.randint(0, 255):02x}{random.randint(0, 255):02x}'

def create_group_polygons(point_layer):
    """Create polygons around groups of points along each line and calculate metrics."""
    polygon_layer = QgsVectorLayer('Polygon?crs=' + point_layer.crs().toWkt(), 'Group Polygons', 'memory')
    polygon_provider = polygon_layer.dataProvider()
    
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
        buffer_geom = convex_hull.buffer(2.0, 5)  # 2m buffer with 5 segments
        polygon_feature = QgsFeature()
        polygon_feature.setGeometry(buffer_geom)
        attributes = [buffer_geom.area(), buffer_geom.length()]
        attributes.extend([species_counts[gatter_id].get(species, 0) for species in unique_species])
        polygon_feature.setAttributes(attributes)
        polygon_provider.addFeature(polygon_feature)

    QgsProject.instance().addMapLayer(polygon_layer)
    return polygon_layer

def create_species_summary_table_with_percentages(point_layer):
    """Create a summary table with the total counts of all species and their percentage values."""
    total_points = point_layer.featureCount()

    species_count = {}
    for feature in point_layer.getFeatures():
        species = feature['species']
        plant_type = feature['type']
        if species and species.strip():
            key = (species, plant_type)
            species_count[key] = species_count.get(key, 0) + 1

    if not species_count:
        iface.messageBar().pushMessage("Error", "No valid species data found.", level=3)
        return None

    table_layer = QgsVectorLayer('None', 'Species Summary with Percentages', 'memory')
    table_provider = table_layer.dataProvider()
    
    fields = QgsFields()
    fields.append(QgsField('species', QVariant.String))
    fields.append(QgsField('type', QVariant.String))
    fields.append(QgsField('count', QVariant.Int))
    fields.append(QgsField('percentage', QVariant.Double))
    table_provider.addAttributes(fields)
    table_layer.updateFields()

    for (species, plant_type), count in species_count.items():
        percentage = (count / total_points) * 100
        feature = QgsFeature()
        feature.setAttributes([species, plant_type, count, percentage])
        table_provider.addFeature(feature)
    
    QgsProject.instance().addMapLayer(table_layer)
    return table_layer

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

# Generate points and return the point layer
point_layer = generate_points(rows, row_spacing, plant_spacing)

# Attribute species to points with clustering
point_layer = attribute_species_to_points_with_clusters(point_layer, species_distribution, tree_percentage, shrub_percentage, rows)

# Create polygons around groups of points and include species counts
polygon_layer = create_group_polygons(point_layer)

# Create a summary table with the total counts of all species and their percentages
summary_table_layer = create_species_summary_table_with_percentages(point_layer)

# Create a group with timestamp
timestamp = datetime.now().strftime("%d%m%y-%H-%M")
group_name = f"version-{timestamp}"

root = QgsProject.instance().layerTreeRoot()
group = root.addGroup(group_name)

# Add layers to the group in the desired order
QgsProject.instance().addMapLayer(summary_table_layer, False)
summary_tree_layer = group.addLayer(summary_table_layer)

QgsProject.instance().addMapLayer(polygon_layer, False)
polygon_tree_layer = group.addLayer(polygon_layer)

QgsProject.instance().addMapLayer(point_layer, False)
point_tree_layer = group.addLayer(point_layer)

# Set visibility
summary_tree_layer.setItemVisibilityChecked(True)
polygon_tree_layer.setItemVisibilityChecked(True)
point_tree_layer.setItemVisibilityChecked(True)

iface.messageBar().pushMessage("Success", f"Hedgerow analysis completed successfully. Layers added to group '{group_name}'.", level=0)
