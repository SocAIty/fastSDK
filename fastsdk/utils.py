import inspect
from typing import Union, Any
import os
from collections.abc import Iterable
import re

from media_toolkit.utils.file_conversion import media_from_file_result


def is_valid_file_path(path: str):
    try:
        is_file = os.path.isfile(path)
        return is_file
    except:
        return False


def get_function_parameters_as_dict(
        func: callable,
        exclude_param_names: Union[list, str] = None,
        exclude_param_types: Union[list, Any] = None,
        func_args: Union[list, tuple] = None,
        func_kwargs: dict = None
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


def normalize_name(name: str, preserve_paths: bool = False) -> Union[str, None]:
    """
    Normalize a name to be openapi compatible and better searchable.
    Will remove any special characters. Transforms lowercase. Replaces spaces with hyphens.
    :param name: The service name to normalize
    :param preserve_paths: If True, preserves forward slashes (/) for path segments
    :return: Normalized service name
    """
    if name is None or not isinstance(name, str):
        return None

    def normalize_segment(text: str) -> str:
        """Helper function to normalize a single segment of text"""
        text = text.lower()
        text = ' '.join(text.split())  # Replace multiple spaces with single space
        text = text.replace("\\", "/")  # Replace backslashes with forward slashes
        text = text.replace(' ', '-').replace("_", '-')   # Replace spaces and _ with hyphens
        text = re.sub(r'[^a-z0-9-]', '', text)  # Keep only alphanumeric and hyphens
        text = re.sub(r'-+', '-', text)  # Replace multiple hyphens with single hyphen
        return text.strip('-')  # Remove leading/trailing hyphens

    if preserve_paths:
        # Normalize each non-empty path segment
        result = '/'.join(
            segment for segment in
            (normalize_segment(s) for s in name.split('/'))
            if segment
        )
    else:
        result = normalize_segment(name)

    return result if result else None

