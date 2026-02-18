# my_mcp_tool/cli.py
import click
from .postman_harvester import harvest_postman_collection, discover_collections_from_org_content
from .openapi_converter import convert_to_openapi
from .file_generator import generate_project_files
import os

@click.command()
@click.option('--collection-id', required=False, help='Postman collection ID')
@click.option('--org-content-url', required=False, help='Postman org/workspace overview URL')
@click.option('--project-dir', default='my-mcp-project', help='Directory to create the project in')
@click.option('--postman-api-key', required=True, help='Postman API key')
@click.option('--ngrok-authtoken', required=False, help='Ngrok authentication token')
def main(collection_id, org_content_url, project_dir, postman_api_key, ngrok_authtoken):
    if not collection_id and not org_content_url:
        raise click.UsageError("Provide either --collection-id or --org-content-url.")
    if collection_id and org_content_url:
        raise click.UsageError("Use only one of --collection-id or --org-content-url.")

    # Ensure the project directory exists
    project_dir = os.path.abspath(project_dir)
    if not os.path.exists(project_dir):
        os.makedirs(project_dir)

    selected_collection_ids = [collection_id] if collection_id else []
    if org_content_url:
        available_collections = discover_collections_from_org_content(org_content_url)
        click.echo("Collections found:")
        for idx, collection in enumerate(available_collections, start=1):
            click.echo(f"{idx}. {collection['name']} ({collection['id']})")
        selection = click.prompt("Select collections by number (comma-separated) or type 'all'", default="all")
        if selection.strip().lower() == "all":
            selected_collection_ids = [collection["id"] for collection in available_collections]
        else:
            try:
                indices = [int(value.strip()) for value in selection.split(",") if value.strip()]
                selected_collection_ids = [available_collections[index - 1]["id"] for index in indices]
            except (ValueError, IndexError):
                raise click.UsageError("Invalid selection. Use 'all' or valid collection numbers separated by commas.")

    # Step 1: Harvest Postman collection(s)
    harvested_collections = [harvest_postman_collection(selected_id, postman_api_key) for selected_id in selected_collection_ids]
    primary_collection = harvested_collections[0]
    if len(harvested_collections) > 1:
        merged_items = []
        descriptions = []
        for collection in harvested_collections:
            merged_items.extend(collection["collection"].get("item", []))
            description = collection["collection"].get("info", {}).get("description")
            if description:
                descriptions.append(description)
        primary_collection = {
            "collection": {
                "info": {
                    "name": "Merged Postman Collections",
                    "description": "\n\n".join(descriptions),
                },
                "item": merged_items,
            }
        }

    # Step 2: Convert to OpenAPI
    openapi_spec, base_url = convert_to_openapi(primary_collection)

    # Step 3: Generate project files
    generate_project_files(project_dir, primary_collection, openapi_spec, base_url, postman_api_key, ngrok_authtoken=None)
    click.echo(f"Project files generated in {project_dir}")

if __name__ == '__main__':
    main()
