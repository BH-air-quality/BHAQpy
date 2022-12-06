# -*- coding: utf-8 -*-
"""
Created on Tue Aug 16 15:57:09 2022

@author: kbenjamin

Be sure to set the working directory to the folder containing this file
Lesson 1 start a new project: 
   - create a new gis project via the AQgisProjectBasemap
   - see some of the attributes associated with an AQgisProject
   - Get the background concentration at the specified site
   - Write an ASP file
   
set your working directory to BHAQpy/examples
"""
#%%
import BHAQpy
import os
from qgis.core import (
    QgsVectorLayer
)
#%%
# we are running as a standalone python script (not within qgis GUI)
run_environment = 'standalone'

# the name our project will be saved
project_name = 'BHAQpy_example'
# path to where the project will be saved
project_dir = 'GIS'
#%%
# path to our QGIS basemap
base_project_path = "C:/Users/kbenjamin/BuroHappold/Environment - 07 Air Quality/2. GIS/1. QGIS Base Map/AQ Basemap.qgz"
# set up a AQgisProjectBasemap object
basemap_project = BHAQpy.AQgisProjectBasemap(base_project_path, run_environment)
# a qgis project has some inherent attributes
print('Project path:', basemap_project.project_path)
print('Project name:', basemap_project.project_name)
print('QGIS application:', basemap_project.qgs_app)
#%%
# create a new project with the supplies red line boundary file
example_project = basemap_project.initialise_project(project_name, project_dir, 
                                                     site_geom_source = os.path.join(project_dir,'red line boundary.shp'),
                                                     clip_distance = 5000)

#%%
# some more useful attributes
print('Path to project geopackage:', example_project.gpkg_path)
# to access the project in PyQGIS. 
example_project_pyqgis = example_project.get_project()
# from here pyqgis functions can be applied e.g. list all layers
print([l.name() for l in example_project_pyqgis.mapLayers().values()])
#%%
# add a new monitoring layer
monitoring_sites_path = 'GIS/monitoring_sites.shp'
# read the file using pyqgis
monitoring_layer = QgsVectorLayer(monitoring_sites_path, 'Islington monitoring')
example_project.add_layer(monitoring_layer)
example_project.save()

#%%
# get the background concentrations at our site 
site_bg_concs_2019 = example_project.get_site_background_concs('Greater_London', 2019)
print(site_bg_concs_2019.T)
#%%
# add our receptors layer called "receptors". 
# It will have the following attributes:
# ReceptorID
# Min height
# Max height
# Separation
# add a new monitoring layer
receptors_path = 'GIS/receptors.shp'
receptors_layer_name = 'receptors'
# read the file using pyqgis
receptors_layer = QgsVectorLayer(receptors_path, receptors_layer_name)
example_project.add_layer(receptors_layer)
example_project.save()
#%%
# now write an asp file with all of our receptors at each separation
receptors = BHAQpy.Receptors(example_project, 'receptors', 
                             id_attr_name = 'ReceptorID',
                             min_height_attr_name='Min height',
                             max_height_attr_name=None, 
                             separation_distance_attr_name=None)

print(receptors.get_attributes_df())
#get saemple addresses for the first receptors
receptor_addresses = receptors.get_address_sample()
print(receptor_addresses)
# define some address we want to exclude
exclude_addr_lines = ['London Borough of Islington', 'London', 'Greater London', 'England', 'United Kingdom']
#get addresses for all receptors
recpetor_addresses = receptors.get_addresses(exclude_addr_lines)

#get defra background concentrations
receptor_bg_conc = receptors.get_defra_background_concentrations(background_region='Greater_London',
                                                                 BG_maps_grid_layer='LAQM 2018 BG Ref clipped')

#save receptors as an asp
asp_save_path = 'Output/receptors.asp'
asp_df = receptors.generate_ASP(asp_save_path)
print(asp_df)
#%%
# end this instance of qgis
if run_environment == 'standalone':
    example_project.qgs_app.exitQgis()