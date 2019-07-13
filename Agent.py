#!/usr/bin/env python3.7

import requests
from bs4 import BeautifulSoup
import pickle
import os
import time
import getpass
import platform
import subprocess
import re
import json


class Agent:
    """
        The Agent class is responsible for logging in, creating the cookie session,
        and for sending/receiving hal api calls.
    """

    # Class Variables
    hosts = ['i.bluehost.com', 'i.justhost.com', 'i.hostmonster.com']


    def __init__(self, username=None):
        """
            Initiates the class and if no username is provided will check if it's WSL or Cygwin
            to grab the username from the system.
        """

        if username:
            self.username = username
        else:
            if platform.system() == 'Linux':
                self.username = subprocess.check_output('/mnt/c/Windows/System32/cmd.exe /C "echo %USERNAME%"', shell=True).strip().decode('utf-8')
            elif re.match(r'CYGWIN', platform.system()):
                self.username = getpass.getuser()
            else:
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

        login_link = "https://" + Agent.hosts[0] + "/cgi/admin/provider"
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

        api_call = "https://" + Agent.hosts[0] + "/cgi/admin/hal/api/" + action
        r = requests.post(api_call, data=args, cookies=cookies)
        return r.json()


    def db_request(self, sqlquery):
        """
            Send a request to the DB which returns a file of the JSON output.
            Read file and return the JSON output.
        """

        cookies = self._load_cookie()
        params = (
            ("sql", sqlquery),
        )
        headers = {
            'authority': 'i.bluehost.com',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.100 Safari/537.36',
            'dnt': '1',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3',
            'accept-encoding': 'gzip, deflate, br',
            'accept-language': 'en-US,en;q=0.9',
        }

        for host in Agent.hosts:
            api_call = "https://" + host + "/cgi-bin/admin/db/jsonfile"
            r = requests.get(api_call, headers=headers, params=params, cookies=cookies)
            if r.headers.get('content-disposition'):
                content = json.loads(r.content.decode('utf-8'))
                if content.get('rows'):
                    return (content['headers'], content['rows'])

        return None


    def cpm_request(self, cust_id, action):
        """
            Send a request to the CPM which returns a JSON response.
        """

        cookies = self._load_cookie()
        params = (
            ("json", action),
            ("cust_id", cust_id)
        )
        headers = {
            'authority': 'i.bluehost.com',
            'upgrade-insecure-requests': '1',
            'dnt': '1',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3',
            'accept-encoding': 'gzip, deflate, br',
            'accept-language': 'en-US,en;q=0.9',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.100 Safari/537.36'
        }

        for host in ['i.hostmonster.com']:
            api_call = "https://" + host + "/cgi/admin/user/cpanel/"
            r = requests.get(api_call, headers=headers, params=params, cookies=cookies)
            if r.headers.get('Content-Type') == 'application/json': 
                content = json.loads(r.content.decode('utf-8'))
                print(content)
                if not content.get('error') and content:
                    return content
        

    def raise_error(self, error):
        pass


if __name__ == "__main__":
    user = Agent()
    #response = user.hal_request(action="whm_exec",server_id="27352",command="df -h")
    #print(user.cpm_request('597965', "get_domains"))
    print(user.db_request("select * from domain where domain = 'infinitedelusionpaintball.com'"))
