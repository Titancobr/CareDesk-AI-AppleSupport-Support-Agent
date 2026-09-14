"""Read-only smoke test for the AppleSupport API."""
from fastapi.testclient import TestClient

from app.main import app


def main() -> int:
    with TestClient(app) as client:
        test = client.get("/test")
        print("GET /test:", test.status_code)
        if test.status_code != 200 or test.json().get("status") != "passed":
            print(test.text)
            return 1
        query = client.post("/query", json={"q": "My iPhone will not turn on", "thread_id": "smoke"})
        print("POST /query:", query.status_code)
        if query.status_code != 200:
            print(query.text)
            return 1
        payload = query.json()
        required = {"answer", "intent", "confidence_score", "citations", "escalation", "thought_process"}
        missing = sorted(required - payload.keys())
        if missing:
            print("Missing response fields:", missing)
            return 1
    print("AppleSupport API smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
