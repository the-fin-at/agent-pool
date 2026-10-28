"""Controlled subprocess fixture. Never contacts a provider."""
import json
import sys
import time

mode = sys.argv[1]
prompt = sys.stdin.read()
if mode == "timeout":
    time.sleep(60)
elif mode == "codex":
    print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "Worker report: " + prompt}}))
    print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 2}}))
elif mode == "claude":
    print(json.dumps({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "utilization": 0.2, "rateLimitType": "five_hour", "resetsAt": time.time() + 300}}))
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "Worker report: " + prompt}))
