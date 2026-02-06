# LocalTibberPulse2MQTT
Docker container that retrieves data from the Tibber Pulse HTTP interface and forwards it to an MQTT broker.

## Enable HTTP Server on the Tibber Bridge:
in order to locally retrieve the data you have to always-enable the web frontend:
https://github.com/ProfDrYoMan/tibber_pulse_local#always-enabling-the-web-frontend

## Create Image from Dockerfile
change to the directory that has the dockerfile and execute 
sudo docker build -t smartmeter .


## Docker Compose example
version: '3.8'
services:
  smartmeter:
    image: smartmeter
    container_name: smartmeter
    environment:
      - TZ=Europe/Berlin
      - HTTP_URL=http://192.168.0.10/data.json?node_id=1 # URL des SML-Endpoints
      - HTTP_USER=admin # HTTP-user
      - HTTP_PASS=AAAA-BBBB # HTTP-password
      - MQTT_HOST=192.168.0.11	 # MQTT Broker Host
      - MQTT_PORT=1883 # MQTT Broker Port
      - MQTT_USER=pulse # MQTT username
      - MQTT_PASS=HdWgqq6Qpl!g8yk2YG0jJVPk  # MQTT password
      - BASE_TOPIC=smartmeter # Basis-Topic for MQTT
      - POLL_INTERVAL=10 # Polling-Intervall in seconds
      - HEALTHCHECK_PORT=8080 # Health Checks port
    restart: unless-stopped
    networks:
      statics:
        ipv4_address: 172.16.0.2 # Assign a static IP address from the range