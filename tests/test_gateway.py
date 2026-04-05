"""
Tests for gateway/router.py
"""
import unittest
from unittest.mock import MagicMock, patch


class TestGatewayRouter(unittest.TestCase):

    def setUp(self):
        # Reset HANDLERS between tests to avoid cross-test pollution
        from gateway.router import HANDLERS
        self._original_handlers = HANDLERS.copy()
        HANDLERS.clear()

    def tearDown(self):
        from gateway.router import HANDLERS
        HANDLERS.clear()
        HANDLERS.update(self._original_handlers)

    def test_register_decorator_adds_handler(self):
        from gateway.router import register, HANDLERS

        @register("test_event")
        def my_handler(event):
            pass

        self.assertIn("test_event", HANDLERS)
        self.assertEqual(HANDLERS["test_event"], my_handler)

    def test_register_multiple_handlers(self):
        from gateway.router import register, HANDLERS

        @register("event_a")
        def handler_a(event): pass

        @register("event_b")
        def handler_b(event): pass

        self.assertIn("event_a", HANDLERS)
        self.assertIn("event_b", HANDLERS)

    def test_register_returns_original_function(self):
        from gateway.router import register

        @register("test_event")
        def my_handler(event):
            return "result"

        self.assertEqual(my_handler({}), "result")

    def test_handler_is_callable(self):
        from gateway.router import register, HANDLERS
        called_with = []

        @register("test_event")
        def my_handler(event):
            called_with.append(event)

        HANDLERS["test_event"]({"type": "test_event", "payload": {}})
        self.assertEqual(len(called_with), 1)
        self.assertEqual(called_with[0]["type"], "test_event")

    def test_overwrite_handler(self):
        from gateway.router import register, HANDLERS

        @register("test_event")
        def handler_v1(event): return "v1"

        @register("test_event")
        def handler_v2(event): return "v2"

        self.assertEqual(HANDLERS["test_event"]({}), "v2")


if __name__ == "__main__":
    unittest.main()
