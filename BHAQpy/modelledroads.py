# -*- coding: utf-8 -*-
"""
Created on Wed Mar 30 11:10:56 2022

@author: kbenjamin
"""
#%%
import pandas as pd
import numpy as np
import xlwings as xw
import os 
import warnings

from qgis.core import (
    QgsCoordinateTransformContext,
    QgsCoordinateReferenceSystem,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsWkbTypes,
    NULL,
    edit
)


from qgis.PyQt.QtCore import QVariant

from qgis.analysis import QgsNativeAlgorithms
import processing
from processing.core.Processing import Processing

from BHAQpy._utils import (select_layer_by_name,
                   attributes_table_df,
                   write_ADMS_input_file)

from BHAQpy.trafficcountpoints import TrafficCountPoints

class ModelledRoads():  
    

    """
    A BHAQpy object representing the roads data in QGIS that should be manipulated and imported into an ADMS model
    
    Attributes
    ----------
    project : BHAQpy.AQgisProject
        The AQgisProject in which the modelled roads correspond to
    
    save_path : str
        Where the modelled roads layer is written to.
    
    layer : QGSVectorLayer 
        The pyqgis layer for the modelled roads object
    
    
    Methods
    -------
    
    get_attributes_df()
        get a pandas datarame of road attributes
    
    match_to_TCP()
        Match road geomtry to traffic count point information.
    
    generate_SPT()
        create an ADMS spt file for the drawn roads
        
    generate_VGT()
        create a vgt file for the drawn roads
        
    generate_EFT_input()
        generate a file that can be copied directly into EFT spreadsheet
    
    generate_EIT()
        create an eit file for the drawn roads
    
    calculate_gradients()
        calculate the gradient of the drawn roads. This can then be used in EFT calculations.
    
    """
    
    
    def __init__(self, project, source=None, save_path='modelled_roads.gpkg', 
                 save_layer_name = 'Modelled Roads ADMS',
                 traffic_count_point_id_col_name = 'TCP ID', 
                 width_col_name = 'Width', 
                 speed_col_name = 'Speed',
                 junction_col_name = 'Junction', 
                 road_height_col_name = 'Height',
                 canyon_height_col_name = 'Canyon height',
                 overwrite_gpkg_layer=False):
        """
        

        Parameters
        ----------
        project : BHAQpy.AQgisProject
            The AQgisProject in which the modelled roads are added to
        source : str, optional
            The layer within a project or the path to a file containing drawn modelled roads. If None then a new layer is created. The default is None.
        save_path : str, optional
            The path to the geopackage where the modelled roads layer will be written. The default is 'modelled_roads.gpkg'.
        save_layer_name : str, optional
            The name of the geopackage layer the modelled roads will be saved to. The default is 'Modelled Roads ADMS'.
        traffic_count_point_id_col_name : str, optional
            The attribute name representing the traffic count point ID. The default is 'TCP ID'.
        width_col_name : str, optional
            The attribute name representing the road width in m. The default is 'Width'.
        speed_col_name : str, optional
            The attribute name representing the traffic speed in kph. The default is 'Speed'.
        junction_col_name : str, optional
            The attribute name representing the boolean value determining if the link is a junction. The default is 'Junction'.
        road_height_col_name : str, optional
            The attribute name representing the road height in metres. The default is 'Height'.
        canyon_height_col_name : str, optional
            The attribute name representing the canyon height in metres. The default is 'Canyon height'.
        overwrite_gpkg_layer : bool, optional
            If geopackage layer exists already, should this be overwritten. The default is False.

        Returns
        -------
        None.

        """
        
        
        self.project = project
        self.save_path = save_path 
        
        #initialise processing
        if project.run_environment == 'standalone':
            Processing.initialize()
            project.qgs_app.processingRegistry().addProvider(QgsNativeAlgorithms())
            
        if source is not None and type(source) != str:
            raise Exception("Source must be a string of layer name or file path")
        
        if os.path.splitext(save_path)[1] != '.gpkg':
            raise Exception("save_path must have a .gpkg file extension")
            
        #copy road geometry with new attributes
        if source is not None:
            qgs_proj = project.get_project()
            input_modelled_road_layer = select_layer_by_name(source, qgs_proj)
        else:
            input_modelled_road_layer = None
            
        #standardise attributes
        modelled_road_layer = _init_modelled_roads_layer(input_modelled_road_layer, 
                                                        save_path,
                                                        save_layer_name,
                                                        traffic_count_point_id_col_name,
                                                        width_col_name, speed_col_name,
                                                        junction_col_name, road_height_col_name,
                                                        canyon_height_col_name,
                                                        overwrite_gpkg_layer)
        
        self.layer = modelled_road_layer
        self._attr_df = attributes_table_df(modelled_road_layer)
        return
        
    def get_attributes_df(self):
        """
        Get attributes of drawn roads as a dataframe

        Returns
        -------
        pandas.DataFrame
            A pandas dataframe with all attributes and values of modelled roads.

        """
        self._attr_df = attributes_table_df(self.layer)
        
        return self._attr_df
    
    def match_to_TCP(self, traffic_count_points : TrafficCountPoints):
        """
        Add traffic information to modelled roads by matching modelled roads to traffic count points.

        Parameters
        ----------
        traffic_count_points : TrafficCountPoints
            BHAQpy.TrafficCountPoints object with ID's that match the modelled roads TCP ID attribute.

        Returns
        -------
        roads_TCP : pandas.DataFrame
            Dataframe containing modelled roads attributes with traffic information.

        """
        
        #TODO: match by intersection
        #TODO: add to traffic count point attributes
            
        if type(traffic_count_points) != TrafficCountPoints:
            raise TypeError("traffic_count_points must be a TrafficCountPoints object")   
        
        TCP_df = traffic_count_points.get_attributes_df().set_index('TCP ID')
        roads_df = self.get_attributes_df().set_index('TCP ID')
        
        roads_TCP = roads_df.join(TCP_df)
        
        return roads_TCP
    
    def generate_SPT(self, output_file = None, headers_file = 'ADMS_template_v5.spt', 
                     traffic_flow_year = 2019, traffic_flow_road_type = 'London (Inner)',
                     traffic_flows_used="No"):
        
        """
        Format roads into SPT format and save to spt file if specified

        Parameters
        ----------
        output_file : str, optional
            Path to save spt file. If None then no file is saved. The default is None.
        headers_file : str, optional
            A path to a file containing ADMS headers for an spt file. These can be automatically generated within ADMS (see manual). The default is 'ADMS_template_v5.spt'.
        traffic_flow_year : int, optional
            The traffic flow year. Not strictly used in modelling (as we create an EIT) but is good for consistency. The default is 2019.
        traffic_flow_road_type : str, optional
            The traffic flow road type, as specified in ADMS documentation.
        traffic_flows_used : str, optional
            Yes or No - whether emissions factors should be defined by EFT at the top of the spt file
            
        Returns
        -------
        spt_data : pandas.DataFrame
            Dataframe of modelled roads formatted into a spt format.

        """
        #TODO: check road types comply
      
        attr_df = self.get_attributes_df()
        
        if not traffic_flows_used == "No" or traffic_flows_used=="Yes":
            raise AssertionError("traffic_flows_used must be either yes or no")
        
        spt_dict = {'Source name' : attr_df['Source ID'],
                    'Use VAR file' : 'No',
                    'Specific heat capacity (J/kg/K)' : 'na',
                    'Molecular mass (g)' : 'na',
                    'Temperature or density?' : 'na',
                    'Temperature (Degrees C) / Density (kg/m3)' : 'na',
                    'Actual or NTP?' : 'na',
                    'Efflux type keyword' : 'na',
                    'Velocity (m/s) / Volume flux (m3/s) / Momentum flux (m4/s2) / Mass flux (kg/s)' : 'na',
                    'Heat release rate (MW)' : 'na',
                    'Source type' : 'Road',
                    'Height (m)' : attr_df['Road height'],
                    'Diameter (m)' : 'na', 
                    'Line width (m) / Road width (m) / Volume depth (m) / Grid depth (m)' : attr_df['Width'],
                    'Canyon height (m)' : attr_df['Canyon height'],
                    'Angle 1 (deg)' : 'na',
                    'Angle 2 (deg)' : 'na',
                    'Mixing ratio (kg/kg)' : 'na',
                    'Traffic flows used': traffic_flows_used,
                    'Traffic flow year' : traffic_flow_year,
                    'Traffic flow road type' : traffic_flow_road_type,
                    'Gradient' : attr_df['Gradient %'],
                    'Main building' : 'na',
                    'Comments' : 'na'}
        
        spt_data = pd.DataFrame(spt_dict)
        
        if output_file is not None:
            write_ADMS_input_file(spt_data, output_file, headers_file)
        
        return spt_data
    
    def generate_VGT(self, output_file = None, headers_file = 'ADMS_template_v5.vgt',
                     simplify_verticies=True):
        """
        Format roads into SPT format and save to spt file if specified

        Parameters
        ----------
        output_file : str, optional
            Path to save vgt file. If None then no file is saved. The default is None.
        headers_file : str, optional
            A path to a file containing ADMS headers for a vgt file. These can be automatically generated within ADMS (see manual). The default is 'ADMS_template_v5.vgt'.

        Returns
        -------
        vgt_data : pandas.DataFrame
            Dataframe of drawn roads in a VGT format.

        """
        verticies = self._extract_verticies(simplify_verticies)
        
        #extract
        vgt_l = []
        for verticie in verticies.getFeatures():
            sourceID = verticie['Source ID']
            X = verticie.geometry().asPoint().x()
            Y = verticie.geometry().asPoint().y()
            vgt_l.append([sourceID, X, Y])
        
        vgt_data = pd.DataFrame(vgt_l, columns = ['Source name', 'X (m)', 'Y (m)'])
        
        if output_file is not None:
            write_ADMS_input_file(vgt_data, output_file, headers_file)
        
        return vgt_data
    
    def generate_EFT_input(self, traffic_count_points, road_type, output_file = None, 
                           no_of_hours = 24, flow_direction = None):
        """
        Format roads into a format that can be directly copied into EFT spreadsheet

        Parameters
        ----------
        traffic_count_points : TrafficCountPoints
            BHAQpy.TrafficCountPoints object with ID's that match the modelled roads TCP ID attribute.
        road_type : str
                The traffic flow road type, as specified in EFT documentation. Options are Urban (Not London), Rural (Not London), Motorway (Not London), London - Central, London - Inner, London - Outer, London - Motorway
        output_file : str, optional
            Path to save csv file that could be copied directly into EFT. The default is None.
        no_of_hours : int, optional
            Operational hours of traffc. See EFT documentation. The default is 24.
        flow_direction : TYPE, optional
            Placeholder for now. The default is None.

        Returns
        -------
        EFT_input_df : pandas.DataFrame
            Dataframe of roads data formatted such that it can be directly imported into EFT.

        """
        
        # TODO: allow user to specify different road_types by matching series index to source ID
        # TODO: allow flow direction input
    
        #check road type is valid        
        road_type_options = ['Urban (Not London)', 'Rural (Not London)',
                             'Motorway (Not London)', 'London - Central',
                             'London - Inner', 'London - Outer', 'London - Motorway']
        
        if road_type not in road_type_options:
            raise Exception(f"road_type must be one of {', '.join(road_type_options)}")
        
        #match roads to traffic count points
        roads_TCP = self.match_to_TCP(traffic_count_points)
        
        EFT_cols = {'Source ID' : 'SourceID', 'Road Type' : 'Road Type', 
                    'Total AADT' : 'Traffic Flow', 'HDV %' : '% HDV', 
                    'Speed' : 'Speed(kph)',
                    'No of Hours' : 'No of Hours', 'Link Length (km)': 'Link Length (km)', 
                    'Gradient %' : '% Gradient', 'Flow Direction' : 'Flow Direction',
                    '% Load' : '% Load'}
        
        roads_TCP['Road Type'] = road_type
        roads_TCP['No of Hours'] = no_of_hours
        roads_TCP['Link Length (km)'] = None
        roads_TCP['% Load'] = None
        roads_TCP['Flow Direction'] = None
        
        roads_TCP = roads_TCP.rename(columns = EFT_cols)
            
        EFT_input_df = roads_TCP[list(EFT_cols.values())]
        
        if output_file is not None:
            EFT_input_df.to_csv(output_file, index = False)
            
        return EFT_input_df
    
    def generate_EIT(self, traffic_count_points, eft_file_path, road_type, area, 
                     year, eit_output_path = None, headers_file = 'ADMS_template_v5.eit',
                     eft_output_path = None, traffic_format = 'Basic Split', 
                     pollutants = ['NOx', 'PM10', 'PM2.5'], eft_version = "11.0"):
        """
        Format drawn roads into EFT format. Run the EFT and save as an EIT.

        Parameters
        ----------
        traffic_count_points : TrafficCountPoints
            BHAQpy.TrafficCountPoints object with ID's that match the modelled roads TCP ID attribute.
        eft_file_path : str
            Path to an EFT spreadsheet. Download from https://laqm.defra.gov.uk/air-quality/air-quality-assessment/emissions-factors-toolkit/
        road_type : str
                The traffic flow road type, as specified in EFT documentation. Options are Urban (Not London), Rural (Not London), Motorway (Not London), London - Central, London - Inner, London - Outer, London - Motorway
        area : str
            Road area, as specified in EFT documentation. Options are England (Not London), London, Northern Ireland, Scotland and Wales.
        year : int
            Year to run EFT for.
        eit_output_path : str, optional
            Path to save eit file to. The default is None.
        headers_file : str, optional
            A path to a file containing ADMS headers for a eit file. These can be automatically generated within ADMS (see manual). The default is 'ADMS_template_v5.eit'.
        eft_output_path : str, optional
            Path of where to save our EFT spreadsheet once it has run. The default is None.
        traffic_format : str, optional
            Which traffic format to run in EFT. Options are Basic Split, Detailed Option 1, Detailed Option 2, Detailed Option 3 and Alternative Technologies. The default is 'Basic Split'.
        pollutants : list, optional
            Which polluants to run EFT for. The default is ['NOx', 'PM10', 'PM2.5'].
        eft_version : str, optional
            eft version that is being run. The default is "11.0".

        Returns
        -------
        eft_data : pandas.DataFrame
            The drawn roads formatted into eit format.

        """
        
        # TODO: add eft results to attributes
        
        #get_eft_data
        eft_input = self.generate_EFT_input(traffic_count_points, road_type)
        
        #calculate eft
        eft_data = run_eft(eft_input.values, eft_file_path, road_type, area, year, 
                         eft_output_path, traffic_format, pollutants, eft_version)
        
        if eit_output_path is not None:
            write_ADMS_input_file(eft_data, eit_output_path, headers_file)
        
        return eft_data
            
    def calculate_gradients(self, DTM_layers, simplify_verticies=True):
        """
        Calulate road gradient of drawn roads, based on defra digital terrain models (DTM)

        Parameters
        ----------
        DTM_layers : str
            Layer name of the digital terrain model to calculate gradients from.

        Returns
        -------
        ModelledRoads
            ModelledRoads object with gradients added into attributes.

        """
        
        if not type(DTM_layers) == list:
            raise Exception("DTM layer must be a list of layer names")
        
        if len(DTM_layers) > 1:
            #TODO merge dtms
            pass
        else:
            qsg_proj = self.project.get_project()
            DTM_layer = select_layer_by_name(DTM_layers[0], qsg_proj)
        
        road_verticies = self._extract_verticies(simplify_verticies)
        
        # get a pd series with gradient for each road link
        road_gradients = _calculate_gradient_by_road(road_verticies, DTM_layer)

        #update layer attrs with gradient+
        modelled_roads_layer = self.layer
        modelled_roads_fields = [f.name() for f in modelled_roads_layer.fields()]
        grad_idx = np.where(np.array(modelled_roads_fields) == 'Gradient %')[0][0]

        with edit(modelled_roads_layer):
            for feature in modelled_roads_layer.getFeatures():
                road_id = feature["Source ID"]
                road_gradient = float(road_gradients[road_id])
                modelled_roads_layer.changeAttributeValue(feature.id(), grad_idx, road_gradient)
                    
        self.layer = modelled_roads_layer
        self._attr_df = attributes_table_df(modelled_roads_layer)
        return self
    
        
    def _extract_verticies(self, simplify_verticies):
        # run simplify
        if simplify_verticies:
            simplified = processing.run("native:simplifygeometries", {'INPUT':self.layer.source(),
                                        'METHOD':0,'TOLERANCE':1.1,'OUTPUT':'TEMPORARY_OUTPUT'})
            # run extract road verticies and save to temporary file
            verticies = processing.run("native:extractvertices", {'INPUT':simplified['OUTPUT'],
                                        'OUTPUT': 'TEMPORARY_OUTPUT'})
        else:
            verticies = processing.run("native:extractvertices", {'INPUT':self.layer.source(),
                                        'OUTPUT': 'TEMPORARY_OUTPUT'})
        
        return verticies['OUTPUT']

