import os
from server.collector_manager import start_collector, stop_collector

try:
    print("Starting collector...")
    status = start_collector("https://www.whatnot.com/live/0dfee123-9f3a-43ad-976a-3f336ab24177", "our_stream")
    print(f"Status: {status}")
except Exception as e:
    print(f"Error starting collector: {e}")
