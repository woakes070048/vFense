from bs4 import BeautifulSoup
import requests
import os
import re
import logging
import logging.config
from vFense import VFENSE_LOGGING_CONFIG
from datetime import datetime


from vFense.utils.common import decoder
from vFense.plugins.patching.utils import build_app_id
from vFense.plugins.vuln.redhat import Redhat, RedhatVulnApp
from vFense.plugins.vuln.redhat._constants import (
    RedhatDataDir, REDHAT_ARCHIVE
)
from vFense.plugins.vuln.redhat._db import insert_bulletin_data

logging.config.fileConfig(VFENSE_LOGGING_CONFIG)
logger = logging.getLogger('cve')

URL = REDHAT_ARCHIVE

def get_threads():

    """
    Parse the Redhat Officlial Annouces (URL: "https://www.redhat.com/archives/rhsa-announce/") and
    return the list of threads

    BASIC USAGE:
        >>> from vFense.plugins.vuln.redhat.get_all_redhat_updates import *
        >>> threads = get_threads()

    RETURNS:
        >>> threads[0]
        'https://www.redhat.com/archives/rhsa-announce/2014-April/thread.html'
        >>>

    """

    threads=[]
    req = requests.get(URL)
    soup= BeautifulSoup(req.text)
    for link in soup.find_all('a'):
        href=link.get('href')
        if "thread" in href:
            threads.append(os.path.join(URL, href))
    rh_threads = list(set(threads))
    return(rh_threads)

def get_msg_links_by_thread(thread):
    """
    Parse the Redhat update thread link and return the list of data link or message link.
    Args:
        thread (url) : This should be valid Redhat thread link.
        e.g:
        >>> thread
        'https://www.redhat.com/archives/rhsa-announce/2014-April/thread.html'

    BASIC USAGE:
    >>> from vFense.plugins.vuln.redhat.get_all_redhat_updates import *
    >>> dlinks=get_dlinks(thread)

    RETURNS:
        >>> dlinks[0]
        'https://www.redhat.com/archives/rhsa-announce/2014-April/msg00016.html'
        >>>
    """

    dlinks = []
    req=requests.get(thread)
    if req.ok:
        date = thread.split('/')[-2]
        tsoup=BeautifulSoup(req.text)
        for mlink in tsoup.find_all('a'):
             if "msg" in mlink.get('href'):
                 hlink = (os.path.join(URL, date, mlink.get('href')))
                 dlinks.append(hlink)

    rh_data_links = list(set(dlinks))
    return(rh_data_links)

def get_html_content(hlink, force=False):
    """
    Parse the content of Individual RedHat Updates or Message link and return the html contents
    Args:
        hlink (url) : Redhat Update or Message link
        e.g:
        >>> hlink
        'https://www.redhat.com/archives/rhsa-announce/2014-April/msg00016.html'

    Basic Usage :
        >>> from vFense.plugins.vuln.redhat.get_all_redhat_updates import *
        >>> content = parse_hdata(hlink)

    Returns:
        html webpage content

    """
    content = None
    msg_location = (
        os.path.join(
            RedhatDataDir.HTML_DIR, '/'.join(hlink.split('/')[-2:])
        )
    )

    if os.path.exists(msg_location) and not force:
        if os.stat(msg_location).st_size == 0:
            request = requests.get(hlink)
            if request.ok:
                content = request.content
                msg_file = open(msg_location, 'wb')
                msg_file.write(content)
                msg_file.close()
    else:
        request = requests.get(hlink)
        if request.ok:
            content = request.content
            msg_file = open(msg_location, 'wb')
            msg_file.write(content)
            msg_file.close()

    return(content)

def make_html_folder(dir_name):
    """
    Verify or Create (if not exist) folder to store the redhat updates (html files) and
    return the PATH name.

    Args:
        dir_name = directory or folder name ('folder-name')

    Basic Usage:

        >>> from vFense.plugins.vuln.redhat._constants import *
        >>> from vFense.plugins.vuln.redhat.get_all_redhat_updates import *
        >>> FPATH = make_html_folder(dname='redhat')

    Returns:

        >>> FPATH
        '/usr/local/lib/python2.7/dist-packages/vFense/plugins/vuln/redhat/data/html/redhat'
        >>>

    """

    fpath = os.path.join(RedhatDataDir.HTML_DIR, dir_name)
    if not os.path.exists(fpath):
        os.makedirs(fpath)
    return(fpath)

def get_apps_info(content):
    """
    Parse the list of rpm packages from the data-file and return as list.
    Args:
        content (str): the html content this function will parse.

    Basic Usage:
        >>> import os
        >>> os.getcwd()
        '/opt/TopPatch/tp/src/plugins/vuln/redhat'
        >>> from vFense.plugins.vuln.redhat.parser import *
        >>> dfile ='data/html/redhat/2010-March/msg00043.html'
        >>> get_rpm_pkgs(dfile=dfile)


    RETURNS:

        List of rpm packages parsed from data file corresponding to redhat updates/
        ['seamonkey-nss-devel-1.0.9-0.52.el3.s390.rpm', 'seamonkey-nss-1.0.9-0.52.el3.s390x.rpm', 'seamonkey-nspr-1.0.9-0.52.el3.s390x.rpm',...]


    """
    rpm_pkgs = []
    data = []
    pkgs = content.split()
    for pkg in pkgs:
        if '.rpm' in pkg:
            if not 'ftp://' in pkg:
                rpm_pkgs.append(pkg)

    rpm_pkgs = list(set(rpm_pkgs))
    for pkg in rpm_pkgs:
        app = RedhatVulnApp()
        if re.search(r'(^[A-Za-z0-9-_]+)?-', pkg):
            app.name = re.search(r'(^[A-Za-z0-9-_]+)?-', pkg).group(1)
            if app.name:
                pkg = re.sub(r'(^[A-Za-z0-9-]+)?-', '', pkg)
                app.version = '.'.join(pkg.split('.')[:-2])
                app.arch = pkg.split('.')[-2]
                app.app_id = build_app_id(app.name, app.version)
                data.append(app.to_dict())

    return data