# further utility functions
def _calc_gradient_percentage(distances, heightsAOD):

    # calculate a gradient as percentage using dtm height
    distances = [i.value() if type(i) == QVariant else float(i) for i in distances]
    heightsAOD = [i.value() if type(i) == QVariant else float(i) for i in heightsAOD]
    
    heightsAOD_2 = []
    for i in heightsAOD:
        if type(i) == QVariant:
            #print(type(i.value()))
            heightsAOD_2.append(NULL)
        else:
            heightsAOD_2.append(float(i))
    
    distances_2 = []
    for i in distances:
        if type(i) == QVariant:
            #print(type(i.value()))
            distances_2.append(NULL)
        else:
            distances_2.append(float(i))
    
    rises = abs(np.diff(heightsAOD_2))
    runs = abs(np.diff(distances_2))
    percentages = pd.DataFrame({'rise' : rises, 'run' : runs})
    percentages['percentage'] = (percentages['rise']/percentages['run'])*100
    
    avg_percentage = np.mean(percentages['percentage']) 
    
    # max eft/ adms gradient is 30%
    if avg_percentage > 30:
        avg_percentage = 30
        
    return avg_percentage

def _init_modelled_roads_layer(input_modelled_road_layer, save_path, save_layer_name,
                traffic_count_point_id_col_name, width_col_name, 
                speed_col_name, junction_col_name, road_height_col_name, 
                canyon_height_col_name, overwrite_gpkg_layer=False):
    '''
    Create a new layer with the geometry of the input layer but with attributes 
    formatted for consistency.
    '''
    
    fields = [QgsField("Source ID", QVariant.String, "text", 100),
                QgsField("TCP ID", QVariant.String, "text", 100),
                QgsField("Junction", QVariant.Bool, "bool", 5),
                QgsField("Width", QVariant.Double, "double", 7),
                QgsField("Speed", QVariant.Double, "double", 7),
                QgsField("Gradient %", QVariant.Double, "double", 7),
                QgsField("Road height", QVariant.Double, "double", 7),
                QgsField("Canyon height", QVariant.Double, "double", 7)]
    
    geom = QgsWkbTypes.MultiLineString
    if input_modelled_road_layer is None:
        crs = QgsCoordinateReferenceSystem('epsg:27700')
    else:
        crs = input_modelled_road_layer.crs()
    
    schema = QgsFields()
    for field in fields:
        schema.append(field)
    
    if os.path.exists(save_path):
        append = True
    else:
        append = False
        
    _create_blank_gpkg_layer(save_path, save_layer_name, geom, crs, schema, append, overwrite_gpkg_layer)
    
    modelled_road_layer = QgsVectorLayer(f'{save_path}|layername={save_layer_name}', 
                                         'modelled roads output', 'ogr')

    if input_modelled_road_layer is not None:
        modelled_road_layer = _copy_input_layer_geometry(modelled_road_layer, 
                                                         input_modelled_road_layer, 
                                                         traffic_count_point_id_col_name, width_col_name, 
                                                         speed_col_name, junction_col_name, road_height_col_name,
                                                         canyon_height_col_name)
    
    return modelled_road_layer

