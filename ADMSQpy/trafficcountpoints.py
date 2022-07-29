# -*- coding: utf-8 -*-
"""
Created on Wed Mar 30 11:29:05 2022

@author: kbenjamin
"""

import os
import pandas as pd
from .utils import (select_layer_by_name,
                   attributes_table_df,
                   write_ADMS_input_file)

class TrafficCountPoints():
    '''
    TODO: add read from file functionality
    '''
    
    def __init__(self, source, tcp_id_col_name = 'ID', 
                 total_AADT_col_name = 'Tot_AADT19', HDV_percentage_col_name = 'HDV %',
                 HDV_AADT_col_name = 'HDV AADT', speed_col_name = 'Sp_kph',
                 project = None):
        
        # TODO: get XY coordinates
        self.source = source
        self.project = project
        if type(source) != str:
            raise Exception("Source must be a string of layer name or file path")
             ##TODO: create a new template layer
         
         # if running from CSV
        if ".csv" in source:
            if not os.path.exists(source):
                raise Exception(f"File path: {source} doesnt exist")
            else:
                tcp_df_raw = pd.read_csv(source)
         #if from a qgis layer
        else:
            if self.project is None:
                raise Exception("Project must be specified if source is not a csv file")
            
            qsg_proj = project.get_project()
            tcp_layer = select_layer_by_name(source, qsg_proj)
            self.layer = tcp_layer
             
            tcp_df_raw = attributes_table_df(tcp_layer)
             
        # reformat data
        f_tcp_id_col_name = 'TCP ID'
        f_total_AADT_col_name = 'Total AADT' 
        f_HDV_AADT_col_name = 'HDV AADT'
        f_HDV_percentage_col_name = 'HDV %'
        f_speed_col_name = 'TCP Speed'
                
        cols = {tcp_id_col_name : f_tcp_id_col_name, 
                total_AADT_col_name : f_total_AADT_col_name, 
                HDV_AADT_col_name : f_HDV_AADT_col_name, 
                HDV_percentage_col_name : f_HDV_percentage_col_name, 
                speed_col_name : f_speed_col_name}
        
        tcp_df_raw = tcp_df_raw.rename(columns = cols)

        columns_values = list(cols.values())
        present_columns = [col for col in columns_values if col in tcp_df_raw.columns.values]

        tcp_df_raw = tcp_df_raw[present_columns]
        
        if 'TCP ID' not in present_columns:
            raise Exception("No valid traffic count id column identified.")
        
        #filter NULL values
        tcp_df_raw = tcp_df_raw[tcp_df_raw[f_tcp_id_col_name].apply(lambda x: type(x) == int)]
        
        # ensure consistent format
        required_columns = columns_values.copy()
        tcp_df_formatted = pd.DataFrame(columns = required_columns)
        for col_name in required_columns:
            if col_name in tcp_df_raw.columns.values:
                if col_name != 'TCP ID':
                    tcp_df_formatted[col_name] = pd.to_numeric(tcp_df_raw[col_name], errors = 'coerce')
                else:
                    tcp_df_formatted[col_name] = tcp_df_raw[col_name].astype(str)
            else:
                tcp_df_formatted[col_name] = None
        
        # calc hdv % if not already available
        if (tcp_df_formatted[f_HDV_percentage_col_name].isnull().all() and not 
            tcp_df_formatted[f_total_AADT_col_name].isnull().all() and not 
            tcp_df_formatted[f_HDV_AADT_col_name].isnull().all()):
                
                tcp_df_formatted[f_HDV_percentage_col_name] = tcp_df_formatted[f_HDV_AADT_col_name] / tcp_df_formatted[f_total_AADT_col_name] * 100
            
        self._attr_df = tcp_df_formatted
        return
    
    def get_attributes_df(self):
        
        return self._attr_df