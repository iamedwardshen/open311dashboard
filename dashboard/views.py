try:
    import simplejson as json
except:
    import json

import datetime
import re
import urllib
import urllib2

from django.template import Context
from django.shortcuts import render # , redirect
from django.http import HttpResponse

from pymongo.connection import Connection
import bson.json_util

from settings import MONGODB
from mongoutils.mapreduce import open311stats
from mongoutils.api import api_query

# Set up the database connection as a global variable
connection = Connection(MONGODB['host'])
db = connection[MONGODB['db']]

def index(request, geography=None, is_json=False):
    """
    Homepage view. Can also return json for the city or neighborhoods.
    """
    c = Context({'test' : "Hello World!"})
    return render(request, 'index.html', c)

# Neighborhood specific pages.
def neighborhood_list(request):
    """
    List the neighborhoods.
    """
    # neighborhoods = Geography.objects.all()
    neighborhoods = db.polygons.find({ 'properties.type' : 'neighborhood' })

    c = Context({
        'neighborhoods': neighborhoods
        })

    return render(request, 'neighborhood_list.html', c)


def neighborhood_detail(request, neighborhood_slug):
    """

    Show detail for a specific neighborhood. Uses templates/geo_detail.html

    """
    neighborhood = db.polygons \
            .find_one({ 'properties.slug' : neighborhood_slug})
    request_dict = {'coordinates' :
        { '$within' : {
            "$polygon" : neighborhood['geometry']['coordinates'][0] }}
        }

    # Set the dictionary to do within specific item.
    today = datetime.datetime.now()
    year_ago = today + datetime.timedelta(-365)
    request_dict['requested_datetime'] = {
            '$gte' : year_ago,
            '$lte' : today
            }

    # Open requests
    open_request_dict = request_dict.copy()
    open_request_dict['status'] = "Open"
    open_count = db.requests.find(open_request_dict).count()

    # Top Requests
    service_counts = open311stats.count(['service_name'], request_dict)
    top_services = sorted(service_counts,
            key=lambda service: -service['value']['count'])
    for service in top_services:
        service["id"] = service["_id"]
        service["id"]["service_name"] = service["id"]["service_name"] \
                .replace("_", " ")
        service['value']['count'] = int(service['value']['count'])

    # Average response time.
    avg_time = open311stats.avg_response_time(request_dict)
    days = avg_time[0]['value']['avg_time'] / 86400000

    c = Context({
        'neighborhood' : neighborhood,
        'avg_response': int(days),
        'bbox' : json.dumps(neighborhood['properties']['bbox']),
        'top_services': top_services[0:9],
        'open_requests': open_count
        })

    return render(request, 'neighborhood_test.html', c)

# Street specific pages.
def street_list(request):
    """

    List the top 10 streets by open service requests.

    """
    streets = db.streets.find({}).limit(25)
    c = Context({
        'streets' : streets
        })

    return render(request, 'street_list.html', c)

def street_specific_list(request, street_name):
    """
    View all of the blocks on a street.
    """
    streets = db.streets.find({ 'properties.slug' : street_name})

    c = Context({ 'streets' : streets })
    return render(request, 'street_list.html', c)


def street_view(request, street_name, min_val, max_val):
    """
    View details for a specific street. Renders geo_detail.html like
    neighborhood_detail does.
    """
    street = db.streets.find_one( {
        'properties.slug' : street_name,
        'properties.min' : int(min_val),
        'properties.max' : int(max_val) }
        )

    c = Context({
        'street': street,
        'json' : json.dumps(street['geometry'])
        })

    return render(request, 'street_test.html', c)

def api_handler(request, collection):
    """
    Serialize values returned from the database.
    """
    resp = []
    lookup = {}
    query_params = {}
    get_params = request.GET.copy()
    geo_collections = ['polygons', 'streets']
    geo = False
    if collection in geo_collections:
        geo = True

    # How big should the page be?
    if 'page_size' in get_params:
        query_params['limit'] = int(get_params['page_size'])
        del get_params['page_size']
    else:
        query_params['limit'] = 1000

    # What page number?
    if 'page' in get_params:
        query_params['skip'] = (int(get_params.get('page'))-1) * \
            query_params['limit']
        del get_params['page']
    else:
        query_params['skip'] = 0

    # Define the sort key.
    if 'sort' in get_params:
        sort = get_params.get('sort')
        if re.search('^-', sort):
            order = -1
            sort = re.sub('^-', '', sort)
        else:
            order = 1

        query_params['sort'] = [(sort, order)]
        print query_params['sort']
        del get_params['sort']

    # Form up the query dictionary.
    lookup = api_query(collection, get_params, geo)

    # Run the query.
    try:
        results = db[collection].find(lookup,
                **query_params)
    except:
        return HttpResponse('Error',status=400)

    # Clean up the results
    for row in results:
        del row['_id']
        resp.append(row)

        # TODO: Clean up datetimes.

    if geo is True:
        resp = { 'type' : "FeatureCollection",
                'features' : resp }

    json_resp = json.dumps(resp, default=bson.json_util.default)
    return HttpResponse(json_resp, 'application/json')

