"""
fastsdk command line interface.

Mirrors the Python API one-to-one:

    fastsdk inspect  <source>                   ->  fastsdk.inspect_service(source)
    fastsdk generate <source> -o clients/       ->  fastsdk.generate_stub(source, save_path="clients/")
    fastsdk call     <source> <endpoint> ...    ->  fastsdk.connect(source).submit_job(endpoint, ...)
    fastsdk registry list|add|remove|show       ->  persistent local registry management

The registry subcommand stores services on disk (default: ~/.fastsdk/registry, override with
FASTSDK_REGISTRY_PATH), so registered services can be used by name in later invocations.
"""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from apipod_registry import FileSystemStore, Registry
from socaity_schemas.contract.address import service_url
from socaity_schemas.platform import AIService

from fastsdk.service_access import service_address, service_contract, service_provider


DEFAULT_REGISTRY_PATH = Path.home() / ".fastsdk" / "registry"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _registry_path() -> Path:
    return Path(os.getenv("FASTSDK_REGISTRY_PATH", str(DEFAULT_REGISTRY_PATH)))


def _open_persistent_registry() -> Registry:
    return Registry(service_store=FileSystemStore(path=str(_registry_path())))


def _resolve_source(source: str) -> Union[str, AIService]:
    """If the source matches a service in the persistent CLI registry, use that service."""
    try:
        stored = _open_persistent_registry().get_service(source)
    except Exception:
        stored = None
    return stored or source


def _address_url(service: AIService) -> str:
    address = service_address(service)
    return service_url(address) if address else "-"


def _service_summary(service: AIService) -> str:
    contract = service_contract(service)
    return (
        f"{service.display_name} (id: {service.id}, spec: {contract.specification}, "
        f"provider: {service_provider(service)}, address: {_address_url(service)})"
    )


def _print_service(service: AIService, as_json: bool = False):
    if as_json:
        print(json.dumps(service.model_dump(exclude_none=True), indent=2, default=str))
        return

    from fastsdk.sdk_factory.sdk_factory import _get_type_hint

    contract = service_contract(service)
    print(f"Service:  {service.display_name}")
    print(f"ID:       {service.id}")
    print(f"Spec:     {contract.specification}")
    print(f"Provider: {service_provider(service)}")
    print(f"Address:  {_address_url(service)}")
    if service.description:
        desc = service.description.strip().split("\n")[0]
        print(f"About:    {desc[:120]}")
    print("Endpoints:")
    for endpoint in contract.endpoints:
        print(f"  {endpoint.path}")
        for param in endpoint.parameters:
            if param.location not in ("body", "query"):
                continue
            type_hint = _get_type_hint(param)
            suffix = ""
            if param.default is not None:
                suffix = f" = {param.default!r}"
            elif not param.required:
                suffix = " (optional)"
            print(f"    {param.name}: {type_hint}{suffix}")


def _parse_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw


def _parse_endpoint_params(extra: List[str]) -> Dict[str, Any]:
    """Convert leftover CLI arguments ("--text", "hello", "--steps=4") into endpoint parameters."""
    params: Dict[str, Any] = {}
    i = 0
    while i < len(extra):
        token = extra[i]
        if not token.startswith("--"):
            raise SystemExit(f"Unexpected argument '{token}'. Endpoint parameters must be passed as --name value.")
        key = token[2:]
        if "=" in key:
            key, raw = key.split("=", 1)
        elif i + 1 < len(extra) and not extra[i + 1].startswith("--"):
            raw = extra[i + 1]
            i += 1
        else:
            raw = "true"  # bare flag
        params[key.replace("-", "_")] = _parse_value(raw)
        i += 1
    return params


