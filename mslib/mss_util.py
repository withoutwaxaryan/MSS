# -*- coding: utf-8 -*-
"""

    mslib.mss_util
    ~~~~~~~~~~~~~~

    Collection of utility routines for the Mission Support System.

    This file is part of mss.

    :copyright: Copyright 2008-2014 Deutsches Zentrum fuer Luft- und Raumfahrt e.V.
    :copyright: Copyright 2011-2014 Marc Rautenhaus (mr)
    :copyright: Copyright 2016-2017 by the mss team, see AUTHORS.
    :license: APACHE-2.0, see LICENSE for details.

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

import os
import pickle
import logging
import datetime
from datetime import datetime as dt
import json
# related third party imports
import numpy as np
from scipy.interpolate import RectBivariateSpline, interp1d
from scipy.ndimage import map_coordinates

try:
    import mpl_toolkits.basemap.pyproj as pyproj
except ImportError:
    import pyproj

from mslib.msui import constants


class FatalUserError(Exception):
    pass


def config_loader(config_file=None, dataset=None, default=None):
    """
    Function for loading json config data

    Args:
        config_file: json file, parameters for initializing mss,
        dataset: section to pull from json file
        default: values to return if dataset was requested and don't exist or config_file is not given

    Returns: a dictionary

    """
    if config_file is None:
        config_file = constants.CACHED_CONFIG_FILE
    data = {}
    try:
        with open(os.path.join(config_file)) as source:
            data = json.load(source)
    except (AttributeError, IOError, TypeError), ex:
        logging.error(u"MSS config File error '{:}' - '{:}' - '{:}'".format(config_file, type(ex), ex))
        if default is not None:
            return default
        raise IOError("MSS config File not found")
    except ValueError, ex:
        error_message = u"MSS config File '{:}' has a syntax error:\n\n'{}'".format(config_file, ex)
        raise FatalUserError(error_message)
    if dataset:
        try:
            return data[dataset]
        except KeyError:
            logging.debug(u"Config File used: '{:}'".format(config_file))
            logging.debug(u"Key not defined in config_file! '{:}'".format(dataset))
            if default is not None:
                return default
            raise KeyError("default value for key not set")

    return data


def get_distance(coord0, coord1):
    """
    Computes the distance between two points on the Earth surface
    Args:
        coord0: coordinate(lat/lon) of first point
        coord1: coordinate(lat/lon) of second point

    Returns:
        length of distance in km
    """
    pr = pyproj.Geod(ellps='WGS84')
    return pr.inv(coord0[1], coord0[0], coord1[1], coord1[0])[-1] / 1000.


def save_settings_pickle(tag, settings):
    """
    Saves a dictionary settings to disk.

    :param tag: string specifying the settings
    :param settings: dictionary of settings
    :return: None
    """
    assert isinstance(tag, basestring)
    assert isinstance(settings, dict)
    settingsfile = os.path.join(constants.MSS_CONFIG_PATH, "mss.{}.cfg".format(tag))
    logging.debug("storing settings for %s to %s", tag, settingsfile)
    try:
        with open(settingsfile, "w") as fileobj:
            pickle.dump(settings, fileobj)
    except (OSError, IOError), ex:
        logging.warn("Problems storing %s settings (%s: %s).", tag, type(ex), ex)


def load_settings_pickle(tag, default_settings=None):
    """
    Loads a dictionary of settings from disk. May supply a dictionary of default settings
    to return in case the settings file is not present or damaged. The default_settings one will
    be updated by the restored one so one may rely on all keys of the default_settings dictionary
    being present in the returned dictionary.

    :param tag: string specifying the settings
    :param default_settings: dictionary of settings or None
    :return: dictionary of settings
    """
    if default_settings is None:
        default_settings = {}
    assert isinstance(default_settings, dict)
    settingsfile = os.path.join(constants.MSS_CONFIG_PATH, "mss.{}.cfg".format(tag))
    logging.debug("loading settings for %s from %s", tag, settingsfile)
    try:
        with open(settingsfile, "r") as fileobj:
            settings = pickle.load(fileobj)
    except (pickle.UnpicklingError, KeyError, OSError, IOError, ImportError), ex:
        logging.warn("Problems reloading stored %s settings (%s: %s). Switching to default",
                     tag, type(ex), ex)
        settings = {}
    if isinstance(settings, dict):
        default_settings.update(settings)
    return default_settings


JSEC_START = datetime.datetime(2000, 1, 1)


def datetime_to_jsec(dt):
    """
    Calculate seconds since Jan 01 2000.
    """
    delta = dt - JSEC_START
    total = delta.days * 3600 * 24
    total += delta.seconds
    total += delta.microseconds * 1e-6
    return total


def jsec_to_datetime(jsecs):
    """
    Get the datetime from seconds since Jan 01 2000.
    """
    return JSEC_START + datetime.timedelta(seconds=jsecs)


def compute_hour_of_day(jsecs):
    date = JSEC_START + datetime.timedelta(seconds=jsecs)
    return date.hour + date.minute / 60. + date.second / 3600.


def fix_angle(ang):
    """
    Normalizes an angle between -180 and 180 degree.
    """
    while ang > 360:
        ang -= 360
    while ang < 0:
        ang += 360
    return ang


def rotate_point(point, angle, origin=(0, 0)):
    """Rotates a point. Angle is in degrees.
    Rotation is counter-clockwise"""
    angle = np.deg2rad(angle)
    temp_point = ((point[0] - origin[0]) * np.cos(angle) -
                  (point[1] - origin[1]) * np.sin(angle) + origin[0],
                  (point[0] - origin[0]) * np.sin(angle) +
                  (point[1] - origin[1]) * np.cos(angle) + origin[1])
    return temp_point


def convertHPAToKM(press):
    return (288.15 / 0.0065) * (1. - (press / 1013.25) ** (1. / 5.255)) / 1000.


def get_projection_params(epsg):
    if epsg.startswith("EPSG:"):
        epsg = epsg[5:]
    proj_params = None
    if epsg == "4326":
        proj_params = {"basemap": {"projection": "cyl"}, "bbox": "latlon"}
    elif epsg == "9810":
        proj_params = {"basemap": {"projection": "stere", "lat_0": 90.0, "lon_0": 0.0}, "bbox": "metres"}
    elif epsg.startswith("777") and len(epsg) == 8:
        lat_0, lon_0 = int(epsg[3:5]), int(epsg[5:])
        proj_params = {"basemap": {"projection": "stere", "lat_0": lat_0, "lon_0": lon_0}, "bbox": "latlon"}
    elif epsg.startswith("778") and len(epsg) == 8:
        lat_0, lon_0 = int(epsg[3:5]), int(epsg[5:])
        proj_params = {"basemap": {"projection": "stere", "lat_0": -lat_0, "lon_0": lon_0}, "bbox": "latlon"}
    return proj_params

# Utility functions for interpolating vertical sections.


def interpolate_vertsec(data3D, data3D_lats, data3D_lons, lats, lons):
    """
    Interpolate curtain[z,pos] (curtain[level,pos]) from data3D[z,y,x]
    (data3D[level,lat,lon]).

    This method is based on scipy.interpolate.RectBivariateSpline().

    data3D has to be on a regular lat/lon grid, coordinates given by lats, lons.
    lats, lons have to be strictly INCREASING, they do not have to be uniform,
    though.
    """
    # Create an empty field to accomodate the curtain.
    curtain = np.zeros([data3D.shape[0], len(lats)])

    # One horizontal interpolation for each model level.
    for ml in range(data3D.shape[0]):
        data = data3D[ml, :, :]
        # Initialise a SciPy interpolation object. RectBivariateSpline is the
        # only class that can handle 2D input fields.
        interpolator = RectBivariateSpline(data3D_lats,
                                           data3D_lons,
                                           data, kx=1, ky=1)
        # RectBivariateSpline returns a full mesh of lat/lon interpolated
        # values.. use diagonal to only get the values at lat/lon pairs.
        curtain[ml, :] = interpolator(lats, lons).diagonal()

    return curtain


def interpolate_vertsec2(data3D, data3D_lats, data3D_lons, lats, lons):
    """
    Interpolate curtain[z,pos] (curtain[level,pos]) from data3D[z,y,x]
    (data3D[level,lat,lon]).

    This method is based on scipy.ndimage.map_coordinates().

    data3D has to be on a regular lat/lon grid, coordinates given by lats, lons.
    The lats, lons arrays can have arbitrary order, they do not have to be uniform.
    """
    # Create an empty field to accomodate the curtain.
    curtain = np.zeros([data3D.shape[0], len(lats)])

    # Transform lat/lon values to array index space. This is necessary to use
    # scipy.ndimage.map_coordinates(). See the comments on
    #      http://old.nabble.com/2D-Interpolation-td18161034.html
    # (2D Interpolation; Ryan May Jun 27, 2008) and the examples on
    #      http://www.scipy.org/Cookbook/Interpolation
    dlat = data3D_lats[1] - data3D_lats[0]
    dlon = data3D_lons[1] - data3D_lons[0]
    ind_lats = (lats - data3D_lats[0]) / dlat
    ind_lons = (lons - data3D_lons[0]) / dlon
    ind_coords = np.array([ind_lats, ind_lons])

    # One horizontal interpolation for each model level. The order
    # parameter controls the degree of the splines used, i.e. order=1
    # stands for linear interpolation.
    for ml in range(data3D.shape[0]):
        data = data3D[ml, :, :]
        curtain[ml, :] = map_coordinates(data, ind_coords, order=1)

    return curtain


def interpolate_vertsec3(data3D, data3D_lats, data3D_lons, lats, lons):
    """
    Interpolate curtain[z,pos] (curtain[level,pos]) from data3D[z,y,x]
    (data3D[level,lat,lon]).

    This method is based on scipy.ndimage.map_coordinates().

    data3D can be on an IRREGULAR lat/lon grid, coordinates given by lats, lons.
    The lats, lons arrays can have arbitrary order, they do not have to be uniform.
    """
    # Create an empty field to accomodate the curtain.
    curtain = np.zeros([data3D.shape[0], len(lats)])

    # Transform lat/lon values to array index space. This is necessary to use
    # scipy.ndimage.map_coordinates().
    interp_lat = interp1d(data3D_lats, np.arange(len(data3D_lats)), bounds_error=False)
    ind_lats = interp_lat(lats)
    interp_lon = interp1d(data3D_lons, np.arange(len(data3D_lons)), bounds_error=False)
    ind_lons = interp_lon(lons)
    ind_coords = np.array([ind_lats, ind_lons])

    # One horizontal interpolation for each model level. The order
    # parameter controls the degree of the splines used, i.e. order=1
    # stands for linear interpolation.
    for ml in range(data3D.shape[0]):
        data = data3D[ml, :, :]
        curtain[ml, :] = map_coordinates(data, ind_coords, order=1)

    curtain[:, np.isnan(ind_lats) | np.isnan(ind_lons)] = np.nan
    return np.ma.masked_invalid(curtain)


# Satellite Track Predictions

def read_nasa_satellite_prediction(fname):
    """Read a text file as downloaded from the NASA satellite prediction tool.

    This method reads satellite overpass predictions in ASCII format as
    downloaded from http://www-air.larc.nasa.gov/tools/predict.htm.

    Returns a list of dictionaries with keys
      -- utc: Nx1 array with utc times as datetime objects
      -- satpos: Nx2 array with lon/lat (x/y) of satellite positions
      -- heading: Nx1 array with satellite headings in degrees
      -- swath_left: Nx2 array with lon/lat of left swath boundary
      -- swath_right: Nx2 array with lon/lat of right swath boundary
    Each dictionary represents a separate overpass.

    All arrays are masked arrays, note that missing values are common. Filter
    out missing values with numpy.ma.compress_rows().

    NOTE: ****** LON in the 'predict' files seems to be wrong --> needs to be
                 multiplied by -1. ******
    """
    # Read the file into a list of strings.
    satfile = open(fname, 'r')
    satlines = satfile.readlines()
    satfile.close()

    # Determine the date from the first line.
    date = dt.strptime(satlines[0].split()[0], "%Y/%m/%d")
    basedate = dt.strptime("", "")

    # "result" will store the individual overpass segments.
    result = []
    segment = {"utc": [], "satpos": [], "heading": [],
               "swath_left": [], "swath_right": []}

    # Define a time difference that specifies when to start a new segment.
    # If the time between to subsequent points in the file is larger than
    # this time, a new segment will be started.
    seg_diff_time = datetime.timedelta(minutes=10)

    # Loop over data lines. Either append point to current segment or start
    # new segment. Before storing segments to the "result" list, convert
    # to masked arrays.
    for line in satlines[2:]:
        values = line.split()
        time = date + (dt.strptime(values[0], "%H:%M:%S") - basedate)

        if len(segment["utc"]) == 0 or (time - segment["utc"][-1]) < seg_diff_time:
            segment["utc"].append(time)
            segment["satpos"].append([-1. * float(values[2]), float(values[1])])
            segment["heading"].append(float(values[3]))
            if len(values) == 8:
                segment["swath_left"].append([-1. * float(values[5]), float(values[4])])
                segment["swath_right"].append([-1. * float(values[7]), float(values[6])])
            else:
                # TODO 20100504: workaround for instruments without swath
                segment["swath_left"].append([-1. * float(values[2]), float(values[1])])
                segment["swath_right"].append([-1. * float(values[2]), float(values[1])])

        else:
            segment["utc"] = np.array(segment["utc"])
            segment["satpos"] = np.ma.masked_equal(segment["satpos"], -999.)
            segment["heading"] = np.ma.masked_equal(segment["heading"], -999.)
            segment["swath_left"] = np.ma.masked_equal(segment["swath_left"], -999.)
            segment["swath_right"] = np.ma.masked_equal(segment["swath_right"], -999.)
            result.append(segment)
            segment = {"utc": [], "satpos": [], "heading": [],
                       "swath_left": [], "swath_right": []}

    return result
