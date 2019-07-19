#!/usr/bin/env python3.7

from Agent import Agent
import argparse
import sys
import string
from jumpssh import SSHSession
from datetime import datetime
import re


def grabLogs(tarfile, username, domains):
    global server_id
    global agent
    command = 'if [[ -f "/usr/sec/bin/grablogs" ]]; then echo True; else echo False; fi'
    if agent.hal_request(action="whm_exec", server_id=server_id, command=command):
        domains_list = "--domains={}".format(" --domains=".join(domains))
        command = f"/usr/sec/bin/grablogs --tarfile={tarfile} --cususer={username} {domains_list}"
        print(command)
        # log_pid = agent.get_pid_for_command(server_id, command=command)
    else:
        print("The grablogs Perl script does not exist. Must fix this first.")
        sys.exit()


agent = Agent()

parser = argparse.ArgumentParser()
parser.add_argument("domain", help="main domain for the cpanel account")
parser.add_argument("-l", "--logs", help="just grab logs for the cpanel account",
                    action="store_true")
args = parser.parse_args()


res = agent.db_request("SELECT cpanel.username, cpanel.hal_server_id, cpanel.hal_account_id, cpanel.type, cpanel.custid FROM domain INNER JOIN cpanel ON domain.account_id = cpanel.custid WHERE domain = '{}'".format(args.domain))

if len(res[1]) == 1 and res[1][0].get('hal_account_id'):
    account_type = res[1][0].get('type')
    if account_type == "vps" or account_type == "dedicated":
        print("This is a VPS/Dedicated server. Exiting...")
        sys.exit()
    query = """
    SELECT customer_meta_name.name FROM domain
    INNER JOIN cpanel ON domain.account_id = cpanel.custid
    INNER JOIN customer_meta ON cpanel.custid = customer_meta.cust_id
    INNER JOIN customer_meta_name ON customer_meta.name_id = customer_meta_name.id
    WHERE domain = '{}'
    AND customer_meta_name.name = 'bluerock'""".format(args.domain)
    bluerock = agent.db_request(query)

    if res[1][0].get('hal_server_id'): 
        server_id = res[1][0].get('hal_server_id')
    else:
        hal_account_id = res[1][0].get('hal_account_id')
        account_info = agent.hal_request(action="account_info", id=hal_account_id)
        server_id = account_info.get('server_id')

    username = res[1][0].get('username')
    custid = res[1][0].get('custid')
    domains_query = agent.db_request(f"SELECT domain.domain FROM domain INNER JOIN cpanel ON cpanel.username = '{username}' WHERE domain.account_id = '{custid}'")[1]
    domains = [domain.get('domain') for domain in domains_query]
    today_date = datetime.now().strftime("%Y-%m-%d")
    custbox = agent.hal_request(action="server_info", id=server_id).get('hostname')
    custhome = agent.hal_request(action="whm_exec", server_id=server_id, command="getent passwd {} | cut -d: -f6".format(username))
    custnum = re.match(r'/home(\d+)/', custhome).group(1)

    if server_id and username and custbox and custhome:
        # SSH Sessions
        gateway_session = SSHSession('zugzug2.bluehost.com', port=5190, username=agent.username)
        legal_session = gateway_session.get_remote_session('10.0.82.205')

        cust_disk_size = int(re.match(r'^(\d+)', agent.hal_request(action="whm_exec", server_id=server_id, command="du -sh {}".format(custhome))).group(1))
        overall_size_est = cust_disk_size * 4
        disk_results = agent.hal_request(action="whm_exec", server_id=server_id, command="df -h | awk '$6 ~ /home/{print $6\":\"$5\":\"$4}'").split('\n')
        home_disks = []
        for disk in disk_results:
            path, usage, avail = disk.split(':')
            if 'T' in avail:
                avail = "".join(c for c in avail if c in string.digits)
                avail = int(avail + "000")
            else:
                avail = int(float(avail.replace('G','')))
            home_disks.append((path, usage, avail))
        home_disks.sort(key = lambda x: x[2], reverse = True)
        for disk in home_disks:
            path, usage, avail = disk
            if avail > overall_size_est:
                home_disk = path
                break
        try:
            home_disk
        except NameError:
            #TODO: Do the preservation in sections
            print("No home disk that can support ~{}G".format(overall_size_est))
            sys.exit()
        else:
            pass

        print("Initiating Legal Request...")
        print()
        print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("Hostname: {}".format(custbox))
        print("User: {}".format(username))
        print("Main Domain: {}".format(args.domain)) #TODO: grab main domain if addon domain used
        print("Requested Domain: {}".format(args.domain))
        print()

        # Legal Server Prep
        legal_dir = "/legal2/{}/{}".format(args.domain, today_date)
        box_dir = "{}/sd/{}".format(home_disk, username)

        legal_session.run_cmd(f"mkdir -p {legal_dir}")
        tarfile = "{}/{}.logs.tar".format(box_dir, username)
        if args.logs:
            print("Processing request for logs.. please wait.")
            grabLogs(tarfile, username, domains)
        else:
            print("Processing request for full preservation and logs.. please wait.")
            grabLogs(tarfile, username, domains)
            dir_command = f"mkdir -p {box_dir}/non-home-data"
            print(dir_command)
            #agent.hal_request(action="whm_exec", server_id=server_id, command=dir_command)
            #pkgacct_pid = agent.get_pid_for_command(action="whm_exec", server_id=server_id, command=command)
            box_command_list = [
                f"/scripts/pkgacct --skiphomedir --skiplogs {username} {box_dir}/non-home-data",
            ]
            legal_command_list = [
                f"rsync -x -rlpt --chown={agent.username}:wheel {custbox}:{custhome}/ {legal_dir}/{username}.home/ 2> ./rsync-err.log",
                f"rsync -x -rlpt --chown={agent.username}:wheel --exclude=homedir {custbox}:/backup{custnum}/cpbackup/seed/{username}/ {legal_dir}/{username}.seed/",
                f"rsync -x -rlpt --chown={agent.username}:wheel --link-dest={legal_dir}/{username}.home {custbox}:/backup{custnum}/cpbackup/seed/{username}/{homedir}/ {legal_dir}/{username}.seed/homedir/",
            ]




    else:
        print("No server id/username was found from the account information in HAL. Exiting...")
        sys.exit()    


else:
    if len(res[1]) > 1:
        print("Receiving multiple results when I shouldn't be, please check results below.")
        print(res[1])
    else:
        print("Didn't find the HAL account id which is how I find the HAL server id.")


