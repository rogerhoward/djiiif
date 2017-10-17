#!/usr/bin/env python


def urljoin(parts):
    """
    Takes a list of URL parts and smushes em together into a string,
    while ensuring no double slashes, but preserving any trailing slash(es)
    """
    if len(parts) == 0:
        raise ValueError('urljoin needs a list of at least length 1')
    return '/'.join([x.strip('/') for x in parts[0:-1]] + [parts[-1].lstrip('/')])
