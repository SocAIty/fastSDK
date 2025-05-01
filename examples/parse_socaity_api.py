#!/usr/bin/env python3

"""
Example script to parse a SocAIty API specification.
This demonstrates how the enhanced OpenAPIParser correctly identifies
file, image, video, and audio parameter types from OpenAPI specifications.
"""

import json
import sys

from fastsdk.service_management.parsers.api_parser import OpenAPIParser


def main():
    """Parse the specified OpenAPI file or use an example spec."""
    # Use the file path provided as argument or use a simple built-in example
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        try:
            with open(input_file, 'r') as f:
                spec = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading OpenAPI spec: {e}")
            sys.exit(1)
    else:
        # Use a minimal example spec if none provided
        spec = {
            "openapi": "3.1.0",
            "info": {
                "title": "SocAIty Media API",
                "summary": "Process media files with AI models",
                "version": "0.1.0",
                "fast-task-api": "1.0.9"
            },
            "paths": {
                "/api/process": {
                    "post": {
                        "summary": "Process Media",
                        "description": "Process media files with AI",
                        "operationId": "process_media",
                        "requestBody": {
                            "content": {
                                "multipart/form-data": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "image_file": {
                                                "anyOf": [
                                                    {"type": "string", "format": "binary"},
                                                    {"$ref": "#/components/schemas/ImageModel"}
                                                ],
                                                "title": "Image File"
                                            },
                                            "audio_file": {
                                                "anyOf": [
                                                    {"type": "string", "format": "binary"},
                                                    {"$ref": "#/components/schemas/AudioModel"}
                                                ],
                                                "title": "Audio File"
                                            },
                                            "video_file": {
                                                "anyOf": [
                                                    {"type": "string", "format": "binary"},
                                                    {"$ref": "#/components/schemas/VideoModel"}
                                                ],
                                                "title": "Video File"
                                            },
                                            "document_file": {
                                                "type": "string",
                                                "format": "binary",
                                                "title": "Document File"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "components": {
                "schemas": {
                    "ImageModel": {
                        "properties": {
                            "file_name": {"type": "string"},
                            "content_type": {"type": "string"},
                            "content": {"type": "string"}
                        },
                        "type": "object",
                        "title": "ImageModel"
                    },
                    "AudioModel": {
                        "properties": {
                            "file_name": {"type": "string"},
                            "content_type": {"type": "string"},
                            "content": {"type": "string"}
                        },
                        "type": "object",
                        "title": "AudioModel"
                    },
                    "VideoModel": {
                        "properties": {
                            "file_name": {"type": "string"},
                            "content_type": {"type": "string"},
                            "content": {"type": "string"}
                        },
                        "type": "object",
                        "title": "VideoModel"
                    }
                }
            }
        }

    # Parse the spec
    parser = OpenAPIParser(spec)
    service = parser.parse()

    # Print basic service info
    print(f"Service: {service.display_name}")
    print(f"Specification type: {service.specification}")
    print(f"Number of endpoints: {len(service.endpoints)}")
    
    # Analyze each endpoint and its parameters
    for endpoint in service.endpoints:
        print(f"\nEndpoint: {endpoint.path} - {endpoint.display_name}")
        if not endpoint.parameters:
            print("  No parameters")
            continue
            
        print("  Parameters:")
        for param in endpoint.parameters:
            required = "required" if param.required else "optional"
            print(f"    - {param.name} ({param.type}, {param.location}, {required})")
            
            # Check if special type (file, image, video, audio)
            if param.type in ["file", "image", "video", "audio"]:
                print(f"      Special media type detected: {param.type}")


if __name__ == "__main__":
    main() 