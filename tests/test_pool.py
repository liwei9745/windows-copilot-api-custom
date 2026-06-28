"""Tests for multi-account pool round-robin routing."""

import sys
import unittest
from unittest.mock import patch, MagicMock

# Force re-importing server.api with mocked glob
class TestAccountPool(unittest.TestCase):
    def test_multi_account_pool_loading_and_routing(self):
        # Clear module cache for server.api so it re-initializes with mocked glob
        if "server.api" in sys.modules:
            del sys.modules["server.api"]

        with patch("glob.glob") as mock_glob, \
             patch("copilot.CopilotClient") as mock_client_class:
            
            # Simulate finding two accounts
            mock_glob.return_value = ["session/account_1", "session/account_2"]
            
            # Mock the clients returned by CopilotClient
            client1 = MagicMock(name="client_1")
            client2 = MagicMock(name="client_2")
            mock_client_class.side_effect = [client1, client2]
            
            # Import server.api to trigger initialization
            import server.api as api
            
            # Check pool loading
            self.assertEqual(len(api._clients), 2)
            self.assertEqual(api._clients[0], client1)
            self.assertEqual(api._clients[1], client2)
            
            # Check round-robin routing
            self.assertEqual(api.get_next_client(), client1)
            self.assertEqual(api.get_next_client(), client2)
            self.assertEqual(api.get_next_client(), client1)
            self.assertEqual(api.get_next_client(), client2)

    def test_single_account_fallback(self):
        # Clear module cache for server.api so it re-initializes with mocked glob
        if "server.api" in sys.modules:
            del sys.modules["server.api"]

        with patch("glob.glob") as mock_glob, \
             patch("copilot.CopilotClient") as mock_client_class:
            
            # Simulate no accounts found
            mock_glob.return_value = []
            
            client_default = MagicMock(name="client_default")
            mock_client_class.return_value = client_default
            
            # Import server.api to trigger initialization
            import server.api as api
            
            # Check default configuration
            self.assertEqual(len(api._clients), 1)
            self.assertEqual(api._clients[0], client_default)
            self.assertEqual(api.get_next_client(), client_default)
            self.assertEqual(api.get_next_client(), client_default)


if __name__ == "__main__":
    unittest.main()
