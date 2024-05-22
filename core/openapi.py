def preprocessing_filter_spec(endpoints):
    filtered = []
    for (path, path_regex, method, callback) in endpoints:
        # Remove all but DRF API endpoints
        if path.startswith("/openapi/v1") and not path.startswith("/openapi/v1/index"):
            filtered.append((path, path_regex, method, callback))
    return filtered