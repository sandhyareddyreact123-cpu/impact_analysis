import hashlib
import hmac

import pytest

from pr_integration.change_classifier import ChangeClassifier
from pr_integration.diff_analyzer import DiffAnalyzer
from pr_integration.webhook_listener import (DuplicateEventException, InvalidWebhookException,
                                              WebhookListener)


def github_payload(action="opened"):
    return {"action": action, "event_id": "delivery-1", "number": 123,
            "repository": {"full_name": "sample-api"},
            "pull_request": {"head": {"ref": "feature/auth", "sha": "abc123"},
                              "base": {"ref": "main"}}}


def test_valid_github_event_and_duplicate():
    listener = WebhookListener()
    event = listener.validate(github_payload(), {"X-GitHub-Event": "pull_request"})
    assert event.repository == "sample-api"
    with pytest.raises(DuplicateEventException):
        listener.validate(github_payload(), {"X-GitHub-Event": "pull_request"})


def test_signature_validation():
    body = "signed-body"
    signature = "sha256=" + hmac.new(b"secret", body.encode(), hashlib.sha256).hexdigest()
    listener = WebhookListener(secret="secret")
    payload = github_payload()
    payload["raw_body"] = body
    assert listener.validate(payload, {"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": signature})
    with pytest.raises(InvalidWebhookException):
        listener.validate(payload, {"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": "bad"})


def test_diff_classification():
    diff = """diff --git a/shared/auth.py b/shared/auth.py
new file mode 100644
--- /dev/null
+++ b/shared/auth.py
@@ -0,0 +1,8 @@
+class AuthService(Base):
+    def login(self):
+        return True
+
+def get_user():
+    return None
+@app.get(\"/users\")
+class User(Base):
+    pass
"""
    inventory = ChangeClassifier().classify(DiffAnalyzer().analyze(diff))
    assert inventory.files[0].change_type == "added"
    assert [item.name for item in inventory.classes] == ["AuthService", "User"]
    assert [item.name for item in inventory.methods] == ["login"]
    assert "get_user" in [item.name for item in inventory.functions]
    assert inventory.endpoints[0].path == "/users"
    assert inventory.models[0].name == "AuthService"
    assert inventory.shared_libraries


def test_config_file_is_detected():
    result = DiffAnalyzer().analyze("", [type("File", (), {"path": "application.yaml", "change_type": "modified"})()])
    assert result.configurations[0].file == "application.yaml"