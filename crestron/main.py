import logging
import time
import paho.mqtt.client as mqtt
import json
import datetime
from crestron import CrestronClient
import threading
import os

logging.basicConfig(
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=logging.DEBUG,
    datefmt='%Y-%m-%d %H:%M:%S')

options = {}

class CrestronMQTT:

    def __init__(self, mqtt_server, mqtt_port, mqtt_username, mqtt_password, crestron_ipaddress, crestron_port, crestron_passcode):
        self.client = mqtt.Client(client_id="crestron")
        self.mqtt_server = mqtt_server
        self.mqtt_port = mqtt_port
        self.mqtt_username = mqtt_username
        self.mqtt_password = mqtt_password
        self.crestron_ipaddress = crestron_ipaddress
        self.crestron_port = crestron_port
        self.crestron_passcode = crestron_passcode
        self.connected = False
        self.crestron_heartbeat_timeout = 60 # seconds

    def connect(self):
        logging.debug("connect")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        self.client.username_pw_set(self.mqtt_username, self.mqtt_password)
        self.client.connect(self.mqtt_server, self.mqtt_port, 60)

    def run(self):
        self.connect()
        while True:
            self.client.loop()

    def crestron_connect(self):
        t1 = threading.Thread(target=self.__crestron_connect, args=())
        t1.daemon = True
        t1.start()
    
    def __crestron_connect(self):
        # Connect to Crestron
        self.crestron_client = CrestronClient(self.crestron_ipaddress, self.crestron_port, self.crestron_passcode)
        self.crestron_client.on_crestron_data_received = self.on_crestron_data_received
        self.crestron_client.run(heartbeat_timeout=self.crestron_heartbeat_timeout)

    # The callback for when the client receives a CONNACK response from the server.p
    def on_connect(self, client, userdata, flags, rc):
        logging.debug("Connected with result code "+str(rc))
        logging.debug(mqtt.connack_string(rc))

        self.client.message_callback_add('crestron/digital/#', self.cb_button)

        self.client.subscribe("crestron/#")
        self.connected = True
 
        self.crestron_connect()

    # pylint: disable=no-self-argument
    def _callback(func):
        """Calback decorator used to check/reestablish crestron
        connection before sending a message
        """
        def wrapper(self, *args, **kwargs):
            logging.debug("Is connected: {}".format(self.crestron_client.is_connected))
            if not self.crestron_client.is_connected:
                self.crestron_connect()
                while not self.crestron_client.is_connected:
                    time.sleep(1)
            # pylint: disable=not-callable
            func(self, *args, **kwargs)
        return wrapper

    # The callback for when a PUBLISH message is received from the server.
    def on_message(self, client, userdata, msg):
        logging.debug(msg.topic+" "+str(msg.payload))

    @_callback
    def cb_button(self, client, userdata, msg):
        logging.debug("MQTT button: {}".format(msg))
        button_id = msg.topic.split("/")[-1]
        #data = json.loads(msg.payload)
        self.crestron_client.button_press(button_id)

    def on_crestron_data_received(self, data_type, id, value):
        #payload = {
        #    'data_type': data_type,
        #    'id': id,
        #    'value': value
        #}
        #self.client.publish('crestron/data', json.dumps(payload))
        self.client.publish('crestron/%s/%s/state' % (data_type, id), value)

def setup_logging():
    # Setup logging
    logging.info(os.environ.get('DEBUG'))

    if os.environ.get('DEBUG') != '' or options['debug']:
        logging.getLogger().setLevel(logging.DEBUG)
        requests_log = logging.getLogger("requests.packages.urllib3")
        requests_log.setLevel(logging.DEBUG)
        requests_log.propagate = True

def parse_options():
    global options

    options_file = '/data/options.json'

    if not os.getenv('HASSIO_TOKEN'):
        # We aren't running in HA
        options_file = './options.json'

    with open(options_file) as json_file:
        data = json.load(json_file)
        options = data
    
    logging.debug(options)

if __name__ == "__main__":

    # Read in user configuration options
    parse_options()

    # Setup logging
    setup_logging()

    client = CrestronMQTT(
        mqtt_server=options['MQTT']['broker'],
        mqtt_port=options['MQTT']['port'],
        mqtt_username=options['MQTT']['username'],
        mqtt_password=options['MQTT']['password'],
        crestron_ipaddress=options['crestron']['IPAddress'],
        crestron_port=options['crestron']['port'],
        crestron_passcode=options['crestron']['passcode']
    )
    client.run()
