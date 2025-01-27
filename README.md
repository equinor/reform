Reform
======

A Python package that makes available Linux' User Namespaces functionality and
wraps around `unshare`, `chroot`, `mount` and so on.

Using
-----

`reform` can only be ran on Linux and requires that user namespaces are enabled.
This is the default on modern Linux distributions.

To use, install this package directly from GitHub: `pip install git+https://github.com/equinor/reform`

It is then possible to 

``` python
import os
from reform import Bind, call

# This is a normal Python function that will be run inside of a
# 'reform' call and will only see the `/hello` directory,
# instead of everything you have on your machine."
def list_files() -> None:
  print(f"Unshared environment: {os.listdir('/')}")

if __name__ == "__main__":
  print(f"Host environment: {os.listdir('/')}")
  
  config = {
    "/hello": Bind("/tmp")
  }
  
  call(config, list_files)
```

Developing
----------

This is an ordinary [Poetry](https://python-poetry.org/) environment. If you use
Nix, you can make use of the self-contained [Devenv](https://devenv.sh/)
configuration.

We use Pytest to run tests. These can only work on Linux as they require Linux-only APIs.
