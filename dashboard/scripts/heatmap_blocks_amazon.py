#works!
import urllib
import json as simplejson
import math
import pprint
import psycopg2 as pg

service_requests_url = 'input/service_requests.json'
blocks_url = 'input/sf_blocks.json'

def connect_with_amazon(**kwargs):
  conn = pg.connect(**kwargs)
  cursor = conn.cursor()
  cursor.execute("""select lat, long from dashboard_request where lat > 0 and
                    requested_datetime > '12-31-2010'""")

  return cursor.fetchall() #returns a list
#def compute_rect_bounds():

def inside_rect_bounds(polygon_bounds,request_location):
  
  #initialize
  lon_init = polygon_bounds[0][0][0]
  lat_init = polygon_bounds[0][0][1]
  
  minLon = lon_init
  maxLon = lon_init
  minLat = lat_init
  maxLat = lat_init
  
  request_lat = request_location[0]
  request_lon = request_location[1]
  
  for i in xrange(1,len(polygon_bounds[0])):
    if minLon > polygon_bounds[0][i][0]:
      minLon = polygon_bounds[0][i][0]
    if maxLon < polygon_bounds[0][i][0]:
      maxLon = polygon_bounds[0][i][0]
    if minLat > polygon_bounds[0][i][1]:
      minLat = polygon_bounds[0][i][1]
    if maxLat < polygon_bounds[0][i][1]:
      maxLat = polygon_bounds[0][i][1]
  
  #rect_bounds = [minLon,maxLon,minLat,maxLat]
  if request_lat >= minLat and request_lat <= maxLat and request_lon >= minLon and request_lon <= maxLon:
    return True
  else:
    return False

def inside_polygon(polygon_bounds,request_location):
  #polygon_bounds is an array
  #request_location is an array, lat/long
  request_lat = request_location[0]
  request_lon = request_location[1]
  
  vertices_count = len(polygon_bounds[0])
  inside = False
  #i = 0
  j = vertices_count - 1
  
  if inside_rect_bounds(polygon_bounds,request_location) == False:
    return False
  else:
    for i in xrange(vertices_count):
      vertexA = polygon_bounds[0][i]
      vertexB = polygon_bounds[0][j]
      
      if (vertexA[0] < request_lon and vertexB[0] >= request_lon) or (vertexB[0] < request_lon and vertexA[0] >= request_lon):
        if vertexA[1] + (((request_lon - vertexA[0]) / (vertexB[0] - vertexA[0])) * (vertexB[1] - vertexA[1])) < request_lat:
          inside = not inside
      j = i
    return inside

#load in data
#service_requests = simplejson.load(urllib.urlopen(service_requests_url))
service_requests = connect_with_amazon(host='', database='', user='',password='')
print service_requests[0][0]

blocks = simplejson.load(urllib.urlopen(blocks_url))

#block_totals = [] #maps to 7386 blocks
block_totals = [0]*len(blocks["features"])

for i in xrange(len(service_requests)):
  print i
  request_lat = service_requests[i][0]
  print request_lat
  request_lon = service_requests[i][1]
  request_location = [float(request_lat),float(request_lon)]
  
  #print request_location
  
  if math.fabs(request_location[0]) != 0 or math.fabs(request_location[1]) != 0:
    for j in xrange(len(blocks["features"])):
      polygon_bounds = blocks["features"][j]["geometry"]["coordinates"]
      
      if inside_polygon(polygon_bounds,request_location) == True:
        block_totals[j] = block_totals[j] + 1
      else:
        continue
  #print block_totals

print 'block_totals: ', block_totals

for i in xrange(len(block_totals)):
  blocks["features"][i]["properties"]["count"] = block_totals[i]
  
f = open('output/block_with_counts_pg.json','w')
simplejson.dump(blocks,f)
f.close()