def api_count_handler(request):
    """
    API endpoint for mapreduce counts.
    """
    get_params = request.GET.copy()
    after_params = {}

    try:
        keys = get_params['keys'].split(',')
        del(get_params['keys'])
    except:
        return HttpResponse('Error: No count keys defined.', status=400)

    # Store the sort order.
    if 'sort' in get_params:
        after_params['sort'] = get_params['sort']
        del(get_params['sort'])

    # Store page number
    if 'page' in get_params:
        after_params['page'] = get_params['page']
        del(get_params['page'])

    # Store page size
    if 'page_size' in get_params:
        after_params['page_size'] = get_params['page_size']
        del(get_params['page_size'])

    # Form up a query.
    query = api_query('requests', get_params)

    # Run the mapreduce
    try:
        count = open311stats.count(keys, query)
    except:
        return HttpResponse("Error", status=400)

    # Clean it up a little.
    clean_count = []
    for row in count:
        row = dict(row['_id'], **row['value'])
        clean_count.append(row)

    # Sort, page, size
    if 'sort' in after_params:
        sort = after_params.get('sort')

        # Regular expression search for negative sorting.
        if re.search('^-', sort):
            reverse = True
            sort = re.sub('^-', '', sort)
        else:
            reverse = False
        print "Triggered"

        clean_count = sorted(clean_count, key=lambda count: count[sort], reverse=reverse)

    begin = 0
    if 'page_size' in after_params:
        page_size = int(after_params['page_size'])
    else:
        page_size = 30

    if 'page' in after_params:
        begin = (int(after_params['page']) - 1) * page_size
        end = int(after_params['page']) * page_size
    else:
        end = page_size

    clean_count = clean_count[begin:end]

    json_resp = json.dumps(clean_count, default=bson.json_util.default)
    return HttpResponse(json_resp, 'application/json')

def api_avg_response_handler(request):
    """ Average response things. """
    get_params = request.GET.copy()
    query = api_query('requests', get_params)

    avg_response = open311stats.avg_response_time(query)
    json_resp = json.dumps(avg_response, default=bson.json_util.default)
    return HttpResponse(json_resp, 'application/json')

# Search for an address!
def street_search(request):
    """
    Do a San Francisco specific geocode and then match that against our street
    centerline data.
    """
    query = request.GET.get('q')
    lat = request.GET.get('lat')
    lon = request.GET.get('lng')
    if not query:
        # They haven't searched for anything.
        return render(request, 'search.html')
    elif query and not lat:
        # Lookup the search string with Yahoo!
        url = "http://where.yahooapis.com/geocode"
        params = {"addr": query,
                "line2": "San Francisco, CA",
                "flags": "J",
                "appid": "1I9Jh.3V34HMiBXzxZRYmx.DO1JfVJtKh7uvDTJ4R0dRXnMnswRHXbai1NFdTzvC" }

        query_params = urllib.urlencode(params)
        data = urllib2.urlopen("%s?%s" % (url, query_params)).read()

        temp_json = json.loads(data)

        if temp_json['ResultSet']['Results'][0]['quality'] > 50:
            lon = temp_json['ResultSet']['Results'][0]["longitude"]
            lat = temp_json['ResultSet']['Results'][0]["latitude"]
        else:
            lat, lon = None, None

    """ if lat and lon:
        nearest_street = Street.objects \
                               .filter(line__dwithin=(point, D(m=100))) \
                               .distance(point).order_by('distance')[:1]
        try:
            return redirect(nearest_street[0])
        except IndexError:
            pass
    c = Context({'error': True})
    return render(request, 'search.html', c) """


def map(request):
    """
    Simply render the map.

    TODO: Get the centroid and bounding box of the city and set that. (See
    neighborhood_detail and geo_detail.html for how this would look)
    """
    return render(request, 'map.html')
