import os
import requests
from requests.auth import HTTPBasicAuth
from smllib import SmlStreamReader
import datetime
import time
import paho.mqtt.client as mqtt
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# Config from environment variables
HTTP_URL = os.getenv('HTTP_URL')
HTTP_USER = os.getenv('HTTP_USER')
HTTP_PASS = os.getenv('HTTP_PASS')
MQTT_HOST = os.getenv('MQTT_HOST')
MQTT_PORT = int(os.getenv('MQTT_PORT', 1883))
MQTT_USER = os.getenv('MQTT_USER')
MQTT_PASS = os.getenv('MQTT_PASS')
BASE_TOPIC = os.getenv('BASE_TOPIC', 'sml_meter')
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', 10))
HEALTHCHECK_PORT = int(os.getenv('HEALTHCHECK_PORT', 8080))
HEALTH_THRESHOLD = 600  # Seconds without data= unhealthy

#Default Health Threshold is 10 minutes, if the poll interval is higher then use triple of the poll interval time instead
if POLL_INTERVAL > HEALTH_THRESHOLD:
    HEALTH_THRESHOLD = 3 * POLL_INTERVAL

# Global variables
last_timestamp = None
last_successful_fetch = None
mqtt_client = None

# ---------------- Healthcheck Server ----------------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global last_successful_fetch
        if self.path == '/health':
            now = time.time()
            status_code = 200
            body = b'OK'

            if last_successful_fetch is None:
                status_code = 503
                body = b'UNHEALTHY: no data fetched yet'
            elif now - last_successful_fetch > HEALTH_THRESHOLD:
                status_code = 503
                body = f'UNHEALTHY: last successful fetch {int(now - last_successful_fetch)}s ago'.encode()

            self.send_response(status_code)
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

def run_health_server():
    server = HTTPServer(('0.0.0.0', HEALTHCHECK_PORT), HealthHandler)
    server.serve_forever()

# ---------------- MQTT ----------------
def init_mqtt():
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    try:
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.loop_start()
        return client
    except Exception as e:
        print(f"MQTT connection error: {e}")
        return None

# ---------------- SML Daten ----------------
def fetch_data():
    global last_timestamp, mqtt_client, last_successful_fetch

    try:
        response = requests.get(HTTP_URL, auth=HTTPBasicAuth(HTTP_USER, HTTP_PASS))
    except Exception as e:
        print(f"HTTP request error: {e}")
        return

    if response.status_code != 200:
        print(f"HTTP error: {response.status_code}")
        return

    try:
        stream = SmlStreamReader()
        stream.add(response.content)
        sml_frame = stream.get_frame()

        if sml_frame is None:
            print("Incomplete frame")
            return

        parsed_msgs = sml_frame.parse_frame()
        obis_values = parsed_msgs[1].message_body.val_list 
        handle_sml_entry(obis_values)

    except Exception as e:
        print(f"Processing error: {e}")

def handle_sml_entry(obis_values):
    global last_timestamp, mqtt_client, last_successful_fetch

    # Berechnete Werte
    [setattr(entry, "calculated_value", round(entry.value * 10 ** entry.scaler, 1))
     for entry in obis_values if entry.unit is not None]

    val_time = next((item.val_time for item in obis_values if item.obis.obis_short == "1.8.0"), None)
    if val_time == last_timestamp:
        return

    time_diff = val_time - last_timestamp if last_timestamp else 0
    total_consumption = next((item.calculated_value for item in obis_values if item.obis.obis_short == "1.8.0"), None)
    system_time = datetime.datetime.now().isoformat()

    print(val_time)

    if mqtt_client is not None:
        try:
            mqtt_client.publish(f"{BASE_TOPIC}/total_consumption", total_consumption, retain=True)
            mqtt_client.publish(f"{BASE_TOPIC}/system_time", system_time, retain=True)
            mqtt_client.publish(f"{BASE_TOPIC}/timestamp_diff", time_diff, retain=True)
            for entry in obis_values:
                if entry.unit is not None:
                    mqtt_client.publish(f"{BASE_TOPIC}/raw/{entry.obis.obis_short}", entry.calculated_value, retain=True)
            last_successful_fetch = time.time()  # Healthcheck
            print(f"Data sent to MQTT: {total_consumption} Wh | Δ {time_diff}s")
        except Exception as e:
            print(f"MQTT send error: {e}")

    last_timestamp = val_time

# ---------------- Main ----------------
if __name__ == "__main__":
    mqtt_client = init_mqtt()
    if mqtt_client is None:
        print("MQTT connection failed")
        exit(1)

    # Healthcheck Server in the Background
    threading.Thread(target=run_health_server, daemon=True).start()

    while True:
        fetch_data()
        print("sleeping")
        time.sleep(POLL_INTERVAL)