def _copy_input_layer_geometry(modelled_road_layer, input_modelled_road_layer, 
                               traffic_count_point_id_col_name, width_col_name, 
                               speed_col_name, junction_col_name, road_height_col_name,
                               canyon_height_col_name):
    
    original_layer_fields = [field.name() for field in input_modelled_road_layer.fields()]
    
    if traffic_count_point_id_col_name not in original_layer_fields:
        raise Exception((f"traffic_count_point_id_col_name: {traffic_count_point_id_col_name}"
                        " not found in specified layer"))
    
    default_values = {width_col_name : 0, speed_col_name : 0, junction_col_name : False, 
                      road_height_col_name : 0, canyon_height_col_name : 0}
    
    #run simplify at this stage
    modelled_road_layer_simplified = processing.run("native:simplifygeometries", {'INPUT':input_modelled_road_layer.source(),
                                                                                  'METHOD':0,'TOLERANCE':1.1,'OUTPUT':'TEMPORARY_OUTPUT'})
    
    modelled_road_layer_simplified = modelled_road_layer_simplified['OUTPUT']
    with edit(modelled_road_layer):
        
        dp = modelled_road_layer.dataProvider()
        
        tcp_register = []
        #look through each feature - copy the geometry but change the attributes
        for original_feature in modelled_road_layer_simplified.getFeatures():
            # check feeture length - dont add if less than 1 m
            road_length = original_feature.geometry().length()
            if road_length > 1:
            
                original_tcp_id = original_feature[traffic_count_point_id_col_name]
                
                original_values = []
                for col_name in list(default_values.keys()):
                    if col_name in original_layer_fields and original_feature[col_name] != NULL:
                        original_value = original_feature[col_name]
                    else:
                        original_value = default_values[col_name]
                    
                    original_values.append(original_value)
                
                original_width, original_speed, original_junction, original_height, original_canyon_height = original_values
                
                #skip if no id
                if  original_tcp_id == NULL or original_tcp_id == '':
                    continue
                
                # initiate feture
                new_feature = QgsFeature()
                # copy geom
                if original_feature.geometry().isNull() or original_feature.geometry().isEmpty():
                    continue
                
                new_feature.setGeometry(original_feature.geometry())
                
                # get source id
                if original_junction == True:
                    junction_str = '.J'
                else:
                    junction_str = ''
                
                tcp_id = str(original_tcp_id)+junction_str
                number = len([i for i in tcp_register if i == tcp_id]) + 1
                source_id = str(tcp_id) + '.' + str(number)  
                # tracker
                tcp_register.append(tcp_id) 
                
                #create feature
                new_feature.setAttributes([None, source_id, str(original_tcp_id), 
                                           original_junction,
                                           original_width, original_speed,
                                           0, original_height, original_canyon_height])
                #add feature   
                dp.addFeatures([new_feature])
    
    return modelled_road_layer
    
