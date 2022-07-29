# -*- coding: utf-8 -*-
"""
Created on Thu Mar 31 09:46:07 2022

@author: kbenjamin
"""

import os
from copy import deepcopy
import numpy as np
import pandas as pd
from itertools import product

from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsVectorLayer,
    QgsMapLayerType,
    QgsPathResolver,
    QgsRasterLayer,
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

from qgis.analysis import QgsNativeAlgorithms
import processing
from processing.core.Processing import Processing

import ADMSQpy

from ADMSQpy.modelledroads import ModelledRoads

from ADMSQpy.utils import (select_layer_by_name,
                           save_to_gpkg,
                           save_raster)

from ADMSQpy.MyFeedback import MyFeedBack
from ADMSQpy.getdefrabackground import get_defra_background_concentrations

class AqQgisProjectBasemap():
    def __init__(self, project_path, run_environment = "qgis_gui"):
       self.project_path = project_path
       
       valid_run_envs = ['qgis_gui', 'standalone']
       assert run_environment in valid_run_envs, f"run_environment must be one of: {', '.join(valid_run_envs)}"
       
       self.run_environment = run_environment
       
       if not os.path.exists(project_path):
           raise Exception("Specified project path does not exist")
       
       #initialise project 
       if run_environment == "qgis_gui":
            project = QgsProject.instance()
       elif run_environment == "standalone":
           qgs = QgsApplication([], True)
           qgs.initQgis()
           
           self.qgs_app = qgs

           project = QgsProject.instance()
           project.read(project_path)
           
           Processing.initialize()
           qgs.processingRegistry().addProvider(QgsNativeAlgorithms())
           
       self._project = project
       self.project_name = os.path.splitext(os.path.basename(project_path))[0]
       return
   
    def get_project(self):
        return self._project
        
    def initialise_project(self, project_name, project_path, site_geom_source,
                           clip_distance = 10000):
        
        # set up paths
        # TODO: make paths absolute?
        project_qgs_path = os.path.join(project_path, project_name+'.qgz')
        gpkg_path = os.path.join(project_path, project_name+'.gpkg')
        
        if os.path.exists(project_qgs_path):
            raise Exception(f"Project {project_qgs_path} already exists.")
        
        base_project = self.get_project()
        
        # the initial layer sources (these get re assigned ugh)
        layer_sources = {layer.name() : layer.source() for layer in base_project.mapLayers().values()}
        # save to new project and initiate project object
        new_project = base_project.write(project_qgs_path)
    
        new_ADMSQ_project = AqQgisProject(project_qgs_path, run_environment=self.run_environment)
        new_ADMSQ_project.set_gpkg_path(gpkg_path)
        
        new_project = new_ADMSQ_project.get_project()
        
        # get site geometry
        site_geom = new_ADMSQ_project.set_site_geom(site_geom_source)
        
        #get area to clip to 
        clip_bounding_box = _get_site_clip_bounding_box(site_geom, clip_distance)
        
        print("Clipping and saving basemap layers...")
        n_layers = len(list(base_project.mapLayers().values()))
        counter = 1
        # clip and add each layer
        for layer in base_project.mapLayers().values():
            
            print(f"{str(counter)}/{str(n_layers)}")
            counter += 1
            
            # get the group to save to
            new_root = new_project.layerTreeRoot()
            layer_node = new_root.findLayer(layer.id())
            group = layer_node.parent()
            
            #temporarily save the style
            layer_style_path = layer.styleURI()
            layer.saveNamedStyle(layer_style_path)
            
            # if a raster save as standalone file
            if layer.type() == QgsMapLayerType.RasterLayer:
                #test if it is from a file (i.e. not open street maps etc)
                if os.path.exists(layer_sources[layer.name()]):
                    try:
                        clipped_layer = save_raster(layer, gpkg_path)
                    except Exception as e:
                        print(f"Failed to save {layer.name()} with message {e}")
                        _remove_temp_style_file(layer_style_path)
                        continue
                # if its an xyz tile e.g. open street map
                else:
                    clipped_layer = QgsRasterLayer(layer.source(), layer.name(), 'wms')
            else:
                #clip layer and save to a geopackage
                clipped_layer = new_ADMSQ_project.clip_layer_around_site(layer, layer_sources[layer.name()],
                                                                         gpkg_path, 
                                                                         clip_bounding_box = clip_bounding_box,
                                                                         clip_distance = 10000)             
                # if clipping fails save it to geopackage without clipping
                if not clipped_layer:
                    try:
                        clipped_layer = save_to_gpkg(layer, gpkg_path)
                    except Exception as e:
                        print(f"Failed to save {layer.name()} with message {e}")
                        _remove_temp_style_file(layer_style_path)
                        continue
            #load style and remove temp file
            _load_style_from_file(clipped_layer, layer_style_path)
            _remove_temp_style_file(layer_style_path)
            
            # add new layer
            new_project.addMapLayer(clipped_layer, False)
            group.addLayer(clipped_layer)
            new_ADMSQ_project.remove_layer(layer)
        
        # TODO: format into red line
        project_group = new_root.findGroup("Project")
        site_geom_gpkg_layer = save_to_gpkg(site_geom, gpkg_path)
        new_project.addMapLayer(site_geom_gpkg_layer, False)
        project_group.addLayer(site_geom_gpkg_layer)
        
        new_ADMSQ_project.set_gpkg_path(gpkg_path)
        
        new_ADMSQ_project.save()
        return new_ADMSQ_project
