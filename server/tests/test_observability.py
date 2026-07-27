from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock, Mock, patch

from app.config import Settings, settings
from app.observability import langsmith_tracer, trace_operation


class LangSmithObservabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prior_values = {
            name: getattr(settings, name)
            for name in (
                "langsmith_tracing",
                "langsmith_api_key",
                "langsmith_project",
                "langsmith_workspace_id",
            )
        }

    def tearDown(self) -> None:
        for name, value in self.prior_values.items():
            setattr(settings, name, value)

    def test_tracing_is_a_no_op_until_explicitly_enabled(self) -> None:
        settings.langsmith_tracing = False
        settings.langsmith_api_key = ""

        self.assertIsNone(langsmith_tracer())
        with trace_operation("test", inputs={"value": "safe"}) as run:
            self.assertIsNone(run)

    def test_standard_langsmith_tracing_environment_variable_enables_settings(self) -> None:
        with patch.dict("os.environ", {"LANGSMITH_TRACING": "true"}):
            self.assertTrue(Settings().langsmith_tracing)

    def test_enabled_tracing_builds_a_genblaze_tracer_for_the_configured_project(self) -> None:
        settings.langsmith_tracing = True
        settings.langsmith_api_key = "lsv2_pt_test"
        settings.langsmith_project = "reelproof-test"
        tracer = Mock()
        module = types.ModuleType("genblaze_langsmith")
        module.LangSmithTracer = tracer

        with patch.dict(sys.modules, {"genblaze_langsmith": module}):
            result = langsmith_tracer()

        self.assertIs(result, tracer.return_value)
        tracer.assert_called_once_with(project_name="reelproof-test", api_key="lsv2_pt_test")

    def test_manual_span_uses_the_configured_project_without_network_calls_in_test(self) -> None:
        settings.langsmith_tracing = True
        settings.langsmith_api_key = "lsv2_pt_test"
        settings.langsmith_project = "reelproof-test"
        settings.langsmith_workspace_id = "workspace-test"
        client = Mock()
        span = Mock()
        context = MagicMock()
        context.__enter__.return_value = span
        module = types.ModuleType("langsmith")
        module.Client = client
        module.trace = Mock(return_value=context)

        with patch.dict(sys.modules, {"langsmith": module}):
            with trace_operation("reelproof.test", inputs={"safe": "value"}) as run:
                self.assertIs(run, span)

        client.assert_called_once_with(api_key="lsv2_pt_test", workspace_id="workspace-test")
        module.trace.assert_called_once()
        context.__exit__.assert_called_once_with(None, None, None)


if __name__ == "__main__":
    unittest.main()
