import re
import os
import datetime as dt
import logging
from urllib import request
from urllib.error import HTTPError, URLError

import pandas as pd
from bs4 import BeautifulSoup as bs

import boto3
from botocore.exceptions import ClientError

# constants
if __name__ != '__main__':
    days_diff = int(os.environ['days_delta'])
    fix_html = bool(os.environ['fix_html'])
    regex = r'' + os.environ['regex_start'] + r'.*' + os.environ['regex_end']
else:
    days_diff = -1
    fix_html = False
    regex = r'<div class="rawhtml".*\(\);'
TODAY = dt.datetime.now() + dt.timedelta(days=days_diff)
MONTHDAYYEAR = "%m-%d-%Y"
S3NAME = 'athenedyne-covid-19'

# RegExs for extraction
county = re.compile(r'^(\w*[\s\w]*)\sCOUNTY.*')
town = re.compile(r'.\s?([\w\s]*):\s(\d+\,\d+|\d+).*')
deaths = re.compile(
    r'.*\w*:\s?.*(?:with)?\s(\d+\,\d+|\d+)\s(?:death|fatalitie|fatality|who died)s?.*',
    re.IGNORECASE
)
recovered = re.compile(
    r'.*(\d+\,\d+|\d+)\s(?:cleared from quarantine|who recovered'
    + r'|have recovered|recovered).*',
    re.IGNORECASE
)

# Generate URL using today's date
url = f"https://www.nj.com/coronavirus/{TODAY.strftime('%Y')}/{TODAY.strftime('%m')}/" + \
      f"where-is-the-coronavirus-in-nj-latest-map-update-on-county-by-county-cases-" + \
      f"{TODAY.strftime('%B').lower()}-{TODAY.strftime('%-d')}-" + \
      f"{TODAY.strftime('%Y')}.html"

# Set url headers
hdr = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36' +
                     '(KHTML, like Gecko) Chrome/51.0.2704.103 Safari/537.36'}

# Function to open URL with error handling


def open_url(url, hdr, fix_html=False, regex=r'<div class="rawhtml".*\(\);'):
    if not fix_html:
        try:
            req = request.Request(url, headers=hdr)
            html = bs(request.urlopen(url))
            print(f'Date: {TODAY.strftime(MONTHDAYYEAR)}\nSuccessfully opened {url}')
        except HTTPError as e:
            print(
                f'Date: {TODAY.strftime(MONTHDAYYEAR)}\nError trying to open {url}:\n{e}')
            quit()
        except URLError as e:
            print(
                f'Date: {TODAY.strftime(MONTHDAYYEAR)}\nError trying to open {url}:\n{e}')
            quit()
    else:
        try:
            req = request.Request(url, headers=hdr)
            response = request.urlopen(req)

            html = bs(re.sub(
                regex,
                '',
                response.read().decode('utf-8'))
                )
            print(
                f'Date: {TODAY.strftime(MONTHDAYYEAR)}\n' +
                f'Successfully opened {url} and repaired')
        except HTTPError as e:
            print(
                f'Date: {TODAY.strftime(MONTHDAYYEAR)}\nError trying to open {url}:\n{e}')
            quit()
        except URLError as e:
            print(
                f'Date: {TODAY.strftime(MONTHDAYYEAR)}\nError trying to open {url}:\n{e}')
            quit()
    return html


def upload_file(file_name, bucket, object_name=None, ExtraArgs = {'ACL': 'public-read'}):
    """Upload a file to an S3 bucket

    :param file_name: File to upload
    :param bucket: Bucket to upload to
    :param object_name: S3 object name. If not specified then file_name is used
    :return: True if file was uploaded, else False
    """

    # If S3 object_name was not specified, use file_name
    if object_name is None:
        object_name = file_name

    # Upload the file
    s3_client = boto3.client('s3')
    try:
        response = s3_client.upload_file(file_name, bucket, object_name, ExtraArgs)
    except ClientError as e:
        logging.error(e)
        return False
    print(f'{object_name} added to {bucket}.')
    return True