#%%
class AqQgisProject(AqQgisProjectBasemap):
    
    def __init__(self, project_path, run_environment = "qgis_gui"):
        super().__init__(project_path, run_environment)
    
    def set_gpkg_path(self, project_gpkg_path):
        self.gpkg_path = project_gpkg_path
        return
    
    def set_site_geom(self, site_geom_source):
        #TODO check file exists
        
        if type(site_geom_source) != str:
             raise Exception("Source must be a string of layer name or file path")
        #TODO: allow geopackage
        # test if from file
        if os.path.splitext(site_geom_source)[1] != '':
            if os.path.splitext(site_geom_source)[1] != '.shp':
                raise Exception("site_geom_source must be a shp file or a layer name")
            site_geometry = QgsVectorLayer(site_geom_source, "site_boundary", "ogr")
        else:
             qgs_proj = self.get_project()
             site_geometry = select_layer_by_name(site_geom_source, qgs_proj)
        
        self.site_geometry = site_geometry
        
        return site_geometry
    
    def get_site_background_concs(self, background_region, year, 
                                  pollutants = ['no2', 'nox', 'pm10', 'pm25'],
                                  base_year = '2018', split_by_source=False):
        
        if 'site_geometry' not in dir(self):
            raise Exception('site_geometry not set. Set with set_site_geom function')
        
        site_geometry = self.site_geometry
        
        site_geometry_extent = site_geometry.extent()
        coordinates = [[site_geometry_extent.xMinimum(), site_geometry_extent.yMinimum()],
                       [site_geometry_extent.xMaximum(), site_geometry_extent.yMaximum()]]
        
        site_background_concs = get_defra_background_concentrations(coordinates, 
                                                                   background_region, year, 
                                                                   pollutants, base_year, 
                                                                   split_by_source)
        
        return site_background_concs
        
    def get_site_buffer(self, buffer_size, group="Construction"):
        # TODO
        
        if 'site_geometry' not in dir(self):
            raise Exception('site_geometry not set. Set with set_site_geom function')
        
        site_geom = self.site_geometry
        buffer_layer_name = 'site_buffer_'+str(buffer_size)+'m'
        
        if 'gpkg_path' not in dir(self):
            project_path = self.project_path
            output = os.path.join(project_path, buffer_layer_name) + ".shp"
        else:
            gpkg_path = self.gpkg_path
            output = 'ogr:dbname=\"'+gpkg_path+'\" table=\"'+buffer_layer_name+'\" (geom) sql='
            
        buffer_result = processing.run("native:buffer", {'INPUT':site_geom.source(),
                'DISTANCE':buffer_size,'SEGMENTS':30,'END_CAP_STYLE':0,'JOIN_STYLE':0,
                'MITER_LIMIT':2,'DISSOLVE':False,
                'OUTPUT': output}, 
                feedback=MyFeedBack())
        
        #buffer_layer = buffer_result['OUTPUT']
        if type(buffer_result['OUTPUT']) == QgsVectorLayer:
            buffer_layer = buffer_result['OUTPUT']
        else:
            buffer_layer = QgsVectorLayer(buffer_result['OUTPUT'], site_geom.name(), "ogr")
        
        ADMSQpy_dir = os.path.split(ADMSQpy.__path__[0])[0]
        styles_dir = os.path.join(ADMSQpy_dir, 'templates', 'styles')
        
        #TODO: replace this crap
        style_path = os.path.join(styles_dir , str(buffer_size)+'m buffer')
        style_path += '.qml'

        if not os.path.exists(style_path):
            buffer_layer.setOpacity(0.5)
            
            renderer = buffer_layer.renderer().clone()
             
            if buffer_size == 500:
                renderer.symbol().setColor(QColor('green'))
            elif buffer_size == 1000:
                renderer.symbol().setColor(QColor('grey'))
            
            buffer_layer.setRenderer(renderer)
        else:
            buffer_layer.loadNamedStyle(style_path)
        
        return buffer_layer
        
    def add_construction_buffers(self):
        pass
        
    def init_modelled_roads(self, modelled_roads_layer_name = None, 
                            gpkg_write_path='modelled_roads.gpkg',
                            traffic_count_point_id_col_name = 'TCP ID', 
                            width_col_name = 'Width', speed_col_name = 'Speed', 
                            overwrite_gpkg_layer=False):
        
        self.modelled_roads_layer_name = modelled_roads_layer_name
        proj = self
        
        if 'gpkg_path' in dir(self) and gpkg_write_path == 'modelled_roads.gpkg':
            print('Saving to: ' + self.gpkg_path)
            gpkg_write_path = self.gpkg_path
            
        modelled_roads = ModelledRoads(proj, modelled_roads_layer_name,
                                       gpkg_write_path, traffic_count_point_id_col_name, 
                                       width_col_name, speed_col_name, overwrite_gpkg_layer)
        
        
        return modelled_roads
    
    def clip_layer_around_site(self, clip_layer, clip_layer_source,
                               gpkg_write_path, clip_bounding_box = None,
                               clip_distance = 10000):
        if 'site_geometry' not in dir(self):
            raise Exception('site_geometry not set. Set with set_site_geom function')
    
        site_geometry = self.site_geometry
       
        if clip_bounding_box is None:
            clip_bounding_box = _get_site_clip_bounding_box(site_geometry, clip_distance)
        
        x_min_clip, x_max_clip, y_min_clip, y_max_clip = clip_bounding_box
        
        #temporarily copy the layer
        # TODO: neaten this up (look at save_raster, save to geopackage etc)
        layer_name = clip_layer.name()
            
        try:
            result = processing.run("native:extractbyextent", {
                'INPUT':clip_layer_source,
                'EXTENT':str(x_min_clip)+','+str(x_max_clip)+ ','+ str(y_min_clip)+','+str(y_max_clip),
                'CLIP':False,
                'OUTPUT':'ogr:dbname=\"'+gpkg_write_path+'\" table=\"'+layer_name+'\" (geom) sql='},
                feedback=MyFeedBack())
            
            clipped_layer = QgsVectorLayer(result['OUTPUT'], layer_name+" clipped", "ogr")
            
            return clipped_layer
            
        except Exception as e:
            print('Clipping failed for layer with message:')
            print(e)
            
            return False
    
    def add_monitoring_sites(self, monitoring_shp_files):
        # TODO: rethink this
        
        if 'gpkg_path' not in dir(self):
            raise Exception('Please set geopackage path with set_gpkg_path function')
        else:
            gpkg_path = self.gpkg_path
        
        # TODO: create a monitoing layer class
        proj = self.get_project()
        #TODO
