import os
import sys
from ... import SpiSlaveBase

__dir_path = os.path.dirname(os.path.abspath(__file__))
__ignore = ['__init__.py']

for f in [f[:-3] for f in os.listdir(__dir_path) if f.endswith('.py') and f not in __ignore]:
    mod = __import__('.'.join([__name__, f]), fromlist=[f])
    objects = [getattr(mod, x) for x in dir(mod)]
    to_import = []

    for a in objects:
        try:
            if issubclass(a, SpiSlaveBase):
                to_import.append(a)
        except TypeError:
            pass

    for i in to_import:
        try:
            setattr(sys.modules[__name__], i.__name__, i)
        except AttributeError:
            pass
