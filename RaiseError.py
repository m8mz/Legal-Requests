#!/usr/bin/env python3.7

class raiseError(Exception):


    def __init__(self, msg):
        self.msg = msg


    def __str__(self):
        return self.msg
