# BHAQpy

Seamless integration of technical air quality work into python. BHAQpy is built upon the python QGIS api [PyQGIS](https://docs.qgis.org/3.22/en/docs/pyqgis_developer_cookbook/index.html)

## Documentation

See the full documentation [here](https://bh-air-quality.github.io/BHAQpy/BHAQpy.html).

## Functionality

BHAQpy allows for a range of facilities including:
- initialise a qgis project from a basemap, clipping base layers around the specified site
- get defra background concentrations at a given point, at a site and at receptor locations
- add construction buffers around a site
- create spt and vgt files from a roads layer in QGIS
- create an EFT input file
- calculate road gradients
- generate an asp, at multiple heights, from a layer in QGIS
- get receptor addresses 

## Intro

To view BHAQpy functionality, go through the [lessons](examples/).

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

#### Currently supported versions
QGIS v3.18.3-Zurich

Python 3.10.2
