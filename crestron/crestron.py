import asyncio
from sys import stdout
import xml.etree.ElementTree as ET
import re
import logging
import time
import json
import datetime
import signal
from myutils import num_map, set_list_value


logging.basicConfig(
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=logging.DEBUG,
    datefmt='%Y-%m-%d %H:%M:%S')


class CrestronClient(asyncio.Protocol):
    def __init__(self, crestron_ip, crestron_port, passcode, **kwargs):
        self.crestron_ip = crestron_ip
        self.crestron_port = crestron_port
        self.passcode = passcode
        self.is_open = False
        self.is_connected = False
        self.heartbeat_task = None
        self.pause_heartbeats = False
        self.heartbeat_timeout = 60 # seconds
        self.last_activity = time.time()
        self.states = {
            'serial': [],
            'analog': [],
            'digital': []
        }

    def __del__(self):
        self.__shutdown()

    ## asyncio methods

    def connection_made(self, transport):
        logging.debug("Connection made")

        self.sockname = transport.get_extra_info("sockname")
        self.transport = transport
        self.is_open = True

    def connection_lost(self, exc):
        logging.debug("Connection lost")
        self.is_open = False
        self.is_connected = False
        self.__shutdown()

    def data_received(self, data):
        if data:
            self.__process_data(data.decode("utf-8"))

    def send(self, data):
        if data:
            logging.debug('SEND: {}'.format(data))
            self.transport.write(data.encode())

    ## end asyncio methods

    ## public methods

    def run(self, heartbeat_timeout=None):
        logging.debug("CrestronClient.run")
        self.heartbeat_timeout = heartbeat_timeout
        
        logging.debug("asyncio.new_event_loop")
        self.loop = asyncio.new_event_loop()

        logging.debug("asyncio.set_event_loop")
        asyncio.set_event_loop(self.loop)

        self.loop.set_exception_handler(self.__handle_exception)

        logging.debug("self.loop.create_connection")
        coro = self.loop.create_connection(lambda: self, self.crestron_ip, self.crestron_port)
        
        logging.debug("self.loop.run_until_complete")
        self.loop.run_until_complete(coro)
        
        # Start the heartbeat thread to keep the connection alive
        logging.debug("self.loop.create_task")
        self.start_heartbeats(heartbeat_timeout)

        logging.debug("self.loop.run_forever")
        self.loop.run_forever()

        self.__shutdown()

    def stop_heartbeats(self):
        logging.debug("stop_heartbeats")
        self.heartbeat_task.cancel()

    def start_heartbeats(self, timeout=None):
        logging.debug("start_heartbeats")
        self.heartbeat_task = self.loop.create_task(self.__heartbeat())

        self.heartbeat_timeout_task = self.loop.create_task(self.__heartbeat_timeout(timeout))

    def crestron_disconnected(self, xml):
        pass

    def crestron_heartbeat_response(self, xml):
        pass

    def on_crestron_data_received(self, data_type, id, value):
        pass

    def sendData(self, data_type, id, value, repeat="true"):
        msg = ''

        if data_type == 'digital':
            msg = '<cresnet><data eom="false" handle="3" slot="0" som="false"><bool id="{}" value="{}" repeating="{}"/></data></cresnet>'.format(id, value, repeat)

        elif data_type == 'analog':
            msg = '<cresnet><data eom="false" handle="3" slot="0" som="false"><i32 id="{}" value="{}" repeating="{}"/></data></cresnet>'.format(id, value, repeat)

        elif data_type == 'serial':
            msg = '<cresnet><data eom="false" handle="3" slot="0" som="false"><string id="{}" value="{}" repeating="{}"/></data></cresnet>'.format(id, value, repeat)
        else:
            raise Exception("Invalid data type: {}".format(data_type))

        self.send(msg)

    def button_press(self, button_id):
        self.sendData('digital', button_id, 'true')
        self.sendData('digital', button_id, 'false')

    ## end Public methods

    ## Private methods

    def __handle_exception(self, context):
        # context["message"] will always be there; but context["exception"] may not
        msg = context.get("exception", context["message"])
        logging.error(f"Caught exception: {msg}")
        logging.info("Shutting down...")
        asyncio.create_task(self.__shutdown())

    async def __shutdown(self):
        """Cleanup tasks tied to the service's shutdown."""
        tasks = [t for t in asyncio.all_tasks() if t is not
                asyncio.current_task()]

        [task.cancel() for task in tasks]

        logging.info(f"Cancelling {len(tasks)} outstanding tasks")
        await asyncio.gather(*tasks, return_exceptions=True)
        self.loop.stop()

    async def __heartbeat(self):
        while True:
            await asyncio.sleep(10)
            if self.is_connected and not self.pause_heartbeats:
                self.__heartbeatRequest()

    async def __heartbeat_timeout(self, timeout):
        """When timeout expires stop the heartbeats and let the connection die.
        This reduces uneccesary network activity when not in use.
        """
        logging.debug("heartbeat timeout: {}".format(timeout))
        if not timeout:
            return

        while True:
            await asyncio.sleep(1)
            if time.time() - self.last_activity > timeout:
                logging.debug("Timeout")
                self.stop_heartbeats()
                break

    def __process_data(self, data):
        logging.debug("RECV: {}".format(data))
        root = ET.fromstring("<root>{}</root>".format(data))
        self.__process_xml(root)

    def __crestron_disconnected(self, xml):
        self.loop.stop()
        self.crestron_disconnected(xml)

    def __store_state(self, data_type, id, value):
        logging.debug("Storing State: {} {} {}".format(data_type, id, value))

        if data_type == 'digital':
            value = True if value == "true" else False 
        elif data_type == 'analog':
            value = int(value)
        elif data_type == 'serial':
            value = str(value)
        
        set_list_value(self.states[data_type], id, value)

        self.on_crestron_data_received(data_type, id, value)

    def __get_state(self, data_type, id):
        try:
            return self.states[data_type][id]
        except IndexError:
            logging.error('Tried to get an invalid data type or id: {} {}'.format(data_type, id))
            return None

    def __connectRequest(self, passcode):
        # connectRequest
        msg = '<cresnet><control><comm><connectRequest><passcode>{}</passcode><mode isAuthenticationRequired="false" isDigitalRepeatSupported="true" isHeartbeatSupported="true" isProgramReadySupported="true" isUnicodeSupported="true"></mode><device><product>Crestron Mobile Android</product><version> 1.00.01.42</version><maxExtendedLengthPacketMask>3</maxExtendedLengthPacketMask></device></connectRequest></comm></control></cresnet>'.format(passcode)
        self.send(msg)

    def __updateRequest(self):
        # updateRequest
        msg = '<cresnet><data eom="false" som="false"><updateCommand><updateRequest></updateRequest></updateCommand></data></cresnet>'
        self.send(msg)

    def __heartbeatRequest(self):
        # heartbeatRequest
        msg = '<cresnet><control><comm><heartbeatRequest></heartbeatRequest></comm></control></cresnet>'
        self.send(msg)

    def __process_xml(self, xml):
        if xml.find('.//cresnet') != None:
            for cresnet in xml.findall('.//cresnet'):
                # connectRequest
                if cresnet.find('.//status') != None and cresnet.find('.//status').text == '02':
                    logging.debug('Ready to connect')
                    time.sleep(1)
                    self.__connectRequest(self.passcode)
                # updateRequest
                elif cresnet.find('.//code') != None and cresnet.find('.//code').text == '0':
                    logging.debug("Successfully Connected!")
                    self.is_connected = True
                    self.__updateRequest()
                # heartbeat
                elif cresnet.find('.//heartbeatResponse') != None:
                    logging.debug("Heartbeat Response")
                    self.crestron_heartbeat_response(cresnet.find('.//heartbeatResponse'))
                elif cresnet.find('.//disconnectRequest') != None:
                    logging.info("Disconnected")
                    self.__crestron_disconnected(cresnet.find('.//disconnectRequest'))
                # data coming in
                elif cresnet.find('.//data') != None:
                    
                    data = cresnet.find('.//data')

                    if data.find('.//bool') != None:
                        digital = data.find('.//bool')

                        self.__store_state('digital', int(digital.get('id')), digital.get('value'))
                        
                    elif data.find('.//i32') != None:
                        analog = data.find('.//i32')

                        self.__store_state('analog', int(analog.get('id')), analog.text)

                    elif data.find('.//string') != None:
                        serial = data.find('.//string')

                        self.__store_state('serial', int(serial.get('id')), serial.text)

                    else:
                        logging.debug("Nothing important found in data: {}".format(ET.tostring(data)))
    
if __name__ == "__main__":
    # Connect to Crestron
    client = CrestronClient('192.168.7.78', 41790, 1234)
    client.run(heartbeat_timeout=10)