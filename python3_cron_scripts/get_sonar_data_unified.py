#!/usr/bin/python3

# Copyright 2018 Adobe. All rights reserved.
# This file is licensed to you under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License. You may obtain a copy
# of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under
# the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR REPRESENTATIONS
# OF ANY KIND, either express or implied. See the License for the specific language
# governing permissions and limitations under the License.

"""
This script searches Sonar DNS data provided through Rapid7 Open Data.
This script searches the data for the root domains tracked by Marinus.
"""

import argparse
import json
import os.path
import subprocess
import sys
import time
from datetime import datetime

import requests

from libs3 import DNSManager, MongoConnector, Rapid7, JobsManager
from libs3.ZoneManager import ZoneManager


mongo_connector = MongoConnector.MongoConnector()
global_dns_manager = DNSManager.DNSManager(mongo_connector)


global_data_dir = "./files/"

def is_running(process):
    """
    Is the provided process name is currently running?
    """
    proc_list = subprocess.Popen(["pgrep", "-f", process], stdout=subprocess.PIPE)
    for proc in proc_list.stdout:
        if proc.decode('utf-8').rstrip() != str(os.getpid()) and proc.decode('utf-8').rstrip() != str(os.getppid()):
            return True
    return False


def download_file(s, url, data_dir):
    """
    Download the file from the provided URL and put it in data_dir
    """
    local_filename = data_dir + url.split('/')[-1]
    # NOTE the stream=True parameter
    req = s.get(url, stream=True)
    with open(local_filename, 'wb') as out_f:
        for chunk in req.iter_content(chunk_size=128*1024):
            if chunk: # filter out keep-alive new chunks
                out_f.write(chunk)
    return local_filename


def find_zone(domain, zones):
    """
    Determine if the domain is in a tracked zone.
    """
    if domain is None:
        return ""

    for zone in zones:
        if domain.endswith("." + zone) or domain == zone:
            return zone
    return ""


def update_dns(dns_file, zones, dns_mgr):
    """
    Insert any matching Sonar DNS records in the Marinus database.
    """
    with open(dns_file, "r") as dns_f:
        for line in dns_f:
            try:
                data = json.loads(line)
            except ValueError:
                continue
            except:
                raise

            dtype = data['type']
            try:
                value = data['value']
                domain = data['name']
                zone = find_zone(domain, zones)
            except KeyError:
                print ("Error with line: " + line)
                value = ""
                zone = ""
                domain = ""

            timestamp = data['timestamp']
            if zone != "" and value != "":
                print ("Domain matches! " + domain + " Zone: " + zone)
                insert_json = {}
                insert_json['fqdn'] = domain
                insert_json['zone'] = zone
                insert_json['type'] = dtype
                insert_json['status'] = 'unknown'
                insert_json['value'] = value
                insert_json['sonar_timestamp'] = int(timestamp)
                insert_json['created'] = datetime.now()
                dns_mgr.insert_record(insert_json, "sonar_dns")


def update_rdns(rdns_file, zones, mongo_connector):
    """
    Insert any matching Sonar RDNS records in the Marinus database.
    """
    rdns_collection = mongo_connector.get_sonar_reverse_dns_connection()

    with open(rdns_file, "r") as read_f:
        for line in read_f:
            try:
                data = json.loads(line)
            except ValueError:
                continue
            except:
                raise

            try:
                domain = data['value']
                ip_addr = data['name']
                zone = find_zone(domain, zones)
            except KeyError:
                domain = ""
                ip_addr = ""
                zone = ""
            timestamp = data['timestamp']
            if zone != "" and domain != "":
                print ("Domain matches! " + domain + " Zone: " + zone)
                result = rdns_collection.find({'ip': ip_addr}).count()
                if result == 0:
                    insert_json = {}
                    insert_json['ip'] = ip_addr
                    insert_json['zone'] = zone
                    insert_json['fqdn'] = domain
                    insert_json['status'] = 'unknown' 
                    insert_json['sonar_timestamp'] = int(timestamp)
                    insert_json['created'] = datetime.now()
                    insert_json['updated'] = datetime.now()
                    rdns_collection.insert(insert_json)
                else:
                    rdns_collection.update({"ip": ip_addr},
                                           {'$set': {"fqdn": domain},
                                            '$currentDate': {"updated": True}})


