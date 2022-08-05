# BHAQpy

Seamless integration of technical air quality work into python

## Documentation

See the full documentation [here](https://bh-air-quality.github.io/BHAQpy/BHAQpy.html).

## Installation

First make sure you have git installed via you anaconda prompt

```
conda install git
```

To install BHAQpy: 
```
pip install git+https://github.com/BH-air-quality/BHAQpy.git
```

### Requirements

- QGIS **>3.18**
- pandas
- xlwings

If running from qgis qui you may need to install from osgeo shell. To do this;

1. Search for your QGIS installation in the windows search bar
2. right click and select 'Open file location'
3. Open the OSGeo4W Shell 
4. In the shell run `pip install xlwings`

## Run environment

A lot of functions rely on the python QGIS api [PyQGIS](https://docs.qgis.org/3.22/en/docs/pyqgis_developer_cookbook/index.html) which behaves differently if you are running within qgis or directly from python


```
#if you are running within the qgis gui:
run_environment = "qgis_gui"

#if you are running from a python script:
run_environment = "standalone"
```
