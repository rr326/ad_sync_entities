# Sync Entities Via MQTT

Sync Entities Via MQTT is an Appdaemon app for HomeAssitant that enables
bi-directional sharing of state between mutiple separate HomeAssistant
installations.

For instance, say you have an HA Office and an HA Home. Both are on separate
networks. Each HA has it's own dashboard. 

Suppose you are at the office and you want to see if your Home is in 
"away" mode - with the heat off, the security lights on, the indoor lights
off, etc.  

You *could* just vpn over to Home and look at that dashboard. 

But better, you'd like that one bit of data on your Office dashboard. 

With SyncEntities, here is how it would work:

* You set up an MQ broker at both locations with "bridge mode" sending
  to a third location that is publicly available in the cloud. 
  (But PW protected.)
* At home, you configure SyncEntities to publish the state of the
  "HomeMode" input_select. 
* At the office, on your dashboard, you display the state of HomeMode.
* You configure the dashboard in Office so that if you click the 
  HomeMode button, it signals your Home to set HomeMode to "away". 
* Of course, this new state at Home will be properly propagated to 
  and displayed at Office. 

# Try This First
This app is complicated, and it turns out HA has some functionality that
might do it almost or just as well, but with off-the-shelf components. 

Read:

* [Custom component in HA](https://github.com/koying/mqtt_discoverystream_ha)
* [MQTT Statestream](https://www.home-assistant.io/integrations/mqtt_statestream/)
* [MQTT Discovery](https://www.home-assistant.io/docs/mqtt/discovery)

# Disclaimer: The Bad and the Ugly
SyncEntities works really well, but it's non-trivial to use. There is
likely a less elegant, but far easier, way to achieve your aims, more or less.

For instance:

* MQ isn't hard, but you need to set up THREE MQ brokers. 
  (Or two, and set your firewall / security properly).
* One needs to be publicly available. And password protected. It's not hard,
  but it does take some debugging.
* Before you even deal with SyncEntities, you'll want to make sure all 
  three MQs are talking together as you'd expect. You'll become friendly with
  `mosquitto_pub` and `mosquitto_sub`. And you'll have three ssh sessions 
  with logs tailing going at the same time. Once again, it's not hard, but
  it isn't trivial.
* Because of a limitation in Appdaemon, all the locally mirrored entities
  will be *sensors*. 
* Also, you want to show which entities are actually local mirrors. But you
  can't use any symbols or spaces in an entity name, so I tack on `xxREMOTExx`  
* So `input_select.home_mode` will become something like
  `sensor.input_select_home_mode_xxhomexx`
* Then you'll need to signal the remote site that you want to change state. 
  The simplest method I've found isn't simple at all:
    * Use the `custom:button-card` card
    * Set a `tap-action` of `call-service` that calls a `script`
    * The script fires an event that tells SyncEntities to tell the remote 
      site to change state.

Yeah, it's a lot!

# Status
Alpha - it works for me in my circumstances. I have no idea what bugs will arise in the wild.

# Installation
Copy this repo to your apps folder somewhere, copy the `sync_entties_via_mqtt.yaml.sample` 
to a `.yaml` name and configure.

Watch your logs to make sure it all loads properly. Set `log_level: DEBUG` when you 
are testing to make sure you have *ample* logs. Set it to `INFO` once it is all working. 

I like to have 3 panes open for both local and remote (6 total).

1. `tail -f appdaemon.log`
2. `mosquitto_sub -v -t "mqtt_shared\#" `
3. Open shell for changes.

Make sure your MQTT bridging is working properly before you start debugging your SyncEntities
app.

# MQTT

Learn about MQTT bridging. For example, [here](http://www.steves-internet-guide.com/mosquitto-bridge-configuration/).

## docker-compose.yml
```yaml
version: '3.8'
services:
  homeassistant:
    # details skipped
  appdaemon:
    # details skipped
  zjs2mqtt:
    # details skipped
  wireguard:
    # details skipped, but you'll want a VPN for testing    
  mosquitto:
    container_name: mosquitto
    image: eclipse-mosquitto:latest
    volumes:
      - mosquitto/config:/mosquitto/config/
      - mosquitto/data:/mosquitto/data/
      - mosquitto/log:/mosquitto/log/
    network_mode: "host"
    ports:
      - '1883:1883'
    restart: unless-stopped
```

## mosquitto.conf -- On your private (not publically visible) servers

```yaml
persistence true
persistence_location /mosquitto/data/
log_dest file /mosquitto/log/mosquitto.log
log_type error
log_type warning
log_type notice
log_type information
log_type subscribe
log_type unsubscribe


# Bridge to do_server mqtt
connection bridge_to_doserver
address XXX.XXX.XXX.XXX:1884
topic mqtt_shared/# both
remote_username XXX
remote_password XXX

keepalive_interval 60
idle_timeout 60
```

## mosquitto.conf - public server (eg: AWS, DigitalOcean, etc.)

```yaml
persistence true
persistence_location /mosquitto/data/
log_dest file /mosquitto/log/mosquitto.log
log_type error
log_type warning
log_type notice
log_type information
log_type subscribe
log_type unsubscribe
connection_messages true

user mosquitto

per_listener_settings true

# Remote - authenticated
listener 1884
password_file /mosquitto/config/passwords
allow_anonymous false

# Local - NOT authenticated - for easy testing. Not strictly necessary.
listener 1883
allow_anonymous true
```

# Configuration
All the `global_modules`, `global_dependencies`, and `TestSyncEntitiesViaMqtt`
are for my own debugging as I built the app. You can ignore.


Sample config - remote site. (Here "Home")

```yaml
SyncEntitiesViaMqtt:
  module: sync_entities_via_mqtt
  class: SyncEntitiesViaMqtt
  myhostname: home # no dashes, symbols, etc.
  state_for_entities: # entities for which you want to publish state
      - light.living_room # Syncing the light where you are working is an easy way to test.
      - input_select.home_mode
  disable: false
  log_level: DEBUG # Set to "INFO" when it is working. 
```

Using the remote state. Here in ("Office").

I'm going to show a two types of usages. 1) Simple - an on/off toggle; 2) Complex - Cycle through states of an input_select. 

## scripts.yaml (in HomeAssistant)
```yaml
fire_event_sync_entities_via_mqtt_toggle:
  alias: "Fire Event - sync_entities_via_mqtt_toggle"
  sequence:
  - event: app.sync_entities_via_mqtt
    event_data:
      action: toggle_state
      entity_id: "{{ entity_id }}"

fire_event_sync_entities_via_mqtt_set_state:
  alias: "Fire Event - sync_entities_via_mqtt_set_state"
  sequence:
  - event: app.sync_entities_via_mqtt
    event_data:
      action: set_state
      entity_id: "{{ entity_id }}"
      state: "{{ state }}"
```

## Simple case - toggle a light. 

### dashboard.yaml (in HomeAssistant)
```yaml
- type: "custom:button-card"
    entity: "sensor.light_living_room_xxhomexx"
    icon: "mdi:lightbulb"
    color_type: "icon"
    color: "auto"
    show_state: true
    tap_action:
        action: call-service
        service: script.fire_event_sync_entities_via_mqtt_toggle
        service_data:
        entity_id: sensor.light_living_room_xxhomexx
```

## Complex case - cycle through options of an input_select

### dashboard.yaml (in HomeAssistant)

```yaml
- type: "custom:button-card"
    entity: sensor.input_select_home_mode_xxhomexx
    icon: mdi:home
    card_size: 1
    name: Haven Home Mode
    tap_action:
        action: call-service
        service: script.fire_event_sync_entities_via_mqtt_set_state
        service_data:
        entity_id: sensor.input_select_home_mode_xxhomexx
        state: >
            [[[
            switch (entity.state) {
                case 'Home':
                return 'Leaving'
                case 'Leaving':
                return 'Away'          
                case 'Away':
                return 'Arriving'
                case 'Arriving':
                return 'Home'
                default:
                console.log(`Unexpected value of entity: ${entity}: ${entity.state}`)
                return 'INVALID_VALUE'
            }
            ]]]

    confirmation:
        text: "Are you sure you want to select the next state?"
    show_state: true
    color_type: card
    styles:
        name:
        - font-size: 20px
        - font-weight: bold
        card:
        - font-size: 20px
        - font-weight: bold
        - color: black
    state:
        - value: "Home"
        styles:
            card:
            - background-color: red
        - value: "Arriving"
        styles:
            card:
            - background-color: pink
        - value: "Away"
        styles:
            card:
            - background-color: white
        - value: "Leaving"
        styles:
            card:
            - background-color: yellow
```