#!/usr/bin/env python

import pickle
import os
import logging
import time
import re
import inkyphat
from optparse import OptionParser, OptionValueError
from smtplib import SMTP
from getpass import getuser
from socket import gethostname, setdefaulttimeout
from PIL import Image, ImageFont, ImageDraw

try:
    from urllib2 import urlopen
except ImportError:
    from urllib.request import urlopen


def generate_email_alerter(to_addrs, from_addr=None, use_gmail=False,
                           username=None, password=None, hostname=None, port=25):
    if not from_addr:
        from_addr = getuser() + "@" + gethostname()

    if use_gmail:
        if username and password:
            server = SMTP('smtp.gmail.com', 587)
            server.starttls()
        else:
            raise OptionValueError('You must provide a username and password to use GMail')
    else:
        if hostname:
            server = SMTP(hostname, port)
        else:
            server = SMTP()
        # server.connect()
        server.starttls()

    if username and password:
        server.login(username, password)

    def email_alerter(message, subject='You have an alert'):
        server.sendmail(from_addr, to_addrs, 'To: %s\r\nFrom: %s\r\nSubject: %s\r\n\r\n%s' % (
            ", ".join(to_addrs), from_addr, subject, message))

    return email_alerter, server.quit


def get_site_status(url):
    try:
        urlfile = urlopen(url)
        status_code = urlfile.code
        if status_code in (200, 302):
            return 'up', urlfile
    except:
        pass
    return 'down', None


def get_headers(url):
    '''Gets all headers from URL request and returns'''
    try:
        return urlopen(url).info().as_string()
    except:
        return 'Headers unavailable'


def compare_site_status(prev_results, alerter):
    '''Report changed status based on previous results'''

    def is_status_changed(url):
        startTime = time.time()
        status, urlfile = get_site_status(url)
        endTime = time.time()
        elapsedTime = endTime - startTime
        msg = "%s took %s" % (url, elapsedTime)
        logging.info(msg)

        if status != "up":
            elapsedTime = -1

        friendly_status = '%s is %s. Response time: %s' % (
            url, status, elapsedTime)

        if url in prev_results and prev_results[url]['status'] != status:
            logging.warning(status)
            # Email status messages
            alerter(str(get_headers(url)), friendly_status)

        # Create dictionary for url if one doesn't exist (first time url was
        # checked)
        if url not in prev_results:
            prev_results[url] = {}
            if status == 'down':
                alerter(str(get_headers(url)), friendly_status)

        # Save results for later pickling and utility use
        prev_results[url]['status'] = status
        prev_results[url]['headers'] = None if urlfile is None else urlfile.info().headers
        prev_results[url]['rtime'] = elapsedTime

    return is_status_changed


def is_internet_reachable():
    '''Checks Google then Yahoo just in case one is down'''
    statusGoogle, urlfileGoogle = get_site_status('http://www.google.com')
    statusYahoo, urlfileYahoo = get_site_status('http://www.yahoo.com')
    if statusGoogle == 'down' and statusYahoo == 'down':
        return False
    return True


def load_old_results(file_path):
    '''Attempts to load most recent results'''
    pickledata = {}
    if os.path.isfile(file_path):
        picklefile = open(file_path, 'rb')
        pickledata = pickle.load(picklefile)
        picklefile.close()
    return pickledata


def store_results(file_path, data):
    '''Pickles results to compare on next run'''
    output = open(file_path, 'wb')
    pickle.dump(data, output)
    output.close()

def print_inkyphat_no_internet(inkyphat_rotation):
    inkyphat.set_image("resources/no-internet.png")
    font = ImageFont.truetype("resources/ChiKareGo.ttf", 16)
    inkyphat.set_rotation(inkyphat_rotation)
    inkyphat.text((50, 74), 'No internet access', inkyphat.BLACK, font=font)
    inkyphat.show()

def print_inkyphat(urls, pickledata_old, pickledata, inkyphat_rotation, data_changed = False):
    '''Compare results, if no updates do not update screen'''
    down_urls = []

    if pickledata_old == {}:
        data_changed = True

    for url in reversed(urls):
        if url not in pickledata_old:
            data_changed = True
            if pickledata[url]['status'] != 'up':
                down_urls += [url]
        elif data_changed is False and pickledata_old[url]['status'] != pickledata[url]['status']:
            data_changed = True
            if pickledata[url]['status'] != 'up':
                down_urls += [url]
        elif data_changed is True and pickledata[url]['status'] != 'up':
                down_urls += [url]

    if data_changed:
        regex = '^(https?)://'
        font = ImageFont.truetype("resources/ChiKareGo.ttf", 16)
        inkyphat.set_image("resources/empty-backdrop.png")
        title = 'Inkfoboard'
        w, h = font.getsize(title)
        x = (inkyphat.WIDTH / 2) - (w / 2)
        inkyphat.text((x, 0), title, inkyphat.BLACK, font=font)
        url_y = 16

        if len(down_urls) >= 5:
            url_y += 8
            inkyphat.text((50, url_y), 'ALERT!!', inkyphat.RED, font=font)
            url_y += 16
            inkyphat.text((50, url_y), str(len(down_urls))+' urls DOWN', inkyphat.RED, font=font)
            url_y += 16
            inkyphat.text((50, url_y), 'Check your email', inkyphat.RED, font=font)
        elif 5 > len(down_urls) > 0:
            for url in down_urls:  # URLs are shorted due to screen size limits
                url_short = re.sub(regex, '', url).rstrip()
                inkyphat.text((50, url_y), url_short+' DOWN', inkyphat.RED, font=font)
                url_y += 16
        else:
            url_y += 24
            inkyphat.text((50, url_y), 'All urls are UP', inkyphat.BLACK, font=font)

        inkyphat.set_rotation(inkyphat_rotation)
        inkyphat.show()


