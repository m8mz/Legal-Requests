#!/usr/bin/env python3.7

import sys
from distutils.core import setup

class BadVersion(Exception):
    
    def __init__(self, m):
        self.message = m
    
    
    def __str__(self):
        return self.message

if sys.version_info < (3, 7, 0, 'final', 0):
    try:
        raise BadVersion('Python 3.7 or later is required!')
    except BadVersion as err:
        print(err)
        
setup(name='Agent',
      version='1.0',
      py_modules=['Agent'],
      )