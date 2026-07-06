"""
Note: This test should be moved to APIPodRegistry tests.
Example demonstrating how to use the apipod_registry Registry.

This example shows how to:
1. Add AIServices built from service contracts
2. Query services by ID, name, model, and category
3. Create and manage models and categories
"""

from apipod_registry import Registry, create_service
from socaity_schemas.contract import ServiceContract
from socaity_schemas.platform import AIModel, AIService, ServiceCategory


def main():
    # Create a service manager
    manager = Registry()

    # Add service categories
    image_category = ServiceCategory(
        id="img_generation",
        name="img_generation",
        display_name="Image Generation",
        input_modalities=["text"],
        output_modalities=["image"],
        description="Services that generate images from text prompts"
    )
    manager.add_category(image_category)

    text_category = ServiceCategory(
        id="text_generation",
        name="text_generation",
        display_name="Text Generation",
        input_modalities=["text"],
        output_modalities=["text"],
        description="Services that generate text from text prompts"
    )
    manager.add_category(text_category)

    # Add models
    sd_model = AIModel(
        id="sd_xl",
        name="sd_xl",
        display_name="Stable Diffusion XL",
        family="stable_diffusion",
    )
    manager.add_model(sd_model)

    llama_model = AIModel(
        id="llama3",
        name="llama3",
        display_name="Llama 3",
        family="llama",
    )
    manager.add_model(llama_model)

    # Create AIServices manually for demo purposes (usually parsed from a spec
    # via fastsdk.register_service or apipod_registry.materialize_contract).
    sd_service: AIService = create_service(
        ServiceContract(title="Stable Diffusion API", description="API for generating images with Stable Diffusion"),
        service_id="sd_service",
    )
    sd_service.categories = ["img_generation"]
    sd_service.models = [sd_model]
    manager.add_service(sd_service)
    print(f"Created demo service: {sd_service.display_name}")

    llm_service: AIService = create_service(
        ServiceContract(title="Llama API", description="API for generating text with Llama models"),
        service_id="llama_service",
    )
    llm_service.categories = ["text_generation"]
    llm_service.models = [llama_model]
    manager.add_service(llm_service)
    print(f"Created demo service: {llm_service.display_name}")

    # Demonstrate service queries

    # Get service by ID
    service = manager.get_service("sd_service")
    if service:
        print(f"\nService by ID: {service.display_name}")

    # Get service by name
    service = manager.get_service("Stable Diffusion API")
    if service:
        print(f"Service by name: {service.display_name}")

    # Get services by model
    services = manager.get_services_by_model("llama3")
    if services:
        print("\nServices using Llama 3:")
        for svc in services:
            print(f"- {svc.display_name}")

    # Get services by category
    services = manager.get_services_by_category("img_generation")
    if services:
        print("\nImage generation services:")
        for svc in services:
            print(f"- {svc.display_name}")

    # List all categories
    print("\nAll categories:")
    for category in manager.list_categories():
        print(f"- {category.display_name}")

    # Update a service (add_service is an upsert)
    sd_service.display_name = "Stable Diffusion XL API"
    manager.add_service(sd_service)
    service = manager.get_service("sd_service")
    if service:
        print(f"\nUpdated service name: {service.display_name}")


if __name__ == "__main__":
    main()
