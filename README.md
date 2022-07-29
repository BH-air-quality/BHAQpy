# BHAQpy

Seamless integration of technical air quality work into python

## Installation

First make sure you have git installed via you anaconda prompt

```
conda install git
```

To install BHAQpy: 
```
pip install git+https://github.com/BH-air-quality/BHAQpy.git
```

## Run environment

A lot of functions rely on the python QGIS api [PyQGIS](https://docs.qgis.org/3.22/en/docs/pyqgis_developer_cookbook/index.html) which behaves differently if you are running within qgis or directly from python


```
#if you are running within the qgis gui:
run_environment = "qgis_gui"

#if you are running from a python script:
run_environment = "standalone"
```
