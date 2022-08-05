# -*- coding: utf-8 -*-
"""
Created on Wed Mar 30 11:14:43 2022

@author: kbenjamin
"""

import os
import csv
import warnings
import pandas as pd
from qgis.core import (
    QgsVectorLayer,
    QgsRasterFileWriter,
    QgsRasterPipe,
    QgsRasterLayer,
    QgsCoordinateTransformContext
)

import processing

from BHAQpy._MyFeedback import MyFeedBack

def select_layer_by_name(layer_name, project):
    '''
    Select a layer by name
    '''
    layer = project.mapLayersByName(layer_name)
    
    if len(layer) > 1:
        raise Exception(f'More than one layer with name: {layer_name} in this project')
    elif not layer:
        raise Exception(f'No layer called: {layer_name} in this project')
    else:
        layer = layer[0]
        return layer

def attributes_table_df(layer):
    '''
    get attributes table as a dataframe
    '''
    #List all columns you want to include in the dataframe
    cols = [field.name() for field in layer.fields()] 

    #A generator to yield one row at a time
    datagen = ([feature[col] for col in cols] for feature in layer.getFeatures())

    layer_df = pd.DataFrame.from_records(data=datagen, columns=cols)
    
    return layer_df

def write_ADMS_input_file(dataframe, output_file, headers_file):
    #extract headers from template file
    headers = []
    if os.path.exists(headers_file):
        with open(headers_file, 'r') as header_template_file:
            reader = csv.reader(header_template_file)
            for line in reader:
                headers.append(line)
        df_values = dataframe.values
    else:
        warnings.warn("Headers template file not found")
        
        #if writing to file without headers then include df column names for writing
        col_names = dataframe.columns.values.tolist()
        df_values = list(dataframe.values)
        df_values.insert(0, col_names)
    
    #check directories
    if not os.path.exists(os.path.dirname(output_file)):
        os.makedirs(os.path.dirname(output_file))
    
    # write to csv
    with open(output_file, 'w+', newline="") as ADMS_file:
        csvwriter = csv.writer(ADMS_file)
        for line in headers:
            csvwriter.writerow(line)
        
        csvwriter.writerows(df_values)    
    return

def save_to_gpkg(layer, gpkg_path, overwrite = False):
        
    processing.run("native:package", {'LAYERS': [layer], 'OUTPUT': gpkg_path, 
                    'OVERWRITE': overwrite, 'SAVE_STYLES': True}, feedback=MyFeedBack())
    
    gpkg_layer = QgsVectorLayer(gpkg_path+'|layername='+layer.name(), layer.name(), 'ogr')
    
    return gpkg_layer 

def save_raster(layer, gpkg_path):
    '''
    save a raster as a standalone file and load this layer
    '''
    #TODO: deprecated    
    layer_name = layer.name()
    file_name = os.path.join(os.path.dirname(gpkg_path), layer_name+'.tif')
    
    file_writer = QgsRasterFileWriter(file_name)
    pipe = QgsRasterPipe()
    provider = layer.dataProvider()

    if not pipe.set(provider.clone()):
        print("Cannot set pipe provider")
        return

    _ = file_writer.writeRaster(
                            pipe,
                            provider.xSize(),
                            provider.ySize(),
                            provider.extent(),
                            layer.crs(),
                            QgsCoordinateTransformContext()
                            )
    
    # add raster layer in new location
    raster_layer = QgsRasterLayer(file_name, layer_name)
    
    return raster_layer