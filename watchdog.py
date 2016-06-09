#!/usr/bin/python2

# Copyright 2015 Institute Of The Czech National Corpus
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
A simple script for testing websites availability.
Results are written into a defined log file and in case of errors,
an e-mail is sent to a defined list of recipients.

A configuration file example:

{
    "logPath": "./watchdog.log",
    "debug": false,
    "pageSizeThreshold": 0.7,
    "mailRecipients":["user1@localhost", "user2@localhost"],
    "smtpServer": "mail.localdomain",
    "mailSender": "watchdog@localdomain",
    "tests": [
        {
            "title": "My site number 1",
            "url": "https://my-site-1.localdomain/serch?query=%(query)s&user=%(user)s",
            "generator": {
                "iquery" : "words.generate_phrase",
                "user" : "users.generate_user_id"
            }
            "size": 121898,
            "responseTimeLimit": 5.0,
            pageSizeIgnore: [
                [{"name": "div", "class": "foo"}, {"name": "form", "id": "credentials"}]
            ]
        },
        ... etc
    ]
}
"""

import urllib
import urllib2
import datetime
import time
import json
import sys
import os
import logging
from logging import handlers
import smtplib
from email.mime.text import MIMEText

import pagesize


def measure_req(url, url_params, orig_size, resp_size_threshold, resp_time_threshold, conf_ignore):
    """
    Performs a request and measures required properties.

    arguments:
    url -- an URL to be tested; it may contain Python str.format placeholders (e.g. 'this-is-{foo}')
    url_params -- a dictionary containing values for url (if needed)
    orig_size -- expected response (body) size
    resp_size_threshold -- a float number between 0 and 1 specifying how big difference in size
                           is tolerated (calc: abs(actual - expected) / expected)
    resp_time_threshold -- a float number between 0 and 1 specifying how big difference in response
                           time (compared to defined one) is tolerated (calc: actual - expected)
    conf_ignore -- HTML elements to be ignored (see module's docstrings for syntax)

    returns:
    a dictionary containing time, code, size, errors
    """
    start = datetime.datetime.now()
    try:
        nf = urllib2.urlopen(url.format(**url_params), timeout=10)
        page = nf.read()
        end = datetime.datetime.now()
        delta = end - start
        current_size = pagesize.page_size(page, conf_ignore)

        ans = {
            'time': delta.seconds / 1000. + delta.microseconds / 1000.,
            'code': nf.getcode(),
            'size': current_size,
            'errors': []
        }
        if orig_size is not None and resp_size_threshold is not None:
            size_diff = get_size_diff(orig=orig_size, current=current_size)
            if size_diff > resp_size_threshold:
                ans['errors'].append('Response body changed by %01.1f%% (threshold = %01.1f%%).' % (size_diff * 100,
                                                                                            resp_size_threshold * 100))
        if ans['time'] > resp_time_threshold * 1000:
            perc = ans['time'] / float(resp_time_threshold) * 100
            ans['errors'].append('Loading time limit exceeded by %01.1f%%.' % perc)
        if int(nf.getcode()) / 100 == 4:
            ans['errors'].append('HTTP status code %s' % nf.getcode())
        nf.close()
    except Exception as e:
        ans = {'time': None, 'code': None, 'size': None, 'errors': ['%s' % e]}
    return ans


def generate_params(gen):
    """
    Generates URL parameters using defined 'generators' (= module+function)

    arguments:
    gen -- a dictionary: param_name => (gen_module, gen_function)

    returns:
    a dictionary param_name => generated_value
    """
    output = {}
    if gen is not None:
        for k, g in gen.items():
            if '.' in g:
                mod, fn = g.rsplit('.', 1)
                m = __import__(mod, fromlist=[])
                output[k] = urllib.quote(getattr(m, fn)())
            else:
                output[k] = apply(getattr(sys.modules[__name__], g))
    return output


def load_config(path):
    return json.load(open(path))


def get_size_diff(orig, current):
    assert orig is not None
    assert current is not None
    orig = float(orig)
    current = float(current)
    return abs(orig - current) / orig


def setup_logger(path, debug=False):
    # logging setup
    logger = logging.getLogger('')
    hdlr = handlers.RotatingFileHandler(path, maxBytes=(1 << 23), backupCount=50)
    hdlr.setFormatter(logging.Formatter('%(asctime)s [%(name)s] %(levelname)s: %(message)s'))
    logger.addHandler(hdlr)
    logger.setLevel(logging.INFO if not debug else logging.DEBUG)


def send_email(failed_tests, server, sender, recipients):
    text = "Web-watchdog script reports following failed tests:\n\n"
    i = 1
    for failed in failed_tests:
        text += "\n%d) %s:\n" % (i, failed['title'])
        for err in failed['errors']:
            text += '\t%s' % err
        i += 1
    text += '\n\nYour watchdog.py'
    s = smtplib.SMTP(server)

    for recipient in recipients:
        msg = MIMEText(text)
        msg['Subject'] = "Web watchdog error report from %s" % time.strftime('%Y-%m-%d %H:%M:%S')
        msg['From'] = sender
        msg['To'] = recipient
        try:
            s.sendmail(sender, [recipient], msg.as_string())
        except Exception as ex:
            log.error('Failed to send an e-email to <%s>, error: %r' % (recipient, ex))
    s.quit()

if __name__ == '__main__':
    num_repeat = 2
    log = logging.getLogger(os.path.basename(__file__))
    failed_tests = []

    if len(sys.argv) < 2:
        print('Config not specified, assuming ./watchdog.json')
        config_file = './watchdog.json'
    else:
        config_file = sys.argv[1]
    config = load_config(config_file)

    setup_logger(config['logPath'], config['debug'])

    for test in config['tests']:
        result = {'errors': [], 'title': test['title']}
        if not test.get('ignore', False):
            page_size_threshold = test.get('pageSizeThreshold', None)
            if page_size_threshold is None:
                page_size_threshold = config.get('pageSizeThreshold', None)

            url_params = generate_params(test.get('generator', None))
            result.update(measure_req(url=test['url'],
                                      url_params=url_params,
                                      orig_size=test.get('size', None),
                                      resp_size_threshold=page_size_threshold,
                                      resp_time_threshold=test['responseTimeLimit'],
                                      conf_ignore=test.get('pageSizeIgnore', None)))
        else:
            result['omitted'] = True
        if len(result['errors']) > 0:
            log.error(json.dumps(result))
        else:
            log.info(json.dumps(result))

        if len(result['errors']) > 0:
            failed_tests.append(result)

    if len(failed_tests) > 0:
        send_email(failed_tests, config['smtpServer'], config['mailSender'], config['mailRecipients'])
