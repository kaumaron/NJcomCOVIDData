import re
import datetime as dt
import logging
from urllib import request
from urllib.error import HTTPError, URLError

import pandas as pd
from bs4 import BeautifulSoup as bs

import boto3
from botocore.exceptions import ClientError


TODAY = dt.datetime.now() + dt.timedelta(days=0)
MONTHDAYYEAR = "%m-%d-%Y"
S3NAME = 'athenedyne-covid-19'


county = re.compile(r'^(\w*[\s\w]*)\sCOUNTY.*')
town = re.compile(r'.\s?(\w*):\s(\d*).*')
deaths = re.compile(
    r'.*\w*:\s?.*(?:with)?\s(\d*)\s(?:death|fatalitie|fatality|who died)s?.*',
    re.IGNORECASE
)
recovered = re.compile(
    r'.*(\d+)\s(?:cleared from quarantine|who recovered'\
    + r'|have recovered|recovered).*',
    re.IGNORECASE
)

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
    try:
        html = bs(request.urlopen(url))
        print(f'Date: {TODAY.strftime(MONTHDAYYEAR)}\nSuccessfully opened {url}')
    except HTTPError as e:
        print(f'Date: {TODAY.strftime(MONTHDAYYEAR)}\nError trying to open {url}:\n{e}')
    except URLError as e:
        print(f'Date: {TODAY.strftime(MONTHDAYYEAR)}\nError trying to open {url}:\n{e}')

    current_county = ''
    towns = []

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

    towns = pd.DataFrame(towns,
                         columns=['County', 'City', 'Cases',
                                  'Deaths', 'Recoveries']
                         )
    print(towns.head())

    zips = pd.read_csv(f's3://{S3NAME}/NJzips.csv',
                       converters={'Zip Code': str})
    print(zips.head())

    output = towns.merge(zips, how='left', left_on=['City', 'County'],
                         right_on=['City', 'County'])

    print(output.head())

    output.to_csv(f'{TODAY.strftime(MONTHDAYYEAR)}-complete.csv')
    output[['Zip Code', 'City', 'Cases']].to_csv(
        f'{TODAY.strftime(MONTHDAYYEAR)}-cases.csv')
    output.groupby('Zip Code').sum().to_csv(f'{TODAY.strftime(MONTHDAYYEAR)}-zips.csv')

    upload_file(f'{TODAY.strftime(MONTHDAYYEAR)}-complete.csv',
                S3NAME)

    upload_file(f'{TODAY.strftime(MONTHDAYYEAR)}-cases.csv',
                S3NAME)

    upload_file(f'{TODAY.strftime(MONTHDAYYEAR)}-zips.csv',
                S3NAME)


if __name__ == '__main__':
    lambda_handler('test', '')
