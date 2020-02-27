#!/usr/bin/env python

import requests
from requests.exceptions import HTTPError
import http.client as http_client
import urllib.parse
import json
import logging
import time
import datetime
import schedule
import re
import os

BASE_URL = 'https://login.herecomesthebus.com'
LOGIN_PATH = '/authenticate.aspx?action=login'
UPDATE_PATH = '/Map.aspx/RefreshMap'
OPENROUTE_API_URL = 'https://api.openrouteservice.org/v2/directions/driving-car'
BUS_STATE_DOMAIN = 'tracker'
BUS_STATE_ENTITY = 'school_bus'
TRACKER_STATE_ENTITY = 'bus_tracker'

options = {}

logging.basicConfig(
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')
logging.getLogger().setLevel(logging.INFO)
request_session = requests.Session()

hassio_token = os.getenv('HASSIO_TOKEN')

def sanitize(string):
    return re.sub('[^0-9a-zA-Z]+', '_', string)

def setup_logging():
    # Setup logging
    logging.info(os.environ.get('DEBUG'))

    if os.environ.get('DEBUG') != '' or options['debug']:
        http_client.HTTPConnection.debuglevel = 1
        logging.getLogger().setLevel(logging.DEBUG)
        requests_log = logging.getLogger("requests.packages.urllib3")
        requests_log.setLevel(logging.DEBUG)
        requests_log.propagate = True

def parse_options():
    global options

    options_file = '/data/options.json'

    if not hassio_token:
        # We aren't running in HA
        options_file = './options.json'

    with open(options_file) as json_file:
        data = json.load(json_file)
        options = data
    
    logging.debug(options)

def update_ha_state(entity, state):

    if not hassio_token: return

    url = 'http://hassio/homeassistant/api/states/{}.{}'.format(BUS_STATE_DOMAIN, entity)
    headers = {
        'Authorization': 'Bearer {}'.format(os.environ.get('HASSIO_TOKEN')),
        'Content-Type': 'application/json',
    }
    payload = {
        "state": state
    }

    response = requests.post(url, headers=headers, data=json.dumps(payload))
    logging.debug(response.text)

def send_request(req_url, headers, params, payload):
    response = request_session.post(req_url, headers=headers, params=params, data=payload, timeout=10)
    return response

def parse_legacy_ids(content):
    logging.debug("Parsing legacyIDs")
    matches = re.findall(r'<option value="([a-z0-9]{8}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{12})">([a-zA-Z ]+)</option>', content)
    for match in matches:
        for child in options['children']:
            if child['name'] == match[1]:
                child['legacyID'] = match[0]
    logging.debug(options['children'])

def login():
    logging.info('Logging in to Here Comes the Bus')

    req_rul = urllib.parse.urljoin(BASE_URL, LOGIN_PATH)
    headers = {}
    params = {
        'action': 'login'
    }
    payload = {
        '__EVENTTARGET': '',
        '__EVENTARGUMENT': '',
        '__VIEWSTATE': '/wEPDwUKMTkxNzQ4NTU0OA9kFgJmD2QWAmYPZBYCAgEPZBYGAgEPEGQQFQMHZW5nbGlzaAhlc3Bhw7FvbAlmcmFuw6dhaXMVAwJlbgJlcwJmchQrAwNnZ2dkZAIDD2QWEAIBDxYCHgdWaXNpYmxlaBYCAgEPDxYEHghDc3NDbGFzcwUEbW50bB4EXyFTQgICZGQCAw8WAh8AaBYCAgEPDxYEHwEFBG1udGwfAgICZGQCBQ8WAh8AaBYCAgEPDxYEHwEFBG1udGwfAgICZGQCBw8WAh8AaBYCAgEPDxYEHwEFBG1udGwfAgICZGQCCQ8WAh8AaBYCAgEPDxYEHwEFBG1udGwfAgICZGQCCw8WAh8AaBYCAgEPDxYGHwEFBG1udGweC05hdmlnYXRlVXJsBS9odHRwOi8vaGVscC5oZXJlY29tZXN0aGVidXMuY29tL2VuL3N1cHBvcnQvaG9tZR8CAgJkZAIND2QWAgIBDw8WBB8BBQ1tbnRsIHNlbGVjdGVkHwICAmRkAg8PFgIfAGgWAgIBDw8WBB8BBQRtbnRsHwICAmRkAgUPZBYCAgMPZBYIAgEPZBYCZg8PFgIfAGhkZAICD2QWBgIGDw8WAh8DBR9+L1Bhc3N3b3JkUmV0cmlldmFsQ29uZmlybS5hc3B4ZGQCDQ8PFgIeBFRleHQFL1RoZSBlbWFpbCBhbmQgcGFzc3dvcmQgeW91IGVudGVyZWQgYXJlIGludmFsaWQuZGQCDg8PFgIfAGhkZAIDDxYCHwBoZAIFDw8WAh8DBRd+L3NpZ251cG9uYm9hcmRpbmcuYXNweGRkGAEFHl9fQ29udHJvbHNSZXF1aXJlUG9zdEJhY2tLZXlfXxYBBS1jdGwwMCRjdGwwMCRjcGhXcmFwcGVyJGNwaENvbnRlbnQkY2J4UmVtZW1iZXKVuV29Mn5SXRSoeAupRzAZHj/B8cB1rOjIR/dCVbHdnA==',
        '__VIEWSTATEGENERATOR': '094BBCBC',
        '__EVENTVALIDATION': '/wEdABNAsQu5L9pmEKcrVAM30O68Q7N1LV9W3LZraND5fxyQVWRPRa87HYnklD2kjNl+oT8Tp7BJXzuUOWUfD5eSKhWwLfJc1VSzmS8rqXemWiEDfjFV4TENDQwatqL5If0K3WDXcG7AQmDNZFyh1XBhzi3p/C+tX+iY1kWLyxOJDNLpjmzQscAErau61wZ49HCpfwilT1gd70QArlgEK7ouXgnfQSDK/X/HysKG+svPEUuFtCUfrIUA4w0BgMkDmDmtD6o8ypBMtseV43VrjV/2UPrM87NGSLKbhHNweYFA+WAyiUXzcmPgmn0Xv2eDuIyLq0P06wGtqT5NLxL9i0Vz+P29SI7U2kMgV5SOqI45WETjWTP7JUcVjp6dlRgvRsafBQWngXVd3SQMECDTCVGlA99ex+LIjvFLd1vjE52V1CovVrGswVJH8FItbl5kuDoAMBI=',
        'ctl00$ctl00$ddlLanguage': 'en',
        'ctl00$ctl00$cphWrapper$cphContent$tbxUserName': options['here_comes_the_bus_username'],
        'ctl00$ctl00$cphWrapper$cphContent$tbxPassword': options['here_comes_the_bus_password'],
        'ctl00$ctl00$cphWrapper$cphContent$tbxAccountNumber': options['here_comes_the_bus_school_code'],
        'ctl00$ctl00$cphWrapper$cphContent$cbxRemember': 'on',
        'ctl00$ctl00$cphWrapper$cphContent$btnAuthenticate': 'Log In',
        'ctl00$ctl00$ucMessageBox$tbxInput': ''
    }
    response = send_request(req_rul, headers, params, payload)
    if response.status_code == 200:
        logging.debug('Success!')
        parse_legacy_ids(response.text)
        return response
    else:
        raise Exception("Bad response: %s" % response.status_code)

def get_latest_location(child, timespan_id, attempt=0):

    logging.debug('getting latest location')

    req_rul = urllib.parse.urljoin(BASE_URL, UPDATE_PATH)
    headers = {
        'Accept-Encoding': 'gzip, deflate, br',
        'Content-Type': 'application/json; charset=UTF-8'
    }
    params = {}

    try:
        legacyID = child['legacyID']
    except KeyError:
        legacyID = ''
    
    payload = {
        'legacyID': legacyID,
        'name': child['name'],
        'timeSpanId': timespan_id,
        'wait': "false"
    }
    try:
        response = send_request(req_rul, headers, params, payload=json.dumps(payload))
        response.raise_for_status()
    except HTTPError as http_err:
        if(attempt > 0):
            logging.error('Failed to authenticate and get bus location')
            logging.error(f'HTTP error occurred: {http_err}')
        # Unauthorized so we need to login first
        elif(http_err.response.status_code == 401):
            login()
            return get_latest_location(child, timespan_id, attempt=1)
    except Exception as err:
        logging.error(f'Other error occurred: {err}, Retrying...')
        time.sleep(10)
        return get_latest_location(child, timespan_id)
    else:
        logging.debug('Success!')
        logging.debug(response.content)
        return parse_location_response(response)

def parse_location_response(resp):
    regex = re.compile(r'SetBusPushPin\((?P<lat>[-]?\d+(?:\.\d+)?),(?P<long>[-]?\d+(?:\.\d+)?)')
    data = json.loads(resp.content)
    matches = regex.search(data['d'])
    try:
        ret = { 'long': matches.group('long'), 'lat': matches.group('lat')}
    except AttributeError:
        ret = None
    
    return ret

def calculate_distance(location_from, location_to, attempts=0):
    headers = {
        'Authorization': options['openroute_api_key'],
        'Accept': 'application/json, application/geo+json, application/gpx+xml, img/png; charset=utf-8'
    }
    payload = {
        'coordinates':[location_from,location_to],
        'units': 'mi'
    }
    resp = requests.post(OPENROUTE_API_URL, headers=headers, json=payload)
    resp = json.loads(resp.text)

    try:
        return resp['routes'][0]['summary']['distance']
    except KeyError:
        logging.error("distance value not found in response: {}".format(resp))
        if attempts > 0:
            return "Unknown"
        return calculate_distance(location_from, location_to, attempts=1)

def is_am():
    dt = datetime.datetime.now()
    return dt.time() < datetime.time(12)

def time_in_range(start, end, x):
    """Return true if x is in the range [start, end]"""
    logging.debug("Checking time. start: {}, end: {}, x: {}".format(start, end, x))
    if start <= end:
        return start <= x <= end
    else:
        return start <= x or x <= end

def time_in_tracking_window(child):
    if is_am():
        start_time = datetime.datetime.strptime(child['start_tracking_time_am'], '%H:%M').time()
        stop_time = datetime.datetime.strptime(child['stop_tracking_time_am'], '%H:%M').time()
    else:
        start_time = datetime.datetime.strptime(child['start_tracking_time_pm'], '%H:%M').time()
        stop_time = datetime.datetime.strptime(child['stop_tracking_time_pm'], '%H:%M').time()

    return time_in_range(start_time, stop_time, datetime.datetime.now().time())

def check_distance(child):
    # Update Tracker State in HA
    update_ha_state(TRACKER_STATE_ENTITY, "Tracking")

    logging.debug('Checking the current distance of the bus for {}'.format(child['name']))

    logging.debug("Is AM: {}".format(is_am()))

    if is_am():
        timespan_id = '55632a13-35c5-4169-b872-f5abdc25df6a'
    else:
        timespan_id = '6e7a050e-0295-4200-8edc-3611bb5de1c1'

    if not time_in_tracking_window(child):
        logging.debug('Current time is not within the tracking window for {}'.format(child['name']))
        schedule.clear('tracking-tasks-{}'.format(sanitize(child['name'])))
        update_ha_state(TRACKER_STATE_ENTITY, "Not Tracking")
        return

    # Get the current location of the bus
    bus_location = get_latest_location(child, timespan_id)
    logging.debug('Bus Location for {}: {}'.format(child['name'], bus_location))
    
    if bus_location:
        # Calculate the distance. Bus[long,lat], Home[long,lat]
        distance = calculate_distance([bus_location['long'], bus_location['lat']],[options['home_location']['long'], options['home_location']['lat']])
    else:
        distance = "Unknown"

    # Send the distance to Home Assistant
    update_ha_state('{}_{}'.format(BUS_STATE_ENTITY, sanitize(child['name'])), distance)

    logging.debug('Bus Distance for {}: {}'.format(child['name'], distance))

def start_tracking(child):

    # Check the distance of the bus every tracker_interval seconds
    schedule.every(options['tracker_interval']).seconds.do(check_distance, child).tag('tracking-tasks-{}'.format(sanitize(child['name'])))

def schedule_trackers(child):
    # Set HA initial state
    update_ha_state('{}_{}'.format(BUS_STATE_ENTITY, sanitize(child['name'])), "Unknown")

    logging.info('Scheduling tracking jobs')

    # Weekday AM Trackers
    schedule.every().monday.at(child['start_tracking_time_am']).do(start_tracking, child)
    schedule.every().tuesday.at(child['start_tracking_time_am']).do(start_tracking, child)
    schedule.every().wednesday.at(child['start_tracking_time_am']).do(start_tracking, child)
    schedule.every().thursday.at(child['start_tracking_time_am']).do(start_tracking, child)
    schedule.every().friday.at(child['start_tracking_time_am']).do(start_tracking, child)

    # Weekday PM Trackers
    schedule.every().monday.at(child['start_tracking_time_pm']).do(start_tracking, child)
    schedule.every().tuesday.at(child['start_tracking_time_pm']).do(start_tracking, child)
    schedule.every().wednesday.at(child['start_tracking_time_pm']).do(start_tracking, child)
    schedule.every().thursday.at(child['start_tracking_time_pm']).do(start_tracking, child)
    schedule.every().friday.at(child['start_tracking_time_pm']).do(start_tracking, child)

def run():
    # Set initial tracker state
    update_ha_state(TRACKER_STATE_ENTITY, "Not Tracking")

    for child in options['children']:
        schedule_trackers(child)

    logging.debug(schedule.jobs)

    # Main loop to execute scheduled jobs
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__=="__main__":
    # Read in user configuration options
    parse_options()

    # Setup logging
    setup_logging()

    # Run the main program
    run()
