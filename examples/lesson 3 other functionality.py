# -*- coding: utf-8 -*-
"""
Created on Tue Aug 16 17:41:55 2022

@author: kbenjamin

Other useful BHAQpy functionality
"""
#%%
import BHAQpy
#%%
# get background concentration at a point
point_of_interest_x_y = [531236.148, 185725.917] 
point_of_interest_bg = BHAQpy.get_defra_background_concentrations(point_of_interest_x_y, 
                                                 background_region='Greater_London',
                                                 year=2022,
                                                 pollutants=['no2', 'nox','pm10', 'pm25'])