def normalize_url(url):
    '''If a url doesn't have a http/https prefix, add http://'''
    if not re.match('^http[s]?://', url):
        url = 'http://' + url
    return url


def get_urls_from_file(filename):
    try:
        f = open(filename, 'r')
        filecontents = f.readlines()
        results = []
        for line in filecontents:
            foo = line.strip('\n')
            results.append(foo)
        return results
    except:
        logging.error('Unable to read %s' % filename)
        return []


def get_command_line_options():
    '''Sets up optparse and command line options'''
    usage = "Usage: %prog [options] url"
    parser = OptionParser(usage=usage)
    parser.add_option("-t", "--log-response-time", action="store_true",
                      dest="log_response_time",
                      help="Turn on logging for response times")

    parser.add_option("-r", "--alert-on-slow-response", action="store_true",
                      help="Turn on alerts for response times")

    parser.add_option("--timeout", dest="timeout", type="float",
                      help="Set the timeout amount (in seconds).")

    parser.add_option("-i", "--inkyphat", action="store_true", dest="inkyphat",
                      help="Enables use of inkyphat. Requires the Inky Phat attached to a RaspberryPi")

    parser.add_option("-o", "--inkyphat-rotation", dest="inkyphat_rotation", type="int",
                      help="Sets the rotation of the inkyphat, accepted values are 0 or 180. Default 0")

    parser.add_option("-g", "--use-gmail", action="store_true", dest="use_gmail",
                      help="Send email with Gmail.  Must also specify username and password")

    parser.add_option("--smtp-hostname", dest="smtp_hostname",
                      help="Set the stmp server host.")

    parser.add_option("--smtp-port", dest="smtp_port", type="int",
                      help="Set the smtp server port.")

    parser.add_option("-u", "--smtp-username", dest="smtp_username",
                      help="Set the smtp username.")

    parser.add_option("-p", "--smtp-password", dest="smtp_password",
                      help="Set the smtp password.")

    parser.add_option("-s", "--from-addr", dest="from_addr",
                      help="Set the from email.")

    parser.add_option("-d", "--to-addrs", dest="to_addrs", action="append",
                      help="List of email addresses to send alerts to.")

    parser.add_option("-f", "--from-file", dest="from_file",
                      help="Import urls from a text file. Separated by newline.")

    return parser.parse_args()


def main():
    # Get argument flags and command options
    (options, args) = get_command_line_options()

    # Print out usage if no arguments are present
    if len(args) == 0 and options.from_file is None:
        print('Usage:')
        print("\tPlease specify a url like: www.google.com")
        print("\tNote: The http:// is not necessary")
        print('More Help:')
        print("\tFor more help use the --help flag")

    # If rotation is not given apply default
    if options.inkyphat and not options.inkyphat_rotation:
        options.inkyphat_rotation = 0

    # If the -f flag is set we get urls from a file, otherwise we get them from the command line.
    if options.from_file:
        urls = get_urls_from_file(options.from_file)
    else:
        urls = args

    urls = map(normalize_url, urls)

    # Change logging from WARNING to INFO when logResponseTime option is set
    # so we can log response times as well as status changes.
    if options.log_response_time:
        logging.basicConfig(level=logging.INFO, filename='checksites.log',
                            format='%(asctime)s %(levelname)s: %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')
    else:
        logging.basicConfig(level=logging.WARNING, filename='checksites.log',
                            format='%(asctime)s %(levelname)s: %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')

    # Load previous data
    pickle_file = 'data.pkl'
    pickledata_old = load_old_results(pickle_file)
    pickledata = load_old_results(pickle_file)

    # Add some metadata to pickle
    pickledata['meta'] = {}  # Intentionally overwrite past metadata
    pickledata['meta']['lastcheck'] = time.strftime('%Y-%m-%d %H:%M:%S')

    # Set timeout
    setdefaulttimeout(options.timeout)

    internet_down_file = 'no_internet.txt'

    # Check sites only if Internet is_available
    if is_internet_reachable():
        # create an alerter
        alerter, quiter = generate_email_alerter(options.to_addrs, from_addr=options.from_addr,
                                                 use_gmail=options.use_gmail,
                                                 username=options.smtp_username, password=options.smtp_password,
                                                 hostname=options.smtp_hostname, port=options.smtp_port)

        status_checker = compare_site_status(pickledata, alerter)
        list(map(status_checker, urls))

        # Store results in pickle file
        store_results(pickle_file, pickledata)

        if options.inkyphat:
            if os.path.isfile(internet_down_file):
                print_inkyphat(urls, pickledata_old, pickledata, options.inkyphat_rotation, True)
                os.remove(internet_down_file)
            else:
                print_inkyphat(urls, pickledata_old, pickledata, options.inkyphat_rotation)

        quiter()
    else:
        logging.error('Either the world ended or we are not connected to the net.')
        if options.inkyphat:
            if not os.path.isfile(internet_down_file):
                output = open(internet_down_file, 'wb')
                output.close()
                print_inkyphat_no_internet(options.inkyphat_rotation)



if __name__ == '__main__':
    # First arg is script name, skip it
    main()
