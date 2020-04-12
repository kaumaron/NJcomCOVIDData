# NJcomCOVIDData

## Functionality

This code scrapes the data from [NJ.com](https://www.nj.com/coronavirus/2020/04/where-is-the-coronavirus-in-nj-latest-map-update-on-county-by-county-cases-april-8-2020.html)
on a daily basis (12 PM EST --> Pushed to 2 PM EST, 4/11/2020 published at 12:30 PM EST).
The data is parsed to extract the **City, County, Cases of
COVID-19, as well as any reported deaths and recoveries**. In my opinion the data set is 
most likely not as robust and accurate as would be ideal.

## Data
The extracted data is then formatted and joined with a ZIP list using City and County to 
handle cities that share a name (i.e.,Franklin is a town in Sussex, Gloucester, Warren, 
Hunterdon and Somerset). The data is also aggregated by ZIP to deal with cities that share
ZIP Codes. For example, 08053 zones for Marlton (recommended) and Evesham (recognized).
It also zones for

* EVESBORO NJ
* EVESHAM TWP NJ
* KRESSON NJ
* MARLTON LAKES NJ
* NORTH MARLTON NJ
* PINE GROVE NJ

To explore this further take a look at the [USPS](https://tools.usps.com/zip-code-lookup.htm?citybyzipcode),
ZIP Code lookup tool.

For cities that have more than one ZIP like Newark, Camden, Edison, etc. it appears the
default behavior is to join the cases, deaths, and recoveries data to each of the ZIPs. 
**This is a gotcha for aggregation**. You'd need to drop duplicate City, County and keep 
first or last. *This is currently not handled in the ZIP aggregate output*.

## Output

The data is then exported as three variants to an [AWS S3 Bucket](https://athenedyne-covid-19.s3.amazonaws.com/index.html).
The variants are: 

1. `MM-DD-YYYY-complete.csv` has County, City, Cases, Deaths, Recoveries, Zip Code.
2. `MM-DD-YYYY-cases.csv` has Zip Code, City, Cases.
3. `MM-DD-YYYY-zips.csv` has Zip Code, Cases aggregate.

Additionally, the code in the [`.py`](NJcomCOVIDData_lambda.py) creates copies of the above
variants starting with current. This allows bookmarking to the current file or using the 
data for a visualization analysis, or other use.

Using Google Sheets and the import data function 
(`=IMPORTDATA("https://athenedyne-covid-19.s3.amazonaws.com/current-complete.csv")`), one
can connect to Tableau to create an
[interactive Viz](https://public.tableau.com/profile/andrew.k.decotiis.mauro#!/vizhome/COVID-19CasesinNJusingNJ_comData/Choropleth-County)
that stays up to date.

## Automation

The Lambda script is set up on AWS Lambda to run at 12 PM EST daily, updating the S3 Bucket.

## Additional Files

The ZIPs were collected into `NJzips.csv` which is somewhat complete, as it may be missing
ZIPs for towns that share ZIPs. It does contain ZIPs for towns on the page as of 04/06/2020.

The `index.html` file is from an answer on the
[AWS forum](https://forums.aws.amazon.com/thread.jspa?threadID=66482) by J. Patel on 
5/3/2011. The pages uses JS to generate HTML text to list all of the files in the S3 bucket.
I modified it to skip `index.html`.

## Additional Notes

This repo can be used locally ([.ipynb](NJcomCOVIDExtract.ipynb) recommended) or as an AWS
Lambda (when zipped with dependencies). When used as a Lambda it's helpful to know that
AWS is running a Linux variant so the `pandas` and `numpy` libraries will need to be for a
Linux system. I'm running MacOS X so I needed to source my libraries from PyPi:

* `pandas`(https://pypi.org/project/pandas/#files) - 
`pandas-1.0.3-cp37-cp37m-manylinux1_x86_64.whl`
* [`numpy`](https://pypi.org/project/numpy/#files) -
 `numpy-1.18.2-cp37-cp37m-manylinux1_x86_64.whl`
 
 This is laid out really well in [AWS Lambda with Pandas and NumPy](https://medium.com/@korniichuk/lambda-with-pandas-fd81aa2ff25e)
 by [Ruslan Korniichuck](https://medium.com/@korniichuk).