# =============================================================================
#         for csv_file in monitoring_csv_files:
#             # additional string to append to run comand
#             csv_str_extra = "?encoding=%s&delimiter=%s&xField=%s&yField=%s&crs=%s" % ("UTF-8",",", csv_file[1], csv_file[2],"epsg:27700")
#      
#             csv_path = csv_file[0]+csv_str_extra
#             monitoring_layer_name = os.path.basename(csv_path).split(".")[0]
#             # add layer save to geopackage
#             monitoring_site_layer = QgsVectorLayer(csv_path, 'Newham monitoring 2020', "delimitedText")
#             
#             monitoring_site_layer_formatted = _format_monitoring_sites(monitoring_site_layer, rules)
#             
#             # TODO: functionise
#             root = proj.layerTreeRoot()
#             group = root.findGroup("Monitoring")
#             monitoring_gpkg_layer = save_to_gpkg(monitoring_site_layer_formatted, gpkg_path)
#             group.addLayer(monitoring_site_layer_formatted)
# =============================================================================
            
        for shp_file in monitoring_shp_files:
            monitoring_layer_name =os.path.basename(shp_file).split(".")[0]
            monitoring_site_layer = QgsVectorLayer(shp_file, monitoring_layer_name, "ogr")
            monitoring_site_layer_formatted = _format_monitoring_sites(monitoring_site_layer, rules)
        
            root = proj.layerTreeRoot()
            group = root.findGroup("Monitoring")
            monitoring_gpkg_layer = save_to_gpkg(monitoring_site_layer_formatted, gpkg_path)
            proj.addMapLayer(monitoring_gpkg_layer, False)
            group.addLayer(monitoring_gpkg_layer)
        
        self.save()
        
        return 
    
    def generate_ASP(self, asp_layer_name, output_file_path, id_attr_name = 'ID',
                     min_height_attr_name = 'Height', max_height_attr_name=None,
                     separation_distance_attr_name=None):
        
        project = self.get_project()
        asp_layer = select_layer_by_name(asp_layer_name, project)
        
        asp_layer_fields = [field.name() for field in asp_layer.fields()]
        
        # test if atrributes are defined correctly
        attr_names = [id_attr_name, min_height_attr_name]
        if max_height_attr_name is not None:
            attr_names.append(max_height_attr_name)
        
        if separation_distance_attr_name is not None:
            attr_names.append(separation_distance_attr_name)
        
        for attr_name in attr_names:
            if attr_name not in asp_layer_fields:
                raise Exception(f"{attr_name} not an attribute of {asp_layer}")

        asp_values = []
        for asp_feature in asp_layer.getFeatures():
            asp_feature_id = asp_feature[id_attr_name]
            asp_feature_min_height = asp_feature[min_height_attr_name]
            
            # define the separation distance 
            if separation_distance_attr_name is not None:
                asp_feature_sep_dist = asp_feature[separation_distance_attr_name]
                if asp_feature_sep_dist != 0:
                    multiple_heights = True
                else:
                    multiple_heights = False
            else:
                asp_feature_sep_dist = 1
                multiple_heights = False
            
            
            # define max height of receptor
            if max_height_attr_name is not None:
                asp_feature_max_height = asp_feature[max_height_attr_name]
            else:
                asp_feature_max_height = asp_feature_min_height+asp_feature_sep_dist
            
            # extract x and y coordinates
            X = asp_feature.geometry().asPoint().x()
            Y = asp_feature.geometry().asPoint().y()
            asp_xy = pd.DataFrame({'X':X, 'Y':Y}, index=[asp_feature_id])
            asp_xy.rename_axis('ID', inplace=True)
            
            if multiple_heights:
                height_range = np.arange(asp_feature_min_height, asp_feature_max_height, asp_feature_sep_dist)
            else:
                height_range = [asp_feature_min_height]
            
            asp_z = pd.DataFrame(product([asp_feature_id], height_range),
                                          columns=['ID', 'Z']).set_index('ID')
            
            asp_xyz = asp_xy.join(asp_z).reset_index()
            
            if multiple_heights:
                asp_xyz['ID'] = asp_xyz['ID'].astype(str) + '(' + asp_xyz['Z'].astype(str) + ')'
            
            asp_values.extend(asp_xyz.values)
            
        asp_df = pd.DataFrame(asp_values, columns = ['ID', 'X', 'Y', 'Z'])
        
        asp_df.to_csv(output_file_path, index=False, header=False)
        
        return asp_df
    
    def save(self):
        proj = self.get_project()
        proj.write()
        return
    
    def add_layer(self, layer):
        proj = self.get_project()
        
        proj.addMapLayer(layer)
        return
    
    def remove_layer(self, layer):
        proj = self.get_project()
        
        proj.removeMapLayer(layer)
        return
    
