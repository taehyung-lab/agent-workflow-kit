import tempfile
import unittest
from pathlib import Path

import service


class Smoke(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "app.db")
        service.init(self.db)

    def test_member_confirm_and_lookup(self):
        result = service.confirm(self.db, "r", "alice", "morning")
        self.assertEqual(result["code"], 200)
        self.assertEqual(service.status(self.db, "r", "alice")["confirmation"], result["confirmation"])

    def test_guest_denied(self):
        self.assertEqual(service.confirm(self.db, "g", "guest", "morning")["code"], 403)
        self.assertEqual(service.status(self.db, "g", "guest")["code"], 403)

    def test_other_member_cannot_lookup(self):
        service.confirm(self.db, "r", "alice", "morning")
        self.assertEqual(service.status(self.db, "r", "bob")["code"], 404)
