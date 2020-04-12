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
TODAY = dt.datetime.now() + dt.timedelta(days=int(os.environ['days_delta']))
MONTHDAYYEAR = "%m-%d-%Y"
S3NAME = 'athenedyne-covid-19'

# RegExs for extraction
county = re.compile(r'^(\w*[\s\w]*)\sCOUNTY.*')
town = re.compile(r'.\s?([\w\s]*):\s(\d+\,\d+|\d+).*')
deaths = re.compile(
    r'.*\w*:\s?.*(?:with)?\s(\d*)\s(?:death|fatalitie|fatality|who died)s?.*',
    re.IGNORECASE
)
recovered = re.compile(
    r'.*(\d+)\s(?:cleared from quarantine|who recovered'\
    + r'|have recovered|recovered).*',
    re.IGNORECASE
)

# Generate URL using today's date
url = f"https://www.nj.com/coronavirus/{TODAY.strftime('%Y')}/{TODAY.strftime('%m')}/" + \
      f"where-is-the-coronavirus-in-nj-latest-map-update-on-county-by-county-cases-" + \
      f"{TODAY.strftime('%B').lower()}-{TODAY.strftime('%-d')}-" + \
      f"{TODAY.strftime('%Y')}.html"


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
    return True


def lambda_handler(event, context):
    # attempt to load generated URL
    try:
        html = bs(request.urlopen(url))
        print(f'Date: {TODAY.strftime(MONTHDAYYEAR)}\nSuccessfully opened {url}')
    except HTTPError as e:
        print(f'Date: {TODAY.strftime(MONTHDAYYEAR)}\nError trying to open {url}:\n{e}')
        quit()
    except URLError as e:
        print(f'Date: {TODAY.strftime(MONTHDAYYEAR)}\nError trying to open {url}:\n{e}')
        quit()

    current_county = ''
    towns = []

    # each listing is in a <p> tag
    # iterate over <p> to find the current county
    # then look for town names, deaths, recoveries
    # append to list
    for p in html.findAll('p'):
        if county.match(p.text):
            current_county = county.match(p.text).group(1).title()
            print(current_county)
        if town.match(p.text):
            town_name = town.match(p.text).group(1)
            town_ct = int(town.match(p.text).group(2))
            death_ct = 0
            recovered_ct = 0
            if deaths.match(p.text):
                death_ct = deaths.match(p.text).group(1)
                print(p.text)
            if recovered.match(p.text):
                recovered_ct = recovered.match(p.text).group(1)
                print(p.text)
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
    print(towns.head())

    # import ZIP list from S3
    zips = pd.read_csv(f's3://{S3NAME}/NJzips.csv',
                       converters={'Zip Code': str})
    print(zips.head())

    # create DF with ZIP by joining on city and county
    output = towns.merge(zips, how='left', left_on=['City', 'County'],
                         right_on=['City', 'County'])

    print(output.head())

    # watch the /tmp/ folder if using local
    # Save CSVs so they can be uploaded
    output.to_csv(f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-complete.csv')
    output[['Zip Code', 'City', 'Cases']].to_csv(
        f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-cases.csv')
    output.groupby('Zip Code').sum().to_csv(
        f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-zips.csv')

    # upload files to S3
    upload_file(f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-complete.csv',
                S3NAME,
                f'{TODAY.strftime(MONTHDAYYEAR)}-complete.csv')

    upload_file(f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-cases.csv',
                S3NAME,
                f'{TODAY.strftime(MONTHDAYYEAR)}-cases.csv')

    upload_file(f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-zips.csv',
                S3NAME,
                f'{TODAY.strftime(MONTHDAYYEAR)}-zips.csv')

    # duplicates as current-whatever.csv
    upload_file(f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-complete.csv',
                S3NAME,
                f'current-complete.csv')

    upload_file(f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-cases.csv',
                S3NAME,
                f'current-cases.csv')

    upload_file(f'/tmp/{TODAY.strftime(MONTHDAYYEAR)}-zips.csv',
                S3NAME,
                f'current-zips.csv')

    # saves the list of missing ZIPs
    output[output['Zip Code'].isna()][['Zip Code', 'City', 'County']]. \
        to_csv(f'{TODAY.strftime(MONTHDAYYEAR)}-missing-ZIPs.csv')
    upload_file(f'{TODAY.strftime(MONTHDAYYEAR)}-missing-ZIPs.csv',
                S3NAME,
                f'{TODAY.strftime(MONTHDAYYEAR)}-missing-ZIPs.csv')


if __name__ == '__main__':
    lambda_handler('test', '')
