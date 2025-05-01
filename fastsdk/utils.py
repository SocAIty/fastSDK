import inspect
from typing import Any, Optional
import os
from collections.abc import Iterable
import re
import unicodedata


def is_valid_file_path(path: str):
    try:
        is_file = os.path.isfile(path)
        return is_file
    except OSError:
        return False


def get_function_parameters_as_dict(
        func: callable,
        exclude_param_names: list | str | None = None,
        exclude_param_types: list | Any = None,
        func_args: list | tuple | None = None,
        func_kwargs: dict | None = None
):
    """
    Get the parameters of a function as a dict
    :param func: the function to get the parameters from
    :param exclude_param_names: the names of the parameters to exclude
    :param exclude_param_types: the types of the parameters to exclude
    :param func_args: the arguments of the function at runtime
    :param func_kwargs: the keyword arguments of the function at runtime
    :return: a dict with the parameters as key and the value as value
    """
    exclude_param_names = [] if not exclude_param_names else exclude_param_names
    exclude_param_types = [] if not exclude_param_types else exclude_param_types
    func_args = [] if not func_args else func_args
    func_kwargs = {} if not func_kwargs else func_kwargs

    if isinstance(exclude_param_names, str):
        exclude_param_names = [exclude_param_names]
    if not isinstance(exclude_param_types, list):
        exclude_param_types = [exclude_param_types]
    exclude_param_names = [p.lower() for p in exclude_param_names]

    named_func_params = [
        p for p in inspect.signature(func).parameters.values()
        if p.annotation not in exclude_param_types
        and p.name.lower() not in exclude_param_names
    ]
    # fill params in order of kwargs
    params = {}
    for i, arg in enumerate(func_args):
        params[named_func_params[i].name] = arg
    # add the kwargs
    params.update(func_kwargs)
    return params


def flatten_list(xs):
    for x in xs:
        if isinstance(x, Iterable) and not isinstance(x, (str, bytes)):
            yield from flatten_list(x)
        else:
            yield x


def normalize_name(name: str, preserve_paths: bool = False) -> Optional[str]:
    """
    Normalizes a string for use as a Python identifier or path component.
    - Converts to lowercase.
    - Removes leading/trailing whitespace.
    - Replaces spaces, underscores, and invalid characters with hyphens.
    - Removes accents from characters.
    - Collapses multiple consecutive hyphens into one.
    - Optionally preserves forward slashes for path normalization.

    Args:
        name: The string to normalize.
        preserve_paths: If True, forward slashes ('/') are kept.

    Returns:
        The normalized string, or None if the input is None or empty after normalization.
    """
    if not name or not isinstance(name, str):
        return None

    # Remove accents and convert to lowercase
    nfkd_form = unicodedata.normalize('NFKD', name.lower())
    normalized = "".join([c for c in nfkd_form if not unicodedata.combining(c)])

    # Keep only alphanumeric, hyphens, and optionally slashes
    if preserve_paths:
        # Allow slashes, replace other invalid chars with hyphen
        normalized = re.sub(r'[^a-z0-9\-/]', '-', normalized) # Keep alphanumeric, hyphen, slash
        # Collapse multiple hyphens, but not around slashes
        normalized = re.sub(r'-+', '-', normalized)
        # Remove leading/trailing hyphens unless it's the only character or next to a slash
        normalized = re.sub(r'(?<!/)-$', '', normalized) # Trailing hyphen unless after slash
        normalized = re.sub(r'^-(?!/)', '', normalized) # Leading hyphen unless before slash

    else:
        # Replace disallowed characters (anything not alphanumeric) with hyphens
        normalized = re.sub(r'[^a-z0-9]+', '-', normalized)
        # Collapse multiple hyphens
        normalized = re.sub(r'-+', '-', normalized)
        # Remove leading/trailing hyphens
        normalized = normalized.strip('-')

    return normalized if normalized else None 


def get_unique_id(base_id: str, existing_ids: set) -> str:
    """
    Generate a unique ID based on a base ID and a set of existing IDs.
    Appends a number to the base ID if it already exists.
    
    Args:
        base_id: Base ID to make unique
        existing_ids: Set of existing IDs to check against
        
    Returns:
        Unique ID string
    """
    if base_id not in existing_ids:
        return base_id
    
    counter = 1
    while f"{base_id}_{counter}" in existing_ids:
        counter += 1
    
    return f"{base_id}_{counter}"

