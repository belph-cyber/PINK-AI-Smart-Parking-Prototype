# -*- coding: utf-8 -*-
"""
PINK AI: MQTT Hardware & CiRA Core Communication Gateway
Handles real-time communication with ESP32 Hardware (SG92R Servo, Traffic Light LEDs, HC-SR04 x3)
and CiRA Core AI Nodes across both Local Broker (127.0.0.1) and Cloud Broker (broker.emqx.io).
"""

import os
import time
import logging
import threading
from typing import Optional, List

import paho.mqtt.client as mqtt
import config

logger = logging.getLogger("mqtt_gateway")

mqtt_clients: List[mqtt.Client] = []
gate_timer: Optional[threading.Timer] = None
timer_lock = threading.Lock()


def get_mqtt_client() -> Optional[mqtt.Client]:
    for c in mqtt_clients:
        if c and c.is_connected():
            return c
    return mqtt_clients[0] if mqtt_clients else None


def set_mqtt_client(client: mqtt.Client):
    if client and client not in mqtt_clients:
        mqtt_clients.append(client)


def _publish_all(topic: str, payload: str, qos: int = 1, retain: bool = False) -> bool:
    published_any = False
    for c in mqtt_clients:
        if c and c.is_connected():
            try:
                c.publish(topic, payload, qos=qos, retain=retain)
                published_any = True
            except Exception as e:
                logger.error("[MQTT] Publish error on %s: %s", topic, e)
    return published_any


def publish_gate_command(action: str, reason: Optional[str] = None) -> bool:
    """
    Publish command to ESP32 Barrier Servo (GPIO 15) & Entry Traffic Light LED (GPIO 33 / 25-27):
    - 'OPEN': opens barrier (90 deg) and turns entry LED to GREEN, starts auto-close timer
    - 'CLOSE': closes barrier (0 deg) and turns entry LED to RED
    - 'EMERGENCY': opens barrier and keeps it open without auto-close timer
    """
    global gate_timer
    act = action.upper()

    if not any(c.is_connected() for c in mqtt_clients):
        logger.warning("[MQTT GATE] No MQTT broker connected, cannot publish %s (reason: %s)", act, reason)
        return False

    try:
        if act in ("OPEN", "UNLOCK"):
            _publish_all("parking/esp/gate", "OPEN", qos=1, retain=False)
            _publish_all("parking/esp/led/entry", "GREEN", qos=1, retain=True)
            logger.info("[MQTT GATE] -> Published 'OPEN' & 'GREEN' to ESP32 (reason: %s)", reason)

            with timer_lock:
                if gate_timer and gate_timer.is_alive():
                    gate_timer.cancel()
                gate_timer = threading.Timer(config.GATE_OPEN_SEC, auto_close_gate)
                gate_timer.daemon = True
                gate_timer.start()

        elif act in ("CLOSE", "LOCK"):
            with timer_lock:
                if gate_timer and gate_timer.is_alive():
                    gate_timer.cancel()
            _publish_all("parking/esp/gate", "CLOSE", qos=1, retain=False)
            _publish_all("parking/esp/led/entry", "RED", qos=1, retain=True)
            logger.info("[MQTT GATE] -> Published 'CLOSE' & 'RED' to ESP32 (reason: %s)", reason)

        elif act == "EMERGENCY":
            with timer_lock:
                if gate_timer and gate_timer.is_alive():
                    gate_timer.cancel()
            _publish_all("parking/esp/gate", "OPEN", qos=1, retain=False)
            _publish_all("parking/esp/led/entry", "GREEN", qos=1, retain=True)
            logger.info("[MQTT GATE] -> Published EMERGENCY UNLOCK to ESP32")

        return True
    except Exception as e:
        logger.error("[MQTT GATE] Error publishing command: %s", e)
        return False


def auto_close_gate():
    """Triggered by timer after GATE_OPEN_SEC to automatically lower the barrier"""
    logger.info("[MQTT GATE] Auto-close timer elapsed (%.1fs) -> Lowering barrier", config.GATE_OPEN_SEC)
    publish_gate_command("CLOSE", reason="Auto-close timer elapsed")


def publish_slots_led(status: str) -> bool:
    """Publish RED / GREEN to parking/esp/led/slots"""
    if not any(c.is_connected() for c in mqtt_clients):
        return False
    color = "GREEN" if status.upper() in ("GREEN", "FREE", "AVAILABLE") else "RED"
    return _publish_all("parking/esp/led/slots", color, qos=1, retain=True)