def _calculate_gradient_by_road(road_verticies, DTM_layer):
    '''
    calculate the gradient for each road, using the etracted verticies layer as
    an input 

    Parameters
    ----------
    road_verticies : TYPE
        DESCRIPTION.

    Returns
    -------
    None.

    '''
    
    # get dtm height at each point
    vertices_DTM = processing.run("native:rastersampling", {'INPUT':road_verticies,
                        'RASTERCOPY':DTM_layer.source(),'COLUMN_PREFIX':'DTM_height_',
                        'OUTPUT':'TEMPORARY_OUTPUT'})
    
    vertice_data = attributes_table_df(vertices_DTM['OUTPUT'])
    
    # add nan values for missing data
    vertice_data["distance"] = [np.nan if type(i) == QVariant else i for i in vertice_data["distance"]]
    vertice_data['DTM_height_1'] = [np.nan if type(i) == QVariant else i for i in vertice_data['DTM_height_1']]
    
    # calculate gradient for each road
    road_gradients = vertice_data.groupby("Source ID").apply(lambda x: _calc_gradient_percentage(x.distance, x['DTM_height_1']))
    # replace nulls wth zero 
    road_gradients = road_gradients.fillna(0)
    
    # replace values > 30 (max eft can handle)
    road_gradients[road_gradients > 30] = 30
    
    return road_gradients

