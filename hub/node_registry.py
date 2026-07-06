"""Node registry — node_id → surveyed coordinates + replay-counter state.

Fixed poles are surveyed once at install (NEO-6M or a phone); the registry is
the single source of truth for "where is node N". LoRa packets then only need
to carry the node id, not live GPS.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class Node:
    node_id: int
    lat: float
    lon: float
    name: str = ""
    last_counter: int = 0


class NodeRegistry:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._nodes: Dict[int, Node] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        for k, v in data.items():
            try:
                nid = int(k)
                self._nodes[nid] = Node(
                    node_id=nid, lat=float(v["lat"]), lon=float(v["lon"]),
                    name=str(v.get("name", "")), last_counter=int(v.get("last_counter", 0)),
                )
            except (KeyError, TypeError, ValueError):
                continue

    def save(self) -> None:
        with self._lock:
            data = {
                str(n.node_id): {"lat": n.lat, "lon": n.lon, "name": n.name,
                                 "last_counter": n.last_counter}
                for n in self._nodes.values()
            }
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)

    def add(self, node: Node) -> None:
        with self._lock:
            self._nodes[node.node_id] = node

    def get(self, node_id: int) -> Optional[Node]:
        with self._lock:
            return self._nodes.get(node_id)

    def bump_counter(self, node_id: int, counter: int) -> None:
        """Record the highest counter seen (replay protection), persisted."""
        with self._lock:
            n = self._nodes.get(node_id)
            if n is not None and counter > n.last_counter:
                n.last_counter = counter
        self.save()

    def __len__(self) -> int:
        with self._lock:
            return len(self._nodes)
