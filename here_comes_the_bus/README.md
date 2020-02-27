# here_comes_the_bus
A Home Assistant (HASS.IO) add-on that will monitor herecomesthebus.com and store the distance between the bust stop and a tracked school bus. Then, you can configure Haome Assistant Automations to do things such as send an Alexa notification when the bus is within 1 mile.

## Requirements

- Valid herecomethebus.com account
- Valid api.openrouteservice.org API key (used for calculating distance)

## Development

The main.py script can be ran locally for testing outside of Home Assistant.

### Prerequisites
- Install python libs
```
    pip install -r requirements.txt
```

### Files
- Dockerfile - Used to build docker container within Home Assistant
- build.json - Docker build config
- config.json - Home Assistant add-on settings config

- main.py - main python script that runs the logic
- options.json - options used when running locally


## Deployment

1. Navigate to Home Assistant>Supervisor>ADD-ON Store
2. Select 'Add new repository by URL'
3. Enter the github repo where this add-on is stored 
4. Click 'Add'
5. Select the 'Here Comes the Bus' addon from the newly listed repository
6. Install
7. Configure
8. Start

