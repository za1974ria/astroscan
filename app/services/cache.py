def cache_read(cache_get, key, ttl):
    """Wrapper minimal vers cache_get existant."""
    return cache_get(key, ttl)


def cache_write(cache_set, key, value):
    """Wrapper minimal vers cache_set existant."""
    cache_set(key, value)