def _get_site_clip_bounding_box(site_geom, clip_distance):
    # get every feature of site_location (can be multiple shapes
    site_features = site_geom.getFeatures()
    # get the area to clip for
    feature_bounding_boxes = []
    for feature in site_features:
        x_min_feature = feature.geometry().boundingBox().xMinimum()-clip_distance
        x_max_feature = feature.geometry().boundingBox().xMaximum()+clip_distance
        y_min_feature = feature.geometry().boundingBox().yMinimum()-clip_distance
        y_max_feature = feature.geometry().boundingBox().yMaximum()+clip_distance
        feature_bounding_boxes.append([x_min_feature, x_max_feature, y_min_feature, y_max_feature])

    feature_bounding_boxes.append([x_min_feature, x_max_feature, y_min_feature, y_max_feature])
    feature_bounding_boxes = np.array(feature_bounding_boxes)

    x_min_clip = np.max(feature_bounding_boxes[:, 0])
    x_max_clip = np.max(feature_bounding_boxes[:, 1])
    y_min_clip = np.max(feature_bounding_boxes[:, 2])
    y_max_clip = np.max(feature_bounding_boxes[:, 3])
    
    return [x_min_clip, x_max_clip, y_min_clip, y_max_clip]

def _load_style_from_file(layer, layer_style_path):
    # load layer style and remove temporary file
    if os.path.exists(layer_style_path):
        _ = layer.loadNamedStyle(layer_style_path)
    return

