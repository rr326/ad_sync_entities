import re
from typing import Optional, Tuple, List

import adplus
from appdaemon.plugins.mqtt import mqttapi as mqtt
from importlib import reload


from _sync_entities.sync_dispatcher import EventListenerDispatcher, EventPattern
from _sync_entities.sync_plugin import Plugin

# pylint: disable=unused-argument


"""
Entity naming / renaming.

# Constraints
* You need a remote entity to have a HOSTNAME suffix
* The suffix can only be alphanumeric characters. Symbols won't work.
* EXCEPT - you CAN have underscore (_) 
    * BUT can't end with it
    * You can not have two in a row
* You can only create *sensor* entities. (Actually, you can create
    any entity, but they are read only. So sensors are more sensible.)

# Rules
host: seattle, entity: light.office -> sensor.light_office_seattle
"""

def entity_add_hostname(entity: str, host: str) -> str:
    """
    light.named_light, host -> light.named_light_host

    opposite: entity_split_hostname()
    """

    # Note- you can't use any symbols for the host delimiter. I tried many.
    # 500 error
    return f"{entity}_{host}"

def entity_split_hostname(entity: str) -> Tuple[str, Optional[str]]:
    """
    light.named_light_pihaven -> ("light.named_light", "pihaven")
    light.local_light -> ("light.local_light", None)

    opposite: entity_add_myhostname()
    """
    match = re.fullmatch(r"(.*)_([^#]+)", entity)
    if match:
        return (match.group(1), match.group(2))
    else:
        return (entity, None)
