"""
Copyright (c) 2021 Spencer Chang

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""
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
