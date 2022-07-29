# -*- coding: utf-8 -*-
"""
Created on Thu Mar 17 11:46:13 2022

@author: kbenjamin
"""

import requests
import pandas as pd
import numpy as np

def get_defra_background_concentrations(coordinates : list, background_region : str, 
                                        year : int, 
                                        pollutants = ['no2', 'nox', 'pm10', 'pm25'],
                                        base_year = '2018', split_by_source=False):
    """
    

    Parameters
    ----------
    coordinates : list
        DESCRIPTION.
    background_region : str
        DESCRIPTION.
    year : int
        DESCRIPTION.
    pollutants : TYPE, optional
        DESCRIPTION. The default is ['no2', 'nox', 'pm10', 'pm25'] : list.
    base_year : TYPE, optional
        DESCRIPTION. The default is '2018' : int.
    split_by_source : TYPE, optional
        DESCRIPTION. The default is False : bool.

    Raises
    ------
    Exception
        DESCRIPTION.

    Returns
    -------
    background_concentrations : TYPE
        DESCRIPTION.

    """
    
    coordinate_shape = np.shape(coordinates) 
    if coordinate_shape != (2,) and coordinate_shape != (2,2):
        raise Exception("coordinates must be a singular point or a maximum minimum extent")
    
    # manipulate shape if getting point
    if coordinate_shape == (2,):
        coordinates = [coordinates, coordinates]
    
    valid_regions = ['Greater_London', 'East_of_England', 'Midlands', 'Northern_England',
                     'Northern_Ireland', 'Scotland', 'Southern_England', 'Wales']
    if background_region not in valid_regions:
        raise Exception(f"{background_region} not valid. Please specify one of: {', '.join(valid_regions)}")
    
    
    valid_pollutants = ['no2', 'nox', 'pm10', 'pm25']
    if not set(pollutants).issubset(valid_pollutants):
        raise Exception(f"At least one specified pollutant is not valid. Please specify one of: {', '.join(valid_pollutants)}")
    
    url_base = 'https://uk-air.defra.gov.uk/data/laqm-background-maps.php'
    
    counter = 1
    for pollutant in pollutants:
        params = {'bkgrd-region' : background_region,
                  'bkgrd-pollutant' : pollutant,
                  'bkgrd-year' : year,
                  'action' : 'data',
                  'year' : '2018',
                  'submit' : 'Download+CSV'}
        res = requests.get(url_base, params=params, headers={'User-Agent': 'Chrome'})
        
        skip_header_rows = 5
        if res.ok:
            data = res.content.decode('utf8')
            data_split = data.split('\n')[skip_header_rows:]
            data_split_rows = [row.split(',') for row in data_split]
            
            pollutant_bg_df= pd.DataFrame(data_split_rows[1:], columns = data_split_rows[0])
        
        pollutant_bg_df['x'] = pollutant_bg_df['x'].astype(float)
        pollutant_bg_df['y'] = pollutant_bg_df['y'].astype(float)
        
        
        polluants_bg_at_coords = pollutant_bg_df[(pollutant_bg_df['x']+500 > coordinates[0][0]) &
                                                (pollutant_bg_df['x']-500 < coordinates[1][0]) &
                                                (pollutant_bg_df['y']+500 > coordinates[0][1]) &
                                                (pollutant_bg_df['y']-500 < coordinates[1][1])]
        
        if counter == 1:
            background_concentrations = polluants_bg_at_coords
        else:
            background_concentrations = pd.merge(background_concentrations, 
                                                 polluants_bg_at_coords, 
                                                 on = ['Local_Auth_Code', 'x', 'y', 'geo_area', 'EU_zone_agglom_01'])
        
        counter += 1            
    
    if not split_by_source:
        keep_columns = ['Local_Auth_Code', 'x', 'y', 'geo_area', 'EU_zone_agglom_01']
        total_columns = [col_n for col_n in list(background_concentrations.columns) if 'Total_' in col_n]
        
        keep_columns.extend(total_columns)
        
        background_concentrations = background_concentrations[keep_columns]
        
        for col in total_columns:
            background_concentrations[col] = background_concentrations[col].astype(float)
        
        background_concentrations.loc['mean'] = background_concentrations[total_columns].mean()
        
    return background_concentrations