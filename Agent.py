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
import sys
import distutils.util


class Agent_Error(Exception):
    """
        Custom error handling
    """


    def __init__(self, msg):
        self.msg = msg


    def __str__(self):
        return self.msg


class Agent:
    """
        The Agent class is responsible for logging in, creating the cookie session,
        and for sending/receiving hal api calls. Also, can make calls to the CPM and DB.
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
                self.username = input("Username: ")
                
        self.cookies = ["/tmp/bluehost_cookie.data", "/tmp/justhost_cookie.data", "/tmp/hostmonster_cookie.data"]
        if not self.logged_in():
            password = getpass.getpass(prompt="Password: ")
            self.login(password)


    def login(self, password):
        """
            Logs into the server and creates the cookie. Grabs some initial
            variables from the init_page and adds them to args for the POST
            login request.
        """

        status = []
        for num in range(3):
            login_link = "https://" + Agent.hosts[num] + "/cgi/admin/provider"
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
                self._set_cookie(res.cookies, num)
                status.append(True)
            else:
                status.append(False)

        if all(status):
            return True
        else:
            self.raise_error("Failed to login to {}, {}, {}".format(Agent.hosts))

            

    def _set_cookie(self, cookies, index):
        """
            Saves the created cookie to a binary cookie file for later usage.
        """
        
        with open(self.cookies[index], 'wb') as file:
            pickle.dump(cookies, file)


    def _load_cookie(self, index):
        """
            Reads and return cookies from the binary cookie file.
        """

        return pickle.load(open(self.cookies[index], 'rb'))


    def logged_in(self):
        """
            Check for a valid cookie session.
        """

        if not all([os.path.isfile(cookie) for cookie in self.cookies]):
            return False

        current_time = int(time.time())
        expired_time = 60 * 60 * 9      # 9 hours
        for num in range(3):
            mtime_cookie = int(os.path.getmtime(self.cookies[num]))
            if current_time - mtime_cookie >= expired_time:
                return False
            else:
                return True


    def hal_request(self, **kwargs):
        """
            Send an API call to HAL. The required field is action which tells
            this function what API call to use.
        """

        cookies = self._load_cookie(0)
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
        json_output = r.json()
        return json_output
        
        
    def whm_exec(self, server_id, command, output=False):
        """
            Send a command through whm_exec HAL method.
        """
        if not output:
            command = f"nohup bash -c '{command}' &"
            
        response = self.hal_request(action="whm_exec", server_id=server_id, command=command)
        if response.get('success') and response['output']['return'] is not None:
            return response['output']['return'].strip() if output else True
        else:
            return False


    def get_pid_for_command(self, server_id, command):
        """
            Send a command through whm_exec HAL method and return the PID for
            tracking/progress purposes. Hal API has a timeout which for long
            running commands will be an issue. This is the work around.
        """

        query = f"nohup bash -c '{command}' & echo $!"
        pid = self.hal_request(action="whm_exec", server_id=server_id, command=query)
        return pid


    def check_process(self, server_id, pid): # for hal_request
        """
            Check on a pid that was initiated from the hal_request method.
            Will return True if still exists and False if it doesn't.
        """

        query = f"if ps p {pid} >/dev/null; then echo False; else echo True; fi"
        response = self.hal_request(action="whm_exec", server_id=server_id, command=query)
        return bool(distutils.util.strtobool(response))


    def db_request(self, sqlquery):
        """
            Send a request to the DB which returns a file of the JSON output.
            Read file and return the JSON output.
        """

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

        for num in range(3):
            cookies = self._load_cookie(num)
            api_call = "https://" + Agent.hosts[num] + "/cgi-bin/admin/db/jsonfile"
            r = requests.get(api_call, headers=headers, params=params, cookies=cookies)
            if r.headers.get('content-disposition'):
                content = json.loads(r.content.decode('utf-8'))
                if len(content) == 3:
                    return (content['headers'], content['rows'])

        return None


    def cpm_request(self, cust_id, action):
        """
            Send a request to the CPM which returns a JSON response.
        """

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

        for num in range(3):
            cookies = self._load_cookie(num)
            api_call = "https://" + Agent.hosts[num] + "/cgi/admin/user/cpanel/"
            r = requests.get(api_call, headers=headers, params=params, cookies=cookies)
            if r.headers.get('Content-Type') == 'application/json': 
                content = json.loads(r.content.decode('utf-8'))
                if not content.get('error') and content:
                    return content
        

    def raise_error(self, error):
        try:
            raise(Agent_Error(error))
        except Agent_Error as err:
            print('Error: {}'.format(err))
            sys.exit()


if __name__ == "__main__":
    user = Agent()
    #pid = user.get_pid_for_command("27352", "sleep 5")
    #print(pid)
    #print(user.check_process(27352, pid))
    #print(user.hal_request(action="whm_exec",server_id="27352",command="df -h"))
    #time.sleep(8)
    #print(user.check_process(27352, pid))
    #print(user.cpm_request('1383314', "get_domains"))
    #print(user.db_request("select * from domain where domain = 'infinitedelusionpaintball.com'"))
    #print(user.db_request("select * from domain where domain = 'bluehostproservices.com'"))
    #print(user.db_request("select * from domain where domain = 'janellektra.net'"))
