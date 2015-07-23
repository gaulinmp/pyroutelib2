#!/etc/env python
#----------------------------------------------------------------
# load OSM data file into memory
#
#------------------------------------------------------
# Copyright 2007, Oliver White
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
# Changelog:
#  2007-11-04  OJW  Modified from pyroute.py
#  2007-11-05  OJW  Multiple forms of transport
#------------------------------------------------------
import os
import re
import sys
import osmapi
import xml.etree.ElementTree as etree
from datetime import datetime

# from pyroutelib2 import (tiledata, tilenames, weights)
import tiledata
import tilenames
import weights

class LoadOsm(object):
  """Parse an OSM file looking for routing information, and do routing with it"""
  def __init__(self, transport):
    """Initialise an OSM-file parser"""
    self.routing = {}
    self.rnodes = {}
    self.transport = transport
    self.tiles = {}
    self.weights = weights.RoutingWeights()
    self.api = osmapi.OsmApi(api="api.openstreetmap.org")
  
  def getArea(self, lat, lon):
    """Download data in the vicinity of a lat/long.
    Return filename to existing or newly downloaded .osm file."""
    
    z = tiledata.DownloadLevel()
    (x,y) = tilenames.tileXY(lat, lon, z)

    tileID = '%d,%d'%(x,y)
    if(self.tiles.get(tileID,False)):
      #print "Already got %s" % tileID
      return
    self.tiles[tileID] = True
    
    filename = tiledata.GetOsmTileData(z,x,y)
    #print "Loading %d,%d at z%d from %s" % (x,y,z,filename)
    return(self.loadOsm(filename))

  def _ParseDate(self, DateString):
    result = DateString
    try:
      result = datetime.strptime(DateString, "%Y-%m-%d %H:%M:%S UTC")
    except:
      try:
        result = datetime.strptime(DateString, "%Y-%m-%dT%H:%M:%SZ")
      except:
        pass
      return result

  def getElementAttributes(self, element):  # noqa
      result = {}
      for k, v in element.attrib.items():
        if k == "uid":
            v = int(v)
        elif k == "changeset":
            v = int(v)
        elif k == "version":
            v = int(v)
        elif k == "id":
            v = int(v)
        elif k == "lat":
            v = float(v)
        elif k == "lon":
            v = float(v)
        elif k == "open":
            v = (v == "true")
        elif k == "visible":
            v = (v == "true")
        elif k == "ref":
            v = int(v)
        elif k == "comments_count":
            v = int(v)
        elif k == "timestamp":
            v = self._ParseDate(v)
        elif k == "created_at":
            v = self._ParseDate(v)
        elif k == "closed_at":
            v = self._ParseDate(v)
        elif k == "date":
            v = self._ParseDate(v)
        result[k] = v
      return result

  def getElementTags(self, element):
    result = {}
    for child in element:
      if child.tag =="tag":
        k = child.attrib["k"]
        v = child.attrib["v"]
        result[k] = v
    return result

  def parseOsmFile(self, filename):
    result = []
    with open(filename, "r") as f:
      for event, elem in etree.iterparse(f): # events=['end']
        if elem.tag == "node":
          data = self.getElementAttributes(elem)
          data["tag"] = self.getElementTags(elem)
          result.append({
            "type": "node",
            "data": data
          })
        elif elem.tag == "way":
          data = self.getElementAttributes(elem)
          data["tag"] = self.getElementTags(elem)
          data["nd"] = []
          for child in elem:
            if child.tag == "nd":
              data["nd"].append(int(child.attrib["ref"]))
          result.append({
            "type": "way",
            "data": data
          })
        elif elem.tag == "relation":
          data = self.getElementAttributes(elem)
          data["tag"] = self.getElementTags(elem)
          data["member"] = []
          for child in elem:
            if child.tag == " member":
              data["member"].append(self.getElementAttributes(child))
          result.append({
            "type": "relation",
            "data": data
          })
          elem.clear()
    return result
    

  def loadOsm(self, filename):
    if(not os.path.exists(filename)):
      print("No such data file %s" % filename)
      return(False)

    nodes, ways = {}, {}

    data = self.parseOsmFile(filename)
    # data = [{ type: node|way|relation, data: {}},...]

    for x in data:
      try:
        if x['type'] == 'node':
          nodes[x['data']['id']] = x['data']
        elif x['type'] == 'way':
          ways[x['data']['id']] = x['data']
        else:
          continue
      except KeyError:
        # Don't care about bad data (no type/data key)
        continue
    #end for x in data
    for way_id, way_data in ways.items():
      way_nodes = []
      for nd in way_data['nd']:
        if nd not in nodes:
          continue
        way_nodes.append([nodes[nd]['id'], nodes[nd]['lat'], nodes[nd]['lon']])
      self.storeWay(way_id, way_data['tag'], way_nodes)
      
    return(True)
  
  def storeWay(self, wayID, tags, nodes):
    highway = self.equivalent(tags.get('highway', ''))
    railway = self.equivalent(tags.get('railway', ''))
    oneway = tags.get('oneway', '')
    reversible = not oneway in('yes','true','1')

    # Calculate what vehicles can use this route
    # TODO: just use getWeight != 0
    access = {}
    access['cycle'] = highway in ('primary','secondary','tertiary','unclassified','minor','cycleway','residential', 'track','service')
    access['car'] = highway in ('motorway','trunk','primary','secondary','tertiary','unclassified','minor','residential', 'service')
    access['train'] = railway in('rail','light_rail','subway')
    access['foot'] = access['cycle'] or highway in('footway','steps')
    access['horse'] = highway in ('track','unclassified','bridleway')

    # Store routing information
    last = [None,None,None]

    if(wayID == 41 and 0):
      print(nodes)
      sys.exit()
    for node in nodes:
      (node_id,x,y) = node
      if last[0]:
        if(access[self.transport]):
          weight = self.weights.get(self.transport, highway)
          self.addLink(last[0], node_id, weight)
          self.makeNodeRouteable(last)
          if reversible or self.transport == 'foot':
            self.addLink(node_id, last[0], weight)
            self.makeNodeRouteable(node)
      last = node

  def makeNodeRouteable(self,node):
    self.rnodes[node[0]] = [node[1],node[2]]
    
  def addLink(self,fr,to, weight=1):
    """Add a routeable edge to the scenario"""
    try:
      if to in list(self.routing[fr].keys()):
        return
      self.routing[fr][to] = weight
    except KeyError:
      self.routing[fr] = {to: weight}

  def equivalent(self,tag):
    """Simplifies a bunch of tags to nearly-equivalent ones"""
    equivalent = { \
      "primary_link":"primary",
      "trunk":"primary",
      "trunk_link":"primary",
      "secondary_link":"secondary",
      "tertiary":"secondary",
      "tertiary_link":"secondary",
      "residential":"unclassified",
      "minor":"unclassified",
      "steps":"footway",
      "driveway":"service",
      "pedestrian":"footway",
      "bridleway":"cycleway",
      "track":"cycleway",
      "arcade":"footway",
      "canal":"river",
      "riverbank":"river",
      "lake":"river",
      "light_rail":"railway"
      }
    try:
      return(equivalent[tag])
    except KeyError:
      return(tag)
    
  def findNode(self,lat,lon):
    """Find the nearest node that can be the start of a route"""
    self.getArea(lat,lon)
    maxDist = 1E+20
    nodeFound = None
    posFound = None
    for (node_id,pos) in list(self.rnodes.items()):
      dy = pos[0] - lat
      dx = pos[1] - lon
      dist = dx * dx + dy * dy
      if(dist < maxDist):
        maxDist = dist
        nodeFound = node_id
        posFound = pos
    # print("found at %s"%str(posFound))
    return(nodeFound)
      
  def report(self):
    """Display some info about the loaded data"""
    print("Loaded %d nodes" % len(list(self.rnodes.keys())))
    print("Loaded %d %s routes" % (len(list(self.routing.keys())), self.transport))

# Parse the supplied OSM file
if __name__ == "__main__":
  data = LoadOsm("cycle")
  if(not data.getArea(29.738632, -95.404546)):
    print("Failed to get data")
  data.getArea(29.738632, -95.404546)
  data.report()

  print("Searching for node: found " + str(data.findNode(52.55291,-1.81824)))
