#!/usr/bin/env python3.7
"""
    Description:
    This script will capture the account data and migrate to the legal server.
    This will work for legacy/bluerock accounts and will perform a divided
    migration if needed. Also, takes care of everything from start to finish to
    the legal server. Including installing the grablogs script, updating perms,
    and cleaning up the data.
    
    Author: Marcus Hancock-Gaillard
"""

from Agent import Agent
import argparse
import sys
import string
from jumpssh import SSHSession, exception
from datetime import datetime
import re
import time


def convertToGigs(x):
    num = float("".join(c for c in x if c in string.digits))
    if 'T' in x:
        num = num * 1000
    elif 'M' in x:
        num = num * .001
    return num


def userConfirm(msg="Please do so manually.."):
    print(msg)
    try:
        input("Press Enter to continue...")
    except (KeyboardInterrupt, SystemExit):
        print("Exiting...")
        sys.exit()
        
        
def waitingForProcesses(command_check, out=True):
    global server_id
    counter = 0
    while True:
        processes = agent.whm_exec(server_id, command_check, output=True)
        if processes:
            pass
        else:
            break
        counter += 1
        print('.', end='', flush=True)
        if counter < 5:
            time.sleep(30)
        elif counter < 15:
            time.sleep(60)
        else:
            time.sleep(90)
    if out:
        print("Done.")


DIVIDE_MIGRATION = False

agent = Agent()

legal_addr = '10.0.82.205'
gateway_session = SSHSession('zugzug2.bluehost.com', port=5190, username=agent.username)
gateway_size = gateway_session.run_cmd("df -h | awk '$6 ~ /^\/$/{print $4}'").output
gateway_size = convertToGigs(gateway_size)
legal_session = gateway_session.get_remote_session(legal_addr)
legal2_size = legal_session.run_cmd("df -h | awk '$6 ~ /legal2/{print $4}'").output
legal2_size = convertToGigs(legal2_size)

parser = argparse.ArgumentParser()
parser.add_argument("domain", help="main domain for the cpanel account")
parser.add_argument("-l", "--logs", help="just grab logs for the cpanel account",
                    action="store_true")
args = parser.parse_args()

query = (
    "SELECT cpanel.username, cpanel.hal_server_id, cpanel.hal_account_id, cpanel.type, cpanel.custid FROM domain "
    "INNER JOIN cpanel ON domain.account_id = cpanel.custid "
    "WHERE domain = '{}'"
).format(args.domain)
res = agent.db_request(query)

