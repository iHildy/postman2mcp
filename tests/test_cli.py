import json
import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from postman2mcp.cli import openapi_main


SAMPLE_COLLECTION = {
    "collection": {
        "info": {
            "name": "Sample API",
            "description": "Sample description",
        },
        "item": [
            {
                "name": "List widgets",
                "request": {
                    "method": "GET",
                    "description": "Fetch widgets",
                    "url": {
                        "raw": "https://api.example.com/widgets?limit=10",
                        "path": ["widgets"],
                        "query": [{"key": "limit", "value": "10"}],
                    },
                },
                "response": [],
            }
        ],
    }
}


class OpenAPICliTests(unittest.TestCase):
    def test_openapi_command_writes_only_openapi_file(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = f"{temp_dir}/generated/openapi.json"
            with patch("postman2mcp.cli.harvest_postman_collection", return_value=SAMPLE_COLLECTION), \
                 patch("postman2mcp.cli.generate_project_files") as mock_generate_project_files:
                result = runner.invoke(
                    openapi_main,
                    [
                        "--collection-id", "collection-123",
                        "--output-file", output_file,
                        "--postman-api-key", "secret-key",
                    ],
                )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("OpenAPI spec written to", result.output)
            self.assertEqual(mock_generate_project_files.call_count, 0)

            with open(output_file, "r", encoding="utf-8") as f:
                openapi_spec = json.load(f)

            self.assertEqual(openapi_spec["openapi"], "3.1.0")
            self.assertIn("/widgets", openapi_spec["paths"])
            self.assertIn("get", openapi_spec["paths"]["/widgets"])


if __name__ == "__main__":
    unittest.main()