def _create_blank_gpkg_layer(gpkg_path: str, layer_name: str, geometry: int,
                            crs: str, schema: QgsFields, append: bool = False,
                            overwrite_layer: bool = False) -> bool:
    #TODO: think of implications of this. make sure we dont overwrite something we really shouldn't
    # To add a layer to an existing GPKG file, pass 'append' as True
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = layer_name
    
    if os.path.exists(gpkg_path):    
        layer = QgsVectorLayer(gpkg_path, layer_name,"ogr")
        subLayers =layer.dataProvider().subLayers()
        
        existing_layer_names = []
        for subLayer in subLayers:
            name = subLayer.split('!!::!!')[1]
            existing_layer_names.append(name)
        
        if layer_name in existing_layer_names and overwrite_layer == False:
            raise Exception(f"Layer name {layer_name} already exists in {gpkg_path}")
    
    if append:
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer 
        options.EditionCapability = QgsVectorFileWriter.CanAddNewLayer
    
    writer = QgsVectorFileWriter.create(
        gpkg_path,
        schema,
        geometry,
        QgsCoordinateReferenceSystem(crs),
        QgsCoordinateTransformContext(),
        options)
    del writer

    return True

def _get_eft_params_for_version(eft_version):
    if eft_version == "11.0":
        area_cell = 'B4'
        year_cell = 'B5'
        traffic_format_cell = 'B6'
        checkbox_object_names = {'pollutants': {'NOx' : 'CB_NoxCop', 'PM10' : 'CB_PM10', 'PM2.5' : 'CB_PM25',
                                 'CO2' : 'CB_CO2'},
                                 'outputs' : {'AQ_modelling' : 'CB_Emgkms',
                                              'emission_rates' : 'CB_Emgkm',
                                              'annual_link_emissions' : 'CB_Emg'}, 
                                 'additional_outputs' : {'breakdown_by_vehicle' : 'CB_EMVehBrk',
                                                         'pm_by_source' : 'CB_PMSplit',
                                                         'source_apportionment' : 'CB_EmPerc'},
                                 'advanced': {'fleet_composition_tool' : 'CB_FP', 
                                              'simple_entry_euro_compositions' : 'CB_UserEuroSimp',
                                              'primary_no2_fraction' : 'CB_FNO2',
                                              'PM25_annual_emissions_euro_split' : 'CB_TfL_OutputPM25EuroSplit',
                                              'PM10_annual_emissions_euro_split' : 'CB_TfL_OutputPM10EuroSplit',
                                              'NOx_annual_emissions_euro_split' : 'CB_TfL_OutputNOxEuroSplit',
                                              'output_perc_euro_classes' : 'CB_UserEuro',
                                              },
                                 'export' : {'save_output' : 'CB_SaveOut'}}
        input_sheet_name = 'Input Data'
        output_sheet_name = 'Output'
        first_input_col = "A"
        first_input_row = "10"
        last_input_col = "J"
        file_out_cell = "D6"
    else:
        raise Exception("invalid eft version. valid options are: 11.0")
        
    return (area_cell, year_cell, traffic_format_cell, checkbox_object_names, 
            input_sheet_name, output_sheet_name, first_input_col, first_input_row, last_input_col, 
            file_out_cell)