if len(res[1]) == 1 and res[1][0].get('hal_account_id'):
    account_type = res[1][0].get('type')
    if account_type == "vps" or account_type == "dedicated":
        print("This is a VPS/Dedicated server. Exiting...")
        sys.exit()

    if res[1][0].get('hal_server_id'): 
        server_id = res[1][0].get('hal_server_id')
    else:
        hal_account_id = res[1][0].get('hal_account_id')
        account_info = agent.hal_request(action="account_info", id=hal_account_id)
        server_id = account_info.get('server_id')

    username = res[1][0].get('username')
    custid = res[1][0].get('custid')
    domains_query = agent.db_request(("SELECT domain.domain FROM domain "
                                      "INNER JOIN cpanel ON cpanel.username = '{}' "
                                      "WHERE domain.account_id = '{}'").format(username, custid))[1]
    domains = [domain.get('domain') for domain in domains_query]
    main_domain = agent.whm_exec(server_id, f"grep '{username}' /etc/trueuserdomains | cut -d: -f1",
                                 output=True)
    today_date = datetime.now().strftime("%Y-%m-%d")
    custbox = agent.hal_request(action="server_info", id=server_id).get('hostname')
    custhome = agent.whm_exec(server_id,
                                 "getent passwd {} | cut -d: -f6".format(username),
                                 output=True)
    custnum = re.match(r'/home(\d+)/', custhome).group(1)
    custbox_addr = agent.whm_exec(server_id, "hostname -i", output=True)
    html_var = "/var/www/html" # for bluerock
    legal_dir = "/legal2/{}/{}".format(main_domain, today_date)
    legal_session.run_cmd(f"mkdir -p {legal_dir}")
    query = (
    "SELECT customer_meta_name.name FROM domain "
    "INNER JOIN cpanel ON domain.account_id = cpanel.custid "
    "INNER JOIN customer_meta ON cpanel.custid = customer_meta.cust_id "
    "INNER JOIN customer_meta_name ON customer_meta.name_id = customer_meta_name.id "
    "WHERE domain = '{}' "
    "AND customer_meta_name.name = 'bluerock'"
    ).format(main_domain)
    bluerock = agent.db_request(query)

    if server_id and username and custbox and custhome:

        cust_disk_size = convertToGigs(agent.whm_exec(server_id, "du -sh {} | awk '{{print $1}}".format(custhome),
                                                                output=True))
        overall_size_est = cust_disk_size * 4
        disk_results = agent.whm_exec(server_id, "df -h | awk '$6 ~ /home/{print $6\":\"$5\":\"$4}'",
                                      output=True).split('\n')
        home_disks = []
        for disk in disk_results:
            path, usage, avail = disk.split(':')
            avail = convertToGigs(avail)
            home_disks.append((path, usage, avail))
        home_disks.sort(key=lambda x: x[2], reverse=True)
        for disk in home_disks:
            path, usage, avail = disk
            if avail > overall_size_est:
                home_disk = path
                break
        try:
            home_disk
        except NameError:
            if not args.logs:
                print("Issue: No home disk that can support ~{}G".format(overall_size_est))
                usable_disks = [disk[0] for disk in home_disks if disk[2] > cust_disk_size + 5]
                if usable_disks:
                    print("Going to migrate the data separately. Will take longer..")
                    print(usable_disks)
                    home_disk = usable_disks[0]
                    DIVIDE_MIGRATION = True
                else:
                    print("Exiting...")
                    sys.exit()
            else:
                home_disk = home_disks[0][0]
        else:
            pass
        
        if legal2_size < overall_size_est:
            print("Err: Not enough space available on the legal server '/legal2' need ~{}".format(overall_size_est))
            print("Exiting..")
            sys.exit()
            
        if bluerock and overall_size_est > gateway_size:
            print("Err: Not enough space available on the zugzug2 server '/' need ~{}".format(overall_size_est))
            print("Exiting..")
            sys.exit()

        print("Initiating Legal Request...")
        print()
        print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("Hostname: {}".format(custbox))
        print("User: {}".format(username))
        print("Main Domain: {}".format(main_domain))
        print("Requested Domain: {}".format(args.domain))
        print()

        # Customer Box Prep
        box_dir = "{}/sd/{}".format(home_disk, username)
        tarfile = "{}/{}.logs.tar".format(box_dir, username)
        waiting_queue = [
                f"/scripts/pkgacct --skiphomedir --skiplogs {username} {box_dir}/non-home-data 2>&1",
                f"rsync -azx {custhome}/ {box_dir}/{username}.home",
                f"rsync -x -rlptgo /backup{custnum}/cpbackup/seed/{username}/ {box_dir}/{username}.seed/",
                f"rsync -x -rlptgo /backup{custnum}/cpbackup/daily/{username}/ {box_dir}/{username}.daily/",
                f"rsync -x -rlptgo /backup{custnum}/cpbackup/weekly/{username}/ {box_dir}/{username}.weekly/",
                f"rsync -x -rlptgo /backup{custnum}/cpbackup/monthly/{username}/ {box_dir}/{username}.monthly/"
        ]
        waiting_queue_names = [
                "non-home-data & logs",
                f"{username}.home",
                f"{username}.seed",
                f"{username}.daily",
                f"{username}.weekly",
                f"{username}.monthly"
        ]
        cleanup_queue = [
                f"chown -R {agent.username} {box_dir}",
                "find " + box_dir + " -xdev -type d ! -perm -500 -exec chmod u+rx {} \;",
                "find " + box_dir + " -xdev -type f ! -perm -400 -exec chmod u+r {} \;"
        ]
        
        grablogs_exist = 'if [[ -f "/usr/sec/bin/grablogs" ]]; then echo True; else echo False; fi'
        if agent.whm_exec(server_id, grablogs_exist, output=True):
            pass
        else:
            print("Installing grablogs to server..")
            agent.whm_exec(server_id, "mkdir -p /usr/sec/bin/ /usr/sec/lib/")
            secbinlog_exist = 'if [[ -f "/usr/sec/lib/SecBinLog.pm" ]]; then echo True; else echo False; fi'
            if not agent.whm_exec(server_id, grablogs_exist, output=True):
                agent.whm_exec(server_id, "wget -O /usr/sec/lib/SecBinLog.pm https://raw.githubusercontent.com/marcushg36/Legal-Requests/master/SecBinLog.pm && chmod 644 /usr/sec/lib/SecBinLog.pm")
            if bluerock:
                agent.whm_exec(server_id, "wget -O /usr/sec/bin/grablogs https://raw.githubusercontent.com/marcushg36/Legal-Requests/master/grablogs_bluerock.pl && chmod 700 /usr/sec/bin/grablogs")
            else:
                agent.whm_exec(server_id, "wget -O /usr/sec/bin/grablogs https://raw.githubusercontent.com/marcushg36/Legal-Requests/master/grablogs.pl && chmod 700 /usr/sec/bin/grablogs")
            print("Done.")

        domains_list = "--domains={}".format(" --domains=".join(domains))
        command = f"/usr/sec/bin/grablogs --tarfile={tarfile} --cususer={username} {domains_list}"
        agent.whm_exec(server_id, command)
        
        """
            This next section may get a little confusing. Basically,
            
            PART 1 is checking if the account is bluerock then within checking
            if args.logs is True meaning if we are just grabbing the logs for
            the account or preservation too.
            
            PART 2 is checking if args.logs is NOT True then proceeding with
            a full preservation. Within this part it checks if this needs to be
            a divided migration.
        """
        # PART 1
        if bluerock:
            if args.logs:
                agent.whm_exec(server_id, f"rsync -x -a /home/apachelogs/{username}/ {box_dir}/logs/")
                agent.whm_exec(server_id, f"rsync -x -a /usr/local/apache/logs/domlogs/ftp.{main_domain}* {box_dir}/logs/")
            else:
                waiting_queue.append(f"rsync -x -a /home/apachelogs/{username}/ {box_dir}/logs/")
                waiting_queue.append(f"rsync -x -a /usr/local/apache/logs/domlogs/ftp.{main_domain}* {box_dir}/logs/")
        else:
            if args.logs:
                agent.whm_exec(server_id, f"rsync -x -a {custhome}/logs {box_dir}/")
            else:
                waiting_queue.append(f"rsync -x -a {custhome}/logs {box_dir}/")
        
        # PART 2
        if not args.logs:
            print("Processing request for full preservation and logs.. please wait.")
            setup_command = f"mkdir -p {box_dir}/non-home-data {box_dir}/{username}.seed {box_dir}/{username}.seed/homedir"
            agent.whm_exec(server_id, setup_command)
            
            if not DIVIDE_MIGRATION:
                for item in waiting_queue:
                    agent.whm_exec(server_id, item)
                    time.sleep(3)
                waitingForProcesses("ps faux | grep " + username + "| awk '/" + box_dir.replace('/','\/') + "/{print $2}'")
                print("Fixing permissions and ownership of data..")
                for item in cleanup_queue:
                    agent.whm_exec(server_id, item)
                waitingForProcesses("ps faux | grep " + username + "| awk '/" + box_dir.replace('/','\/') + "/{print $2}'")
                print("Starting the process of migrating the data to the legal server..")
                if not bluerock:    # LEGACY MIGRATION
                    print("Data currently being migrated..")
                    legal_session.run_cmd(f"rsync -e 'ssh -o StrictHostKeyChecking=no' -rlptgoH {custbox}:{box_dir}/* {legal_dir}/ 2> ./rsync-err.log")
                    
                else:               # BLUEROCK MIGRATION
                    custbox_var = agent.whm_exec(server_id, "df -h | awk '$6 ~ /var$/{print $6\":\"$5\":\"$4}'",
                                                 output=True)
                    custbox_var_size = custbox_var.split(':')[2]
                    custbox_var_size = convertToGigs(custbox_var_size)
                    
                    custbox_sd_size = convertToGigs(agent.whm_exec(server_id, f"du -sh {box_dir} | awk '{{print $1}}",
                                                                   output=True))
                    if custbox_var_size > custbox_sd_size:
                        print("Creating compressed file for transfer..")
                        agent.whm_exec(server_id, f"cd {box_dir} && tar -caf {html_var}/{username}.tgz *")
                        waitingForProcesses(f"ps faux | grep '{username}.tgz' | grep -v grep | awk '{{print $2}}'")
                        agent.whm_exec(server_id, f"""sed -i "s/RewriteRule !^index.cgi|/RewriteRule !^{username}.tgz|index.cgi|/" {html_var}/.htaccess""")
                        print("Data currently being migrated..")
                        try:
                            gateway_session.run_cmd(f"wget {custbox_addr}/{username}.tgz")
                        except exception.RunCmdError:
                            print(f"Issue updating {html_var}/.htaccess to allow the compressed file '{html_var}/{username}.tgz' in the RewriteRule.")
                            sys.exit()
                        gateway_session.run_cmd(f"scp {username}.tgz {legal_addr}:{legal_dir}/")
                        legal_session.run_cmd(f"cd {legal_dir} && tar -xf {username}.tgz")
                        print("Cleaning up bluerock migration..")
                        agent.whm_exec(server_id, f"""sed -i "s/RewriteRule !^{username}.tgz|index.cgi|/RewriteRule !^index.cgi|/" {html_var}/.htaccess""")
                        agent.whm_exec(server_id, f"rm -f {html_var}/{username}.tgz")
                        gateway_session.run_cmd(f"rm -f {username}.tgz")
                    else:
                        print("Issue: Not enough space on /var to hold the tar file")
                        print("Migrate this manually to the legal server.")
                        print("https://confluence.endurance.com/pages/viewpage.action?pageId=111327316")
                        print("Legal Dir: {}".format(legal_dir))
                        print()
                        userConfirm("Waiting for manual migration..")
            elif DIVIDE_MIGRATION and bluerock:
                custbox_var = agent.whm_exec(server_id, "df -h | awk '$6 ~ /var$/{print $6\":\"$5\":\"$4}'",
                                                 output=True)
                custbox_var_size = custbox_var.split(':')[2]
                custbox_var_size = convertToGigs(custbox_var_size)
                if custbox_var_size > overall_size_est:
                    print("Grabbing user data and logs..", end='', flush=True)
                    agent.whm_exec(server_id, f"rsync -x -a /home/apachelogs/{username}/ {box_dir}/logs/")
                    agent.whm_exec(server_id, f"rsync -x -a /usr/local/apache/logs/domlogs/ftp.{main_domain}* {box_dir}/logs/")
                    agent.whm_exec(server_id, f"/scripts/pkgacct --skiphomedir --skiplogs {username} {box_dir}/non-home-data 2>&1")
                    time.sleep(3)
                    waitingForProcesses("ps faux | grep " + username + "| awk '/" + box_dir.replace('/','\/') + "/{print $2}'")
                    for item in cleanup_queue:
                        agent.whm_exec(server_id, item)
                    time.sleep(1)
                    waitingForProcesses("ps faux | grep " + username + "| awk '/" + box_dir.replace('/','\/') + "/{print $2}'", out=False)
                    bluerock_waiting_queue = [
                            f"cd {box_dir} && tar -cf {html_var}/{username}.tar non-home-data/ logs/ {tarfile}",
                            f"cd {custhome}/.. && tar -rf {html_var}/{username}.tar --transform s/^{username}/{username}.home/ {username}/",
                            f"cd /backup{custnum}/cpbackup/seed/ && tar -rf {html_var}/{username}.tar --transform s/^{username}/{username}.seed/ {username}/",
                            f"cd /backup{custnum}/cpbackup/daily/ && tar -rf {html_var}/{username}.tar --transform s/^{username}/{username}.daily/ {username}/",
                            f"cd /backup{custnum}/cpbackup/weekly/ && tar -rf {html_var}/{username}.tar --transform s/^{username}/{username}.weekly/ {username}/",
                            f"cd /backup{custnum}/cpbackup/monthly/ && tar -rf {html_var}/{username}.tar --transform s/^{username}/{username}.monthly/ {username}/",
                    ]
                    print("Creating compressed file for transfer..")
                    for name, item in zip(waiting_queue_names, bluerock_waiting_queue):
                        print("Archiving {}..".format(name), end='', flush=True)
                        agent.whm_exec(server_id, item)
                        time.sleep(3)
                        waitingForProcesses(f"ps faux | grep '{username}.tar' | grep -v grep | awk '{{print $2}}'")
                    print("Compressing..", end='', flush=True)
                    agent.whm_exec(server_id, f"gzip /var/www/html/{username}.tar")
                    waitingForProcesses(f"ps faux | grep '{username}.tar' | grep -v grep | awk '{{print $2}}'")
                    print("Migrating data...")
                    agent.whm_exec(server_id, f"""sed -i "s/RewriteRule !^index.cgi|/RewriteRule !^{username}.tar.gz|index.cgi|/" {html_var}/.htaccess""")
                    print("Data currently being migrated..")
                    try:
                        gateway_session.run_cmd(f"wget {custbox_addr}/{username}.tar.gz",
                                                retry=3,
                                                retry_interval=3)
                    except exception.RunCmdError:
                        print(f"Issue updating {html_var}/.htaccess to allow the compressed file '{html_var}/{username}.tar.gz' in the RewriteRule.")
                        sys.exit()
                    gateway_session.run_cmd(f"scp {username}.tar.gz {legal_addr}:{legal_dir}/",
                                            retry=3,
                                            retry_interval=3)
                    legal_session.run_cmd(f"cd {legal_dir} && tar -xf {username}.tar.gz",
                                          retry=3,
                                          retry_interval=3)
                    print("Cleaning up bluerock migration..")
                    agent.whm_exec(server_id, f"""sed -i "s/RewriteRule !^{username}.tar.gz|index.cgi|/RewriteRule !^index.cgi|/" {html_var}/.htaccess""")
                    agent.whm_exec(server_id, f"rm -f {html_var}/{username}.tar.gz")
                    gateway_session.run_cmd(f"rm -f {username}.tar.gz",
                                            retry=3,
                                            retry_interval=3)
                else:
                    print("Issue: Not enough space on /var to hold the tar file")
                    print("Migrate this manually to the legal server.")
                    print("https://confluence.endurance.com/pages/viewpage.action?pageId=111327316")
                    print("Legal Dir: {}".format(legal_dir))
                    print()
                    userConfirm("Waiting for manual migration..")
                
            elif DIVIDE_MIGRATION and not bluerock:
                for name, item in zip(waiting_queue_names, waiting_queue):
                    print("{}..".format(name), end='', flush=True)
                    agent.whm_exec(server_id, item)
                    time.sleep(3)
                    waitingForProcesses("ps faux | grep " + username + "| awk '/" + box_dir.replace('/','\/') + "/{print $2}'")
                    print("Fixing permissions and ownership of data..")
                    for item in cleanup_queue:
                        agent.whm_exec(server_id, item)
                    time.sleep(1)
                    waitingForProcesses("ps faux | grep " + username + "| awk '/" + box_dir.replace('/','\/') + "/{print $2}'")
                    print("Migrating {}...".format(name))
                    legal_session.run_cmd(f"rsync -e 'ssh -o StrictHostKeyChecking=no' -rlptgoH {custbox}:{box_dir}/* {legal_dir}/ 2>> ./rsync-err.log",
                                          retry=3,
                                          retry_interval=3)
                    agent.whm_exec(server_id, f"rm -rf {box_dir}/*", output=True)
                print("Done.")
            
            print("Synchronizing seed..")
            legal_session.run_cmd(f"rsync -a {legal_dir}/{username}.seed/homedir/ {legal_dir}/{username}.home/",
                                  retry=3,
                                  retry_interval=3)
            legal_session.run_cmd(f"rsync -a {legal_dir}/{username}.home/ {legal_dir}/{username}.seed/homedir/",
                                  retry=3,
                                  retry_interval=3)
            legal_session.run_cmd(f"rsync -a {legal_dir}/{username}.daily/ {legal_dir}/{username}.seed/",
                                  retry=3,
                                  retry_interval=3)
            legal_session.run_cmd(f"rsync -a {legal_dir}/{username}.weekly/ {legal_dir}/{username}.seed/",
                                  retry=3,
                                  retry_interval=3)
            legal_session.run_cmd(f"rsync -a {legal_dir}/{username}.monthly/ {legal_dir}/{username}.seed/",
                                  retry=3,
                                  retry_interval=3)
        
        print("Finished migrating the data.")
        print("Updating group to 'wheel' recursively..")
        legal_session.run_cmd(f"chown -R mhancock-gaillard:wheel {legal_dir}/*")
        print("Calculating size..")
        legal_size = legal_session.run_cmd(f"du -sh {legal_dir}").output.split('\t')[0]
        print(f"Cleaning up data on customer's box '{box_dir}'..")
        agent.whm_exec(server_id, f"rm -rf {box_dir}/*")
        print("Done.")
        print()
        print("Location: {}".format(legal_dir))
        print("Size: {}".format(legal_size))
        print()

    else:
        print("No server id/username was found from the account information in HAL")
        print("or the user does not exist on the box. Exiting...")
        sys.exit()

else:
    if len(res[1]) > 1:
        print("Receiving multiple results when I shouldn't be, please check results below.")
        print(res[1])
    else:
        print("Didn't find the HAL account id which is how I find the HAL server id.")


