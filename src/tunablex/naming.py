def ns_to_field(ns: str) -> str:
    """Convert a dotted namespace to a valid attribute name on the AppConfig."""
    return ns.replace(".", "__").replace("-", "_")
