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
import fastsdk  # noqa: E402
from apipod_registry import create_service  # noqa: E402
from socaity_schemas.contract import (  # noqa: E402
    Endpoint,
    EndpointParameter,
    ParameterDefinition,
    ServiceContract,
)


def main():
    """Main function demonstrating client factory usage."""
    # Create an example service from a handwritten contract
    contract = ServiceContract(
        title="Example Service",
        description="An example service for demonstration purposes",
        endpoints=[
            Endpoint(
                operation_id="swap-faces",
                path="/swap-img-to-img",
                display_name="Swap Images",
                description="Swap faces between two images",
                parameters=[
                    EndpointParameter(
                        name="source_img",
                        definition=ParameterDefinition(type="string", format="image"),
                        required=True,
                        location="body",
                        description="Source image containing the face(s) to swap from"
                    ),
                    EndpointParameter(
                        name="target_img",
                        definition=ParameterDefinition(type="string", format="image"),
                        required=True,
                        location="body",
                        description="Target image containing the face(s) to swap to"
                    ),
                    EndpointParameter(
                        name="enhance_face_model",
                        definition=ParameterDefinition(type="string"),
                        required=False,
                        default="gpen_bfr_512",
                        location="body",
                        description="Face enhancement model to use"
                    )
                ]
            ),
            Endpoint(
                operation_id="swap-video",
                path="/swap-video-to-video",
                display_name="Swap Video",
                description="Swap faces in a video",
                parameters=[
                    EndpointParameter(
                        name="faces",
                        definition=ParameterDefinition(type="string", format="file"),
                        required=True,
                        location="body",
                        description="The face(s) to swap to"
                    ),
                    EndpointParameter(
                        name="media",
                        definition=ParameterDefinition(type="string", format="file"),
                        required=True,
                        location="body",
                        description="The image or video to swap faces in"
                    ),
                    EndpointParameter(
                        name="enhance_face_model",
                        definition=ParameterDefinition(type="string"),
                        required=False,
                        default="gpen_bfr_512",
                        location="body",
                        description="Face enhancement model to use"
                    )
                ]
            )
        ]
    )
    service = create_service(contract, address="https://api.example.com", service_id="example-service")

    # Generate a client stub for this service (also registers it in the registry)
    output_dir = Path(__file__).parent / "generated_clients"
    stub = fastsdk.generate_stub(
        service,
        save_path=str(output_dir),
        class_name="ExampleService"
    )
    
    print(f"Client stub generated at: {stub.path}")
    
    # Print the contents of the generated file
    with open(stub.path, "r") as f:
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