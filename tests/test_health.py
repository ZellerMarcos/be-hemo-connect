import json
import unittest
from urllib.request import urlopen


class HealthEndpointTest(unittest.TestCase):
    def test_health(self) -> None:
        with urlopen("http://127.0.0.1:8000/health") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read()), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()