def get_rh_cve_ids(content):
    """
    Parse cve_ids from the data file and return the list of cve_ids.

    Args:
        content (str): the html content this function will parse.

    Basic Usage:

        >>> import os
        >>> os.getcwd()
        '/opt/TopPatch/tp/src/plugins/vuln/redhat'
        >>> from vFense.plugins.vuln.redhat.parser import *
        >>> cve_ids=get_rh_cve_ids(dfile=dfile)


    RETURNS:
        List of CVE-IDs for specific redhat vulnerability update.
        ['CVE-2010-0174', 'CVE-2010-0175', 'CVE-2010-0176', 'CVE-2010-0177']

    """
    cve_ids = []
    cve_search = re.search(r"CVE\sNames:\s+(\w.*)", content, re.DOTALL)
    if cve_search:
        cve_data = cve_search.group().split(':')[1].strip()
        for cve in cve_data.split():
            if 'CVE-' in cve:
                cve_ids.append(cve)

    cve_id_list = list(set(cve_ids))

    return cve_id_list

def get_rh_data(content):
    """
    Parse data file to get the vulnerability update Summary, Decsriptions etc. and return
    dictionary data with all the redhay update info.

    Args:
        dfile : data file to parse the cve-ids for specific redhat vulnerabilty updates.

    Basic Usage:
        >>> import os
        >>> os.getcwd()
        '/opt/TopPatch/tp/src/plugins/vuln/redhat'
        >>> from vFense.plugins.vuln.redhat.parser import *
        >>> rh_data=get_rh_data(dfile=dfile)

    RETURNS:
        A dictionary data contents redhat update info.

        >>> rh_data['bulletin_id']
        'RHSA-2010:0333-01'
        >>> rh_data.keys()
        ['product', 'bulletin_details', 'bullentin_summary', 'bulletin_id', 'solutions', 'references', 'support_url', 'cve_ids', 'apps', 'date_posted']
        >>>

    """

    #smry = re.search('1\.\s+Summary:\n\n(\w.*)\n\n.*2.', data, re.DOTALL)
    #if smry:
    #    summary = decoder(smry.group(1))
    redhat = Redhat()
    description_search  = (
        re.search('Description:\n\n(\w.*)\n\n.*\s+Solution', content, re.DOTALL)
    )
    if description_search:
        redhat.details = decoder(description_search.group(1))

    #sol = (re.search('Solution:\n\n(\w.*)\n\n.*\.\s+Bugs fixed', data, re.DOTALL))
    #if sol:
    #    solutions=decoder(sol.group(1))
    #bug_fixed=re.search('5\.\s+Bugs fixed:\n\n(\w.*)\n\n.*6\.\s+Package List', data, re.DOTALL).group(1)

    redhat.apps = get_apps_info(content)

    #ref = (re.search('References:\n\n(\w.*)\n\n.*\.\s+Contact', data, re.DOTALL))
    #if ref:
    #    references=ref.group(1)

    vulnerability_id_search = re.search(r'Advisory\sID:.*', content)
    if vulnerability_id_search:
        redhat.vulnerability_id = (
            vulnerability_id_search.group().split(':', 1)[1].strip()
        )

    #product = None
    #prod=(re.search(r"Product:\s.*", data))
    #if prod:
    #   product=prod.group().split(':',1)[1].strip()

    advisory_url_search = re.search(r"Advisory\sURL:\s.*", content)
    if advisory_url_search:
        redhat.support_url = (
            advisory_url_search.group().split(':',1)[1].strip()
        )

    date_posted_search = re.search(r"Issue\sdate:\s.*", content)
    if date_posted_search:
        issue_date = date_posted_search.group().split(':',1)[1].strip()
        redhat.date_posted = (
            int(datetime.strptime(issue_date, "%Y-%m-%d").strftime('%s'))
        )

    redhat.cve_ids = get_rh_cve_ids(content)

    return(redhat.to_dict_db())

def insert_data_to_db(thread):
    """
    Insert the redhat vulnerability updates parsed from data files to the db. It first collects
    data link parsed from threads and then parse each data link and update the list of updates to
    db for the thread.

    ARGS:
        thread : redhat update thread link for specific month

    Basic Usage:
        >>> from vFense.plugins.vuln.redhat.parser import *
        >>> threads = get_threads()
        >>> thread =threads[0]
        >>> insert = insert_data_to_db(thread=thread)

    """
    cve_updates = []
    msg_links = get_msg_links_by_thread(thread)
    if msg_links:
        date = thread.split('/')[-2]
        make_html_folder(date)

        for link in msg_links:
            content = get_html_content(link)
            if content:
                cve_data = get_rh_data(content)
                if cve_data:
                    cve_updates.append(cve_data)

        insert=insert_bulletin_data(bulletin_data=cve_updates)
        return(insert)


def begin_redhat_archive_processing():
    """
    This will call the function to insert the data into db for all the threads
    and will insert the data one by one.

    Basic Usage:
        >>> from vFense.plugins.vuln.redhat.parser import *
        >>> update_all_redhat_data()

    """
    threads=get_threads()
    if threads:
        for thread in threads:
            insert_data_to_db(thread)
