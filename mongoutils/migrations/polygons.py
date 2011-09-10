from pymongo.connection import Connection
from django.template.defaultfilters import slugify

from dashboard.scripts.calculate_centroid import compute_centroid

from settings import MONGODB

connection = Connection(MONGODB['host'])
db = connection[MONGODB['db']]

def clean_up(filter = {}):
    """
    Clean up the raw SF polygon import.
    """

    polygons = db.polygons.find(filter)

    for polygon in polygons:

        db.polygons.update({ '_id' : polygon['_id']},
                { '$set' : { 'properties' : 
                    { 'name' : polygon['properties']['NBRHOOD'],
                        'type' : 'neighborhood',
                        'slug' : slugify(polygon['properties']['NBRHOOD'])
                        } } } )

def add_indexes():
    """
    Add polygon indexes.
    """
    db.polygons.ensure_index([('geometry.coordinates.0', '2d')])

def find_centroid(filter = {}):
    """
    Find the centroid of the polygons
    """
    polygons = db.polygons.find(filter)

    for polygon in polygons:
        centroid = compute_centroid(polygon['geometry']['coordinates'][0])
        db.polygons.update({ '_id' : polygon['_id']},
                { '$set' : {'properties.centroid' : centroid }})

if __name__ == "__main__":
    clean_up()
    add_indexes()
    find_centroid()