def _remove_temp_style_file(layer_style_path):
    if os.path.exists(layer_style_path):
        os.remove(layer_style_path)
    return

def _average_isotropic_z0(roughness_length_output_dir):
    z0_out_file = os.path.join(roughness_length_output_dir, 'roughness_length_results.csv')
    
    isotropic_output_files = [file for file in os.listdir(roughness_length_output_dir) if '_isotropic' in file]
    
    method_names = []
    method_z0s = []
    
    for isotropic_output_file in isotropic_output_files:  
        isotropic_output = pd.read_csv(os.path.join(roughness_length_output_dir, isotropic_output_file), sep=' ')
        
        method_z0 = isotropic_output.loc[0, 'z0']
        
        method_name = isotropic_output_file.replace('_IMPPoint_isotropic.txt', '')
        method_names.append(method_name)
        method_z0s.append(method_z0)
    
    mean_z0 = np.mean(method_z0s)
    median_z0 = np.median(method_z0s)
    
    _ = [method_names.append(i) for i in ['Mean', 'Median']]
    _ = [method_z0s.append(i) for i in [mean_z0, median_z0]]
    
    z0_df = pd.DataFrame({'Method' : method_names, 'Roughness length' : method_z0s})
    
    z0_df.to_csv(z0_out_file)
    
    print(f'Results saved to {z0_out_file}')
    return

    
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