def _set_eft_chkbx_values(checkbox_object_names, sheet, eft_output_path, pollutants):
    for pollutant, obj_name in checkbox_object_names['pollutants'].items():
        if pollutant in pollutants:
            sheet.api.OLEObjects(obj_name).Object.Value = True
        else:
            sheet.api.OLEObjects(obj_name).Object.Value = False
    
    for outputs_name, obj_name in checkbox_object_names['outputs'].items():
        if outputs_name == 'AQ_modelling':
            sheet.api.OLEObjects(obj_name).Object.Value = True
        else:
            sheet.api.OLEObjects(obj_name).Object.Value = False
    
    for outputs_name, obj_name in checkbox_object_names['additional_outputs'].items():
        sheet.api.OLEObjects(obj_name).Object.Value = False
    
    for outputs_name, obj_name in checkbox_object_names['advanced'].items():
        sheet.api.OLEObjects(obj_name).Object.Value = False
    
    sheet.api.OLEObjects(checkbox_object_names['export']['save_output']).Object.Value = False
    
    return

def _check_run_eft_inputs(eft_file_path, eft_input_list, area, year, traffic_format):
    if not os.path.exists(eft_file_path):
        raise Exception("eft_file_path not found")
    else:
        eft_file_ext = os.path.splitext(eft_file_path)[1]
        if eft_file_ext != '.xlsb':
            raise Exception("EFT file must have .xlsb extension")
    
    # check input list is valid
    if type(eft_input_list) not in [np.ndarray, list]:
        raise Exception("eft_input_list must be a list or numpy array")
    
    if type(eft_input_list) == list:
        eft_input_list = np.array(eft_input_list)
        
    if len(eft_input_list.shape) != 2 or eft_input_list.shape[1] != 10:
        raise Exception("eft_input_list must have 10 columns")
    
    #check inputs    
    valid_areas = ['London', 'England (not London)', 'Northern Ireland', 'Scotland',
                   'Wales']
    if area not in valid_areas:
        raise Exception(f"Specified area not valid. Valid areas are: {', '.join(valid_areas)}")
    
    first_valid_year = 2018
    last_valid_year = 2030
    valid_years = list(range(first_valid_year, last_valid_year+1))
    if int(year) not in valid_years:
        raise Exception((f"Specified year is not within valid range of {str(first_valid_year)}"
                        f" to {str(last_valid_year)}"))
        
    valid_traffic_format = ['Basic Split', 'Detailed Option 1', 'Detailed Option 2',
                            'Detailed Option 3', 'Alternative Technologies']
    if traffic_format not in valid_traffic_format:
        raise Exception(f"Specified traffic format not valid. Valid areas are: {', '.join(valid_traffic_format)}")
    
    return
    