def download_remote_files(s, file_reference, data_dir, jobs_manager):
    """
    Download the provided file URL
    """
    subprocess.run("rm " + data_dir + "*", shell=True)

    dns_file = download_file(s, file_reference, data_dir)

    now = datetime.now()
    print ("Downloaded file: " + str(now))

    try:
        subprocess.run(["gunzip", dns_file], check=True)
    except:
        print("Could not unzip file: " + dns_file)
        jobs_manager.record_job_error()
        exit(1)

    unzipped_dns = dns_file.replace(".gz", "")

    return unzipped_dns


def main():
    """
    Begin Main...
    """

    if is_running(os.path.basename(__file__)):
        print ("Already running...")
        exit(0)

    now = datetime.now()
    print ("Starting: " + str(now))

    r7 = Rapid7.Rapid7()

    zones = ZoneManager.get_distinct_zones(mongo_connector)

    parser = argparse.ArgumentParser(description='Parse Sonar files based on domain zones.')
    parser.add_argument('--sonar_file_type', required=True, help='Specify "dns-any", "dns-a", or "rdns"')
    args = parser.parse_args()

    # A session is necessary for the multi-step log-in process
    s = requests.Session()

    if args.sonar_file_type == "rdns":
        now = datetime.now()
        print ("Updating RDNS: " + str(now))
        jobs_manager = JobsManager.JobsManager(mongo_connector, 'get_sonar_data_rdns')
        jobs_manager.record_job_start()

        try:
            html_parser = r7.find_file_locations(s, "rdns", jobs_manager)
            if html_parser.rdns_url == "":
                now = datetime.now()
                print ("Unknown Error: " + str(now))
                jobs_manager.record_job_error()
                exit(0)

            unzipped_rdns = download_remote_files(s, html_parser.rdns_url, global_data_dir, jobs_manager)
            update_rdns(unzipped_rdns, zones, mongo_connector)
        except Exception as ex:
            now = datetime.now()
            print ("Unknown error occured at: " + str(now))
            print ("Unexpected error: " + str(ex))
            jobs_manager.record_job_error()
            exit(0)

        jobs_manager.record_job_complete()
    elif args.sonar_file_type == "dns-any":
        now = datetime.now()
        print ("Updating DNS: " + str(now))

        jobs_manager = JobsManager.JobsManager(mongo_connector, 'get_sonar_data_dns-any')
        jobs_manager.record_job_start()

        try:
            html_parser = r7.find_file_locations(s, "fdns", jobs_manager)
            if html_parser.any_url != "":
                unzipped_dns = download_remote_files(s, html_parser.any_url, global_data_dir, jobs_manager)
                update_dns(unzipped_dns, zones, global_dns_manager)
        except Exception as ex:
            now = datetime.now()
            print ("Unknown error occured at: " + str(now))
            print ("Unexpected error: " + str(ex))
            jobs_manager.record_job_error()
            exit(0)

        jobs_manager.record_job_complete()
    elif args.sonar_file_type == "dns-a":
        now = datetime.now()
        print ("Updating DNS: " + str(now))

        jobs_manager = JobsManager.JobsManager(mongo_connector, 'get_sonar_data_dns-a')
        jobs_manager.record_job_start()

        try:
            html_parser = r7.find_file_locations(s, "fdns", jobs_manager)
            if html_parser.a_url != "":
                unzipped_dns = download_remote_files(s, html_parser.a_url, global_data_dir, jobs_manager)
                update_dns(unzipped_dns, zones, global_dns_manager)
            if html_parser.aaaa_url != "":
                unzipped_dns = download_remote_files(s, html_parser.aaaa_url, global_data_dir, jobs_manager)
                update_dns(unzipped_dns, zones, global_dns_manager)
        except Exception as ex:
            now = datetime.now()
            print ("Unknown error occured at: " + str(now))
            print ("Unexpected error: " + str(ex))
            jobs_manager.record_job_error()
            exit(0)

        jobs_manager.record_job_complete()
    else:
        print ("Unrecognized sonar_file_type option. Exiting...")

    now = datetime.now()
    print ("Complete: " + str(now))


if __name__ == "__main__":
    main()