def lambda_handler(event, context):
    # attempt to load generated URL
    html = open_url(url, hdr, fix_html= fix_html, regex= regex)
    current_county = ''
    towns = []

    # each listing is in a <p> tag
    # iterate over <p> to find the current county
    # then look for town names, deaths, recoveries
    # append to list
    for p in html.find_all('p', ['article__paragraph', 'article__paragraph--left']):
        if county.match(p.text):
            current_county = county.match(p.text).group(1).title()
            print(current_county)
        if town.match(p.text):
            town_name = town.match(p.text).group(1)
            town_ct = int(town.match(p.text).group(2).replace(',', ''))
            death_ct = 0
            recovered_ct = 0
            if deaths.match(p.text):
                death_ct = int(deaths.match(p.text).group(1).replace(',', ''))
                print(p.text, death_ct)
            if recovered.match(p.text):
                recovered_ct = int(recovered.match(p.text).group(1).replace(',', ''))
                print(p.text, recovered_ct)
            towns.append(
                [current_county,
                 town_name,
                 town_ct,
                 death_ct,
                 recovered_ct
                 ])

    # convert extracted data into DF
    towns = pd.DataFrame(towns,
                         columns=['County', 'City', 'Cases',
                                  'Deaths', 'Recoveries']
                         )
    print('\nTowns:\n')
    print(towns.head())

    # import ZIP list from S3
    zips = pd.read_csv(f's3://{S3NAME}/NJzips.csv',
                       converters={'Zip Code': str})
    print('\nZIPs:\n')
    print(zips.head())

    # create DF with ZIP by joining on city and county
    output = towns.merge(zips, how='left', left_on=['City', 'County'],
                         right_on=['City', 'County'])

    print('\nMerge:\n')
    print(output.head())

    # determine ZIP count per town
    shared_zips = output[['City', 'County', 'Cases']].groupby(
        ['City', 'County']).count().rename(columns={'Cases': 'Shared ZIPs'})

    # join shared ZIPs with output
    cases_w_shared_zips = output.merge(shared_zips, how='left',
                                       left_on=['City', 'County'],
                                       right_on=['City', 'County'])

    # determine average cases per town ZIP
    cases_w_shared_zips['Adjusted Cases'] = round(
        cases_w_shared_zips['Cases'] / cases_w_shared_zips['Shared ZIPs'], 1)
    print('\nAdjusted by shared ZIP\n')
    print(cases_w_shared_zips.head())

    # watch the /tmp/ folder if using local
    # Save CSVs so they can be uploaded
    cases_w_shared_zips.to_csv(f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-complete.csv',
                               index=False)
    output[['Zip Code', 'City', 'Cases']].to_csv(
        f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-cases.csv',
        index=False)
    output.drop_duplicates(['City', 'County'], keep='first').groupby('Zip Code'). \
        sum().to_csv(f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-zips.csv',
                     index=False)

    # upload files to S3
    upload_file(f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-complete.csv',
                S3NAME,
                f'Complete/{TODAY.strftime(MONTHDAYYEAR)}-complete.csv')

    upload_file(f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-cases.csv',
                S3NAME,
                f'Cases/{TODAY.strftime(MONTHDAYYEAR)}-cases.csv')

    upload_file(f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-zips.csv',
                S3NAME,
                f'ZIPs/{TODAY.strftime(MONTHDAYYEAR)}-zips.csv')

    # duplicates as current-whatever.csv
    upload_file(f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-complete.csv',
                S3NAME,
                f'Active/current-complete.csv')

    upload_file(f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-cases.csv',
                S3NAME,
                f'Active/current-cases.csv')

    upload_file(f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-zips.csv',
                S3NAME,
                f'Active/current-zips.csv')

    # saves the list of missing ZIPs
    if output[output['Zip Code'].isna()][['Zip Code', 'City', 'County']].shape[0] > 0:
        output[output['Zip Code'].isna()][['Zip Code', 'City', 'County']]. \
            to_csv(f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-missing-ZIPs.csv',
                   index=False)
        upload_file(f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-missing-ZIPs.csv',
                    S3NAME,
                    f'MissingZIPs/{TODAY.strftime(MONTHDAYYEAR)}-missing-ZIPs.csv')


if __name__ == '__main__':
    lambda_handler('test', '')
