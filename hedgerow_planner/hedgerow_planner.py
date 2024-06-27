import os
import math
from qgis.core import (QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, 
                       QgsPointXY, QgsFields, QgsField, QgsWkbTypes, QgsMarkerSymbol)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QDialog
from qgis.utils import iface
from .hedgerow_planner_dialog import HedgerowPlannerDialog

def calculate_angle(point1, point2):
    """Calculate angle in degrees between two points."""
    dx = point2.x() - point1.x()
    dy = point2.y() - point1.y()
    return math.degrees(math.atan2(dy, dx))

class HedgerowPlanner:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.
        
        :param iface: A QGIS interface instance.
        :type iface: QgsInterface
        """
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = self.tr("&Hedgerow Planner")
        self.toolbar = self.iface.addToolBar("HedgerowPlanner")
        self.toolbar.setObjectName("HedgerowPlanner")

    def tr(self, message):
        """Get the translation for a string using Qt translation API."""
        return QCoreApplication.translate("HedgerowPlanner", message)

    def add_action(self, icon_path, text, callback, enabled_flag=True, add_to_menu=True, add_to_toolbar=True, status_tip=None, whats_this=None, parent=None):
        """Add a toolbar icon to the toolbar."""
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        self.actions.append(action)
        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        icon_path = ':/plugins/hedgerow_planner/icon.png'
        self.add_action(icon_path, text=self.tr("Hedgerow Planner"), callback=self.run, parent=self.iface.mainWindow())

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(self.tr("&Hedgerow Planner"), action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar

    def run(self):
        """Run method that performs all the real work."""
        dialog = HedgerowPlannerDialog()
        dialog.exec_()
        
        if dialog.result() == QDialog.Accepted:
            rows = dialog.rows_spinbox.value()
            row_spacing = dialog.row_spacing_spinbox.value()
            plant_spacing = dialog.plant_spacing_spinbox.value()
            self.generate_points(rows, row_spacing, plant_spacing)

    def generate_points(self, rows, row_spacing, plant_spacing):
        """Generate points based on the user input."""
        line_layer = self.iface.activeLayer()

        if not isinstance(line_layer, QgsVectorLayer) or line_layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.iface.messageBar().pushMessage("Error", "Please select a line layer.", level=QgsMessageBar.CRITICAL)
            return

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
        self.iface.messageBar().pushMessage("Success", "Hedgerow points created successfully.", level=QgsMessageBar.INFO)
