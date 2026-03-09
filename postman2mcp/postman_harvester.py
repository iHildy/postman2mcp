import requests
import re


def harvest_postman_collection(collection_id, postman_api_key):
    url = f"https://api.postman.com/collections/{collection_id}"
    headers = {
        "X-Api-Key": postman_api_key
    }
    print(f"Fetching collection from {url}...")
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch collection: {response.status_code} {response.text}")
    print(f"Collection ID: {collection_id} fetched successfully!")
    return response.json()


def discover_collections_from_org_content(org_content_url):
    response = requests.get(org_content_url, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch org content URL: {response.status_code} {response.text}")

    matches = re.findall(r"https://www\.postman\.com/[^\"'\\s]+/collection/([A-Za-z0-9-]+)/([A-Za-z0-9-]+)", response.text)
    matches.extend(re.findall(r"/[^\"'\\s]+/collection/([A-Za-z0-9-]+)/([A-Za-z0-9-]+)", response.text))

    collections = []
    seen = set()
    for collection_id, slug in matches:
        if collection_id in seen:
            continue
        seen.add(collection_id)
        collections.append({
            "id": collection_id,
            "name": slug.replace("-", " "),
        })

    if not collections:
        raise RuntimeError("No collections found in the provided Postman org content URL.")
    return collections
