import json
import re
from urllib.parse import urlparse, parse_qs
from typing import List, Dict, Tuple, Any, Optional

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
        # Merge schemas of all items in the list if possible, or just use the first one
        item_schema = {}
        if len(data) > 0:
            item_schema = generate_schema_from_example(data[0])
        return {"type": "array", "items": item_schema}
    if isinstance(data, dict):
        properties = {}
        for key, value in data.items():
            properties[key] = generate_schema_from_example(value)
        return {"type": "object", "properties": properties}
    return {"type": "string"}

def merge_schemas(s1: Dict, s2: Dict) -> Dict:
    """Simple deep merge of two OpenAPI schemas."""
    if not s1: return s2
    if not s2: return s1
    if s1.get("type") != s2.get("type"):
        return s1 # Conflict, keep first
    
    if s1.get("type") == "object":
        p1 = s1.get("properties", {})
        p2 = s2.get("properties", {})
        merged_props = {}
        all_keys = set(p1.keys()) | set(p2.keys())
        for k in all_keys:
            merged_props[k] = merge_schemas(p1.get(k, {}), p2.get(k, {}))
        return {"type": "object", "properties": merged_props}
    
    if s1.get("type") == "array":
        return {
            "type": "array",
            "items": merge_schemas(s1.get("items", {}), s2.get("items", {}))
        }
    
    return s1

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

def extract_request_body(request: Dict, responses: Optional[List[Dict]] = None) -> Dict:
    """
    Extract request body from main request and also check examples if necessary.
    """
    if responses is None:
        responses = []
    # Try the main request body first
    body_obj = request.get("body")
    primary_content = {}
    if body_obj:
        mode = body_obj.get("mode")
        if mode == "raw":
            raw_data = body_obj.get("raw", "")
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
            
            primary_content[media_type] = {
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
            primary_content["application/x-www-form-urlencoded"] = {
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
                        
            primary_content["multipart/form-data"] = {
                "schema": {
                    "type": "object",
                    "properties": properties
                }
            }

    # If the main body is lacking or simple, scan examples for better schemas/examples
    if responses:
        for resp in responses:
            orig_req = resp.get("originalRequest", {})
            orig_body = orig_req.get("body", {})
            if orig_body.get("mode") == "raw" and orig_body.get("raw"):
                raw_data = orig_body["raw"]
                try:
                    body_val = json.loads(raw_data)
                    new_schema = generate_schema_from_example(body_val)
                    media_type = "application/json"
                    
                    if media_type not in primary_content:
                        primary_content[media_type] = {
                            "schema": new_schema,
                            "examples": {}
                        }
                    
                    # Merge schemas if it was just a generic object
                    if primary_content[media_type]["schema"].get("type") == "object" and \
                       not primary_content[media_type]["schema"].get("properties"):
                        primary_content[media_type]["schema"] = new_schema
                    else:
                        primary_content[media_type]["schema"] = merge_schemas(primary_content[media_type]["schema"], new_schema)
                    
                    # Store as a named example in the requestBody
                    if "examples" not in primary_content[media_type]:
                        primary_content[media_type]["examples"] = {}
                    
                    ex_name = slugify(resp.get("name", "example"))
                    primary_content[media_type]["examples"][ex_name] = {
                        "summary": resp.get("name", ""),
                        "value": body_val
                    }
                    
                except:
                    pass

    if primary_content:
        return {"content": primary_content, "required": True}
    return {}

def extract_examples(responses: List[Dict]) -> Dict:
    examples = {}
    for i, resp in enumerate(responses):
        # Focus on response examples only
        res_body = resp.get("body", "")
        summary = resp.get("name", f"example_{i+1}")
        
        # In Postman, response body can be raw
        try:
            res_val = json.loads(res_body)
        except:
            res_val = res_body
            
        examples[f"example_{i+1}"] = {
            "summary": summary,
            "value": res_val
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
            "description": postman["collection"]["info"].get("description", "")
        },
        "paths": {}
    }

    used_operation_ids = set()

    def process_items(items: List[Dict]):
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
                
                resp_list = item.get("response", [])
                request_body = extract_request_body(request, resp_list)
                summary = item.get("name", f"{method.upper()} {path}")
                description = request.get("description", "")
                
                op_id = slugify(summary)
                base_op_id = op_id
                counter = 1
                while op_id in used_operation_ids:
                    op_id = f"{base_op_id}_{counter}"
                    counter += 1
                used_operation_ids.add(op_id)

                examples = extract_examples(resp_list)

                if path not in openapi["paths"]:
                    openapi["paths"][path] = {}
                
                # Merge schemas from all response examples for the response schema
                resp_schema = {"type": "object"}
                for ex in examples.values():
                    ex_val = ex.get("value")
                    if ex_val:
                        resp_schema = merge_schemas(resp_schema, generate_schema_from_example(ex_val))

                responses_obj = {
                    "200": {
                        "description": "Successful response",
                        "content": {
                            "application/json": {
                                "schema": resp_schema
                            }
                        }
                    }
                }
                
                if examples:
                    responses_obj["200"]["content"]["application/json"]["examples"] = examples

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