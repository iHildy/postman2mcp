import json
import re
from urllib.parse import urlparse, parse_qs
from typing import List, Dict, Tuple, Any

def slugify(text: str) -> str:
    """Convert text to a valid operationId slug."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")

def generate_schema_from_example(data: Any) -> Dict:
    """Recursively generate an OpenAPI schema from an example data structure."""
    if data is None:
        return {"nullable": True}
    if isinstance(data, bool):
        return {"type": "boolean"}
    if isinstance(data, int):
        return {"type": "integer"}
    if isinstance(data, float):
        return {"type": "number"}
    if isinstance(data, str):
        return {"type": "string"}
    if isinstance(data, list):
        if not data:
            return {"type": "array", "items": {}}
        return {"type": "array", "items": generate_schema_from_example(data[0])}
    if isinstance(data, dict):
        properties = {}
        for key, value in data.items():
            properties[key] = generate_schema_from_example(value)
        return {"type": "object", "properties": properties}
    return {"type": "string"}

def extract_query_parameters(url_obj: Dict) -> List[Dict]:
    return [
        {
            "name": param["key"],
            "in": "query",
            "schema": {
                "type": infer_type_from_value(param.get("value", ""))
            },
            "description": param.get("description", "")
        }
        for param in url_obj.get("query", []) if param.get("key")
    ]
    
def infer_type_from_value(value: str) -> str:
    if not value:
        return "string"  # fallback default
    if value in ["true", "false"]:
        return "boolean"
    if value.isdigit():
        return "integer"
    try:
        float(value)
        return "number"
    except ValueError:
        return "string"


def extract_path(url_obj: Dict) -> Tuple[str, List[Dict]]:
    segments = url_obj.get("path", [])
    path_parts = []
    path_params = []
    for segment in segments:
        if segment.startswith(":"):
            param_name = segment[1:]
            path_parts.append(f"{{{param_name}}}")
            path_params.append({
                "name": param_name,
                "in": "path",
                "required": True,
                "schema": {"type": "string"}
            })
        else:
            path_parts.append(segment)
    return "/" + "/".join(path_parts), path_params

def extract_request_body(request: Dict) -> Dict:
    body_obj = request.get("body")
    if not body_obj:
        return {}
    
    mode = body_obj.get("mode")
    if not mode:
        return {}
    
    content = {}
    if mode == "raw":
        raw_data = body_obj.get("raw", "")
        # Try to infer language if available
        language = body_obj.get("options", {}).get("raw", {}).get("language", "json")
        media_type = f"application/{language}" if language == "json" else "text/plain"
        
        schema = {"type": "string"}
        example = raw_data
        if language == "json":
            try:
                example = json.loads(raw_data)
                schema = generate_schema_from_example(example)
            except:
                schema = {"type": "object"}
        
        content[media_type] = {
            "schema": schema,
            "example": example
        }
    elif mode == "urlencoded":
        params = body_obj.get("urlencoded", [])
        properties = {}
        for p in params:
            if p.get("key"):
                properties[p["key"]] = {
                    "type": "string",
                    "description": p.get("description", ""),
                    "default": p.get("value", "")
                }
        content["application/x-www-form-urlencoded"] = {
            "schema": {
                "type": "object",
                "properties": properties
            }
        }
    elif mode == "formdata":
        params = body_obj.get("formdata", [])
        properties = {}
        for p in params:
            if p.get("key"):
                p_type = p.get("type", "text")
                properties[p["key"]] = {
                    "type": "string",
                    "description": p.get("description", ""),
                }
                if p_type == "file":
                    properties[p["key"]]["format"] = "binary"
                else:
                    properties[p["key"]]["default"] = p.get("value", "")
                    
        content["multipart/form-data"] = {
            "schema": {
                "type": "object",
                "properties": properties
            }
        }
        
    if content:
        return {"content": content, "required": True}
    return {}

def extract_examples(responses: List[Dict]) -> Dict:
    examples = {}
    for i, resp in enumerate(responses):
        req = resp.get("originalRequest", {})
        url_obj = req.get("url", {})
        query_list = url_obj.get("query", [])
        query_dict = {
            param["key"]: param.get("value", "")
            for param in query_list if param.get("key")
        }
        
        # Check for body example in response originalRequest
        body_obj = req.get("body", {})
        if body_obj.get("mode") == "raw" and body_obj.get("raw"):
            try:
                body_val = json.loads(body_obj["raw"])
                query_dict["request_body"] = body_val
            except:
                pass

        summary = resp.get("name", f"example_{i+1}")
        examples[f"example_{i+1}"] = {
            "summary": summary,
            "value": query_dict
        }
    return examples

def extract_base_url_from_first_request(items: List[Dict]) -> str:
    """
    Recursively traverse items to find the first request and extract its base URL.
    """
    for item in items:
        if "item" in item:
            # Folder, recurse
            url = extract_base_url_from_first_request(item["item"])
            if url:
                return url
        else:
            request = item.get("request", {})
            url_obj = request.get("url", {})
            # Prefer 'raw' if available, else reconstruct from protocol/host
            if "raw" in url_obj:
                raw_url = url_obj["raw"]
                parsed = urlparse(raw_url)
                return f"{parsed.scheme}://{parsed.netloc}"
            elif "protocol" in url_obj and "host" in url_obj:
                protocol = url_obj["protocol"]
                host = url_obj["host"]
                if isinstance(host, list):
                    host = ".".join(host)
                return f"{protocol}://{host}"
    return "http://localhost:8000"  # fallback

def convert_to_openapi(postman_collection) -> Tuple[dict, str]:
    postman = postman_collection if isinstance(postman_collection, dict) else json.loads(postman_collection)
    openapi = {
        "openapi": "3.1.0",
        "info": {
            "title": postman["collection"]["info"]["name"],
            "version": "1.0.0",
            "description": postman["collection"]["info"]["description"]
        },
        "paths": {}
    }

    def process_items(items: List[Dict]):
        used_operation_ids = set()
        
        for item in items:
            if "item" in item:
                process_items(item["item"])  # Recurse into folders
            else:
                request = item.get("request", {})
                if not request:
                    continue

                method = request.get("method", "GET").lower()
                url_obj = request.get("url", {})
                path, path_params = extract_path(url_obj)
                parameters = path_params + extract_query_parameters(url_obj)
                request_body = extract_request_body(request)
                summary = item.get("name", f"{method.upper()} {path}")
                description = request.get("description", "")
                
                op_id = slugify(summary)
                base_op_id = op_id
                counter = 1
                while op_id in used_operation_ids:
                    op_id = f"{base_op_id}_{counter}"
                    counter += 1
                used_operation_ids.add(op_id)

                examples = extract_examples(item.get("response", []))

                if path not in openapi["paths"]:
                    openapi["paths"][path] = {}
                
                responses_obj = {
                    "200": {
                        "description": "Successful response",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"}
                            }
                        }
                    }
                }
                
                if examples:
                    responses_obj["200"]["content"]["application/json"]["examples"] = examples
                    # Try to generate a more descriptive schema from the first example
                    first_example_val = list(examples.values())[0].get("value")
                    if first_example_val:
                        responses_obj["200"]["content"]["application/json"]["schema"] = generate_schema_from_example(first_example_val)

                operation_obj = {
                    "operationId": op_id,
                    "summary": summary,
                    "responses": responses_obj
                }
                
                if description:
                    operation_obj["description"] = description

                if parameters:
                    operation_obj["parameters"] = parameters
                
                if request_body:
                    operation_obj["requestBody"] = request_body
                
                openapi["paths"][path][method] = operation_obj
    def reinject_examples_in_description(openapi):
        for path, methods in openapi.get("paths", {}).items():
            for method, details in methods.items():
                desc = details.get("description", "")
                responses = details.get("responses", {})
                has_meaningful_examples = False
                example_text = "\n\n---\n**Examples:**\n"
                
                for resp in responses.values():
                    content = resp.get("content", {})
                    for ctype in content.values():
                        examples = ctype.get("examples", {})
                        if examples:
                            for ex in examples.values():
                                val = ex.get('value', {})
                                if val and val != {}:
                                    has_meaningful_examples = True
                                    example_text += f"- {ex.get('summary', '')}: `{json.dumps(val)}`\n"
                
                if has_meaningful_examples:
                    details["description"] = desc + example_text
                else:
                    details["description"] = desc
        return openapi

    process_items(postman["collection"]["item"])
    base_url = extract_base_url_from_first_request(postman["collection"]["item"])
    openapi["servers"] = [{"url": "http://localhost:8000"}]
    openapi = reinject_examples_in_description(openapi)
    return openapi,base_url