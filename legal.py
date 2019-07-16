#!/usr/bin/env python3.7

from Agent import Agent
import argparse
import sys

agent = Agent()

parser = argparse.ArgumentParser()
parser.add_argument("domain", help="main domain for the cpanel account")
parser.add_argument("-l", "--logs", help="just grab logs for the cpanel account",
                    action="store_true")
args = parser.parse_args()


res = agent.db_request("SELECT cpanel.username, cpanel.hal_server_id, cpanel.hal_account_id FROM domain INNER JOIN cpanel ON domain.account_id = cpanel.custid WHERE domain = '{}'".format(args.domain))
if len(res[1]) == 1 and res[1][0].get('hal_account_id') and not res[1][0].get('hal_server_id'):
    if res[1][0].get('hal_server_id'): # Indication of a VPS/DEDI server
        print("This is a VPS/Dedicated server. Exiting...")
        sys.exit()

    hal_account_id = res[1][0].get('hal_account_id')
    account_info = agent.hal_request(action="account_info", id=hal_account_id)
    server_id = account_info.get('server_id')
    username = account_info.get('username') or res[1][0].get('username')
    if server_id and username:
        cust_disk_size = agent.hal_request(action="whm_exec", server_id=server_id, command="du -sh /home/{}/".format(username))
        print(cust_disk_size)
        print(agent.hal_request(action="whm_exec", server_id=server_id, command="df -h | awk '$6 ~ /home/{print $6\":\"$5\":\"$4}'"))
    else:
        print("No server id/username was found from the account information in HAL. Exiting...")
        sys.exit()    


else:
    if len(res[1]) > 1:
        print("Receiving multiple results when I shouldn't be, please check results below.")
        print(res[1])
    else:
        print("Didn't find the HAL account id which is how I find the HAL server id.")
