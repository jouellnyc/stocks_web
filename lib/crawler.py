#!/usr/bin/python3

import sys
import traceback
from pprint import pprint
import datetime

from alpha_vantage.fundamentaldata import FundamentalData
from pymongo.errors import ServerSelectionTimeoutError
from millify import millify
import pandas as pd

""" All Assignment of df Slices """
pd.options.mode.chained_assignment = None

from mongodb import MongoCli

api_key = "ZZZZZZZZZZZZZZZZZ"

format = "pandas"

alpha = FundamentalData(key=api_key, output_format=format, indexing_type="integer")


def mk_pretty(num):
    """ Pretty print Growth Rate """
    # return "%.2f" % (num * 100) + "%"
    return "%.2f" % (num * 100)


def cut(x):
    return x.rpartition("-")[0].rpartition("-")[0]


def add_str(string):
    return string + "Years"


def stock_exists(stock, mg):
    try:
        data = mg.lookup_stock(stock)
    except ValueError:
        return False, "NA"
    else:
        return True, data


def main(stock, mg, force, force_new):

    debug = True

    _, data = stock_exists(stock, mg)

    if debug:
        print("data", data)
        print("force force_new", force, force_new)

    if data:

        print(f"{stock} already in Mongo")
        if force is False:
            print("...Passing due to force option")
            return True
        else:
            print("...Trying due to force option")
            try:

                if data["DateCrawled"]:

                    if force_new is False:
                        print(
                            "...crawled with date data but passing due to force_new option"
                        )
                        return True
                    else:
                        print(
                            "...crawled with date data -- continuing due to force_new option"
                        )
                        pass

            except KeyError:

                print(f"{stock} does not have crawl date -- continuing to crawl")
                pass

            except TypeError:
                print(f"{stock} does not have data or has incorrect data -- continuing")
                pass

    else:
        print(f"{stock} was not already in Mongo -- continuing")
        pass

    try:

        print(f"Connecting to Alpha Vantage for {stock}")
        """ Pull Down Income Data from Alpha Vantage """
        income_data, stock_name = alpha.get_income_statement_annual(stock)
        income_data.replace("None", 0, inplace=True)
        currency = income_data["reportedCurrency"].values[0]

        """ Setup our panda dataframe """
        df = income_data[["fiscalDateEnding", "totalRevenue", "netIncome"]]

        if df["totalRevenue"].iloc[0] == "0":
            print("0 Revenue -- Sending blank to Mongo")
            mg.dbh.insert_one({"Stock": stock})
            sys.exit(0)
        else:
            print(df["totalRevenue"].iloc[0])

        """
        df looks like this now:
                  fiscalDateEnding  totalRevenue    netIncome
        index
        0           2019-12-31  161857000000  34343000000
        1           2018-12-31  136819000000  30736000000
        2           2017-12-31  110855000000  12662000000
        3           2016-12-31   90272000000  19478000000
        4           2015-12-31   74989000000  16348000000
        """

        if debug:
            print("df:\n", df, "\n")

        """  Set data to numbers from strings """
        df[["totalRevenue", "netIncome"]] = df[["totalRevenue", "netIncome"]].apply(
            pd.to_numeric
        )

        """ Calculate the x-Year Growth Rate for Revenue and Net Income """
        """ The growth values are relative to the last year of data     """

        # Trim the year value to get just the year
        df["Years"] = df["fiscalDateEnding"].apply(cut).apply(pd.to_numeric)
        last_year_value = df["Years"].iloc[-1]
        last_rev_value = int(df.totalRevenue.iloc[-1])
        last_ninc_value = int(df.netIncome.iloc[-1])

        df["Revenue_Growth"] = (last_rev_value / df["totalRevenue"]) ** (
            1 / (last_year_value - df["Years"])
        ) - 1

        df["NetInc_Growth"] = (last_ninc_value / df["netIncome"]) ** (
            1 / (last_year_value - df["Years"])
        ) - 1

        df["Years_From"] = df["Years"] - last_year_value
        df["Years_From"] = df["Years_From"].apply(str)
        df["Years_From"] = df["Years_From"].apply(add_str)
        df = df.fillna(0)

        if debug:
            print("df:\n", df, "\n")

        """
        df looks like this now:
               fiscalDateEnding  totalRevenue    netIncome  Years  Revenue_Growth  NetInc_Growth Years_From
        index
        0           2019-12-31  161857000000  34343000000   2019        0.212086       0.203908     4Years
        1           2018-12-31  136819000000  30736000000   2018        0.221939       0.234225     3Years
        2           2017-12-31  110855000000  12662000000   2017        0.215847      -0.119927     2Years
        3           2016-12-31   90272000000  19478000000   2016        0.203803       0.191461     1Years
        4           2015-12-31   74989000000  16348000000   2015        0.000000       0.000000     0Years

        df.to_dict\('records'\) looks like this now:

        [{'NetInc_Growth': 0.20390827677878742,
          'Revenue_Growth': 0.21208612858558862,
          'Years': 2019,
          'Years_From': '4Years',
          'fiscalDateEnding': '2019-12-31',
          'netIncome': 34343000000,
          'totalRevenue': 161857000000},
         {'NetInc_Growth': 0.23422471699892022,
          'Revenue_Growth': 0.22193925428985017,
          'Years': 2018,
          'Years_From': '3Years',
          'fiscalDateEnding': '2018-12-31',
          'netIncome': 30736000000,
          'totalRevenue': 136819000000},
         {'NetInc_Growth': -0.11992671079483375,
          'Revenue_Growth': 0.21584681665796124,
          'Years': 2017,
          'Years_From': '2Years',
          'fiscalDateEnding': '2017-12-31',
          'netIncome': 12662000000,
          'totalRevenue': 110855000000},
         {'NetInc_Growth': 0.19146072914117918,
          'Revenue_Growth': 0.20380322447292265,
          'Years': 2016,
          'Years_From': '1Years',
          'fiscalDateEnding': '2016-12-31',
          'netIncome': 19478000000,
          'totalRevenue': 90272000000},
         {'NetInc_Growth': 0.0,
          'Revenue_Growth': 0.0,
          'Years': 2015,
          'Years_From': '0Years',
          'fiscalDateEnding': '2015-12-31',
          'netIncome': 16348000000,
          'totalRevenue': 74989000000}]
        """

        if debug:
            print("df.to_dict\('records'\):\n")
            pprint(df.to_dict("records"))
            print("\n")

        """ Setup our mongo doc as a hash to prepare to send to Mongo """
        mongo_doc = {}
        mongo_doc["Years"] = {}

        """ millify() and mk_pretty() the data and re-arrange df """
        for year in df.to_dict("records"):

            mongo_doc["Years"][year["Years_From"]] = {
                "Date": year["fiscalDateEnding"],
                "Revenue": float(millify(year["totalRevenue"], precision=2)[:-1]),
                "RevDenom": millify(year["totalRevenue"], precision=2)[-1],
                "NetIncome": float(millify(year["netIncome"], precision=2)[:-1]),
                "NetIncDenom": millify(year["netIncome"], precision=2)[-1],
                "NetIncGrowth": float(mk_pretty(year["NetInc_Growth"])),
                "RevenueGrowth": float(mk_pretty(year["Revenue_Growth"])),
            }

        """
        mongo_doc looks like this now:
        {'Years': {'0Years': {'Date': '2015-12-31',
                              'NetIncDenom': 'B',
                              'NetIncGrowth': 0.0,
                              'NetIncome': '16.35',
                              'RevDenom': 'B',
                              'Revenue': '74.99',
                              'RevenueGrowth': 0.0},
                   '1Years': {'Date': '2016-12-31',
                              'NetIncDenom': 'B',
                              'NetIncGrowth': 19.15,
                              'NetIncome': '19.48',
                              'RevDenom': 'B',
                              'Revenue': '90.27',
                              'RevenueGrowth': 20.38},
                   '2Years': {'Date': '2017-12-31',
                              'NetIncDenom': 'B',
                              'NetIncGrowth': -11.99,
                              'NetIncome': '12.66',
                              'RevDenom': 'B',
                              'Revenue': '110.86',
                              'RevenueGrowth': 21.58},
                   '3Years': {'Date': '2018-12-31',
                              'NetIncDenom': 'B',
                              'NetIncGrowth': 23.42,
                              'NetIncome': '30.74',
                              'RevDenom': 'B',
                              'Revenue': '136.82',
                              'RevenueGrowth': 22.19},
                   '4Years': {'Date': '2019-12-31',
                              'NetIncDenom': 'B',
                              'NetIncGrowth': 20.39,
                              'NetIncome': '34.34',
                              'RevDenom': 'B',
                              'Revenue': '161.86',
                              'RevenueGrowth': 21.21}}}


        """
        if debug:
            print("mongo_doc: \n")
            pprint(mongo_doc)
            print("\n")

        """ Pull Down Overview Data from Alpha Vantage """
        overview_data, stock_name = alpha.get_company_overview(stock)
        if debug:
            print("overview_data: \n", overview_data, "\n")

        """ Pull out Each value and millify() """
        revenue_ttm = float(overview_data["RevenueTTM"].values[0])
        market_cap = overview_data["MarketCapitalization"].values[0]
        PETTM = int(float(overview_data["TrailingPE"].values[0]))
        price2sales = float(overview_data["PriceToSalesRatioTTM"].values[0])
        price2book = float(overview_data["PriceToBookRatio"].values[0])
        book_value = overview_data["BookValue"].values[0]
        if book_value.startswith("None"):
            mongo_doc["BookValue"] = 0.0
        else:
            mongo_doc["BookValue"] = float(book_value)

        """ Add each as a key:value pair ... """
        if revenue_ttm > 0:
            mongo_doc["RevTTM"] = millify(revenue_ttm, precision=2)
            mongo_doc["RevTTM_Denom"] = mongo_doc["RevTTM"][-1]
            mongo_doc["RevTTM"] = float(mongo_doc["RevTTM"][:-1])
        else:
            mongo_doc["RevTTM_Denom"] = "NA"
            mongo_doc["RevTTM"] = revenue_ttm

        mongo_doc["Market_Cap"] = millify(market_cap, precision=2)
        mongo_doc["Market_Cap_Denom"] = mongo_doc["Market_Cap"][-1]
        mongo_doc["Market_Cap"] = float(mongo_doc["Market_Cap"][:-1])

        mongo_doc["Currency"] = currency
        mongo_doc["TrailingPE"] = float(PETTM)
        # mongo_doc["PriceToSalesTTM"] = float(millify(price2sales, precision=2))
        mongo_doc["PriceToSalesTTM"] = millify(float(price2sales), precision=2)
        mongo_doc["PriceToBookRatio"] = float(millify(price2book, precision=2))
        mongo_doc["DateCrawled"] = datetime.datetime.utcnow()

        """
        mongo_doc now looks like this:

        {'BookValue': 314.169,
         'Currency': 'USD',
         'Market_Cap': 1.28,
         'Market_Cap_Denom': 'T',
         'PriceToBookRatio': 6.02,
         'PriceToSalesTTM': 7.61,
         'RevTTM': 171.7,
         'RevTTM_Denom': 'B',
         'TrailingPE': 36.0,
         'Years': {'0Years': {'Date': '2015-12-31',
                              'NetIncDenom': 'B',
                              'NetIncGrowth': 0.0,
                              'NetIncome': '16.35',
                              'RevDenom': 'B',
                              'Revenue': '74.99',
                              'RevenueGrowth': 0.0},
                   '1Years': {'Date': '2016-12-31',
                              'NetIncDenom': 'B',
                              'NetIncGrowth': 19.15,
                              'NetIncome': '19.48',
                              'RevDenom': 'B',
                              'Revenue': '90.27',
                              'RevenueGrowth': 20.38},
                   '2Years': {'Date': '2017-12-31',
                              'NetIncDenom': 'B',
                              'NetIncGrowth': -11.99,
                              'NetIncome': '12.66',
                              'RevDenom': 'B',
                              'Revenue': '110.86',
                              'RevenueGrowth': 21.58},
                   '3Years': {'Date': '2018-12-31',
                              'NetIncDenom': 'B',
                              'NetIncGrowth': 23.42,
                              'NetIncome': '30.74',
                              'RevDenom': 'B',
                              'Revenue': '136.82',
                              'RevenueGrowth': 22.19},
                   '4Years': {'Date': '2019-12-31',
                              'NetIncDenom': 'B',
                              'NetIncGrowth': 20.39,
                              'NetIncome': '34.34',
                              'RevDenom': 'B',
                              'Revenue': '161.86',
                              'RevenueGrowth': 21.21}}}
        """

        if debug:
            print("mongo_doc:\n")
            pprint(mongo_doc)
            print("\n")

    except Exception:
        raise
    else:
        """ And now we are ready to send the Data to Mongo """
        print(f"OK, Sending data to Mongo for {stock}\n")
        print(mg.dbh.update_one({"Stock": stock}, {"$set": mongo_doc}, upsert=True))


if __name__ == "__main__":

    force = True
    force_new = True

    try:
        stock = sys.argv[1]
        mg = MongoCli()
    except ServerSelectionTimeoutError as e:
        print("Can't connect to Mongodb - Quitting Crawl", e)
        sys.exit(1)

    try:
        main(stock, mg, force=force, force_new=force_new)
    except KeyError as e:
        print("Likely a Data Issue")
        print("Sending blank to Mongo")
        mg.dbh.insert_one({"Stock": stock})
        print(type(e), e)
    except ValueError as e:
        if "Thank you" in str(e.args):
            print("Error: Hit Api limit")
        elif "no return was given" in str(e.args):
            print("No Data Returned from Api")
            print("Sending blank to Mongo")
            mg.dbh.insert_one({"Stock": stock})
        else:
            print("Unhandled Value Error")
            print(traceback.format_exc())
    except Exception as e:
        print("Unhandled Error")
        print(type(e), e)
        print(traceback.format_exc())
