import json
import urllib.request
from jinja2 import Template
import subprocess
from configparser import ConfigParser
import argparse
import os


class Harvest:
    """Class for handling all communication to and from Harvest."""

    def __init__(self, headers, print_responses=False):
        self.headers = headers
        self.print_responses = print_responses

    def __request_data(self, url, per_page=100, page=1, print_response=False):
        url_paginated = 'https://api.harvestapp.com/v2/' + url + '?page=' + str(page) + '&per_page=' + str(per_page)
        request = urllib.request.Request(url=url_paginated, headers=self.headers)
        response = urllib.request.urlopen(request, timeout=5)
        response_body = response.read().decode("utf-8")
        json_response = json.loads(response_body)  # convert to python dict object
        if print_response:
            print(json.dumps(json_response, sort_keys=True, indent=4))
        return json_response

    def get_invoice(self, number):
        """Search all invoices to locate the one with the given invoice number."""
        next_page = 1
        while next_page:
            json_data = self.__request_data('invoices', page=next_page, print_response=self.print_responses)
            for json_invoice in json_data['invoices']:
                if json_invoice['number'] == number:
                    return json_invoice
            next_page = json_data['next_page']
        return None

    def get_time_entries(self, invoice_id):
        """Search all time entries to locate the ones linked to the given invoice ID."""
        next_page = 1
        lines = []
        while next_page:
            json_data = self.__request_data('time_entries', page=next_page, print_response=self.print_responses)
            for entry in json_data['time_entries']:
                if entry['invoice']:
                    if entry['invoice']['id'] == invoice_id:
                        lines.append(entry)
            next_page = json_data['next_page']
        return lines

    def get_client(self, client_id):
        """Return the client with the given ID."""
        return self.__request_data('clients/' + str(client_id), print_response=self.print_responses)


class Config:
    """Load the configuration file."""
    def __init__(self, filename='config.ini'):
        configparser = ConfigParser()
        configparser.read(filename)
        self.headers = {
            "User-Agent": configparser.get('auth', 'user-agent'),
            "Authorization": 'Bearer ' + configparser.get('auth', 'token'),
            "Harvest-Account-ID": configparser.get('auth', 'account-id')
        }
        self.translations = dict(configparser.items('translations'))
        self.customizations = dict(configparser.items('customizations'))


def generate_report(invoice, client, items, keephtml, customizations, translations):
    """Generate the PDF report."""
    jinja2_template_string = open("./html/template.html", 'rb').read().decode("utf-8")
    template = Template(jinja2_template_string)
    html_template_string = template.render(customizations=customizations,
                                           translations=translations,
                                           header="TIMESHEET",
                                           client=client,
                                           invoice=invoice,
                                           items=items).encode("utf-8")
    filename = 'Timesheet {} {}'.format(invoice['number'], client['name'])
    f = open('./html/' + filename + '.html', "wb")
    f.write(html_template_string)
    f.close()

    subprocess.run([r'.\wkhtmltopdf\bin\wkhtmltopdf.exe',
                    '--enable-local-file-access',
                    '--print-media-type',
                    '--dpi',  '1200',
                    '--no-outline',
                    './html/' + filename + '.html',
                    filename + '.pdf'])

    if not keephtml:
        os.remove('./html/' + filename + '.html')

    return filename + '.pdf'


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate timesheet from Harvest invoice number.')
    parser.add_argument('invoice',
                        type=str,
                        help='The number for the invoice to generate a report from.')
    parser.add_argument('--keep-html',
                        '-k',
                        action='store_true',
                        help='Do not delete the html file after the pdf has been generated.')
    args = parser.parse_args()

    config = Config()

    harvest = Harvest(config.headers, print_responses=False)
    invoice = harvest.get_invoice(args.invoice)
    if invoice:
        print('Invoice found.')
    else:
        print('Invoice not found, exiting.')
        exit(1)
    time_entries = harvest.get_time_entries(invoice['id'])
    if time_entries:
        print('Found {} time entries.'.format(len(time_entries)))
    else:
        print('No time entries found, exiting.')
        exit(2)
    client = harvest.get_client(invoice['client']['id'])

    print('Generating report...')
    file = generate_report(customizations=config.customizations,
                           translations=config.translations,
                           invoice=invoice,
                           client=client,
                           items=time_entries,
                           keephtml=args.keep_html)
    print('Successfully generated report: ' + file)
    print('Done.')
