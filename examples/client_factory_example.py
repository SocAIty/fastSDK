#!/usr/bin/env python
"""
Example demonstrating the use of the fastSDK client factory.
This script creates a Python client for a service definition.
"""

import sys
from pathlib import Path

# Add parent directory to path to import fastsdk
current_path = Path(__file__).parent.parent
sys.path.append(str(current_path))

# Now we can import from fastsdk
from fastsdk.client_factory.api_client_factory import create_client  # noqa: E402
from fastsdk.service_management import ServiceManager  # noqa: E402
from fastsdk.service_management.service_definition import (  # noqa: E402
    ServiceDefinition, EndpointDefinition, EndpointParameter,
    ServiceAddress
)


def main():
    """Main function demonstrating client factory usage."""
    # Create an example service definition
    service = ServiceDefinition(
        id="example-service",
        display_name="Example Service",
        description="An example service for demonstration purposes",
        service_address=ServiceAddress(url="https://api.example.com"),
        endpoints=[
            EndpointDefinition(
                id="swap-faces",
                path="/swap-img-to-img",
                display_name="Swap Images",
                description="Swap faces between two images",
                parameters=[
                    EndpointParameter(
                        name="source_img",
                        type="image",
                        required=True,
                        location="body",
                        description="Source image containing the face(s) to swap from"
                    ),
                    EndpointParameter(
                        name="target_img",
                        type="image",
                        required=True,
                        location="body",
                        description="Target image containing the face(s) to swap to"
                    ),
                    EndpointParameter(
                        name="enhance_face_model",
                        type="string",
                        required=False,
                        default="gpen_bfr_512",
                        location="body",
                        description="Face enhancement model to use"
                    )
                ]
            ),
            EndpointDefinition(
                id="swap-video",
                path="/swap-video-to-video",
                display_name="Swap Video",
                description="Swap faces in a video",
                parameters=[
                    EndpointParameter(
                        name="faces",
                        type="file",
                        required=True,
                        location="body",
                        description="The face(s) to swap to"
                    ),
                    EndpointParameter(
                        name="media",
                        type="file",
                        required=True,
                        location="body",
                        description="The image or video to swap faces in"
                    ),
                    EndpointParameter(
                        name="enhance_face_model",
                        type="string",
                        required=False,
                        default="gpen_bfr_512",
                        location="body",
                        description="Face enhancement model to use"
                    )
                ]
            )
        ]
    )

    # Register the service with the ServiceManager
    ServiceManager._services[service.id] = service
    
    # Create a client for this service
    output_dir = Path(__file__).parent / "generated_clients"
    client_path = create_client(
        service_definition=service,
        save_path=str(output_dir),
        class_name="ExampleService"
    )
    
    print(f"Client generated at: {client_path}")
    
    # Print the contents of the generated file
    with open(client_path, "r") as f:
        print("\nGenerated client code:")
        print("-" * 50)
        print(f.read())
    
    # Usage example (would work if the client was actually installed)
    print("\nUsage example:")
    print("-" * 50)
    print("from generated_clients.exampleservice import ExampleService")
    print("client = ExampleService(api_key='your_api_key')")
    print("result = client.swap_img_to_img(source_img='path/to/source.jpg', target_img='path/to/target.jpg')")
    print("print(result)")


if __name__ == "__main__":
    main() 