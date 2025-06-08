"""
Example demonstrating how to use the fastsdk ServiceManager.

This example shows how to:
1. Add service definitions from OpenAPI specs
2. Query services by ID, name, family, and category
3. Create and manage service families and categories
"""

from fastsdk.service_management.service_manager import ServiceManager
from fastsdk.service_management.service_definition import (
    ServiceFamily, ServiceCategory, ModelDefinition, ServiceDefinition
)


def main():
    # Create a service manager
    manager = ServiceManager()
    
    # Add service categories
    image_category = ServiceCategory(
        id="img_generation",
        display_name="Image Generation",
        input_domain="text",
        output_domain="image",
        description="Services that generate images from text prompts"
    )
    manager.add_category(image_category)
    
    text_category = ServiceCategory(
        id="text_generation",
        display_name="Text Generation",
        input_domain="text",
        output_domain="text",
        description="Services that generate text from text prompts"
    )
    manager.add_category(text_category)
    
    # Add service families
    stable_diffusion_family = ServiceFamily(
        id="stable_diffusion",
        display_name="Stable Diffusion",
        description="Stable Diffusion image generation models",
        short_desc="Text-to-image models"
    )
    manager.add_family(stable_diffusion_family)
    
    llama_family = ServiceFamily(
        id="llama",
        display_name="Llama",
        description="Meta's Llama large language models",
        short_desc="Text generation models"
    )
    manager.add_family(llama_family)
    
    # Add models
    sd_model = ModelDefinition(
        id="sd_xl",
        display_name="Stable Diffusion XL",
        author="Stability AI",
        license="CreativeML Open RAIL-M",
        paper_url="https://arxiv.org/abs/2307.01952"
    )
    manager.add_model(sd_model)
    
    llama_model = ModelDefinition(
        id="llama3",
        display_name="Llama 3",
        author="Meta AI",
        license="Meta Llama 3 License",
        paper_url="https://ai.meta.com/llama/"
    )
    manager.add_model(llama_model)
    
    # Add services from OpenAPI specs
    # This would typically load from a URL or file path
    # For example purposes, we'll use placeholder data
    try:
        # In a real application, use actual OpenAPI spec URLs
        sd_service = manager.add_service(
            "sd_service", 
            "https://api.example.com/sd_api/openapi.json"
        )
        print(f"Added service: {sd_service.display_name}")
    except (ValueError, TypeError) as e:
        # We're using a dummy URL, so this will likely fail
        print(f"Could not add service: {e}")
        
        # Create a ServiceDefinition manually for demo purposes
        sd_service = ServiceDefinition(
            id="sd_service",
            display_name="Stable Diffusion API",
            description="API for generating images with Stable Diffusion",
            specification="socaity",
            category=["img_generation"],  # Reference to category ID
            family_id="stable_diffusion",  # Reference to family ID
            used_models=[sd_model]  # Reference to model
        )
        manager._services[sd_service.id] = sd_service
        print(f"Created demo service: {sd_service.display_name}")
        
        llm_service = ServiceDefinition(
            id="llama_service",
            display_name="Llama API",
            description="API for generating text with Llama models",
            specification="socaity",
            category=["text_generation"],  # Reference to category ID
            family_id="llama",  # Reference to family ID
            used_models=[llama_model]  # Reference to model
        )
        manager._services[llm_service.id] = llm_service
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
    
    # Get services by family
    services = manager.get_services_by_family("llama")
    if services:
        print("\nServices in Llama family:")
        for svc in services:
            print(f"- {svc.display_name}")
    
    # Get services by category
    services = manager.get_services_by_category("img_generation")
    if services:
        print("\nImage generation services:")
        for svc in services:
            print(f"- {svc.display_name}")
    
    # Demonstrate other features
    
    # List all categories
    print("\nAll categories:")
    for category in manager.list_categories():
        print(f"- {category.display_name}")
    
    # List all families
    print("\nAll families:")
    for family in manager.list_families():
        print(f"- {family.display_name}")
    
    # Update a service
    manager.update_service("sd_service", display_name="Stable Diffusion XL API")
    service = manager.get_service("sd_service")
    if service:
        print(f"\nUpdated service name: {service.display_name}")


if __name__ == "__main__":
    main() 