def _emit_result(result: Any, output: Optional[str]):
    if result is None:
        print("Job finished but returned no result.")
        return

    if isinstance(result, (list, tuple)) and result and all(hasattr(r, "save") for r in result):
        for idx, media in enumerate(result):
            target = f"{Path(output).stem}_{idx}{Path(output).suffix}" if output else getattr(media, "file_name", f"result_{idx}.bin")
            media.save(str(target))
            print(f"Saved result to {target}")
        return

    if hasattr(result, "save"):
        target = output or getattr(result, "file_name", None) or "result.bin"
        result.save(str(target))
        print(f"Saved result to {target}")
        return

    text = json.dumps(result, indent=2, default=str) if isinstance(result, (dict, list)) else str(result)
    if output:
        Path(output).write_text(text, encoding="utf-8")
        print(f"Saved result to {output}")
    else:
        print(text)


def _import_hint(stub_path: str, class_name: str) -> str:
    try:
        relative = Path(stub_path).resolve().relative_to(Path.cwd())
        module = ".".join(relative.with_suffix("").parts)
        return f"from {module} import {class_name}"
    except ValueError:
        return f"# stub saved outside the current directory:\n  # {stub_path} (class {class_name})"


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_inspect(args: argparse.Namespace):
    import fastsdk
    service = fastsdk.inspect_service(_resolve_source(args.source), api_key=args.api_key)
    _print_service(service, as_json=args.json)


def cmd_generate(args: argparse.Namespace):
    import fastsdk
    kwargs = {}
    if args.service_name:
        kwargs["service_name"] = args.service_name
    stub = fastsdk.generate_stub(
        _resolve_source(args.source),
        save_path=args.output,
        class_name=args.name,
        template=args.template,
        api_key=args.api_key,
        **kwargs
    )
    print(f"Generated {stub.path}")
    print(f"  class:   {stub.class_name}")
    print(f"  service: {_service_summary(stub.service)}")
    print()
    print("Use it:")
    print(f"  {_import_hint(stub.path, stub.class_name)}")
    print(f"  client = {stub.class_name}()")


def cmd_call(args: argparse.Namespace, extra: List[str]):
    from fastsdk.fastClient import FastClient

    params = _parse_endpoint_params(extra)
    client = FastClient(_resolve_source(args.source), api_key=args.api_key)
    service = client.service
    endpoints = service_contract(service).endpoints

    endpoint = args.endpoint
    if not endpoint:
        if len(endpoints) == 1:
            endpoint = endpoints[0].path
        else:
            paths = "\n  ".join(ep.path for ep in endpoints)
            raise SystemExit(f"Service has multiple endpoints, please specify one:\n  {paths}")

    print(f"Calling {endpoint} on {service.display_name} ...")
    try:
        job = client.submit_job(endpoint, **params)
        result = job.wait_for_result()
        _emit_result(result, args.output)
    finally:
        # shut down the meseex worker threads so the process exits cleanly
        job_manager = client.fsdk._api_job_manager
        if job_manager is not None:
            try:
                job_manager.meseex_box.shutdown(graceful=True)
            except Exception:
                pass


