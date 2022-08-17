# -*- coding: utf-8 -*-
"""
Created on Tue Aug 16 17:40:40 2022

@author: kbenjamin

Lesson 2 modelled roads 
    - initiate a ModelledRoads object
    - calculate road gradients
    - generate SPT files
    - generate VGT files
    - initiate a TrafficCountPoints object
    - Generate an EIT and an EFT input files

set your working directory to BHAQpy/examples
"""
#%%
import BHAQpy
import os
from qgis.core import QgsRasterLayer
#%%
run_environment = 'standalone'

# where our project from the previous lesson is saved
project_name = 'BHAQpy_example'
project_dir = 'GIS'
#%%
# initialise a project object 
proj = BHAQpy.AQgisProject(os.path.join(project_dir, project_name+'.qgz'), run_environment)
#%%
# create a blank modelled roads layer 
# =============================================================================
# modelled_roads = proj.init_modelled_roads(gpkg_write_path='GIS/BHAQpy_example.gpkg',
#                                           overwrite_gpkg_layer=True)
# proj.add_layer(modelled_roads.layer)
# proj.save()
# =============================================================================
#%%
# now go into qgis and draw dome roads!
#%%
# if you want to use an exiting modelled roads layer (this will write to a new layer within a geopackage)
modelled_roads = BHAQpy.ModelledRoads(proj, source = 'modelled roads', 
                               gpkg_write_path='GIS/BHAQpy_example.gpkg',
                               gpkg_layer_name='Modelled Roads V2', 
                               overwrite_gpkg_layer=True)

#%%
# we can view the attributes of the modelled roads easily
road_attributes = modelled_roads.get_attributes_df()
print(road_attributes)
#%%
# calculate the road gradients. First we must load in the digital terrain model (DTM)
# this can be downloaded from https://environment.data.gov.uk/DefraDataDownload/?Mode=survey
DTM_layer_name = "Defra Lidar DTM"
# =============================================================================

# DTM_layer = QgsRasterLayer(os.path.join('GIS', 'LIDAR-DTM-1m-2020-TQ38nw', 'TQ38nw_DTM_1m.tif'), 
#                           DTM_layer_name)
# proj.add_layer(DTM_layer)
# proj.save()
# =============================================================================

modelled_roads_gradients = modelled_roads.calculate_gradients([DTM_layer_name])
road_attributes_grads = modelled_roads_gradients.get_attributes_df()
print(road_attributes_grads)
#%%
# directory where our ADMS header templates are saved
template_dir = '../templates/ADMS files/v5/'
# create ADMS input files - SPT
spt = modelled_roads_gradients.generate_SPT(output_file='Output/BHAQpy_example.spt',
                                      headers_file=os.path.join(template_dir, 
                                                                'ADMS_template_v5.spt'),
                                      traffic_flow_year=2019,
                                      traffic_flow_road_type='London (Inner)')
print(spt)
#%%
# generate a vgt - roads are simplified within this fuction
vgt = modelled_roads_gradients.generate_VGT(output_file='Output/BHAQpy_example.vgt',
                                      headers_file=os.path.join(template_dir, 'ADMS_template_v5.vgt'))
print(vgt)
#%% generating an EIT is a bit more complicated - fist we must initialise a trafficcountpoints object
tcps = BHAQpy.TrafficCountPoints(source = "LAEI 2019 road middle points clipped", 
                                 project=proj)
print(tcps.get_attributes_df())
#%% matching a ModelledRoads object to a TrafficCountPoints lets you see the traffic
# details of a road
modelled_roads_tcps = modelled_roads_gradients.match_to_TCP(tcps)
print(modelled_roads_tcps)
#%% generate an EFT - this will attempt t run an excel macro. You will need to 
# open the EFT excel file and 'enable content'
eft_file_path = 'EFT/EFT2021_v11p0.xlsb'
road_type = 'London - Inner'
area = 'London'
year = '2019'
eit_output_path = 'Output/BHAQpy_example.eit'
headers_file = os.path.join(template_dir, 'ADMS_template_v5.eit')
eft_output_path = 'Outut/BHAQp_example_EFT.xlsb'
eit = modelled_roads_gradients.generate_EIT(tcps, eft_file_path, road_type, area, 
                                         year, eit_output_path, headers_file,
                                         eft_output_path)
#%% Running excel can be very tempramental so it can be better to simply create 
# an input file that can be copied into the EFT
eft_input = modelled_roads_gradients.generate_EFT_input(tcps, road_type, 
                                                    'Output/BHAQpy_example_EFT_input.csv')

#%%
# end this instance of qgis
if run_environment == 'standalone':
    proj.qgs_app.exitQgis()