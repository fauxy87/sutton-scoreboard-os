#!/usr/bin/env python3

from engine import MatchEngine

engine = MatchEngine()

def packet_received(packet):
    engine.process_packet(packet)

def publish_if_ready():
    engine.publish_if_ready()
