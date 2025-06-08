import re


def normalize_identifier(
    original: str,
    replacement_char: str,
    allowed_non_alphanum: str,
    trim_chars: str
) -> str:
    """
    Generalized identifier normalization utility.

    Args:
        original (str): The original string to normalize.
        replacement_char (str): Character to replace disallowed characters with (e.g., "-" or "_").
        allowed_non_alphanum (str): A string of non-alphanumeric characters that should be allowed.
        trim_chars (str): Characters to strip from the beginning and end of the result.

    Returns:
        str: A normalized, lowercase identifier with enforced formatting rules.
    """
    # Convert to lowercase
    normalized = original.lower()

    # Optional: Convert backslashes to slashes for web names
    if replacement_char == "-":
        normalized = normalized.replace("\\", "/")

    # Replace all characters that are not a-z, 0-9, or explicitly allowed
    allowed = f"a-z0-9{re.escape(allowed_non_alphanum)}"
    normalized = re.sub(f"[^{allowed}]+", replacement_char, normalized)

    # Replace multiple consecutive replacement characters with one
    normalized = re.sub(f"{re.escape(replacement_char)}+", replacement_char, normalized)

    # Trim unwanted leading/trailing characters
    normalized = normalized.strip(trim_chars + replacement_char)

    # Ensure the identifier does not start with a digit
    if normalized and normalized[0].isdigit():
        normalized = replacement_char + normalized

    return normalized

            
def normalize_name_for_py(name: str) -> str:
    """
    Normalizes a string to be used as a Python module, method or class name by:
    - Replacing all special characters with underscores
    - Lowercasing the result
    - Preventing double underscores and invalid leading/trailing characters
    - Avoiding names that start with a digit

    Args:
        name (str): The input string to normalize.

    Returns:
        str: A Python module-safe, normalized string.
    """
    name = normalize_identifier(
        original=name,
        replacement_char='_',
        allowed_non_alphanum='',
        trim_chars='_'
    )
    if len(name) == 0:
        return "no_name"
    return name
