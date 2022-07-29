import pathlib

import os


from qgis.core import (
    QgsVectorLayer,
    QgsSimpleMarkerSymbolLayerBase,
    QgsSymbol,
    QgsWkbTypes,
    QgsRuleBasedRenderer,
    QgsFeatureRequest,
    QgsPalLayerSettings,
    QgsTextFormat,
    QgsTextBufferSettings,
    QgsVectorLayerSimpleLabeling
    )

from PyQt5.QtGui import QColor 

class AQMonitoring():
    def __init__(self, source, x_col_name='X (m)', y_col_name='Y (m)', delim=',',
                 crs="epsg:27700"):
        
        try:
            source_path = pathlib.Path(source) 
        except Exception as err:
            print("Error with source:") 
            print(err) 
        
        if type(source) is not str:
            raise Exception("source must be a path string to a shapefile of csv file")
        
        if not source_path.exists():
            raise Exception("source does not exist")
        
        # rules for conditional formatting label, rule_exression, color, size, shape
        rules = [["Non-automatic", '"Type" = \'Non-automatic\'', "blue", 2, QgsSimpleMarkerSymbolLayerBase.Circle],
                ["Automatic", '"Type" = \'Automatic\'', "orange", 4, QgsSimpleMarkerSymbolLayerBase.CrossFill]]
        
        if source_path.suffix == '.csv':
            monitoring_site_layer = _handle_csv_source(source_path, x_col_name, y_col_name, 
                                                       delim, crs)
        elif source_path.suffix == '.shp':
            monitoring_site_layer = _handle_shp_source(source_path, rules)
        else:
            raise Exception("source must have a .csv or .shp extension")
        
        monitoring_site_layer_formatted = _format_monitoring_sites(monitoring_site_layer, rules)
        
        self.layer = monitoring_site_layer_formatted
        
        
def _handle_csv_source(source_path, x_col_name, y_col_name, delim, crs, encoding="UTF-8"):
    
    csv_str_extra = (f"?encoding={encoding}&delimiter={delim}&xField={x_col_name}"
                     f"&yField={y_col_name}&crs={crs}")
    csv_path = str(source_path)+csv_str_extra
    monitoring_layer_name = source_path.parts[-1].replace(source_path.suffix, '')
    
    csv_path = 'file:///' + csv_path
    
    # add layer save to geopackage
    monitoring_site_layer = QgsVectorLayer(csv_path, monitoring_layer_name, "delimitedtext")
                 
    return monitoring_site_layer
            

def _handle_shp_source(source_path):
    monitoring_layer_name = source_path.parts[-1].replace(source_path.suffix, '')
    monitoring_layer = QgsVectorLayer(str(source_path), monitoring_layer_name, "ogr")
    return monitoring_layer 


def _format_monitoring_sites(monitoring_site_layer, rules):
    
    symbol = QgsSymbol.defaultSymbol(QgsWkbTypes.PointGeometry)
    renderer = QgsRuleBasedRenderer(symbol)
    root_rule = renderer.rootRule()
    # add rule based rendering
    for label, rule_expr, color, size, shape in rules:
        rule = root_rule.children()[0].clone()
        
        rule.setLabel(label)
        rule.symbol().setSize(size)
        rule.symbol().symbolLayer(0).setShape(shape)
        rule.setFilterExpression(rule_expr)
        root_rule.appendChild(rule)
        
        rule.symbol().setColor(QColor(color))
    
    # apply the renderer
    renderer.setUsingSymbolLevels(True)
    # order by type (this is alphabetical and not ideal)
    renderer.setOrderBy(QgsFeatureRequest.OrderBy([QgsFeatureRequest.OrderByClause('Type', False, False)]))
    renderer.setOrderByEnabled(True)
    
    monitoring_site_layer.setRenderer(renderer)
    monitoring_text_settings  = QgsPalLayerSettings()
    
    # add labels
    text_format = QgsTextFormat()
    buffer_settings = QgsTextBufferSettings()
    buffer_settings.setEnabled(True)
    text_format.setBuffer(buffer_settings)
    
    monitoring_text_settings.setFormat(text_format)
    monitoring_text_settings.fieldName = "Site ID"
    monitoring_text_settings.enabled = True
    
    layer_settings = QgsVectorLayerSimpleLabeling(monitoring_text_settings)
    monitoring_site_layer.setLabelsEnabled(True)
    monitoring_site_layer.setLabeling(layer_settings)
    monitoring_site_layer.triggerRepaint()
    
    return monitoring_site_layer