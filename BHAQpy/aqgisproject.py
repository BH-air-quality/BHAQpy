# -*- coding: utf-8 -*-
"""
Created on Thu Mar 31 09:46:07 2022

@author: kbenjamin
"""

import os
import numpy as np
import pandas as pd
from itertools import product

from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsVectorLayer,
    QgsMapLayerType,
    QgsRasterLayer,
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

import BHAQpy

from BHAQpy.modelledroads import ModelledRoads

from BHAQpy._utils import (select_layer_by_name,
                           save_to_gpkg,
                           save_raster)

from BHAQpy._MyFeedback import MyFeedBack
from BHAQpy.getdefrabackground import get_defra_background_concentrations

class AQgisProjectBasemap():
    """
    QGIS basemap object with all required basemap layers
    
    Attributes
    ----------
    project_path : str
        The path to the project file
    
    run_environment : str
        Either standalone or qgis_app. Standalone if running from a python script, 
        qgis_app if running from qgis interface. Currently only standalone is supported.
    
    qgs_app : 
        The details of the QGIS process that is running
    
    project_name : str
        The name of the project
    
    Methods
    -------
    
    get_project()
        returns the qgis project (see https://qgis.org/pyqgis/3.0/core/Project/QgsProject.html)
        
    initialise_project(project_name, project_path, site_geom_source, clip_distance = 10000)
        create a new qgis project with clipped layers around a project site, saved to a single geopackage
    
    """

    def __init__(self, project_path, run_environment = "standalone"):
        """
        

        Parameters
        ----------
        project_path : str
            The path to a qgis project.
        run_environment : TYPE, optional
            Either standalone or qgis_app. Standalone if running from a python script, 
            qgis_app if running from qgis interface. Currently only standalone is supported.

        Returns
        -------
        None.

        """
       
        self.project_path = project_path
        
        valid_run_envs = ['qgis_gui', 'standalone']
        assert run_environment in valid_run_envs, f"run_environment must be one of: {', '.join(valid_run_envs)}"
        
        if run_environment == 'qgis_gui':
            raise Exception("Using a qgis_gui run environment is currently not supported")
        
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
        """
        

        Returns
        -------
        qgis.core.QgsProject
            The qgis project (see https://qgis.org/pyqgis/3.0/core/Project/QgsProject.html).
            From here the PyQGIS api can be used to edit and test the qgis project.

        """
        return self._project
        
    def initialise_project(self, project_name, project_path, site_geom_source,
                           clip_distance = 10000):
        """
        

        Parameters
        ----------
        project_name : str
            Name of the project to be initialised.
        project_path : str
            The full project path for the project to be saved to.
        site_geom_source : str
            A path to a shapefile or layer name within the basemap project containing the site geometry.
        clip_distance : int, optional
            How far around the site to clip base layers. The default is 10000.

        Returns
        -------
        new_ADMSQ_project : AQgisProject
            A QGIS project with all clipped base layers and site geometry.

        """
        
        
        # set up paths
        # TODO: make paths absolute?
        project_qgs_path = os.path.join(project_path, project_name+'.qgz')
        gpkg_path = os.path.join(project_path, project_name+'.gpkg')
        
        if os.path.exists(project_qgs_path):
            raise Exception(f"Project {project_qgs_path} already exists.")
        
        if not os.path.exists(site_geom_source):
            raise Exception(f"Site geom source {site_geom_source} does not exist.")
        
        base_project = self.get_project()
        
        # the initial layer sources (these get re assigned ugh)
        layer_sources = {layer.name() : layer.source() for layer in base_project.mapLayers().values()}
        # save to new project and initiate project object
        new_project = base_project.write(project_qgs_path)
    
        new_ADMSQ_project = AQgisProject(project_qgs_path, run_environment=self.run_environment)
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
class AQgisProject(AQgisProjectBasemap): 
    
    """
    Core class for an air quality QGIS project. Controls any functionality relating to a full project.
    
    Attributes
    ----------
    project_path : str
        The path to the project file
    
    run_environment : str
        Either standalone or qgis_app. Standalone if running from a python script, 
        qgis_app if running from qgis interface.
    
    qgs_app : 
        The details of the QGIS process that is running
    
    project_name : str
        The name of the project
    
    gpkg_path : str
        The path to the geopackage containing project layers
    
    modelled_roads_layer_name : str
        The name of the layer within the project that represents the modelled roads to be imported into ADMS.
    
    Methods
    -------
    set_gpkg_path()
        set the gpkg_path associated with the project, containing all project layers
    
    set_site_geom()
        set the site geometry layer or file containing geometry for project
    
    get_site_background_concs()
        get the defra modelled background concentration at the set_geom
    
    get_site_buffer()
        create a buffer layer around site geom. TODO.
    
    add_construction_buffers()
        TODO
    
    init_modelled_roads()
        initialise a ModelledRoads object for the project. This is the QGIS version of roads to be imported into ADMS. 
    
    clip_layer_around_site()
        clip a specified layer around site_geom
    
    add_monitoring_sites()
        add monioting sites to project. TODO.
    
    save()
        write QGIS project
        
    add_layer()
        add a layer to the QGIS project
        
    remove_layer()
        remove a layer from the QGIS project

    """
    
    def __init__(self, project_path, run_environment = "qgis_gui"):
        """
        

        Parameters
        ----------
        project_path : str
            Full project path to the QGIS project file.
        run_environment : str, optional
            Either standalone or qgis_app. Standalone if running from a python script, 
            qgis_app if running from qgis interface. The default is "qgis_gui". The default is "qgis_gui".

        Returns
        -------
        None.

        """
        super().__init__(project_path, run_environment)
    
    def set_gpkg_path(self, project_gpkg_path):
        """
        

        Parameters
        ----------
        project_gpkg_path : str
            
        Set the path to the geopackage file associated with the project.

        Returns
        -------
        None.

        """
        self.gpkg_path = project_gpkg_path
        return
    
    def set_site_geom(self, site_geom_source):
        """
        

        Parameters
        ----------
        site_geom_source : str
            A path to a shapefile or layer name within the basemap project containing the geometry of a project site.
            e.g. BuroHappold/Environment - 07 Air Quality/1. Projects/22/PROJECT NAME/4. GIS/Red Line Boundary.shp

        Returns
        -------
        site_geometry : QgsVectorLayer
            Vector layer containing the site geometry.

        """
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
        """
        Get defra background concentrations at the project site from https://uk-air.defra.gov.uk/data/laqm-background-maps?year=2018

        Parameters
        ----------
        background_region : str
            Background region as defined in defra background maps. 
            Options: Greater_London, East_of_England, Midlands, Northern_England,
            Northern_Ireland, Scotland, Southern_England, Wales.
        year : int
            The background year to get.
        pollutants : list, optional
            Pollutants to get background concentrations for. The default is ['no2', 'nox', 'pm10', 'pm25'].
        base_year : int, optional
            Base year of modelled background concentrations. The default is '2018'.
        split_by_source : Bool, optional
            Whether to split contributions of background concentrations into sources. The default is False.

        Returns
        -------
        site_background_concs : pandas.DataFrame
            Pandas dataframe with background concentrations for grid square(s) site falls within

        """
        
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
        """
        TODO

        Parameters
        ----------
        buffer_size : TYPE
            DESCRIPTION.
        group : TYPE, optional
            DESCRIPTION. The default is "Construction".

        Raises
        ------
        Exception
            DESCRIPTION.

        Returns
        -------
        buffer_layer : TYPE
            DESCRIPTION.

        """
        
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
        
        BHAQpy_dir = os.path.split(BHAQpy.__path__[0])[0]
        styles_dir = os.path.join(BHAQpy_dir, 'templates', 'styles')
        
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
        """
        Initialise a modelled roads object in this project

        Parameters
        ----------
        modelled_roads_layer_name : str, optional
            The layer name of the existing modelled roads file. If None then a new layer is created. The default is None.
        gpkg_write_path : str, optional
            Path to geopackage at which modelled roads layer is saved. The default is self.geopackage_write_path, else 'modelled_roads.gpkg'.
        traffic_count_point_id_col_name : str, optional
            The attribute name representing the traffic count point ID. The default is 'TCP ID'.
        width_col_name : str, optional
            The attribute name representing the road width in m. The default is 'Width'.
        speed_col_name : str, optional
            The attribute name representing the traffic speed in kph. The default is 'Speed'.
        overwrite_gpkg_layer : bool, optional
            If geopackage layer exists already, should this be overwritten. The default is False.

        Returns
        -------
        modelled_roads : BHAQpy.ModelledRoads
            A ModelledRoads object. A number of functions can be carried out on.

        """
        
        
        self.modelled_roads_layer_name = modelled_roads_layer_name
        proj = self
        
        if 'gpkg_path' in dir(self) and gpkg_write_path == 'modelled_roads.gpkg':
            print('Saving to: ' + self.gpkg_path)
            gpkg_write_path = self.gpkg_path
            
        modelled_roads = ModelledRoads(proj, modelled_roads_layer_name,
                                       gpkg_write_path, 
                                       traffic_count_point_id_col_name = traffic_count_point_id_col_name, 
                                       width_col_name = width_col_name, 
                                       speed_col_name = speed_col_name, 
                                       overwrite_gpkg_layer = overwrite_gpkg_layer)
        
        
        return modelled_roads
    
    def clip_layer_around_site(self, clip_layer, clip_layer_source,
                               gpkg_write_path, clip_bounding_box = None,
                               clip_distance = 10000):
        """
        clip a layer around site geometry for a specified distance

        Parameters
        ----------
        clip_layer : str
            Name of the layer within the project to clip.
        clip_layer_source : str
            Path to the file containing the layer to be clipped.
        gpkg_write_path : str
            The path to write the clipped laeyr to.
        clip_bounding_box : list, optional
            Specified x_min, x_max, y_min and y_max coordinates to clip to. If None then a bounding box is created using clip_distance. The default is None.
        clip_distance : int, optional
            The distance from the site geomoetery to clip layer to in metres. The default is 10000.

        Raises
        ------
        Exception
            DESCRIPTION.

        Returns
        -------
        TYPE
            DESCRIPTION.

        """
        
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
        """
        TODO

        Parameters
        ----------
        monitoring_shp_files : TYPE
            DESCRIPTION.

        Raises
        ------
        Exception
            DESCRIPTION.

        Returns
        -------
        None.

        """
        
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
            #monitoring_site_layer_formatted = _format_monitoring_sites(monitoring_site_layer, rules)
            monitoring_site_layer_formatted = monitoring_site_layer
            
            root = proj.layerTreeRoot()
            group = root.findGroup("Monitoring")
            monitoring_gpkg_layer = save_to_gpkg(monitoring_site_layer_formatted, gpkg_path)
            proj.addMapLayer(monitoring_gpkg_layer, False)
            group.addLayer(monitoring_gpkg_layer)
        
        self.save()
        
        return
    
    def save(self):
        """
        write changes to a project

        Returns
        -------
        None.

        """
        
        proj = self.get_project()
        proj.write()
        return
    
    def add_layer(self, layer):
        """
        Add a QGIS layer to a project

        Parameters
        ----------
        layer : qgis.core.QgsVectorLayer
            The pyqgis layer to add to a project.

        Returns
        -------
        None.

        """
        
        proj = self.get_project()
        
        proj.addMapLayer(layer)
        return
    
    def remove_layer(self, layer):
        """
        Remove a QGIS layer from a project

        Parameters
        ----------
        layer : qgis.core.QgsVectorLayer
            The pyqgis layer to remove from a project.

        Returns
        -------
        None.

        """
        
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