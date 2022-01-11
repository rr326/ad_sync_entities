import re
from typing import Optional, Tuple, List
from importlib import reload

import adplus
from appdaemon.plugins.mqtt import mqttapi as mqtt

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
* Also I'm not sure if CAPITALLETTERS work

# Rules
host: seattle, entity: light.office -> sensor.light_office_xxseattlexx

why "xx" - so someone can name an entity with underscores.

"""


def entity_remote_to_local(remote_entity: str, host: str) -> str:
    """
    light.named_light, host -> sensor.light_named_light_host

    opposite: entity_local_to_remote()
    """

    # Note- you can't use any symbols for the host delimiter. I tried many.
    # 500 error
    platform, sep, entity_name = remote_entity.partition(".")
    if sep == "":
        raise ValueError(f"Invalid format for remote_entity: {remote_entity}")
    if re.match(" |_", platform):
        raise NotImplementedError(
            f"Got a space or _ in remote_entity platform (stuff before the dot): {remote_entity}"
        )
    return f"sensor.{platform}_{entity_name}_xx{host}xx"


def entity_local_to_remote(local_entity: str) -> Tuple[str, str]:
    """
    sensor_light_named_light_xxpihavenxx -> ("light.named_light", "pihaven")
    light.my_local_light -> ValueError()

    opposite: entity_remote_to_local()
    """
    match = re.fullmatch(
        r"sensor.(?P<platform>(input_(select|number|text|datetime|boolean)|[^_]*))_(?P<entity>.*)_xx(?P<host>[^#]+)xx",
        local_entity,
    )
    if not match:
        raise ValueError(f"Invalid format for entity_local_to_remote: {local_entity}")

    remote_entity = f'{match.group("platform")}.{match.group("entity")}'
    return (remote_entity, match.group("host"))
