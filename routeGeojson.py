#!/usr/bin/python
# -*- mode: python; indent-tabs-mode: nil; tab-width: 2 -*-
#----------------------------------------------------------------
# routeGeojson - routes from GeoJSON with OSM data, and generates a
# GeoJSON file containing the results. Input file must be in WGS84 CRS.
#
#------------------------------------------------------
# Usage: 
#  routeGeojson.py [input_file] -o [output_file]
#------------------------------------------------------
# Copyright 2007-2008, Oliver White
# Copyright 2016, Michael Farrell
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#------------------------------------------------------

import argparse
import geojson
from route import Router
from loadOsm import LoadOsm

def pythagoras(x1, y1, x2, y2):
  # Not really correct for world geometry, but good enough for what we're doing
  # with it.
  x_d = abs(x1 - x2)
  y_d = abs(y1 - y2)
  return ((x_d ** 2) + (y_d ** 2)) ** 0.5
  


def route_geojson(input_f, output_f, mode='foot', local_planet=None):
  osmdata = LoadOsm(mode)
  
  if local_planet != None:
    osmdata.getArea = lambda lat, lon: None
    osmdata.api = None
    print('loading osm data (this may take a while)...')
    osmdata.loadOsm(local_planet)

  print('starting router...')
  router = Router(osmdata)

  print('processing shapes...')
  # First load up the shapes
  layer = geojson.load(input_f)
  non_linestring = 0
  not_two_points = 0
  unsuccessful = 0
  successful = 0
  very_long = 0
  first = True

  output_f.write('{"crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}, "type": "FeatureCollection", "features": [\n')
  
  for feature in layer.features:
    if feature.geometry.type != 'LineString':
      # Not a LineString, skip!
      non_linestring += 1
      continue

    geometry = list(feature.geometry.coordinates)
    if len(geometry) != 2:
      # LineString with other than two points, skip!
      not_two_points += 1
      continue

    if pythagoras(*geometry[0] + geometry[1]) > 1.0:
      very_long += 1
      continue

    # Now find a route. Data has x,y coordinates, but function is y,x, so
    # reverse the parameters.
    start = osmdata.findNode(*geometry[0][::-1])
    end = osmdata.findNode(*geometry[1][::-1])
    
    result, route = router.doRoute(start, end)
    if result != 'success':
      unsuccessful += 1
      continue
    
    routed_geometry = []
    for node_id in route:
      node = osmdata.rnodes[node_id]
      routed_geometry.append((node[1], node[0]))

    new_feature = geojson.Feature(
      geometry=geojson.LineString(coordinates=routed_geometry),
      properties=feature.properties,
      id=feature.id,
    )
    
    if not first:
      output_f.write(',\n')
    first = False

    geojson.dump(new_feature, output_f)
    output_f.flush()
    successful += 1
  output_f.write('\n]}\n')
  output_f.close()

  print('%d LineStrings routed. Errors: %d non-linestring(s), %d linestring(s) with !=2 points, %d very long, %d unsuccessful routings' % (successful, non_linestring, not_two_points, very_long, unsuccessful))


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('input', nargs=1, type=argparse.FileType('rb'))
  parser.add_argument('-o', '--output', required=True, type=argparse.FileType('wb'))
  parser.add_argument('-m', '--mode', default='foot',
    help='Mode of transportation to route on [default: %(default)s]')
  parser.add_argument('-l', '--local-planet',
    help='Use a local OSM XML file. Make sure to crop it for good performance!')
  options = parser.parse_args()
  route_geojson(options.input[0], options.output, options.mode, options.local_planet)

if __name__ == "__main__":  
  main()

