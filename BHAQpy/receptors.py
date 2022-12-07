# -*- coding: utf-8 -*-
"""
Created on Mon Dec  5 14:46:57 2022

@author: kbenjamin
"""
import pandas as pd
import numpy as np
from itertools import product
import time

from geopy.geocoders import Nominatim
from pyproj import Transformer

from ._utils import (select_layer_by_name,
                   attributes_table_df)
from BHAQpy.getdefrabackground import get_defra_background_concentrations


class Receptors:
    """
    Receptor object with specific functions applied to layers representing receptor points.
    
    Attributes
    ----------
    source : str
        The data source of the traffic count points dataset
    
    project : BHAQpy.AQgisProject
        The AQgisProject object in which the TCP layer is within
        
    layer : qgis.core.QGSVectorLayer
        The QGIS vector layer with the traffic count points data.
        
    Methods
    -------
    get_attributes_df()
        get a pandas dataframe with traffic count point data.
    
    generate_ASP()
        save receptors as an asp
    
    get_addresses()
        Extract receptor addresses (from Nomatim)
    
    get_address_sample()
        Helper function that gets the address of the first receptor. This allows the user to decide which address lines to keep and which to exclude.
    
    get_defra_background_concentrations()
        Get defra background maps concentration for each receptor
    
    """
    def __init__(self, project, source, id_attr_name = 'ID', 
                 min_height_attr_name = 'Height', max_height_attr_name=None,
                 separation_distance_attr_name=None):
        """
        Parameters
        ----------
        project : TYPE, optional
            BHAQpy.AQgisProject in which the layer is within. The default is None.
        source : str
            Source of data. A layer name within a project or a csv file.
        id_attr_name : str, optional
            The layer attribute containing the ID/name of the specificed point. The default is 'ID'.
        min_height_attr_name : str, optional
            The layer attribute containing the minimum height of the specificed point. The default is 'Height'.
        max_height_attr_name : str, optional
            The layer attribute containing the maximum of the specificed points. 
            If None then specifed points are noly created at value specified in min_height_attr_name. 
            If not None then specified points are created at value specified in the layers attribute specified in min_height_attr_name
            If  The default is None.
        separation_distance_attr_name : str, optional
            The layer attribute containing the height separation of the specificed points. The default is None.

        Returns
        -------
        None.

        """
        self.source = source
        self.project = project
        self.id_attr_name = id_attr_name
        self.min_height_attr_name = min_height_attr_name
        self.max_height_attr_name = max_height_attr_name
        self.separation_distance_attr_name = separation_distance_attr_name
        
        if type(source) != str:
            raise Exception("Source must be a string of layer name or file path")
        
        qsg_proj = project.get_project()
        receptor_layer = select_layer_by_name(source, qsg_proj)
        self.layer = receptor_layer
        
        receptor_layer_fields = [field.name() for field in receptor_layer.fields()]
        
        # test if atrributes are defined correctly
        attr_names = [id_attr_name, min_height_attr_name]
        if max_height_attr_name is not None:
            attr_names.append(max_height_attr_name)
        
        if separation_distance_attr_name is not None:
            attr_names.append(separation_distance_attr_name)
        
        for attr_name in attr_names:
            if attr_name not in receptor_layer_fields:
                raise Exception(f"{attr_name} not an attribute of {receptor_layer}")
                
        receptor_df_raw = attributes_table_df(receptor_layer)
        receptor_df_raw = receptor_df_raw[[id_attr_name, min_height_attr_name, 
                                           max_height_attr_name, separation_distance_attr_name]]
        
        # reformat data
        f_receptor_id_col_name = 'ID'
        f_min_height_col_name = 'Min height' 
        f_max_height_col_name = 'Max height' 
        f_sep_distance_col_name = 'Separation'
                
        cols = {id_attr_name : f_receptor_id_col_name, 
                min_height_attr_name : f_min_height_col_name, 
                max_height_attr_name : f_max_height_col_name, 
                separation_distance_attr_name : f_sep_distance_col_name}
        
        receptor_df_raw = receptor_df_raw.rename(columns = cols)
        
        if max_height_attr_name is None:
            receptor_df_raw[f_max_height_col_name] = receptor_df_raw[f_min_height_col_name]
        
        if separation_distance_attr_name is None:
            receptor_df_raw[f_sep_distance_col_name] = 0
        
        # get X and Y values
        receptor_x_y_values = []
        receptor_features = receptor_layer.getFeatures()
        for receptor_feature in receptor_features:
            receptor_feature_id = receptor_feature[id_attr_name]
            X = receptor_feature.geometry().asPoint().x()
            Y = receptor_feature.geometry().asPoint().y()
            receptor_x_y_values.append([receptor_feature_id, X, Y])
        
        receptor_x_y_df = pd.DataFrame(receptor_x_y_values, columns=[f_receptor_id_col_name, 'X', 'Y'])
        receptor_df = pd.merge(receptor_df_raw, receptor_x_y_df, on=f_receptor_id_col_name) 
        # re-arrange 
        receptor_df = receptor_df[[f_receptor_id_col_name, 'X', 'Y', f_min_height_col_name,
                                  f_max_height_col_name, f_sep_distance_col_name]]
        
        self._attr_df = receptor_df
        return
    
    def get_attributes_df(self):
        """
        Get the attributes table as a dataframe

        Returns
        -------
        pandas.DataFrame
            Dataframe of attributes table.

        """
        
        return self._attr_df
    
    def generate_ASP(self, output_file_path):
        """
        Create an asp file for receptors. Compute for all heights.

        Parameters
        ----------
        output_file_path : str
            Path to the file at which asp file will be saved.

        Returns
        -------
        asp_df : pandas.DataFrame
            Pandas dataframe containing all specified point ID, X, Y, Z.

        """
        
        receptor_df = self.get_attributes_df()
        asp_values = []
        for receptor_feature in receptor_df.values:
            receptor_feature_id = receptor_feature[0]
            
            receptor_feature_min_height = float(receptor_feature[3])
            receptor_feature_max_height = receptor_feature[4]
            receptor_feature_sep_dist = receptor_feature[5]
            
            # check for null sep distances 
            if str(receptor_feature_sep_dist) == 'NULL':
                receptor_feature_sep_dist = 0
                multiple_heights = False
            else:
               receptor_feature_sep_dist = float(receptor_feature_sep_dist) 

            # define the separation distance 
            if receptor_feature_sep_dist != 0:
                multiple_heights = True
            else:
                multiple_heights = False
            
            # define max height of receptor
            if str(receptor_feature_max_height) == 'NULL':
                receptor_feature_max_height = float(receptor_feature_min_height)+receptor_feature_sep_dist
            else:
                if float(receptor_feature_max_height) == receptor_feature_min_height:
                    receptor_feature_max_height = receptor_feature_min_height+receptor_feature_sep_dist
                else:
                    receptor_feature_max_height = float(receptor_feature_max_height)
            
            
            # get receptor heights
            if multiple_heights:
                height_range = np.arange(receptor_feature_min_height, receptor_feature_max_height+0.001, receptor_feature_sep_dist)
            else:
                height_range = [receptor_feature_min_height]
            
            receptor_z = pd.DataFrame(product([receptor_feature_id], height_range),
                                          columns=['ID', 'Z']).set_index('ID')
            
            receptor_xy = pd.DataFrame([list(receptor_feature[0:3])], columns = ['ID', 'X', 'Y']).set_index('ID')
            receptor_xyz = receptor_xy.join(receptor_z).reset_index()
            
            if multiple_heights:
                receptor_xyz['ID'] = receptor_xyz['ID'].astype(str) + '(' + receptor_xyz['Z'].astype(str) + ')'
            
            asp_values.extend(receptor_xyz.values)
            
        asp_df = pd.DataFrame(asp_values, columns = ['ID', 'X', 'Y', 'Z'])
        
        #save to csv
        asp_df.to_csv(output_file_path, index=False, header=False)
        
        return asp_df
    
    def get_addresses(self, excluded_address_lines_contents=[]):
        """
        Get addresses from Nomatim, using Geopy.

        Parameters
        ----------
        excluded_address_lines_contents : list
            Names within address to exclude. For example if you wanted to remove London, United Kingdom from every address then excluded_address_lines_contents would be set to ['London', 'United Kingdom'].

        Returns
        -------
        Pandas dataframe of receptor attributes and addresses.

        """
        receptor_address_df = self.get_attributes_df()
        
        # settings for transforming receptor locations
        transformer = Transformer.from_crs("epsg:27700", "epsg:4326")
        geolocator = Nominatim(user_agent="http")
        
        # collect address names
        addresses = []
        counter = 1
        for receptor in receptor_address_df.values:
            print(f"{counter}/{len(receptor_address_df.values)} {receptor[0]}")
            address_str = _get_address(receptor, transformer, geolocator, 
                                       excluded_address_lines_contents)
            addresses.append(address_str)
            time.sleep(1)
            counter+=1
    
        receptor_address_df['Address'] = addresses
        self._attr_df = receptor_address_df
        
        return receptor_address_df
    
    def get_address_sample(self):
        """
        Helper function used to determine excluded_address_lines_contents. Extract the address of the first receptor in the dataframe

        Returns
        -------
        list
            Receptor ID of the first receptor and the address.

        """
        receptor_df = self.get_attributes_df()
        receptor = receptor_df.iloc[0].values
        # settings for transforming receptor locations
        transformer = Transformer.from_crs("epsg:27700", "epsg:4326")
        geolocator = Nominatim(user_agent="http")
        
        address_str = _get_address(receptor, transformer, geolocator, 
                                   excluded_address_lines_contents=[])
        return [receptor[0], address_str]
    
    def get_defra_background_concentrations(self, background_region, 
                                            BG_maps_grid_layer='LAQM 2018 BG Ref clipped'):
        """
        

        Parameters
        ----------
        background_region : str
            Background region as defined in defra background maps. Options: Greater_London, East_of_England, Midlands, Northern_England, Northern_Ireland, Scotland, Southern_England, Wales.
        BG_maps_grid_layer : TYPE, optional
            DESCRIPTION. The default is 'LAQM 2018 BG Ref clipped'.

        Returns
        -------
        Pandas dataframe containing defra background maps concentration at each receptor.

        """
        # TODO: calculate grid square from X and Y not from intersection
        #select background maps layer (to get grid square)
        receptor_df = self.get_attributes_df()
        qsg_proj = self.project.get_project()
        BG_maps_layer = select_layer_by_name(BG_maps_grid_layer, qsg_proj)
        
        #get features 
        BG_maps_geom = [f for f in BG_maps_layer.getFeatures()]
        receptor_geom = [f for f in self.layer.getFeatures()]

        receptor_grid_sq = []
        for point in receptor_geom:
            receptor_ID = point[self.id_attr_name]
            receptor_geom = point.geometry()
            
            grid_sq_intersecting = [f for f in BG_maps_geom if receptor_geom.intersects(f.geometry())] 
            grid_sq_x = grid_sq_intersecting[0]['x']
            grid_sq_y = grid_sq_intersecting[0]['y']
            
            receptor_grid_sq.append([receptor_ID, grid_sq_x, grid_sq_y])    

        receptor_grid_sq_df = pd.DataFrame(receptor_grid_sq, columns = ['ID', 'Grid sq x', 'Grid sq y'])

        unique_grid_sq = receptor_grid_sq_df.groupby(['Grid sq x', 'Grid sq y'], as_index=False).size()

        grid_bg = []
        for index, row in unique_grid_sq.iterrows():
            print(row['Grid sq x'],row['Grid sq y'])
            bg_conc = get_defra_background_concentrations([row['Grid sq x'],row['Grid sq y']], background_region, 2019)
            bg_values = bg_conc.iloc[0][['Total_NO2_19', 'Total_NOx_19', 'Total_PM10_19', 'Total_PM2.5_19']].values
            
            bg_values = np.append([row['Grid sq x'],row['Grid sq y']], bg_values)
            grid_bg.append(bg_values)

        grid_bg_df = pd.DataFrame(grid_bg, columns = ['Grid sq x', 'Grid sq y', 'Total_NO2_19', 
                                                      'Total_NOx_19', 'Total_PM10_19', 'Total_PM2.5_19'])

        receptor_bg_df = pd.merge(receptor_grid_sq_df, grid_bg_df, left_on=['Grid sq x', 'Grid sq y'], 
                                    right_on = ['Grid sq x', 'Grid sq y'])
        
        receptor_data_bg_df = pd.merge(receptor_df, receptor_bg_df, on='ID')
        
        self._attr_df = receptor_data_bg_df
        return receptor_data_bg_df

def _get_address(receptor, transformer, geolocator, excluded_address_lines_contents):
    lat,lon = transformer.transform(receptor[1], receptor[2])
    location = geolocator.reverse(f"{lat}, {lon}")
    address = location.address
    address_split = address.split(', ')
    address_select = [i for i in address_split if i not in excluded_address_lines_contents]
    address_str = ', '.join(address_select)
    return address_str