def run_eft(eft_input_list, eft_file_path, road_type, area, year, 
            eft_output_path = None, traffic_format = 'Basic Split', 
            pollutants = ['NOx', 'PM10', 'PM2.5'], eft_version = "11.0"):
    
    #TODO: check macros enabled
    
    _check_run_eft_inputs(eft_file_path, eft_input_list, area, year, traffic_format)
        
    (area_cell, year_cell, traffic_format_cell, checkbox_object_names, 
     input_sheet_name, ouput_sheet_name, first_input_col, first_input_row, last_input_col, 
     file_out_cell) = _get_eft_params_for_version(eft_version)

    # initial input cells
    cell_values = {area_cell : area, year_cell : year, traffic_format_cell : traffic_format}
        
    # first and last cells
    first_input_cell = first_input_col+first_input_row
    last_input_cell = last_input_col+"10000"
    clear_cell_range = first_input_cell+':'+last_input_cell        
    
    #initiate workbook
    wb = xw.Book((eft_file_path))
    app = xw.apps.active

    #select input sheet
    sheet = wb.sheets[input_sheet_name]
    sheet.range(clear_cell_range).clear_contents()

    # set initial options in spreadsheet
    for cell, value in cell_values.items():
        sheet.range(cell).value = value

    #iniate checkboxes for pollutants
    _set_eft_chkbx_values(checkbox_object_names, sheet, eft_output_path, pollutants)
        
    #populate sheet with values
    sheet.range(first_input_cell).value = eft_input_list

    #run macro
    _ = wb.macro("Master").run()

    # view results
    output_sheet = wb.sheets[ouput_sheet_name]

    output_eft = output_sheet.range('A1').options(pd.DataFrame, header=1, 
                                                  index=False, expand='table').value

    eft_df = output_eft[['Source Name', 'Pollutant Name', 'All Vehicles (g/km/s)']].copy()
    eft_df['Comments'] = 'g/km/s'
    
    if eft_output_path is not None:
        if os.path.splitext(eft_output_path)[1] != '.xlsb':
            eft_output_path = os.path.splitext(eft_output_path)[0] + '.xlsb'
        wb.save(eft_output_path)
        
    try:
        _ = app.quit()
    except:
        warnings.warn("cannot close excel")
            
    return eft_df

