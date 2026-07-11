"""
Tests for agent_deepagents/tools.py — wrapping existing roles/*/tools.py
TOOL_REGISTRY callables as LangChain tools from the existing Anthropic-style
TOOLS schema, without reimplementing any tool body.
"""
import unittest

from agent_deepagents.tools import wrap_tool_registry, replace_tool, _schema_to_pydantic


class TestSchemaConversion(unittest.TestCase):

    def test_required_fields_have_no_default(self):
        model = _schema_to_pydantic("get_customer", {
            "type": "object",
            "properties": {"customer_id": {"type": "string"}},
            "required": ["customer_id"],
        })
        self.assertIn("customer_id", model.model_fields)
        self.assertTrue(model.model_fields["customer_id"].is_required())

    def test_optional_fields_default_to_none(self):
        model = _schema_to_pydantic("foo", {
            "type": "object",
            "properties": {"note": {"type": "string"}},
            "required": [],
        })
        self.assertFalse(model.model_fields["note"].is_required())

    def test_empty_schema_produces_empty_model(self):
        model = _schema_to_pydantic("get_unread_emails", {"type": "object", "properties": {}})
        self.assertEqual(model.model_fields, {})


class TestWrapToolRegistry(unittest.TestCase):

    def _sample_role_tools(self):
        registry = {
            "get_thing": lambda thing_id: {"thing_id": thing_id, "found": True},
        }
        schema = [{
            "name": "get_thing",
            "description": "Fetch a thing by id",
            "input_schema": {
                "type": "object",
                "properties": {"thing_id": {"type": "string"}},
                "required": ["thing_id"],
            },
        }]
        return schema, registry

    def test_wraps_every_schema_entry_with_a_matching_registry_fn(self):
        schema, registry = self._sample_role_tools()
        wrapped = wrap_tool_registry(schema, registry)
        self.assertEqual(len(wrapped), 1)
        self.assertEqual(wrapped[0].name, "get_thing")
        self.assertEqual(wrapped[0].description, "Fetch a thing by id")

    def test_skips_schema_entries_with_no_registry_match(self):
        schema, registry = self._sample_role_tools()
        schema.append({"name": "orphan_tool", "description": "d", "input_schema": {"type": "object", "properties": {}}})
        wrapped = wrap_tool_registry(schema, registry)
        self.assertEqual([t.name for t in wrapped], ["get_thing"])

    def test_wrapped_tool_still_calls_the_real_implementation(self):
        schema, registry = self._sample_role_tools()
        wrapped = wrap_tool_registry(schema, registry)
        result = wrapped[0].invoke({"thing_id": "abc"})
        self.assertEqual(result["thing_id"], "abc")
        self.assertTrue(result["found"])

    def test_large_result_gets_truncated_like_legacy(self):
        """agent.loop._truncate_result truncates large `emails` lists the
        same way for both backends — the same context-size guardrail."""
        big_emails = [{"id": str(i), "preview": "x" * 200} for i in range(200)]
        registry = {"get_unread_emails": lambda: {"emails": big_emails}}
        schema = [{"name": "get_unread_emails", "description": "d",
                   "input_schema": {"type": "object", "properties": {}}}]
        wrapped = wrap_tool_registry(schema, registry)
        result = wrapped[0].invoke({})
        self.assertIn("_truncated", result)
        self.assertLess(len(str(result)), len(str(big_emails)))

    def test_replace_tool_swaps_only_named_tool(self):
        schema, registry = self._sample_role_tools()
        schema.append({
            "name": "add_to_pending_queue", "description": "d",
            "input_schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
        })
        registry["add_to_pending_queue"] = lambda x: {"queued": x}
        wrapped = wrap_tool_registry(schema, registry)

        replacement_calls = []
        args_model = _schema_to_pydantic("add_to_pending_queue", schema[1]["input_schema"])
        new_wrapped = replace_tool(
            wrapped, "add_to_pending_queue",
            lambda x: replacement_calls.append(x) or {"replaced": True},
            "replacement description", args_model,
        )

        names = [t.name for t in new_wrapped]
        self.assertEqual(sorted(names), ["add_to_pending_queue", "get_thing"])
        result = next(t for t in new_wrapped if t.name == "add_to_pending_queue").invoke({"x": "hi"})
        self.assertTrue(result["replaced"])
        self.assertEqual(replacement_calls, ["hi"])
        # get_thing untouched
        result2 = next(t for t in new_wrapped if t.name == "get_thing").invoke({"thing_id": "abc"})
        self.assertEqual(result2["thing_id"], "abc")


if __name__ == "__main__":
    unittest.main()