def cmd_registry(args: argparse.Namespace):
    import fastsdk
    registry = _open_persistent_registry()

    if args.registry_command == "list":
        services = registry.list_services()
        if not services:
            print(f"No services registered ({_registry_path()}).")
            return
        for service in services:
            print(f"  {_service_summary(service)}")

    elif args.registry_command == "add":
        service = fastsdk.inspect_service(
            args.source,
            service_id=args.id,
            name=args.name,
            api_key=args.api_key
        )
        registry.add_service(service)
        print(f"Registered {_service_summary(service)}")
        print(f"Registry: {_registry_path()}")

    elif args.registry_command == "remove":
        if registry.remove_service(args.id):
            print(f"Removed service '{args.id}'.")
        else:
            raise SystemExit(f"Service '{args.id}' not found in registry ({_registry_path()}).")

    elif args.registry_command == "show":
        service = registry.get_service(args.id)
        if not service:
            raise SystemExit(f"Service '{args.id}' not found in registry ({_registry_path()}).")
        _print_service(service, as_json=args.json)

    else:
        raise SystemExit("Usage: fastsdk registry {list,add,remove,show}")


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fastsdk",
        description="fastsdk CLI - inspect AI/web services, generate Python client stubs and call endpoints.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  fastsdk inspect http://localhost:8009                       Show endpoints + parameters of a service
  fastsdk generate http://localhost:8009 -o clients/          Generate a Python client stub
  fastsdk generate replicate:black-forest-labs/flux-schnell   Generate a stub for a Replicate model
  fastsdk call http://localhost:8009 /text2voice --text "hi"  Call an endpoint directly
  fastsdk registry add http://localhost:8009 --name speech    Register a service for later use by name
  fastsdk registry list                                       List registered services
        """
    )

    sub = parser.add_subparsers(dest="command")

    p_inspect = sub.add_parser("inspect", help="Show service name, address, endpoints and parameters")
    p_inspect.add_argument("source", help="Service URL, openapi.json path, Replicate model ref or registered service name")
    p_inspect.add_argument("--api-key", default=None, help="API key (required for RunPod/Replicate sources)")
    p_inspect.add_argument("--json", action="store_true", help="Print the raw service definition as JSON")

    p_gen = sub.add_parser("generate", help="Generate a Python client stub (.py) for a service")
    p_gen.add_argument("source", help="Service URL, openapi.json path, Replicate model ref or registered service name")
    p_gen.add_argument("-o", "--output", default=None, help="File or directory for the generated stub (default: current directory)")
    p_gen.add_argument("--name", default=None, help="Class name for the generated client (default: derived from service name)")
    p_gen.add_argument("--service-name", default=None, help="Override the service display name")
    p_gen.add_argument("--template", default=None, help="Custom Jinja2 template path")
    p_gen.add_argument("--api-key", default=None, help="API key (required for RunPod/Replicate sources)")

    p_call = sub.add_parser(
        "call",
        help="Call a service endpoint directly from the terminal",
        description="Endpoint parameters are passed as additional --name value pairs, e.g.: "
                    "fastsdk call http://localhost:8009 /text2voice --text \"hello\" --voice hermine"
    )
    p_call.add_argument("source", help="Service URL, openapi.json path, Replicate model ref or registered service name")
    p_call.add_argument("endpoint", nargs="?", default=None, help="Endpoint path (optional if the service has exactly one endpoint)")
    p_call.add_argument("--api-key", default=None, help="API key for the service")
    p_call.add_argument("-o", "--output", default=None, help="Save the result to this file (auto-detected for media results)")

    p_reg = sub.add_parser("registry", help="Manage the local persistent service registry")
    reg_sub = p_reg.add_subparsers(dest="registry_command")
    reg_sub.add_parser("list", help="List registered services")
    reg_add = reg_sub.add_parser("add", help="Load a service and store it in the local registry")
    reg_add.add_argument("source", help="Service URL, openapi.json path or Replicate model ref")
    reg_add.add_argument("--name", default=None, help="Display name for the service")
    reg_add.add_argument("--id", default=None, help="Service ID (default: derived from the spec)")
    reg_add.add_argument("--api-key", default=None, help="API key (required for RunPod/Replicate sources)")
    reg_remove = reg_sub.add_parser("remove", help="Remove a service from the local registry")
    reg_remove.add_argument("id", help="Service ID or name")
    reg_show = reg_sub.add_parser("show", help="Show a registered service")
    reg_show.add_argument("id", help="Service ID or name")
    reg_show.add_argument("--json", action="store_true", help="Print the raw service definition as JSON")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args, extra = parser.parse_known_args(argv)

    if args.command != "call" and extra:
        parser.error(f"Unrecognized arguments: {' '.join(extra)}")

    try:
        if args.command == "inspect":
            cmd_inspect(args)
        elif args.command == "generate":
            cmd_generate(args)
        elif args.command == "call":
            cmd_call(args, extra)
        elif args.command == "registry":
            cmd_registry(args)
        else:
            parser.print_help()
            return 1
    except KeyboardInterrupt:
        print("\nAborted.")
        return 130
    except (ValueError, ImportError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
