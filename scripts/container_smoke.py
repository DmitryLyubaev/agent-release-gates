import http.client
import json
from pathlib import Path

connection = http.client.HTTPConnection("127.0.0.1", 55416, timeout=10)
connection.request("GET", "/health")
response = connection.getresponse()
assert response.status == 200
assert json.loads(response.read()) == {"status": "ok", "mode": "offline"}
path = next(Path("examples/scripted").glob("run_*/bundle.json"))
raw = json.loads(path.read_bytes())
connection.request(
    "POST",
    "/runs/import",
    body=json.dumps(raw).encode(),
    headers={"Content-Type": "application/json"},
)
response = connection.getresponse()
body = response.read()
assert response.status == 200, (response.status, body)
imported = json.loads(body)
connection.request("GET", "/runs/" + imported["id"])
response = connection.getresponse()
assert response.status == 200
stored = json.loads(response.read())
assert stored["manifest"]["run_id"] == raw["manifest"]["run_id"]
connection.close()
print(json.dumps({"health": "pass", "import_readback": "pass", "mode": "offline"}))
