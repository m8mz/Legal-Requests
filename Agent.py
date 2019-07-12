#!/usr/bin/env python3.7

import requests
from bs4 import BeautifulSoup
import pickle
import os
import time
import getpass
import platform


class Agent:
    """
        The Agent class is responsible for logging in, creating the cookie session,
        and for sending/receiving hal api calls.
    """

    # Class Variables
    bluehost, hostmonster, justhost = ['i.bluehost.com', 'i.hostmonster.com', 'i.justhost.com']


    def __init__(self, username=None):
        if username:
            self.username = username
        else:
            if platform.system() == 'Linux':
                pass
                
        self.cookie = "/tmp/agent_cookie.b"
        if not self.logged_in():
            password = getpass.getpass(prompt="Password: ")
            self.login(password)


    def login(self, password):
        """
            Logs into the server and creates the cookie. Grabs some initial
            variables from the init_page and adds them to args for the POST
            login request.
        """

        login_link = "https://" + Agent.bluehost + "/cgi/admin/provider"
        init_page = requests.get(login_link)
        args = {
            "admin_user": self.username,
            "admin_pass": password
        }

        parsed = BeautifulSoup(init_page.content, 'lxml')
        hidden_values = parsed.find_all("input", type="hidden")
        if len(hidden_values) == 4:
            for v in hidden_values:
                key = v.get('name')
                val = v.get('value')
                args[key] = val
        
        res = requests.post(login_link, data=args)
        if res.status_code == 200 and 'Set-Cookie' in res.headers:
            self._set_cookie(res.cookies)
            return True
        else:
            return False
            

    def _set_cookie(self, cookies):
        """
            Saves the created cookie to a binary cookie file for later usage.
        """
        
        with open(self.cookie, 'wb') as file:
            pickle.dump(cookies, file)


    def _load_cookie(self):
        """
            Reads and return cookies from the binary cookie file.
        """

        return pickle.load(open(self.cookie, 'rb'))


    def logged_in(self):
        """
            Check for a valid cookie session.
        """

        if not os.path.isfile(self.cookie):
            return False

        mtime_cookie = int(os.path.getmtime(self.cookie))
        current_time = int(time.time())
        expired_time = 60 * 60 * 9      # 9 hours
        if current_time - mtime_cookie >= expired_time:
            return False
        else:
            return True


    def hal_request(self, **kwargs):
        """
            Send an API call to HAL. The required field is action which tells
            this function what API call to use.
        """

        cookies = self._load_cookie()
        args = {
            "_format": "json-api-text"
        }
        for key, value in kwargs.items():
            if key == "action":
                action = value
            else:
                args[key] = value

        api_call = "https://" + Agent.bluehost + "/cgi/admin/hal/api/" + action
        r = requests.post(api_call, data=args, cookies=cookies)
        return r.json()
        

    def raise_error(self, error):
        pass


if __name__ == "__main__":
    user = Agent("mhancock-gaillard")
    response = user.hal_request(action="whm_exec",server_id="27352",command="df -h")
    print(response)
