"""Topic registry — associates topic names with type names and QoS."""

from __future__ import annotations

from dataclasses import dataclass

from vibedds.qos import QosPolicy


@dataclass
class Topic:
    """A DDS topic with a name, type name, and default QoS."""
    name: str
    type_name: str
    qos: QosPolicy | None = None
    type_information: bytes | None = None
    type_object: bytes | None = None
    keyed: bool | None = None

    def __hash__(self) -> int:
        return hash((self.name, self.type_name))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Topic):
            return NotImplemented
        return self.name == other.name and self.type_name == other.type_name


class TopicRegistry:
    """Stores registered topics."""

    def __init__(self):
        self._topics: dict[str, Topic] = {}

    def register(self, topic: Topic) -> Topic:
        """Register a topic. Returns existing if already registered with same type."""
        existing = self._topics.get(topic.name)
        if existing is not None:
            if existing.type_name != topic.type_name:
                raise ValueError(
                    f"Topic '{topic.name}' already registered with type "
                    f"'{existing.type_name}', cannot re-register with '{topic.type_name}'"
                )
            if existing.type_information is None and topic.type_information is not None:
                existing.type_information = topic.type_information
            if existing.type_object is None and topic.type_object is not None:
                existing.type_object = topic.type_object
            if existing.keyed is None and topic.keyed is not None:
                existing.keyed = topic.keyed
            return existing
        self._topics[topic.name] = topic
        return topic

    def get(self, name: str) -> Topic | None:
        return self._topics.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._topics
