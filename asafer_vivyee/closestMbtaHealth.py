import urllib.request
import json
import dml
import prov.model
import datetime
import uuid
import requests
import math

class closestMbtaHealth(dml.Algorithm):
    contributor = 'asafer_vivyee'
    reads = ['asafer_vivyee.healthy_locations', 'asafer_vivyee.mbta_routes']
    writes = ['asafer_vivyee.health_mbta']

    @staticmethod
    def select(R, s):
        return [t for t in R if s(t)]

    @staticmethod
    def aggregate(R, f):
        keys = [r[0] for r in R]
        return [(key, f([v for (k,v) in R if k == key])) for key in keys]

    @staticmethod
    def project(R, p):
        return [p(t) for t in R]

    @staticmethod
    def product(R, S):
        return [(t,u) for t in R for u in S]

    @staticmethod
    def calculate_distance(info):
        healthy, stop = info
        healthy_lat = float(healthy['location'][0])
        healthy_lon = float(healthy['location'][1])

        stop_lat = float(stop['stop_lat'])
        stop_lon = float(stop['stop_lon'])

        # formula from: http://andrew.hedges.name/experiments/haversine/
        # used R = 3961 miles
        dlon = healthy_lon - stop_lon
        dlat = healthy_lat - stop_lat
        a = math.sin(dlat/2)**2 + (math.cos(stop_lat) * math.cos(healthy_lat) * math.sin(dlon/2)**2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        d = 3961 * c
        return (healthy, (stop, d))

    @staticmethod
    def close_stop(info):
        return info[1][1] <= 2

    @staticmethod
    def convert_to_dictionary(info):
            return {'healthy_locations': info[0], 'stops': info[1]}

    @staticmethod
    def get_stops(info):
        stops = []
        for i in info['path']['direction']:
            stops += i['stop']
        return stops

    @staticmethod
    def execute(trial = False):
        startTime = datetime.datetime.now()

        #set up the datebase connection
        client = dml.pymongo.MongoClient()
        repo = client.repo
        repo.authenticate('asafer_vivyee','asafer_vivyee')

        #loads
        healthy_locations = repo['asafer_vivyee.healthy_locations']
        mbta_routes = repo['asafer_vivyee.mbta_routes']

        repo.dropCollection('asafer_vivyee.health_mbta')
        repo.createCollection('asafer_vivyee.health_mbta')

        # get all stops by location
        stops = closestMbtaHealth.project(mbta_routes.find(), closestMbtaHealth.get_stops)
        all_stops = []
        for stop in stops:
            all_stops += stop

        # map all stops with all locations
        all_combos = closestMbtaHealth.product(healthy_locations.find(), all_stops)

        # calculate distance for healthy loc b/w every stop
        distances = closestMbtaHealth.project(all_combos, closestMbtaHealth.calculate_distance)
        
        # find all places within a mile
        filtered_stops = closestMbtaHealth.select(distances, closestMbtaHealth.close_stop)

        # aggregate stops by location they're close to
        stops_by_location = closestMbtaHealth.aggregate(filtered_stops, lambda x: x)

        # convert to dictionary format
        stops_by_location_dict = closestMbtaHealth.project(stops_by_location, closestMbtaHealth.convert_to_dictionary)

        repo['asafer_vivyee.health_mbta'].insert_many(stops_by_location_dict)
        repo['asafer_vivyee.health_mbta'].metadata({'complete': True})

        print('all uploaded')

        endTime = datetime.datetime.now

        return {"start":startTime, "end":endTime}


    @staticmethod
    def provenance(doc = prov.model.ProvDocument(), startTime = None, endTime = None):
        # Set up the database connection.
        client = dml.pymongo.MongoClient()
        repo = client.repo
        repo.authenticate('asafer_vivyee', 'asafer_vivyee')
        doc.add_namespace('alg', 'http://datamechanics.io/algorithm/') # The scripts are in <folder>#<filename> format.
        doc.add_namespace('dat', 'http://datamechanics.io/data/') # The data sets are in <user>#<collection> format.
        doc.add_namespace('ont', 'http://datamechanics.io/ontology#') # 'Extension', 'DataResource', 'DataSet', 'Retrieval', 'Query', or 'Computation'.
        doc.add_namespace('log', 'http://datamechanics.io/log/') # The event log.

        this_script = doc.agent('alg:asafer_vivyee#health_mbta', {prov.model.PROV_TYPE:prov.model.PROV['SoftwareAgent'], 'ont:Extension':'py'})

        # datamechanics.io data
        healthy_locations_resource = doc.entity('dat:asafer_vivyee', {'prov:label': 'Aggregate of Health related locations', prov.model.PROV_TYPE:'ont:DataResource'})
        mbta_routes_resource = doc.entity('dat:asafer_vivyee', {'prov:label': 'MBTA Routes', prov.model.PROV_TYPE:'ont:DataResource', 'ont:Extension':'json'})
        health_mbta_resource = doc.entity('dat:asafer_vivyee', {'prov:label': 'Closest MBTA stops to Health locations', prov.model.PROV_TYPE:'ont:DataResource'})

        get_healthy_locations = doc.activity('log:uuid' + str(uuid.uuid4()), startTime, endTime) # LOL
        get_mbta_routes = doc.activity('log:uuid' + str(uuid.uuid4()), startTime, endTime)
        get_health_mbta = doc.activity('log:uuid' + str(uuid.uuid4()), startTime, endTime)

        doc.wasAssociatedWith(get_healthy_locations, this_script)
        doc.wasAssociatedWith(get_mbta_routes, this_script)
        doc.wasAssociatedWith(get_health_mbta, this_script)

        doc.usage(get_healthy_locations, healthy_locations_resource, startTime, None, {prov.model.PROV_TYPE:'ont:Retrieval'})
        doc.usage(get_mbta_routes, mbta_routes_resource, startTime, None, {prov.model.PROV_TYPE:'ont:Retrieval'})
        doc.usage(get_health_mbta, health_mbta_resource, startTime, None, {prov.model.PROV_TYPE:'ont:Retrieval'})

        healthy_locations = doc.entity('dat:asafer_vivyee#healthy_locations', {prov.model.PROV_LABEL:'Aggregate of Health related locations', prov.model.PROV_TYPE:'ont:DataSet'})
        doc.wasAttributedTo(healthy_locations, this_script)
        doc.wasGeneratedBy(healthy_locations, get_healthy_locations, endTime)
        doc.wasDerivedFrom(healthy_locations, healthy_locations_resource, get_healthy_locations, get_healthy_locations, get_healthy_locations)

        mbta_routes = doc.entity('dat:asafer_vivyee#mbta_routes', {prov.model.PROV_LABEL:'MBTA Routes', prov.model.PROV_TYPE:'ont:DataSet'})
        doc.wasAttributedTo(mbta_routes, this_script)
        doc.wasGeneratedBy(mbta_routes, get_mbta_routes, endTime)
        doc.wasDerivedFrom(mbta_routes, mbta_routes_resource, get_mbta_routes, get_mbta_routes, get_mbta_routes)

        health_mbta = doc.entity('dat:asafer_vivyee#health_mbta', {prov.model.PROV_LABEL:'Closest MBTA stops to Health locations', prov.model.PROV_TYPE:'ont:DataSet'})
        doc.wasAttributedTo(health_mbta, this_script)
        doc.wasGeneratedBy(health_mbta, get_health_mbta, endTime)
        doc.wasDerivedFrom(health_mbta, health_mbta_resource, get_health_mbta, get_health_mbta, get_health_mbta)

        repo.logout()

        return doc


closestMbtaHealth.execute()
doc = closestMbtaHealth.provenance()
print(doc.get_provn())
print(json.dumps(json.loads(doc.serialize()), indent=4))
        






